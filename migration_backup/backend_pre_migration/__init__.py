"""
backend/__init__.py — Public API surface for the ENTROPY-PRIME backend.

RULES (enforced here):
  1. Only re-export FUNCTION-BASED entry points: run() and run_legacy().
  2. Do NOT import class names that don't exist as public exports from their
     modules (Stage1BiometricInterpreter, Stage2HoneypotClassifier, etc.).
     Those are internal implementation details.
  3. Dataclasses and contracts ARE re-exported so callers don't need to dig
     into sub-packages.

Breaking change vs. old __init__.py:
  Removed class imports:
    Stage1BiometricInterpreter   — was never a public class
    Stage2HoneypotClassifier     — was never a public class
    Stage3ResourceGovernor       — was never a public class
    Stage4SessionWatchdog        — was never a public class
  These imports caused ImportError on every startup.
"""

# ── Contracts (safe to expose) ────────────────────────────────────────────────
from .pipeline.contracts import (
    BiometricInput,
    BiometricResult,
    HoneypotResult,
    GovernorResult,
    WatchdogResult,
    PipelineOutput,
    ChallengePayload,
    TenantPolicy,
    Confidence,
    HoneypotVerdict,
    SecurityPreset,
    WatchdogAction,
    GovernorAction,
)

# ── Function-based stage APIs ─────────────────────────────────────────────────
from .pipeline.stage1_biometric import run as run_stage1
from .pipeline.stage1_biometric import run_legacy as run_stage1_legacy

from .pipeline.stage2_honeypot import run as run_stage2
from .pipeline.stage2_honeypot import verify_challenge_signature

from .pipeline.stage3_governor import run as run_stage3

from .pipeline.stage4_watchdog import run as run_stage4

# ── Orchestrator (full pipeline) ──────────────────────────────────────────────
from .models.orchestrator import PipelineOrchestrator

# ── Convenience aliases used by existing integration tests ────────────────────
def run(raw: BiometricInput, orchestrator: PipelineOrchestrator) -> PipelineOutput:
    """Top-level run() convenience wrapper. Equivalent to orchestrator.run(raw)."""
    return orchestrator.run(raw)


def run_legacy(raw: BiometricInput, orchestrator: PipelineOrchestrator) -> PipelineOutput:
    """Legacy alias for run() — kept for backward compat with old test suites."""
    return orchestrator.run(raw)


__all__ = [
    # contracts
    "BiometricInput", "BiometricResult", "HoneypotResult", "GovernorResult",
    "WatchdogResult", "PipelineOutput", "ChallengePayload", "TenantPolicy",
    "Confidence", "HoneypotVerdict", "SecurityPreset", "WatchdogAction", "GovernorAction",
    # stage functions
    "run_stage1", "run_stage1_legacy",
    "run_stage2", "verify_challenge_signature",
    "run_stage3",
    "run_stage4",
    # orchestrator
    "PipelineOrchestrator",
    # top-level
    "run", "run_legacy",
]