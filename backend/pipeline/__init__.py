"""
pipeline/__init__.py

Thin redirect package so main.py can do:
    from pipeline import PipelineOrchestrator, BiometricInput
    from pipeline import stage1_biometric as s1
    from pipeline.contracts import WatchdogAction, SecurityPreset
    from pipeline.orchestrator import _make_session_token

All real code lives in backend/models/.  This package re-exports it.
"""
from models.orchestrator import PipelineOrchestrator   # noqa: F401
from models.contracts    import BiometricInput          # noqa: F401
from models              import stage1_biometric        # noqa: F401
from models              import stage2_honeypot         # noqa: F401
from models              import stage3_governor         # noqa: F401
from models              import stage4_watchdog         # noqa: F401

__all__ = [
    "PipelineOrchestrator",
    "BiometricInput",
    "stage1_biometric",
    "stage2_honeypot",
    "stage3_governor",
    "stage4_watchdog",
]
