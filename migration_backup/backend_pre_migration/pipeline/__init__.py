"""Pipeline re-export package for legacy imports."""

try:
    from ..models.orchestrator import PipelineOrchestrator  # noqa: F401
    from ..models.contracts import BiometricInput  # noqa: F401
    from ..models import stage1_biometric  # noqa: F401
    from ..models import stage2_honeypot  # noqa: F401
    from ..models import stage3_governor  # noqa: F401
    from ..models import stage4_watchdog  # noqa: F401
except ImportError:
    from models.orchestrator import PipelineOrchestrator  # type: ignore # noqa: F401
    from models.contracts import BiometricInput  # type: ignore # noqa: F401
    from models import stage1_biometric  # type: ignore # noqa: F401
    from models import stage2_honeypot  # type: ignore # noqa: F401
    from models import stage3_governor  # type: ignore # noqa: F401
    from models import stage4_watchdog  # type: ignore # noqa: F401

__all__ = [
    "PipelineOrchestrator",
    "BiometricInput",
    "stage1_biometric",
    "stage2_honeypot",
    "stage3_governor",
    "stage4_watchdog",
]
