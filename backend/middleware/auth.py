"""
middleware/auth.py — SaaS API Gateway: FastAPI auth dependencies
================================================================

Two dependency families live here:

  Public SDK routes  →  require_api_key  (or  RequireApiKey(scope=…))
  ─────────────────
  Validates the `X-API-Key` header against the `sites` collection via
  auth_service.get_site_by_api_key.  On success injects a `SiteContext`.
  Missing / invalid keys → HTTP 401.  Inactive sites → HTTP 403.

  Admin routes  →  require_admin  (or  RequireAdmin(scope=…))
  ────────────
  Validates the `Authorization: Bearer <jwt>` header using RS256 via
  auth_service.verify_admin_jwt.  Supports optional per-route scope
  enforcement.  Invalid / expired tokens → HTTP 401.  Insufficient scope
  → HTTP 403.

Usage example (in main.py or any router)
─────────────────────────────────────────

    from middleware.auth import (
        SiteCtx, AdminCtx,
        require_api_key, require_admin,
        RequireAdmin,
    )

    # Public SDK route — any valid API key
    @app.post("/sdk/score")
    async def sdk_score(site: SiteCtx):
        tenant_id = site.tenant_id
        ...

    # Public route scoped to a specific feature flag check (app-level, not dep-level)
    @app.post("/sdk/biometric")
    async def sdk_biometric(site: SiteCtx):
        if "biometric" not in site.features:
            raise HTTPException(403, "Feature not available on your plan")
        ...

    # Admin route — any valid admin JWT
    @app.get("/admin/tenants")
    async def list_tenants(admin: AdminCtx):
        ...

    # Admin route — requires write scope
    @app.delete("/admin/tenants/{tenant_id}")
    async def delete_tenant(tenant_id: str, admin: Annotated[AdminClaims, Depends(RequireAdmin("admin:write"))]):
        ...

Dependency graph
────────────────

    require_api_key  ←  _APIKeyDep()        (no scope arg, convenience singleton)
    RequireApiKey    ←  _APIKeyDep           (callable class, pass scope= kwarg)

    require_admin    ←  _AdminJWTDep()       (no scope enforcement, convenience singleton)
    RequireAdmin     ←  _AdminJWTDep         (callable class, pass required_scope= kwarg)
"""

# removed: from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status

from services.auth_service import (
    AdminClaims,
    SiteContext,
    get_site_by_api_key,
    verify_admin_jwt,
)

logger = logging.getLogger("entropy_prime.middleware.auth")


# ─────────────────────────────────────────────────────────────────────────────
# Public SDK auth — X-API-Key → SiteContext
# ─────────────────────────────────────────────────────────────────────────────

class _APIKeyDep:
    """
    FastAPI dependency: validates the `X-API-Key` request header.

    Instantiate with no args for the convenience `require_api_key` singleton,
    or use `RequireApiKey` as a class alias to parameterise per route.

    Raises
    ──────
    HTTP 401  — header absent or key not found in DB
    HTTP 403  — key found but site is inactive
    HTTP 503  — DB unavailable during lookup
    """

    # Injected at app startup by attach_db(); avoids circular imports.
    _db = None

    def __init__(self) -> None:
        pass  # no per-instance config; parameterisation happens via subclass / kwarg below

    async def __call__(self, request: Request) -> SiteContext:
        raw_key: Optional[str] = request.headers.get("X-API-Key")

        if not raw_key:
            raise HTTPException(
                status_code = status.HTTP_401_UNAUTHORIZED,
                detail      = "Missing X-API-Key header",
                headers     = {"WWW-Authenticate": 'ApiKey realm="entropy-prime"'},
            )

        if self._db is None:
            logger.error("[APIKeyDep] DB not attached — call middleware.auth.attach_db() at startup")
            raise HTTPException(
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
                detail      = "Auth service unavailable",
            )

        try:
            site = await get_site_by_api_key(self._db, raw_key)
        except Exception as exc:
            logger.error("[APIKeyDep] DB error during key lookup: %s", exc)
            raise HTTPException(
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
                detail      = "Auth service unavailable",
            )

        if site is None:
            # Intentionally vague — do not reveal whether the key exists
            raise HTTPException(
                status_code = status.HTTP_401_UNAUTHORIZED,
                detail      = "Invalid or revoked API key",
                headers     = {"WWW-Authenticate": 'ApiKey realm="entropy-prime"'},
            )

        if not site.is_active:
            raise HTTPException(
                status_code = status.HTTP_403_FORBIDDEN,
                detail      = "Site is inactive — contact support",
            )

        logger.debug(
            "[APIKeyDep] Authenticated: site=%s tenant=%s plan=%s",
            site.site_id, site.tenant_id, site.plan,
        )
        return site


# Convenience singleton — inject with Depends(require_api_key)
require_api_key = _APIKeyDep()

# Annotated alias — use as a type hint in handler signatures
SiteCtx = Annotated[SiteContext, Depends(require_api_key)]

# Class alias for parameterised use (reserved for future scope-gating at dep level)
RequireApiKey = _APIKeyDep


# ─────────────────────────────────────────────────────────────────────────────
# Admin JWT auth — Authorization: Bearer <jwt> → AdminClaims
# ─────────────────────────────────────────────────────────────────────────────

class _AdminJWTDep:
    """
    FastAPI dependency: validates an RS256 JWT in the Authorization header.

    Args:
        required_scope: When provided, the token's `scope` claim must include
                        this exact string or HTTP 403 is raised.
                        Pass None (default) to authenticate without scope check.

    Raises
    ──────
    HTTP 401  — header absent, token malformed / expired / bad signature
    HTTP 403  — token valid but does not carry the required scope
    """

    def __init__(self, required_scope: Optional[str] = None) -> None:
        self._required_scope = required_scope

    async def __call__(self, request: Request) -> AdminClaims:
        auth_header: Optional[str] = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code = status.HTTP_401_UNAUTHORIZED,
                detail      = "Missing or malformed Authorization header (expected 'Bearer <token>')",
                headers     = {"WWW-Authenticate": "Bearer"},
            )

        raw_token = auth_header.removeprefix("Bearer ").strip()

        try:
            claims = verify_admin_jwt(raw_token, required_scope=self._required_scope)
        except ValueError as exc:
            msg = str(exc)

            # Scope failures → 403 (authenticated but not authorised)
            if "scope" in msg.lower():
                logger.warning("[AdminJWTDep] Scope failure: %s", msg)
                raise HTTPException(
                    status_code = status.HTTP_403_FORBIDDEN,
                    detail      = msg,
                )

            # Everything else (expired, bad sig, malformed, missing claims) → 401
            logger.warning("[AdminJWTDep] Token rejected: %s", msg)
            raise HTTPException(
                status_code = status.HTTP_401_UNAUTHORIZED,
                detail      = msg,
                headers     = {"WWW-Authenticate": "Bearer"},
            )

        logger.debug(
            "[AdminJWTDep] Admin authenticated: sub=%s tenant=%s scopes=%s",
            claims.sub, claims.tenant_id, claims.scopes,
        )
        return claims


# Convenience singleton — no scope enforcement
require_admin = _AdminJWTDep()

# Annotated alias
AdminCtx = Annotated[AdminClaims, Depends(require_admin)]

# Class alias for per-route instantiation: Depends(RequireAdmin("admin:write"))
RequireAdmin = _AdminJWTDep


# ─────────────────────────────────────────────────────────────────────────────
# Startup wiring
# ─────────────────────────────────────────────────────────────────────────────

def attach_db(db) -> None:
    """
    Inject the Motor DB handle into the API-key dependency at startup.

    Call this inside your lifespan after `db_handler.connect_to_mongo()`:

        from middleware.auth import attach_db
        attach_db(db_handler.db)

    This avoids a circular import between main.py → middleware → database.
    """
    _APIKeyDep._db = db
    logger.info("[Auth] DB handle attached to API key dependency")


# ─────────────────────────────────────────────────────────────────────────────
# Tenant scope guard (higher-order helper for route handlers)
# ─────────────────────────────────────────────────────────────────────────────

def assert_tenant_match(site: SiteContext, admin: AdminClaims) -> None:
    """
    Cross-auth guard: ensure an admin JWT is scoped to the same tenant as the
    API key context — or is a super-admin (tenant_id == "*").

    Use this in routes that accept BOTH an admin JWT *and* a site API key
    (e.g., admin-initiated operations on behalf of a specific site).

    Raises HTTP 403 on mismatch.
    """
    if admin.tenant_id == "*":
        return  # super-admin may act on any tenant
    if admin.tenant_id != site.tenant_id:
        logger.warning(
            "[Auth] Tenant mismatch: jwt_tenant=%s  site_tenant=%s",
            admin.tenant_id, site.tenant_id,
        )
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail      = "Admin token is not scoped to this tenant",
        )