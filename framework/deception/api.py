"""
api.py — Deception Shadow API router (Features 3, 4, 5, 9)
=========================================================

A self-contained FastAPI ``APIRouter`` that main.py mounts with one line:

    from framework.deception.api import router as deception_router
    app.include_router(deception_router)

It exposes the believable synthetic environment to shadow-routed attackers and
a defender-only threat-intel view.

Routing model
-------------
    Every /api/shadow/* request must carry the shadow session token
    (Authorization: Bearer <token>, or ?token=).  The token is looked up in the
    server-side ShadowStateStore:
        • found  → resolve the attacker's world (banking / shadow_admin) and
                   return synthetic JSON; record the interaction.
        • absent → believable 404 (we never reveal that "shadow mode" exists).

Why /api/shadow/* and not bare /api/*?
    To avoid colliding with any real application routes the host app may mount.
    In a production reverse-proxy deployment, nginx rewrites a shadow session's
    /api/* to /api/shadow/* transparently (documented, not part of MVP code).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from .synthetic_success import get_default_store
from .shadow_world import get_engine
from .threat_intel import get_recorder

router = APIRouter(tags=["deception"])


# ── token resolution ──────────────────────────────────────────────────────────
def _extract_token(authorization: Optional[str], token_q: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return token_q


def _require_shadow(authorization: Optional[str], token_q: Optional[str]):
    """Resolve shadow state or raise a believable 404."""
    token = _extract_token(authorization, token_q)
    state = get_default_store().get(token) if token else None
    if state is None:
        # Never leak the existence of the deception layer.
        raise HTTPException(status_code=404, detail="Not Found")
    return state


def _record(state, event_type: str, detail: dict) -> None:
    get_recorder().record(
        session_token = state.session_token,
        tenant_id     = state.tenant_id,
        attack_class  = state.attack_class,
        event_type    = event_type,
        detail        = detail,
    )


def _resolve(state, asset: str, **params) -> dict:
    engine = get_engine()
    try:
        return engine.resolve(state.world, state.world_seed, asset, **params)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not Found")


# ── session bootstrap ─────────────────────────────────────────────────────────
@router.get("/api/shadow/me")
def shadow_me(
    request: Request,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    """What environment am I in?  (the SDK calls this right after 'login')"""
    state = _require_shadow(authorization, token)
    get_default_store().touch(state.session_token)
    _record(state, "page_visit", {"path": "/api/shadow/me"})
    return {
        "world":  state.world,
        "assets": get_engine().assets(state.world),
        "user":   {"role": "admin" if state.world == "shadow_admin" else "user"},
    }


# ── Banking shadow world (Feature 4) ──────────────────────────────────────────
@router.get("/api/shadow/dashboard")
def shadow_dashboard(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    state = _require_shadow(authorization, token)
    _record(state, "page_visit", {"path": "/api/shadow/dashboard"})
    return _resolve(state, "dashboard")


@router.get("/api/shadow/accounts")
def shadow_accounts(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    state = _require_shadow(authorization, token)
    _record(state, "api_call", {"path": "/api/shadow/accounts"})
    return _resolve(state, "accounts")


@router.get("/api/shadow/transactions")
def shadow_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    state = _require_shadow(authorization, token)
    _record(state, "api_call", {"path": "/api/shadow/transactions", "page": page})
    return _resolve(state, "transactions", page=page, page_size=page_size)


@router.get("/api/shadow/beneficiaries")
def shadow_beneficiaries(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    state = _require_shadow(authorization, token)
    _record(state, "api_call", {"path": "/api/shadow/beneficiaries"})
    return _resolve(state, "beneficiaries")


@router.get("/api/shadow/statements")
def shadow_statements(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    state = _require_shadow(authorization, token)
    _record(state, "api_call", {"path": "/api/shadow/statements"})
    return _resolve(state, "statements")


@router.get("/api/shadow/profile")
def shadow_profile(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    state = _require_shadow(authorization, token)
    _record(state, "api_call", {"path": "/api/shadow/profile"})
    return _resolve(state, "profile")


# ── Shadow Admin world (Feature 3) ────────────────────────────────────────────
@router.get("/api/shadow/admin/users")
def admin_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    state = _require_shadow(authorization, token)
    _record(state, "api_call", {"path": "/api/shadow/admin/users", "page": page})
    return _resolve(state, "users", page=page, page_size=page_size)


@router.get("/api/shadow/admin/logs")
def admin_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    state = _require_shadow(authorization, token)
    _record(state, "api_call", {"path": "/api/shadow/admin/logs", "page": page})
    return _resolve(state, "logs", page=page, page_size=page_size)


@router.get("/api/shadow/admin/analytics")
def admin_analytics(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    state = _require_shadow(authorization, token)
    _record(state, "api_call", {"path": "/api/shadow/admin/analytics"})
    return _resolve(state, "analytics")


@router.get("/api/shadow/admin/config")
def admin_config(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    state = _require_shadow(authorization, token)
    _record(state, "api_call", {"path": "/api/shadow/admin/config"})
    return _resolve(state, "config")


@router.get("/api/shadow/admin/secrets")
def admin_secrets(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    """High-value bait: canary secrets.  Viewing them is a strong intent signal."""
    state = _require_shadow(authorization, token)
    _record(state, "canary_hit", {"path": "/api/shadow/admin/secrets"})
    return _resolve(state, "secrets")


# ── Defender-only Threat Intelligence (Feature 5) ─────────────────────────────
# NOTE: in production gate these behind admin auth.  Kept open in MVP so the
# existing ThreatPage.jsx / ThreatIntel.jsx can poll without new auth wiring.

@router.get("/admin/deception/summary")
def deception_summary():
    return get_recorder().summary()


@router.get("/admin/deception/sessions")
def deception_sessions(limit: int = Query(100, ge=1, le=500)):
    return {"sessions": get_recorder().sessions(limit=limit)}


@router.get("/admin/deception/events")
def deception_events(
    limit: int = Query(200, ge=1, le=1000),
    session_token: Optional[str] = Query(None),
):
    return {"events": get_recorder().events(limit=limit, session_token=session_token)}
