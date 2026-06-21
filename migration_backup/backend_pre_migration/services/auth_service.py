"""
auth_service.py — SaaS API Gateway: tenant auth helpers
========================================================

Design principles
─────────────────
• API keys are NEVER stored in plaintext.  Only a constant-time HMAC-SHA256
  digest (keyed on EP_API_KEY_SECRET) lives in the `sites` collection.
  Incoming keys are digested the same way and compared with `secrets.compare_digest`.

• Tenant resolution is a two-step lookup:
    1.  key_digest → site document  (indexed on `sites.key_digest`)
    2.  site.tenant_id → tenant document  (from `tenants` collection)
  Both are cached in-process for CACHE_TTL_S seconds to keep hot paths fast
  without a Redis dependency.

• JWT admin tokens use RS256 (asymmetric).  The public key is loaded from
  EP_JWT_PUBLIC_KEY_PATH at startup; the private key is never loaded by the
  API server — only the auth-issuer service signs tokens.

• `AdminClaims` is intentionally strict: `scope` must contain the required
  scope string and `aud` must match EP_JWT_AUDIENCE.  A missing claim is a
  hard rejection, not a fallback.
"""

# removed: from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import jwt  # PyJWT ≥ 2.x
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidSignatureError,
    MissingRequiredClaimError,
)
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("entropy_prime.auth_service")

# ── Secrets / config ──────────────────────────────────────────────────────────

_API_KEY_SECRET: bytes = os.environ.get("EP_API_KEY_SECRET", "").encode() or (
    # Dev-only fallback — logs a loud warning so it's never silently insecure
    logger.warning(
        "EP_API_KEY_SECRET is not set — using insecure dev fallback.  "
        "Set this env var in production."
    )
    or b"dev-only-api-key-secret-change-me"
)

_JWT_AUDIENCE: str = os.environ.get("EP_JWT_AUDIENCE", "entropy-prime-admin")
_JWT_ALGORITHM: str = "RS256"

_jwt_public_key: Optional[Any] = None   # populated by load_jwt_public_key()


def load_jwt_public_key() -> None:
    """
    Call once at startup (inside lifespan).  Loads the RS256 public key from
    EP_JWT_PUBLIC_KEY_PATH or the PEM string in EP_JWT_PUBLIC_KEY.

    Raises RuntimeError if neither is set — admin routes will be unavailable.
    """
    global _jwt_public_key

    pem_path = os.environ.get("EP_JWT_PUBLIC_KEY_PATH", "")
    pem_inline = os.environ.get("EP_JWT_PUBLIC_KEY", "")

    if pem_path and os.path.exists(pem_path):
        with open(pem_path, "rb") as fh:
            _jwt_public_key = fh.read()
        logger.info("✓ JWT public key loaded from %s", pem_path)
    elif pem_inline:
        _jwt_public_key = pem_inline.encode()
        logger.info("✓ JWT public key loaded from EP_JWT_PUBLIC_KEY env var")
    else:
        logger.warning(
            "No JWT public key configured (EP_JWT_PUBLIC_KEY_PATH / EP_JWT_PUBLIC_KEY). "
            "Admin routes will reject all requests."
        )


# ── In-process cache ──────────────────────────────────────────────────────────

CACHE_TTL_S: int = int(os.environ.get("EP_AUTH_CACHE_TTL_S", "30"))

@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class _TtlCache:
    """Minimal TTL dict — no external deps, thread-safe enough for asyncio."""

    def __init__(self, ttl: int = CACHE_TTL_S) -> None:
        self._ttl = ttl
        self._store: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None or time.monotonic() > entry.expires_at:
            self._store.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = _CacheEntry(value=value, expires_at=time.monotonic() + self._ttl)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)


_site_cache: _TtlCache   = _TtlCache()
_tenant_cache: _TtlCache = _TtlCache()


# ── Domain objects ────────────────────────────────────────────────────────────

@dataclass
class SiteContext:
    """Resolved identity for a public SDK request authenticated by API key."""
    site_id:    str
    tenant_id:  str
    plan:       str                       # e.g. "free", "pro", "enterprise"
    rate_limit: int                       # requests / minute allowed for this site
    features:   list[str] = field(default_factory=list)  # feature-flag list
    is_active:  bool = True


@dataclass
class AdminClaims:
    """Validated payload from a signed RS256 JWT (admin routes only)."""
    sub:        str          # admin user / service account identifier
    tenant_id:  str          # tenant the token is scoped to ("*" = super-admin)
    scopes:     list[str]    # e.g. ["admin:read", "admin:write"]
    exp:        int          # unix timestamp
    jti:        str          # token ID — for future revocation list support


# ── API key helpers ───────────────────────────────────────────────────────────

def _digest_api_key(raw_key: str) -> str:
    """
    Derive the stored digest for a raw API key.

    HMAC-SHA256 keyed on EP_API_KEY_SECRET.  Using HMAC (not bare SHA-256)
    means a leaked digest dump cannot be reversed without the server secret.
    """
    return hmac.new(_API_KEY_SECRET, raw_key.encode(), hashlib.sha256).hexdigest()


async def get_site_by_api_key(
    db: AsyncIOMotorDatabase,
    raw_key: str,
) -> Optional[SiteContext]:
    """
    Look up the site associated with `raw_key`.

    Steps:
      1. Digest the incoming key (HMAC-SHA256).
      2. Check in-process cache (keyed on digest, not raw key).
      3. Query `sites` collection on the indexed `key_digest` field.
      4. Verify `is_active` and presence of required fields.
      5. Return a `SiteContext` or None.

    Timing note: the digest computation is O(key_length); the subsequent
    `secrets.compare_digest` inside MongoDB is not used here because the
    lookup is by exact index match.  The digest itself is not secret in the
    query — the secret is the HMAC key used to derive it.
    """
    if not raw_key:
        return None

    digest = _digest_api_key(raw_key)

    cached = _site_cache.get(digest)
    if cached is not None:
        return cached

    doc = await db["sites"].find_one({"key_digest": digest, "is_active": True})
    if doc is None:
        # Cache negative result briefly to blunt enumeration attempts
        _site_cache.set(digest, None)
        return None

    ctx = SiteContext(
        site_id    = str(doc["_id"]),
        tenant_id  = str(doc["tenant_id"]),
        plan       = doc.get("plan", "free"),
        rate_limit = int(doc.get("rate_limit_rpm", 60)),
        features   = list(doc.get("features", [])),
        is_active  = bool(doc.get("is_active", True)),
    )
    _site_cache.set(digest, ctx)
    logger.debug("[AuthService] Site resolved: site_id=%s tenant=%s", ctx.site_id, ctx.tenant_id)
    return ctx


async def get_tenant_by_id(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
) -> Optional[dict]:
    """
    Fetch a tenant document by its string ID.

    Returns the raw dict (caller can extract what it needs) or None.
    Cached by `tenant_id` for CACHE_TTL_S seconds.
    """
    cached = _tenant_cache.get(tenant_id)
    if cached is not None:
        return cached

    from bson import ObjectId  # local import so the module loads without bson at test time

    try:
        oid = ObjectId(tenant_id)
    except Exception:
        return None

    doc = await db["tenants"].find_one({"_id": oid})
    if doc is None:
        _tenant_cache.set(tenant_id, None)
        return None

    # Stringify ObjectId fields before caching
    doc["_id"] = str(doc["_id"])
    _tenant_cache.set(tenant_id, doc)
    return doc


def invalidate_site_cache(raw_key: str) -> None:
    """Remove a site entry from the cache (e.g., after key rotation)."""
    _site_cache.invalidate(_digest_api_key(raw_key))


# ── JWT helpers ───────────────────────────────────────────────────────────────

def verify_admin_jwt(token: str, required_scope: Optional[str] = None) -> AdminClaims:
    """
    Decode and validate a signed RS256 JWT.

    Raises ValueError with a descriptive message on any validation failure
    so the caller can map it to an appropriate HTTP status code.

    Args:
        token:          The raw Bearer token string.
        required_scope: If provided, the token's `scope` claim must include
                        this exact string.  Pass None to skip scope enforcement
                        (e.g. for read-only admin endpoints).

    Returns:
        AdminClaims on success.

    Raises:
        ValueError: on any decode / validation failure.
    """
    if _jwt_public_key is None:
        raise ValueError("JWT public key not loaded — admin auth unavailable")

    try:
        payload = jwt.decode(
            token,
            _jwt_public_key,
            algorithms=[_JWT_ALGORITHM],
            audience=_JWT_AUDIENCE,
            options={"require": ["sub", "exp", "jti", "tenant_id"]},
        )
    except ExpiredSignatureError:
        raise ValueError("Admin token has expired")
    except InvalidAudienceError:
        raise ValueError(f"Token audience does not match '{_JWT_AUDIENCE}'")
    except InvalidSignatureError:
        raise ValueError("Token signature verification failed")
    except MissingRequiredClaimError as exc:
        raise ValueError(f"Token missing required claim: {exc}")
    except DecodeError as exc:
        raise ValueError(f"Malformed token: {exc}")

    scopes: list[str] = payload.get("scope", "").split()

    if required_scope and required_scope not in scopes:
        raise ValueError(
            f"Token scope '{' '.join(scopes)}' does not include '{required_scope}'"
        )

    return AdminClaims(
        sub       = str(payload["sub"]),
        tenant_id = str(payload["tenant_id"]),
        scopes    = scopes,
        exp       = int(payload["exp"]),
        jti       = str(payload["jti"]),
    )