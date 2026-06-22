"""
framework.deception.anti_fingerprint — seeded decoy generation (Feature 6)
"""
from .decoy_factory import (
    generate_decoys,
    session_seed,
    DecoyFieldSpec,
)

__all__ = ["generate_decoys", "session_seed", "DecoyFieldSpec"]
