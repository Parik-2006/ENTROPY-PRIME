"""
stage3_governor.py — Stage 3: Resource Governor (DQN + PPO)

Two complementary agents work in sequence:

  DQN  — selects the Argon2id *compute hardening* preset (ECONOMY → PUNISHER).
          Inputs: (θ, server_load, is_suspect).

  PPO  — selects the *behavioral response* (ALLOW / LOG / CHALLENGE / BLOCK).
          Inputs: (θ, server_load, is_suspect, is_bot, risk_tolerance).
          Policy is shaped per-tenant via the TenantPolicy risk_tolerance field.

Both agents are overridable by hard rules that encode non-negotiable business
logic (bots on overloaded servers → ECONOMY; tenant block_bots_hard → BLOCK).

Function-based API — both call signatures work without errors:
  run(bio, dqn_agent)                                   ← old test path
  run(bio, dqn_agent, ppo_agent=None, policy=None)      ← new integration shape

DQN action → Argon2id preset mapping
─────────────────────────────────────
  0  ECONOMY   64 MB / t=2 / p=4    — bots, high-load fallback
  1  STANDARD 128 MB / t=3 / p=4    — default for legitimate users
  2  HARD     256 MB / t=4 / p=8    — elevated-risk sessions
  3  PUNISHER 512 MB / t=5 / p=8    — maximum hardening (suspicious human)

PPO action space (GovernorAction)
─────────────────────────────────
  0  ALLOW     — proceed; Argon2id preset is the only hardening
  1  LOG       — allow but emit high-priority audit event
  2  CHALLENGE — require additional proof-of-work / CAPTCHA
  3  BLOCK     — reject request outright

Policy application order
────────────────────────
  1. Hard override  — business rules that bypass both agents entirely
  2. DQN preset     — compute intensity
  3. PPO action     — behavioral response
  4. Policy clamp   — tenant floor/ceiling applied *after* both agents
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from .contracts import (
    BiometricResult,
    Confidence,
    GovernorAction,
    GovernorResult,
    HoneypotVerdict,
    SecurityPreset,
    TenantPolicy,
    SERVER_LOAD_HIGH,
)

logger = logging.getLogger("entropy_prime.stage3")

# ── Argon2id preset table ─────────────────────────────────────────────────────

_PRESETS: dict[int, tuple[SecurityPreset, int, int, int]] = {
    #           preset              memory_kb   time_cost  parallelism
    0: (SecurityPreset.ECONOMY,     65_536,     2,         4),
    1: (SecurityPreset.STANDARD,   131_072,     3,         4),
    2: (SecurityPreset.HARD,       262_144,     4,         8),
    3: (SecurityPreset.PUNISHER,   524_288,     5,         8),
}

# Ordered lists for floor/ceiling comparisons
_PRESET_ORDER = [
    SecurityPreset.ECONOMY,
    SecurityPreset.STANDARD,
    SecurityPreset.HARD,
    SecurityPreset.PUNISHER,
]

_ACTION_ORDER = [
    GovernorAction.ALLOW,
    GovernorAction.LOG,
    GovernorAction.CHALLENGE,
    GovernorAction.BLOCK,
]

_DEFAULT_DQN_ACTION = 1              # STANDARD
_DEFAULT_PPO_ACTION = GovernorAction.ALLOW


def _default_policy() -> TenantPolicy:
    """
    Policy used when callers omit an explicit tenant policy.

    Legacy pipeline tests and ``run(bio, dqn_agent)`` expect the original
    bot rules (overloaded → ECONOMY, healthy → HARD).  SaaS tenants that
    want unconditional bot blocking must pass an explicit TenantPolicy with
    block_bots_hard=True.
    """
    return TenantPolicy(site_id="__default__", block_bots_hard=False)


# ── Main entry point ──────────────────────────────────────────────────────────

def run(
    bio:       BiometricResult,
    dqn_agent,
    ppo_agent=None,                  # Optional — old tests pass nothing here
    policy:    Optional[TenantPolicy] = None,
) -> GovernorResult:
    """
    Determine both the Argon2id preset (DQN) and behavioral action (PPO) for
    this request, subject to the tenant's policy constraints.

    Backward-compatible: calling ``run(bio, dqn_agent)`` works identically to
    ``run(bio, dqn_agent, ppo_agent=None, policy=None)``.

    Parameters
    ──────────
    bio        — BiometricResult from Stage 1.
    dqn_agent  — Agent with .select_action(np.ndarray) → int; selects the
                 Argon2id SecurityPreset.
    ppo_agent  — Optional PPOPolicyAgent with .select_action(np.ndarray) → int;
                 selects the GovernorAction overlay.  When None the governor
                 defaults to ALLOW (no overlay).
    policy     — Optional TenantPolicy for this site_id.  When None a default
                 policy (risk_tolerance=0.5, all defaults) is used so the
                 function always behaves sensibly.

    Returns
    ───────
    GovernorResult with both preset and governor_action populated.
    Never raises.
    """
    effective_policy = policy or _default_policy()

    # ── Hard overrides (bypass both agents) ──────────────────────────────────
    hard = _hard_override(bio, effective_policy)
    if hard is not None:
        dqn_action, gov_action = hard
        preset, mem, tc, par   = _PRESETS[dqn_action]
        logger.debug(
            "[S3] Hard override → dqn=%d (%s) action=%s site=%s",
            dqn_action, preset.value, gov_action.value,
            effective_policy.site_id,
        )
        return GovernorResult(
            action          = dqn_action,
            preset          = preset,
            memory_kb       = mem,
            time_cost       = tc,
            parallelism     = par,
            confidence      = Confidence.HIGH,
            fallback        = True,
            governor_action = gov_action,
            policy_applied  = effective_policy.site_id,
        )

    # ── DQN: Argon2id preset ──────────────────────────────────────────────────
    dqn_action, dqn_conf, dqn_fallback = _run_dqn(bio, dqn_agent)

    # ── PPO: behavioral action ────────────────────────────────────────────────
    gov_action, ppo_fallback = _run_ppo(bio, ppo_agent, effective_policy)

    # ── Apply tenant policy constraints ──────────────────────────────────────
    dqn_action = _apply_preset_ceiling(dqn_action, effective_policy)
    gov_action = _apply_action_floor(gov_action, effective_policy)
    gov_action = _apply_suspect_rule(gov_action, bio, effective_policy)

    # ── Cap preset under high server load ─────────────────────────────────────
    if bio.server_load >= SERVER_LOAD_HIGH:
        dqn_action = min(dqn_action, 1)  # at most STANDARD under load

    preset, mem, tc, par = _PRESETS[dqn_action]
    any_fallback         = dqn_fallback or ppo_fallback

    logger.debug(
        "[S3] dqn=%d (%s) ppo=%s conf=%s fallback=%s site=%s",
        dqn_action, preset.value, gov_action.value,
        dqn_conf.value, any_fallback, effective_policy.site_id,
    )

    return GovernorResult(
        action          = dqn_action,
        preset          = preset,
        memory_kb       = mem,
        time_cost       = tc,
        parallelism     = par,
        confidence      = dqn_conf,
        fallback        = any_fallback,
        governor_action = gov_action,
        policy_applied  = effective_policy.site_id,
    )


# ── DQN sub-pipeline ──────────────────────────────────────────────────────────

def _run_dqn(
    bio:       BiometricResult,
    dqn_agent,
) -> tuple[int, Confidence, bool]:
    """Run the DQN and return (action, confidence, fallback_flag)."""
    # Low-confidence classification → conservative STANDARD
    if bio.confidence == Confidence.LOW:
        return _DEFAULT_DQN_ACTION, Confidence.LOW, False

    try:
        state  = _build_dqn_state(bio)
        action = int(dqn_agent.select_action(state))
        action = max(0, min(3, action))
        conf   = _action_confidence(bio)
        return action, conf, False
    except Exception as exc:
        logger.error("[S3] DQN inference failed: %s — STANDARD fallback", exc)
        return _DEFAULT_DQN_ACTION, Confidence.LOW, True


# ── PPO sub-pipeline ──────────────────────────────────────────────────────────

def _run_ppo(
    bio:    BiometricResult,
    ppo_agent,
    policy: TenantPolicy,
) -> tuple[GovernorAction, bool]:
    """
    Run the PPO and return (governor_action, fallback_flag).

    When ppo_agent is None (old call path) the default ALLOW action is
    returned with fallback=True so callers can detect the absence gracefully.
    """
    if ppo_agent is None:
        return _DEFAULT_PPO_ACTION, True
    try:
        state      = _build_ppo_state(bio, policy)
        action_raw = ppo_agent.select_action(state)
        if isinstance(action_raw, tuple):   # some PPO impls return (action, log_prob)
            action_raw = action_raw[0]
        action_idx = int(action_raw)
        action_idx = max(0, min(len(_ACTION_ORDER) - 1, action_idx))
        return _ACTION_ORDER[action_idx], False
    except Exception as exc:
        logger.error("[S3] PPO inference failed: %s — ALLOW fallback", exc)
        return _DEFAULT_PPO_ACTION, True


# ── Hard overrides ────────────────────────────────────────────────────────────

def _hard_override(
    bio:    BiometricResult,
    policy: TenantPolicy,
) -> Optional[tuple[int, GovernorAction]]:
    """
    Return (dqn_action, governor_action) when business rules must bypass agents.

    Rules applied in priority order:
    1. BOT + block_bots_hard          → ECONOMY + BLOCK
    2. BOT + high server load         → ECONOMY + LOG  (save resources, still log)
    3. BOT + healthy server           → HARD    + LOG  (punish scraping)
    """
    if bio.is_bot:
        if policy.block_bots_hard:
            return 0, GovernorAction.BLOCK
        if bio.server_load > SERVER_LOAD_HIGH:
            return 0, GovernorAction.LOG
        return 2, GovernorAction.LOG

    return None  # no override — let agents decide


# ── Policy clamps ─────────────────────────────────────────────────────────────

def _apply_preset_ceiling(action: int, policy: TenantPolicy) -> int:
    """Cap the DQN action at the tenant's max_preset."""
    max_idx = _PRESET_ORDER.index(policy.max_preset)
    return min(action, max_idx)


def _apply_action_floor(action: GovernorAction, policy: TenantPolicy) -> GovernorAction:
    """Raise the PPO action to at least the tenant's min_action."""
    floor_idx  = _ACTION_ORDER.index(policy.min_action)
    action_idx = _ACTION_ORDER.index(action)
    return _ACTION_ORDER[max(action_idx, floor_idx)]


def _apply_suspect_rule(
    action: GovernorAction,
    bio:    BiometricResult,
    policy: TenantPolicy,
) -> GovernorAction:
    """
    Enforce challenge_on_suspect: if the verdict is SUSPECT and the policy
    requires at least CHALLENGE, bump the action up if needed.
    """
    if not (policy.challenge_on_suspect and bio.is_suspect):
        return action
    challenge_idx = _ACTION_ORDER.index(GovernorAction.CHALLENGE)
    current_idx   = _ACTION_ORDER.index(action)
    return _ACTION_ORDER[max(current_idx, challenge_idx)]


# ── State builders ────────────────────────────────────────────────────────────

def _build_dqn_state(bio: BiometricResult) -> np.ndarray:
    """
    3-element state vector for the DQN:
      [theta, server_load, is_suspect_float]
    """
    return np.array(
        [bio.theta, bio.server_load, float(bio.is_suspect)],
        dtype=np.float32,
    )


def _build_ppo_state(bio: BiometricResult, policy: TenantPolicy) -> np.ndarray:
    """
    5-element state vector for the PPO:
      [theta, server_load, is_suspect, is_bot, risk_tolerance]
    """
    return np.array(
        [
            bio.theta,
            bio.server_load,
            float(bio.is_suspect),
            float(bio.is_bot),
            policy.risk_tolerance,
        ],
        dtype=np.float32,
    )


# ── Confidence mapping ────────────────────────────────────────────────────────

def _action_confidence(bio: BiometricResult) -> Confidence:
    """Propagate Stage-1 confidence into the governor result."""
    return bio.confidence