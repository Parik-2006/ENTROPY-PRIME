"""
framework.api_gateway — Framework API Gateway (/v1)
===================================================

Provides a versioned, resource-grouped ``/v1`` API surface that mirrors the
existing endpoints in ``backend/main.py`` without modifying or removing any of
them. ``backend/main.py`` remains the compatibility layer and the single source
of truth for handler logic; this package only *organizes* and *aliases*.

Usage (already wired at the bottom of backend/main.py, guarded/non-fatal):

    from framework.api_gateway import build_v1_routers
    for r in build_v1_routers(sys.modules[__name__]):
        app.include_router(r)

``build_v1_routers`` is a pure function with no import-time side effects, so
importing ``framework.api_gateway`` never triggers loading the FastAPI app.
"""
from __future__ import annotations

from ._clone import V1_PREFIX
from .routers import ALL_GROUPS

__all__ = ["build_v1_routers", "V1_PREFIX"]


def build_v1_routers(main_module):
    """
    Build the list of /v1 APIRouters by mirroring the live routes on
    ``main_module.app``. Call this AFTER all original routes are registered
    (i.e., at the bottom of main.py), so every route is available to mirror.
    """
    return [group.make_router(main_module) for group in ALL_GROUPS]
