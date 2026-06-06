"""
backend/services/governor_service.py — Governor Service (Multi-Tenant Orchestrator)
====================================================================================

Changes from v3.1.0
--------------------
• RedisAsyncPolicyStore — async-native Redis policy store using aioredis.
  Keys: ``governor:policy:{site_id}``  (no TTL; admin-managed lifecycle).
• get_governor_service() factory — auto-selects Redis or in-memory store
  based on Redis availability, exactly like the profile store factory.
• HoneypotChallengeStore — lightweight Redis store for ephemeral challenge
  state (``honeypot:challenge:{challenge_id}``, TTL = challenge expiry).
• All pre-v3.1.0 classes (InMemoryPolicyStore, RedisPolicyStore (sync),
  GovernorService) are preserved and signature-compatible.

No changes to GovernorService.evaluate() logic or the DQN/PPO inference path.
"""
from __future__ import annotations

import abc
import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from ..models.ppo_agents import PPOPolicyAgent, RolloutBuffer
from ..models import stage3_governor as _s3
from ..pipeline.contracts import (
    BiometricResult,
    GovernorAction,
    GovernorResult,
    SecurityPreset,
    TenantPolicy,
)

logger = logging.getLogger("entropy_prime.governor_service")

# Redis key namespaces
_POLICY_KEY_PREFIX    = "governor:policy"
_CHALLENGE_KEY_PREFIX = "honeypot:challenge"


# ── Policy Store abstraction ──────────────────────────────────────────────────

class AbstractPolicyStore(abc.ABC):
    @abc.abstractmethod
    def get(self, site_id: str) -> Optional[TenantPolicy]: ...
    @abc.abstractmethod
    def save(self, policy: TenantPolicy) -> None: ...
    @abc.abstractmethod
    def delete(self, site_id: str) -> bool: ...
    @abc.abstractmethod
    def list_site_ids(self) -> list[str]: ...


# ── In-memory store (tests / no-Redis fallback) ───────────────────────────────

class InMemoryPolicyStore(AbstractPolicyStore):
    """Thread-safe dict-backed store."""

    def __init__(self) -> None:
        self._store: Dict[str, TenantPolicy] = {}
        self._lock  = threading.Lock()

    def get(self, site_id: str) -> Optional[TenantPolicy]:
        with self._lock:
            return self._store.get(site_id)

    def save(self, policy: TenantPolicy) -> None:
        with self._lock:
            self._store[policy.site_id] = policy
        logger.debug("[PolicyStore:mem] saved site=%r", policy.site_id)

    def delete(self, site_id: str) -> bool:
        with self._lock:
            existed = site_id in self._store
            self._store.pop(site_id, None)
        return existed

    def list_site_ids(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())


# ── Sync Redis store (legacy / preserved from v3.1.0) ────────────────────────

class RedisPolicyStore(AbstractPolicyStore):
    """
    Synchronous redis-py backed store (preserved for backwards compatibility).
    For new code prefer RedisAsyncPolicyStore with the aioredis client.
    """

    _KEY_PREFIX = _POLICY_KEY_PREFIX

    def __init__(self, redis_client, ttl_seconds: int = 0) -> None:
        self._r   = redis_client
        self._ttl = ttl_seconds

    def _key(self, site_id: str) -> str:
        return f"{self._KEY_PREFIX}:{site_id}"

    def _serialize(self, policy: TenantPolicy) -> str:
        return json.dumps({
            "site_id":              policy.site_id,
            "risk_tolerance":       policy.risk_tolerance,
            "min_action":           policy.min_action.value,
            "max_preset":           policy.max_preset.value,
            "challenge_on_suspect": policy.challenge_on_suspect,
            "block_bots_hard":      policy.block_bots_hard,
        })

    def _deserialize(self, raw: str) -> Optional[TenantPolicy]:
        try:
            d = json.loads(raw)
            return TenantPolicy(
                site_id              = d["site_id"],
                risk_tolerance       = d["risk_tolerance"],
                min_action           = GovernorAction(d["min_action"]),
                max_preset           = SecurityPreset(d["max_preset"]),
                challenge_on_suspect = d["challenge_on_suspect"],
                block_bots_hard      = d["block_bots_hard"],
            )
        except Exception as exc:
            logger.error("[PolicyStore:redis] deserialize failed: %s", exc)
            return None

    def get(self, site_id: str) -> Optional[TenantPolicy]:
        raw = self._r.get(self._key(site_id))
        return self._deserialize(raw) if raw else None

    def save(self, policy: TenantPolicy) -> None:
        data = self._serialize(policy)
        if self._ttl:
            self._r.setex(self._key(policy.site_id), self._ttl, data)
        else:
            self._r.set(self._key(policy.site_id), data)

    def delete(self, site_id: str) -> bool:
        return bool(self._r.delete(self._key(site_id)))

    def list_site_ids(self) -> list[str]:
        prefix = f"{self._KEY_PREFIX}:"
        return [
            k.decode().removeprefix(prefix)
            for k in self._r.keys(f"{prefix}*")
        ]


# ── Async Redis store (preferred; uses aioredis client from redis_client.py) ──

class RedisAsyncPolicyStore(AbstractPolicyStore):
    """
    Async-native policy store backed by the shared aioredis connection pool.

    Keys: ``governor:policy:{site_id}``  (no TTL by default; policies are
    created/deleted by operators and should persist indefinitely).

    The sync methods delegate to async variants via asyncio.  Callers inside
    async request handlers should use the aget/asave/adelete variants directly.
    """

    def __init__(self, redis_client, ttl_seconds: int = 0) -> None:
        self._r   = redis_client
        self._ttl = ttl_seconds

    def _key(self, site_id: str) -> str:
        return f"{_POLICY_KEY_PREFIX}:{site_id}"

    def _serialize(self, policy: TenantPolicy) -> str:
        return json.dumps({
            "site_id":              policy.site_id,
            "risk_tolerance":       policy.risk_tolerance,
            "min_action":           policy.min_action.value,
            "max_preset":           policy.max_preset.value,
            "challenge_on_suspect": policy.challenge_on_suspect,
            "block_bots_hard":      policy.block_bots_hard,
        })

    def _deserialize(self, raw: str) -> Optional[TenantPolicy]:
        try:
            d = json.loads(raw)
            return TenantPolicy(
                site_id              = d["site_id"],
                risk_tolerance       = d["risk_tolerance"],
                min_action           = GovernorAction(d["min_action"]),
                max_preset           = SecurityPreset(d["max_preset"]),
                challenge_on_suspect = d["challenge_on_suspect"],
                block_bots_hard      = d["block_bots_hard"],
            )
        except Exception as exc:
            logger.error("[PolicyStore:redis-async] deserialize failed: %s", exc)
            return None

    # ── Async API ─────────────────────────────────────────────────────────

    async def aget(self, site_id: str) -> Optional[TenantPolicy]:
        try:
            raw = await self._r.get(self._key(site_id))
            return self._deserialize(raw) if raw else None
        except Exception as exc:
            logger.error("[PolicyStore:redis-async] aget failed: %s", exc)
            return None

    async def asave(self, policy: TenantPolicy) -> None:
        try:
            data = self._serialize(policy)
            if self._ttl:
                await self._r.setex(self._key(policy.site_id), self._ttl, data)
            else:
                await self._r.set(self._key(policy.site_id), data)
            logger.debug("[PolicyStore:redis-async] saved site=%r", policy.site_id)
        except Exception as exc:
            logger.error("[PolicyStore:redis-async] asave failed: %s", exc)

    async def adelete(self, site_id: str) -> bool:
        try:
            n = await self._r.delete(self._key(site_id))
            return bool(n)
        except Exception as exc:
            logger.error("[PolicyStore:redis-async] adelete failed: %s", exc)
            return False

    async def alist_site_ids(self) -> list[str]:
        try:
            prefix = f"{_POLICY_KEY_PREFIX}:"
            keys = await self._r.keys(f"{prefix}*")
            return [k.removeprefix(prefix) for k in keys]
        except Exception as exc:
            logger.error("[PolicyStore:redis-async] alist failed: %s", exc)
            return []

    # ── Sync shims for AbstractPolicyStore compatibility ──────────────────

    def get(self, site_id: str) -> Optional[TenantPolicy]:
        import asyncio
        try:
            return asyncio.get_event_loop().run_until_complete(self.aget(site_id))
        except Exception:
            return None

    def save(self, policy: TenantPolicy) -> None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.asave(policy))
            else:
                loop.run_until_complete(self.asave(policy))
        except Exception as exc:
            logger.error("[PolicyStore:redis-async] save (sync shim) failed: %s", exc)

    def delete(self, site_id: str) -> bool:
        import asyncio
        try:
            return asyncio.get_event_loop().run_until_complete(self.adelete(site_id))
        except Exception:
            return False

    def list_site_ids(self) -> list[str]:
        import asyncio
        try:
            return asyncio.get_event_loop().run_until_complete(self.alist_site_ids())
        except Exception:
            return []


# ── Honeypot challenge store (Redis only, ephemeral) ─────────────────────────

class HoneypotChallengeStore:
    """
    Short-lived Redis store for honeypot challenge state.

    Keys: ``honeypot:challenge:{challenge_id}``
    TTL:  Challenge expiry time (typically 120 seconds).

    Stores the signed challenge payload JSON so the /honeypot/trigger
    handler can validate inbound reports without a MongoDB round-trip.

    When Redis is unavailable the store silently no-ops — the trigger
    handler already validates the HMAC signature directly, so the
    redundant DB lookup is just an optimisation.
    """

    def __init__(self, redis_client=None) -> None:
        self._r = redis_client

    async def save(self, challenge_id: str, payload: dict, expires_at: float) -> None:
        if self._r is None:
            return
        ttl = max(1, int(expires_at - time.time()) + 5)  # +5s grace
        try:
            await self._r.setex(
                f"{_CHALLENGE_KEY_PREFIX}:{challenge_id}",
                ttl,
                json.dumps(payload),
            )
        except Exception as exc:
            logger.debug("[ChallengeStore] save failed (non-critical): %s", exc)

    async def get(self, challenge_id: str) -> Optional[dict]:
        if self._r is None:
            return None
        try:
            raw = await self._r.get(f"{_CHALLENGE_KEY_PREFIX}:{challenge_id}")
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("[ChallengeStore] get failed (non-critical): %s", exc)
            return None

    async def delete(self, challenge_id: str) -> None:
        if self._r is None:
            return
        try:
            await self._r.delete(f"{_CHALLENGE_KEY_PREFIX}:{challenge_id}")
        except Exception:
            pass


# ── Factory ───────────────────────────────────────────────────────────────────

def get_governor_service(
    dqn_agent=None,
    ppo_agent=None,
    redis_client=None,
) -> "GovernorService":
    """
    Build a GovernorService with the best available policy store.

    When ``redis_client`` is set, uses RedisAsyncPolicyStore so policy
    lookups survive process restarts and are shared across workers.
    Otherwise falls back to InMemoryPolicyStore.
    """
    if redis_client is not None:
        store = RedisAsyncPolicyStore(redis_client)
        logger.info("[GovernorService] Using RedisAsyncPolicyStore (governor:policy:*)")
    else:
        store = InMemoryPolicyStore()
        logger.info("[GovernorService] Using InMemoryPolicyStore")
    return GovernorService(
        dqn_agent=dqn_agent,
        ppo_agent=ppo_agent,
        policy_store=store,
    )


# ── Stub DQN ─────────────────────────────────────────────────────────────────

class _StubDQN:
    def select_action(self, state) -> int:
        return 1  # STANDARD fallback


# ── Main service (unchanged from v3.1.0) ─────────────────────────────────────

class GovernorService:
    """
    Stateless orchestrator.  All v3.1.0 methods are signature-compatible.

    Parameters
    ----------
    dqn_agent:    DQN agent with .select_action(np.ndarray) → int
    ppo_agent:    PPOPolicyAgent instance
    policy_store: Any AbstractPolicyStore implementation
    """

    def __init__(
        self,
        dqn_agent=None,
        ppo_agent=None,
        policy_store: Optional[AbstractPolicyStore] = None,
        ppo_state_dim:  int = 5,
        ppo_action_dim: int = 4,
    ) -> None:
        self._dqn   = dqn_agent    or _StubDQN()
        self._ppo   = ppo_agent    or PPOPolicyAgent(
            state_dim=ppo_state_dim, action_dim=ppo_action_dim
        )
        self._store = policy_store or InMemoryPolicyStore()

    # ── Evaluation ────────────────────────────────────────────────────────────

    def evaluate(self, bio: BiometricResult, site_id: str) -> GovernorResult:
        policy = self._store.get(site_id)
        if policy is None:
            logger.debug("[GovService] No policy for site=%r — using defaults", site_id)
        result = _s3.run(bio=bio, dqn_agent=self._dqn, ppo_agent=self._ppo, policy=policy)
        logger.info(
            "[GovService] site=%r verdict=%s preset=%s action=%s conf=%s fallback=%s",
            site_id, bio.verdict.value, result.preset.value,
            result.governor_action.value if result.governor_action else "n/a",
            result.confidence.value, result.fallback,
        )
        return result

    # ── Policy CRUD ───────────────────────────────────────────────────────────

    def get_policy(self, site_id: str) -> Optional[TenantPolicy]:
        return self._store.get(site_id)

    def create_policy(self, policy: TenantPolicy) -> TenantPolicy:
        if self._store.get(policy.site_id) is not None:
            raise ValueError(
                f"Policy for site_id={policy.site_id!r} already exists. "
                "Use update_policy() to modify it."
            )
        self._store.save(policy)
        logger.info("[GovService] Policy created for site=%r", policy.site_id)
        return policy

    def update_policy(self, policy: TenantPolicy) -> TenantPolicy:
        if self._store.get(policy.site_id) is None:
            raise KeyError(
                f"No policy for site_id={policy.site_id!r}. "
                "Use create_policy() first."
            )
        self._store.save(policy)
        logger.info("[GovService] Policy updated for site=%r", policy.site_id)
        return policy

    def upsert_policy(self, policy: TenantPolicy) -> TenantPolicy:
        self._store.save(policy)
        return policy

    def delete_policy(self, site_id: str) -> bool:
        removed = self._store.delete(site_id)
        if removed:
            logger.info("[GovService] Policy deleted for site=%r", site_id)
        return removed

    def list_policies(self) -> list[str]:
        return self._store.list_site_ids()

    # ── Agent management ──────────────────────────────────────────────────────

    def load_ppo_checkpoint(self, path: "str | Path") -> None:
        self._ppo = PPOPolicyAgent.load(path)
        logger.info("[GovService] PPO checkpoint loaded from %s", path)

    def save_ppo_checkpoint(self, path: "str | Path") -> None:
        self._ppo.save(path)

    def get_rollout_buffer(self) -> RolloutBuffer:
        return RolloutBuffer()

    def train_ppo_step(self, buffer: RolloutBuffer, last_value: float = 0.0) -> dict:
        return self._ppo.update(buffer, last_value=last_value)
