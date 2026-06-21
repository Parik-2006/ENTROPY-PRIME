"""
framework.honeypot_engine — PHASE 3: Generative Honeypot Engine
===============================================================

Purpose
-------
Deception instead of blocking. Confirmed bots (and high-confidence suspects)
are shadow-routed into a honeypot and served signed, invisible DOM decoys. A
Multi-Armed Bandit learns which decoy strategy catches each attacker class.

Attack class -> intended decoy strategy
---------------------------------------
    Credential stuffing  -> Echo honeypot   (mirrored / mutated form fields)
    Brute force          -> Tarpit honeypot (heavy form bait, slowed responses)
    Reconnaissance       -> Shadow-Admin    (fake privileged surface) [planned]
    Scraping / crawlers  -> Canary honeypot (silent minimal audit)

Current MAB arm mapping (backend.models.stage2_honeypot)
    arm 0 = Tarpit, arm 1 = Echo, arm 2 = Canary
(Shadow-Admin is described in the honeypot UI under frontend/honeypot-ui and
will be wired to a dedicated arm/route in a later phase.)

Inputs : BiometricResult (verdict + confidence), shadow secret, client IP.
Outputs: HoneypotResult (should_shadow, synthetic_token, MAB arm, signed
         ChallengeConfig with DecoySpec list).

Models / UI
-----------
    MABAgent (UCB1)         backend.models.mab
    Decoy renderer / UI     frontend/honeypot-ui (DecoyRenderer, FakeTerminal,
                            FakeVault, ShadowDashboard)

Facade mapping (v0.1 — re-export, no code moved)
------------------------------------------------
    .process / .run             <- backend.pipeline.stage2_honeypot.run
    .ChallengeConfig            <- backend.models.stage2_honeypot.ChallengeConfig
    .DecoySpec                  <- backend.models.stage2_honeypot.DecoySpec
    .verify_challenge_signature <- backend.models.stage2_honeypot.verify_challenge_signature
    .update_mab_reward          <- backend.models.stage2_honeypot.update_mab_reward
    .MABAgent                   <- backend.models.mab.MABAgent
"""
from __future__ import annotations

# ── Core Stage 2 honeypot logic (stdlib/numpy; safe to import) ───────────────
from backend.pipeline import stage2_honeypot as core
from backend.pipeline.stage2_honeypot import (
    run,
    ChallengeConfig,
    DecoySpec,
    verify_challenge_signature,
    update_mab_reward,
)

process = run

# ── Deception arm selector ───────────────────────────────────────────────────
try:
    from backend.models.mab import MABAgent
    MODELS_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    MABAgent = None
    MODELS_AVAILABLE = False
    _MODELS_ERROR = str(exc)

__all__ = [
    "core",
    "process",
    "run",
    "ChallengeConfig",
    "DecoySpec",
    "verify_challenge_signature",
    "update_mab_reward",
    "MABAgent",
    "MODELS_AVAILABLE",
]
