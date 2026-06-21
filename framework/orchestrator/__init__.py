"""
framework.orchestrator — Engine Sequencer
=========================================

Runs the four engines in sequence and assembles a single result. This is the
fail-safe core: every engine call is wrapped so the pipeline never raises; a
``degraded`` flag signals partial failure instead.

Execution order (note: differs from phase *numbering*)
------------------------------------------------------
    1. Cadence    (Phase 1)  ->  humanity verdict
    2. Honeypot   (Phase 3)  ->  shadow-route bots (short-circuits 3 & 4)
    3. DMS        (Phase 2)  ->  Argon2id preset + behavioral action
    4. Continuous (Phase 4)  ->  drift / trust action

Facade mapping (v0.1 — re-export, no code moved)
------------------------------------------------
    .PipelineOrchestrator   <- backend.pipeline.PipelineOrchestrator
    .BiometricInput         <- backend.pipeline.BiometricInput
    .make_session_token     <- backend.pipeline.orchestrator._make_session_token
"""
from __future__ import annotations

from backend.pipeline import PipelineOrchestrator, BiometricInput
from backend.pipeline.orchestrator import _make_session_token as make_session_token

# Framework-preferred alias.
EngineSequencer = PipelineOrchestrator

__all__ = [
    "PipelineOrchestrator",
    "EngineSequencer",
    "BiometricInput",
    "make_session_token",
]
