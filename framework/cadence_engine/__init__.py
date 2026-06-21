"""
framework.cadence_engine — PHASE 1: Cognitive Cadence Engine
============================================================

Purpose
-------
Human vs Bot classification from behavioral biometrics. Turns raw keystroke
and pointer dynamics into a humanity score (theta), a trust signal, and a
behavioral embedding.

Inputs : dwell/flight times, keystroke dynamics, mouse velocity/acceleration,
         scroll dynamics, cursor path (collected browser-side; only derived
         features reach the server).
Outputs: humanity score (theta), behavioral verdict (bot/suspect/human),
         confidence band, 32-dim embedding.

Models
------
    CNN1D                       backend.models.cnn1d           (server-side embedder)
    (browser 1D-CNN)            src/services/biometrics.js     (theta scorer, tfjs)

Facade mapping (v0.1 — re-export, no code moved)
------------------------------------------------
    .process / .run             <- backend.pipeline.stage1_biometric.run
    .run_legacy                 <- backend.pipeline.stage1_biometric.run_legacy
    .receive_biometric_event    <- backend.pipeline.stage1_biometric.receive_biometric_event
    .CNN1D                      <- backend.models.cnn1d.CNN1D
    .service                    <- backend.services.biometric_services (Stage 1 service layer)

``MODELS_AVAILABLE`` is False when torch is not installed; the rest of the
engine (pure-numpy analysis) still imports.
"""
from __future__ import annotations

# ── Core Stage 1 logic (numpy-only; safe to import) ──────────────────────────
from backend.pipeline import stage1_biometric as core
from backend.pipeline.stage1_biometric import (
    run,
    run_legacy,
    receive_biometric_event,
    analyze_biometrics,
    calculate_risk_score,
)

# Canonical name for the framework-level "evaluate this input" entry point.
process = run

# ── Stage 1 service layer (profiles, baselines, anomaly history) ─────────────
try:
    from backend.services import biometric_services as service
    SERVICE_AVAILABLE = True
except Exception as exc:  # pragma: no cover - optional deps
    service = None
    SERVICE_AVAILABLE = False
    _SERVICE_ERROR = str(exc)

# ── Behavioral embedder (torch) ──────────────────────────────────────────────
try:
    from backend.models.cnn1d import CNN1D
    MODELS_AVAILABLE = True
except Exception as exc:  # pragma: no cover - torch may be absent
    CNN1D = None
    MODELS_AVAILABLE = False
    _MODELS_ERROR = str(exc)

__all__ = [
    "core",
    "process",
    "run",
    "run_legacy",
    "receive_biometric_event",
    "analyze_biometrics",
    "calculate_risk_score",
    "service",
    "SERVICE_AVAILABLE",
    "CNN1D",
    "MODELS_AVAILABLE",
]
