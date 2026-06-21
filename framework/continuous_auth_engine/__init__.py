"""
framework.continuous_auth_engine — PHASE 4: Continuous Authentication
=====================================================================

Purpose
-------
Identity-drift detection that answers, continuously: "Is this still the same
human?" Tolerant of human variability (fast/slow/tired days) because it scores
*relative* drift against an adaptive per-user baseline, not absolute speed.

Confidence zones
----------------
    GREEN   high trust          -> OK
    YELLOW  suspicious           -> PASSIVE_REAUTH / DISABLE_SENSITIVE_API
    RED     identity drift       -> FORCE_LOGOUT (only when profile is `stable`)

Inputs : 32-dim behavioral latent vector, autoencoder reconstruction error
         (e_rec), DB-sourced trust score, adaptive threshold, drift window.
Outputs: WatchdogResult (action, trust_score, e_rec, confidence, reason).

Statistical basis
-----------------
  * Browser-side: EMA profile + variance + adaptive threshold (mean + 2*std)
    in src/services/biometrics.js (UserBehavioralProfile).
  * Server-side : PPO policy + deterministic threshold fallback rules
    (EREC_WARN/CRITICAL, TRUST_WARN/CRITICAL).

Models
------
    PPOAgent (actor-critic)   backend.models.ppo        (10 -> 3)
    Autoencoder               src/services/biometrics.js (tfjs, browser-side)

Facade mapping (v0.1 — re-export, no code moved)
------------------------------------------------
    .process / .run         <- backend.pipeline.stage4_watchdog.run
    .run_with_threat_gate   <- backend.pipeline.stage4_watchdog.run_with_threat_gate
    .fallback_rules         <- backend.pipeline.stage4_watchdog._fallback_rules
    .PPOAgent               <- backend.models.ppo.PPOAgent
    .WatchdogService        <- backend.services.watchdog_services.WatchdogService
"""
from __future__ import annotations

# ── Core Stage 4 watchdog logic ──────────────────────────────────────────────
# Note: backend.pipeline.stage4_watchdog is a thin shim that re-exports only
# `run` and `_fallback_rules` from backend.models.stage4_watchdog. The async
# cross-site `run_with_threat_gate` lives only in the models module, so it is
# sourced from there directly (and guarded — it pulls in the watchdog service).
from backend.pipeline import stage4_watchdog as core
from backend.pipeline.stage4_watchdog import (
    run,
    _fallback_rules as fallback_rules,
)

process = run

try:
    from backend.models.stage4_watchdog import run_with_threat_gate
    THREAT_GATE_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    run_with_threat_gate = None
    THREAT_GATE_AVAILABLE = False
    _THREAT_GATE_ERROR = str(exc)

# ── Watchdog service (per-session + cross-site gate) ─────────────────────────
try:
    from backend.services.watchdog_services import WatchdogService
    SERVICE_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    WatchdogService = None
    SERVICE_AVAILABLE = False
    _SERVICE_ERROR = str(exc)

# ── Drift policy agent (torch) ───────────────────────────────────────────────
try:
    from backend.models.ppo import PPOAgent
    MODELS_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    PPOAgent = None
    MODELS_AVAILABLE = False
    _MODELS_ERROR = str(exc)

__all__ = [
    "core",
    "process",
    "run",
    "run_with_threat_gate",
    "THREAT_GATE_AVAILABLE",
    "fallback_rules",
    "WatchdogService",
    "SERVICE_AVAILABLE",
    "PPOAgent",
    "MODELS_AVAILABLE",
]
