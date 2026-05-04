"""
pipeline/__init__.py

Public surface of the pipeline package.
main.py imports `from pipeline import PipelineOrchestrator, BiometricInput`
and `from pipeline import stage1_biometric as s1` etc., so we expose those here.
"""
from .orchestrator import PipelineOrchestrator   # noqa: F401
from .contracts    import BiometricInput          # noqa: F401
from .             import stage1_biometric        # noqa: F401
from .             import stage2_honeypot         # noqa: F401
from .             import stage3_governor         # noqa: F401
from .             import stage4_watchdog         # noqa: F401

__all__ = [
    "PipelineOrchestrator",
    "BiometricInput",
    "stage1_biometric",
    "stage2_honeypot",
    "stage3_governor",
    "stage4_watchdog",
]
