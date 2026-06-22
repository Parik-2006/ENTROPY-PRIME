"""
framework.deception.synthetic_success — believable login + shadow state (Feature 1)
"""
from .injector import (
    SyntheticSuccessInjector,
    ShadowState,
    ShadowStateStore,
    get_default_store,
)

__all__ = [
    "SyntheticSuccessInjector",
    "ShadowState",
    "ShadowStateStore",
    "get_default_store",
]
