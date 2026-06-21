"""pipeline/stage3_governor.py — redirect to models.stage3_governor."""
try:
    from ..models.stage3_governor import run  # noqa: F401
except ImportError:
    from models.stage3_governor import run  # type: ignore # noqa: F401
