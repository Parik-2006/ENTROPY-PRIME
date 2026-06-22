"""
framework.deception.classifier — Attack Classification Engine (Feature 2)
"""
from .attack_classifier import (
    AttackClass,
    AttackClassification,
    AttackSignals,
    classify,
    DEFAULT_STRATEGY_FOR_CLASS,
)

__all__ = [
    "AttackClass",
    "AttackClassification",
    "AttackSignals",
    "classify",
    "DEFAULT_STRATEGY_FOR_CLASS",
]
