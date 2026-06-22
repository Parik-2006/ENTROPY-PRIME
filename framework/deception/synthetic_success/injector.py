"""
injector.py — Synthetic Success Injection (Feature 1)
=====================================================

Goal: a detected bot must believe authentication SUCCEEDED.

    BEFORE:  bot detected → "bot_"/"ep_shadow_" token → obvious decoy forms
    AFTER:   bot detected → normal-looking success response → silent isolation

Key guarantees
--------------
1. The response body is byte-shaped like a real login success
   (``{"status": "success", "token": ..., "user": {...}, "redirect": ...}``).
   No warning screens, no honeypot indicators.
2. The session token has the SAME format as a genuine token — no "bot_" or
   "ep_shadow_" prefix that a bot could grep for.  The legacy
   ``_make_shadow_token`` prefix is therefore NOT used on the wire.
3. The "this is a shadow session" fact is stored SERVER-SIDE only
   (``ShadowStateStore``), keyed by the opaque token.  It never leaves the
   server, so the attacker cannot detect shadow mode by inspecting their token.

The store is pluggable: an in-process dict by default (so demos/tests run with
no infra), optionally backed by Redis in production.  The shadow world API
(framework.deception.api) looks the token up here to decide whether — and into
which synthetic world — to route subsequent requests.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ShadowState:
    """Server-side record describing one shadow (honeypot) session."""
    session_token: str
    tenant_id:     str
    attack_class:  str
    world:         str            # "banking" | "shadow_admin" | ...
    world_seed:    str            # drives deterministic synthetic content
    arm:           int = -1
    ip_address:    str = "?"
    created_at:    float = field(default_factory=time.time)
    # Lightweight activity counters (richer telemetry lives in threat_intel).
    pages_visited: int = 0
    last_seen:     float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "session_token": self.session_token,
            "tenant_id":     self.tenant_id,
            "attack_class":  self.attack_class,
            "world":         self.world,
            "world_seed":    self.world_seed,
            "arm":           self.arm,
            "ip_address":    self.ip_address,
            "created_at":    self.created_at,
            "pages_visited": self.pages_visited,
            "last_seen":     self.last_seen,
        }


class ShadowStateStore:
    """
    Thread-safe in-process shadow-state store.

    Production can subclass / wrap this to persist into Redis (the existing
    backend.services.redis_client) — the interface is deliberately tiny:
    ``put`` / ``get`` / ``touch`` / ``all``.
    """

    def __init__(self, ttl_seconds: int = 3600):
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._store: dict[str, ShadowState] = {}

    def put(self, state: ShadowState) -> None:
        with self._lock:
            self._store[state.session_token] = state

    def get(self, token: str) -> Optional[ShadowState]:
        with self._lock:
            st = self._store.get(token)
            if st is None:
                return None
            if time.time() - st.created_at > self._ttl:
                # expired — drop it
                self._store.pop(token, None)
                return None
            return st

    def touch(self, token: str) -> Optional[ShadowState]:
        """Mark activity on a session (page visit)."""
        with self._lock:
            st = self._store.get(token)
            if st is not None:
                st.pages_visited += 1
                st.last_seen = time.time()
            return st

    def all(self) -> list[ShadowState]:
        with self._lock:
            return list(self._store.values())

    def is_shadow(self, token: str) -> bool:
        return self.get(token) is not None


# A module-level default store so the API router and the /score handler share
# the same in-process state without wiring a singleton through everything.
_DEFAULT_STORE: Optional[ShadowStateStore] = None


def get_default_store() -> ShadowStateStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = ShadowStateStore()
    return _DEFAULT_STORE


class SyntheticSuccessInjector:
    """
    Mints a believable "login success" + registers server-side shadow state.

    Parameters
    ----------
    secret  HMAC secret (reuse the existing EP_SESSION_SECRET so shadow tokens
            are indistinguishable from real ones in both format and entropy).
    store   ShadowStateStore (defaults to the shared in-process store).
    """

    def __init__(self, secret: str, store: Optional[ShadowStateStore] = None):
        self._secret = secret or secrets.token_hex(32)
        self._store = store or get_default_store()

    # ── token minting ─────────────────────────────────────────────────────────
    def _mint_token(self, subject: str) -> str:
        """
        Produce a token in the SAME shape as a genuine session token:
            ep_<hmac-sha256-hex>_<random-hex>
        (mirrors backend.pipeline.orchestrator._make_session_token).  No shadow
        markers — indistinguishable from a real token.
        """
        payload = f"{subject}:{secrets.token_hex(8)}"
        sig = hmac.new(self._secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"ep_{sig}_{secrets.token_hex(8)}"

    def _world_seed(self, token: str, tenant_id: str) -> str:
        """Deterministic, unguessable world seed bound to the session."""
        return hmac.new(
            self._secret.encode(),
            f"world:{tenant_id}:{token}".encode(),
            hashlib.sha256,
        ).hexdigest()

    # ── public API ────────────────────────────────────────────────────────────
    def mint_success(
        self,
        *,
        tenant_id:    str,
        attack_class: str,
        world:        str,
        arm:          int = -1,
        ip_address:   str = "?",
        subject:      str = "user",
        redirect:     str = "/dashboard",
        display_name: Optional[str] = None,
    ) -> tuple[dict, ShadowState]:
        """
        Returns ``(response_body, shadow_state)``.

        ``response_body`` is what the attacker receives — a normal success
        envelope.  ``shadow_state`` is registered server-side and returned so
        the caller can log it / record threat intel.
        """
        token = self._mint_token(subject)
        seed = self._world_seed(token, tenant_id)

        state = ShadowState(
            session_token = token,
            tenant_id     = tenant_id,
            attack_class  = attack_class,
            world         = world,
            world_seed    = seed,
            arm           = arm,
            ip_address    = ip_address,
        )
        self._store.put(state)

        # The believable success envelope.  Mirrors a typical login response so
        # the attacker's tooling parses it as a genuine authenticated session.
        response = {
            "status":  "success",
            "token":   token,
            "user": {
                "id":       hashlib.sha256(token.encode()).hexdigest()[:24],
                "name":     display_name or "Account Holder",
                "role":     "user",
                "verified": True,
            },
            "redirect": redirect,
            "expires_in": 3600,
        }
        return response, state

    def register(
        self,
        *,
        session_token: str,
        tenant_id:    str,
        attack_class: str,
        world:        str,
        arm:          int = -1,
        ip_address:   str = "?",
    ) -> ShadowState:
        """
        Register shadow state for an ALREADY-MINTED token (e.g. the token the
        pipeline orchestrator produced).  Use this from /score so the session
        keeps a single token while still gaining a deterministic world seed and
        server-side shadow flag.
        """
        state = ShadowState(
            session_token = session_token,
            tenant_id     = tenant_id,
            attack_class  = attack_class,
            world         = world,
            world_seed    = self._world_seed(session_token, tenant_id),
            arm           = arm,
            ip_address    = ip_address,
        )
        self._store.put(state)
        return state
