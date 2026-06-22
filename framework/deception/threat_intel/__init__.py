"""
framework.deception.threat_intel — attacker activity recording (Feature 5)
"""
from .recorder import (
    ThreatIntelRecorder,
    AttackerEvent,
    get_recorder,
)

__all__ = ["ThreatIntelRecorder", "AttackerEvent", "get_recorder"]
