"""
framework.dms_engine — PHASE 2: Dynamic Memory Security (DMS)
============================================================

Purpose
-------
Adaptive password hardening. Shifts compute cost onto attackers by selecting
Argon2id parameters dynamically: weak passwords / low-trust sessions get a
heavier cost; strong passwords / trusted humans get a lighter cost.
Asymmetric defense.

Inputs : password expectation entropy (Hexp), Zipf pattern analysis, server
         load, biometric verdict (theta, is_suspect, is_bot), tenant policy.
Logic  : DQN selects the Argon2id preset (ECONOMY -> PUNISHER); PPOPolicyAgent
         selects the behavioral action (ALLOW/LOG/CHALLENGE/BLOCK); tenant
         policy clamps the result.
Outputs: GovernorResult (preset, memory_kb, time_cost, parallelism, action).

Models
------
    DQNAgent          backend.models.dqn          (Argon2id preset, 3 -> 4)
    PPOPolicyAgent    backend.models.ppo_agents   (behavioral action, 5 -> 4)

Where the Argon2id / Hexp / Zipf pieces currently live
------------------------------------------------------
  * Preset selection + policy clamps : backend.models.stage3_governor (this engine)
  * Argon2id hashing call            : inline in backend/main.py (PasswordHasher);
                                       a later phase extracts it into dms_engine.hashing.
  * Expectation entropy (Hexp/Zipf)  : computed browser-side in
                                       src/services/biometrics.js (computeExpectationEntropy);
                                       backend.services.governor_services holds server helpers.

Facade mapping (v0.1 — re-export, no code moved)
------------------------------------------------
    .process / .run    <- backend.pipeline.stage3_governor.run
    .DQNAgent          <- backend.models.dqn.DQNAgent
    .PPOPolicyAgent    <- backend.models.ppo_agents.PPOPolicyAgent
    .service           <- backend.services.governor_services
"""
from __future__ import annotations

# ── Core Stage 3 governor logic ──────────────────────────────────────────────
from backend.pipeline import stage3_governor as core
from backend.pipeline.stage3_governor import run

process = run

# ── Governor service helpers ─────────────────────────────────────────────────
try:
    from backend.services import governor_services as service
    SERVICE_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    service = None
    SERVICE_AVAILABLE = False
    _SERVICE_ERROR = str(exc)

# ── Agents (torch) ───────────────────────────────────────────────────────────
try:
    from backend.models.dqn import DQNAgent
    from backend.models.ppo_agents import PPOPolicyAgent
    MODELS_AVAILABLE = True
except Exception as exc:  # pragma: no cover - torch may be absent
    DQNAgent = None
    PPOPolicyAgent = None
    MODELS_AVAILABLE = False
    _MODELS_ERROR = str(exc)

__all__ = [
    "core",
    "process",
    "run",
    "service",
    "SERVICE_AVAILABLE",
    "DQNAgent",
    "PPOPolicyAgent",
    "MODELS_AVAILABLE",
]
