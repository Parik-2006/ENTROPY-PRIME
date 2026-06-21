"""
framework.api_gateway.routers — resource-grouped /v1 routers
============================================================

Each module owns a slice of the API surface and exposes:

    TAG            : str                       OpenAPI tag for the group
    matches(path)  : Callable[[str], bool]     which existing paths belong here
    make_router(m) : APIRouter                 the /v1 mirror for the group

The group's `/v1` router is a faithful mirror of the existing routes (see
``framework.api_gateway._clone``); it adds no new logic and removes nothing.
"""

from . import auth, score, session, biometric, honeypot, admin, integration, health

# Order defines OpenAPI grouping order; every group is independent.
ALL_GROUPS = [auth, score, session, biometric, honeypot, admin, integration, health]

__all__ = ["ALL_GROUPS", "auth", "score", "session", "biometric",
           "honeypot", "admin", "integration", "health"]
