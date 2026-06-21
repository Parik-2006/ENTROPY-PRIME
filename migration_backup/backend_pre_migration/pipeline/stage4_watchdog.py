"""pipeline/stage4_watchdog.py — redirect to models.stage4_watchdog."""
try:
    from ..models.stage4_watchdog import run, _fallback_rules  # noqa: F401
except ImportError:
    from models.stage4_watchdog import run, _fallback_rules  # type: ignore # noqa: F401
