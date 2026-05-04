"""pipeline/contracts.py — re-exports all contracts + _CONF_RANK for test imports."""
from models.contracts import *  # noqa: F401, F403
from models.contracts import (
    BiometricInput, BiometricResult, HoneypotResult, GovernorResult,
    WatchdogResult, PipelineOutput, Confidence, HoneypotVerdict,
    SecurityPreset, WatchdogAction,
    BOT_THETA_HARD, BOT_THETA_SOFT,
    EREC_WARN, EREC_CRITICAL,
    TRUST_WARN, TRUST_CRITICAL,
    SERVER_LOAD_HIGH,
)
# test_pipeline.py imports _CONF_RANK from pipeline.contracts
from models.orchestrator import _CONF_RANK  # noqa: F401
