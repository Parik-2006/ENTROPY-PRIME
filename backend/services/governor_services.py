"""
services/governor_service.py  —  Governor Service (Multi-Tenant Orchestrator)

Single entry point for Stage 3 in the multi-tenant pipeline.  Callers never
touch the DQN, PPO, or policy store directly.

Responsibilities
────────────────
1. Load or create the per-tenant TenantPolicy from the policy store.
2. Run stage3_governor.run() with both agents and the tenant policy.
3. Expose policy CRUD operations (create / read / update / delete).
4. Expose agent checkpoint management (load / save).

Thread-safety
─────────────
GovernorService is safe to share across threads.  The policy store handles its
own locking.  PyTorch inference (no_grad) is thread-safe for CPU tensors.
For GPU inference, instantiate one GovernorService per thread or use a lock.

Dependency injection
────────────────────
All external dependencies are injected through __init__ so the service is
fully testable without touching the filesystem or a real database.

Example (FastAPI)::

    dqn   = load_dqn_agent("checkpoints/dqn.pt")
    ppo   = PPOPolicyAgent.load("checkpoints/ppo_governor.pt")
    store = RedisPolicyStore(redis_client)
    gov   = GovernorService(dqn_agent=dqn, ppo_agent=ppo, policy_store=store)

    @router.post("/governor/evaluate")
    async def evaluate(body: GovernorEvaluateRequest):
        bio    = _build_bio_result(body)          # map Pydantic → dataclass
        result = await asyncio.to_thread(gov.evaluate, bio=bio, site_id=body.site_id)
        return GovernorEvaluateResponse.from_result(result)
"""
from __future__ import annotations

import abc
import json
import logging
import threading
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


# ── Policy Store abstraction ──────────────────────────────────────────────────

class AbstractPolicyStore(abc.ABC):
    """All policy stores must satisfy this interface."""

    @abc.abstractmethod
    def get(self, site_id: str) -> Optional[TenantPolicy]:
        """Return the stored policy, or None if the tenant has no custom policy."""

    @abc.abstractmethod
    def save(self, policy: TenantPolicy) -> None:
        """Persist (create or overwrite) a tenant policy."""

    @abc.abstractmethod
    def delete(self, site_id: str) -> bool:
        """Remove a policy.  Returns True if it existed."""

    @abc.abstractmethod
    def list_site_ids(self) -> list[str]:
        """Return all site_ids with stored policies."""


class InMemoryPolicyStore(AbstractPolicyStore):
    """Thread-safe dict-backed store (tests / single-process deployments)."""

    def __init__(self) -> None:
        self._store: Dict[str, TenantPolicy] = {}
        self._lock  = threading.Lock()

    def get(self, site_id: str) -> Optional[TenantPolicy]:
        with self._lock:
            return self._store.get(site_id)

    def save(self, policy: TenantPolicy) -> None:
        with self._lock:
            self._store[policy.site_id] = policy
        logger.debug("[PolicyStore] saved site=%r", policy.site_id)

    def delete(self, site_id: str) -> bool:
        with self._lock:
            existed = site_id in self._store
            self._store.pop(site_id, None)
        return existed

    def list_site_ids(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())


class RedisPolicyStore(AbstractPolicyStore):
    """
    Redis-backed store.  Policies are stored as JSON under:
        ``governor:policy:{site_id}``

    Requires redis-py:  pip install redis

    Usage::

        store = RedisPolicyStore(Redis.from_url("redis://localhost:6379/0"))
    """

    _KEY_PREFIX = "governor:policy"

    def __init__(self, redis_client, ttl_seconds: int = 0) -> None:
        """
        ttl_seconds — 0 = no expiry (recommended; policies are admin-managed).
        """
        self._r   = redis_client
        self._ttl = ttl_seconds

    def _key(self, site_id: str) -> str:
        return f"{self._KEY_PREFIX}:{site_id}"

    def get(self, site_id: str) -> Optional[TenantPolicy]:
        raw = self._r.get(self._key(site_id))
        if raw is None:
            return None
        data = json.loads(raw)
        return TenantPolicy(
            site_id              = data["site_id"],
            risk_tolerance       = data["risk_tolerance"],
            min_action           = GovernorAction(data["min_action"]),
            max_preset           = SecurityPreset(data["max_preset"]),
            challenge_on_suspect = data["challenge_on_suspect"],
            block_bots_hard      = data["block_bots_hard"],
        )

    def save(self, policy: TenantPolicy) -> None:
        data = {
            "site_id":              policy.site_id,
            "risk_tolerance":       policy.risk_tolerance,
            "min_action":           policy.min_action.value,
            "max_preset":           policy.max_preset.value,
            "challenge_on_suspect": policy.challenge_on_suspect,
            "block_bots_hard":      policy.block_bots_hard,
        }
        if self._ttl:
            self._r.setex(self._key(policy.site_id), self._ttl, json.dumps(data))
        else:
            self._r.set(self._key(policy.site_id), json.dumps(data))

    def delete(self, site_id: str) -> bool:
        return bool(self._r.delete(self._key(site_id)))

    def list_site_ids(self) -> list[str]:
        prefix = f"{self._KEY_PREFIX}:"
        return [
            k.decode().removeprefix(prefix)
            for k in self._r.keys(f"{prefix}*")
        ]


# ── Stub DQN (used when no real DQN is available) ─────────────────────────────

class _StubDQN:
    """Fallback agent that always returns STANDARD (action=1)."""
    def select_action(self, state) -> int:   # noqa: ARG002
        return 1


# ── Main service ──────────────────────────────────────────────────────────────

class GovernorService:
    """
    Stateless orchestrator; all mutable state lives in the injected stores.

    Parameters
    ──────────
    dqn_agent     — DQN agent (any object with .select_action(np.ndarray) → int).
                    Defaults to _StubDQN if not provided.
    ppo_agent     — PPOPolicyAgent instance.
                    Defaults to a freshly initialised (untrained) agent.
    policy_store  — AbstractPolicyStore implementation.
                    Defaults to InMemoryPolicyStore.
    ppo_state_dim — state dimension for PPO (must match checkpoint if loading one).
    """

    def __init__(
        self,
        dqn_agent:    Optional[object]             = None,
        ppo_agent:    Optional[PPOPolicyAgent]      = None,
        policy_store: Optional[AbstractPolicyStore] = None,
        ppo_state_dim: int = 5,
        ppo_action_dim: int = 4,
    ) -> None:
        self._dqn    = dqn_agent    or _StubDQN()
        self._ppo    = ppo_agent    or PPOPolicyAgent(
            state_dim=ppo_state_dim, action_dim=ppo_action_dim
        )
        self._store  = policy_store or InMemoryPolicyStore()

    # ── Evaluation ────────────────────────────────────────────────────────────

    def evaluate(self, bio: BiometricResult, site_id: str) -> GovernorResult:
        """
        Run Stage 3 for the given biometric result under the tenant's policy.

        Parameters
        ──────────
        bio      — output of Stage 1 (BiometricResult).
        site_id  — tenant identifier; used to load the TenantPolicy.

        Returns
        ───────
        GovernorResult with both preset (DQN) and governor_action (PPO) set.
        Never raises.
        """
        policy = self._store.get(site_id)
        if policy is None:
            logger.debug("[GovService] No policy for site=%r — using defaults", site_id)

        result = _s3.run(
            bio       = bio,
            dqn_agent = self._dqn,
            ppo_agent = self._ppo,
            policy    = policy,    # None → stage3 uses TenantPolicy defaults
        )

        logger.info(
            "[GovService] site=%r verdict=%s preset=%s action=%s conf=%s fallback=%s",
            site_id,
            bio.verdict.value,
            result.preset.value,
            result.governor_action.value if result.governor_action else "n/a",
            result.confidence.value,
            result.fallback,
        )
        return result

    # ── Policy CRUD ───────────────────────────────────────────────────────────

    def get_policy(self, site_id: str) -> Optional[TenantPolicy]:
        """Return the stored policy, or None if the tenant has no custom policy."""
        return self._store.get(site_id)

    def create_policy(self, policy: TenantPolicy) -> TenantPolicy:
        """
        Store a new tenant policy.

        Raises ValueError if a policy already exists for this site_id.
        Use update_policy() to modify an existing one.
        """
        if self._store.get(policy.site_id) is not None:
            raise ValueError(
                f"Policy for site_id={policy.site_id!r} already exists. "
                f"Use update_policy() to modify it."
            )
        self._store.save(policy)
        logger.info("[GovService] Policy created for site=%r", policy.site_id)
        return policy

    def update_policy(self, policy: TenantPolicy) -> TenantPolicy:
        """
        Replace the stored policy for a tenant.

        Raises KeyError if no policy exists yet (use create_policy() first).
        """
        if self._store.get(policy.site_id) is None:
            raise KeyError(
                f"No policy for site_id={policy.site_id!r}. "
                f"Use create_policy() to create one."
            )
        self._store.save(policy)
        logger.info("[GovService] Policy updated for site=%r", policy.site_id)
        return policy

    def upsert_policy(self, policy: TenantPolicy) -> TenantPolicy:
        """Create or replace a tenant policy without checking existence first."""
        self._store.save(policy)
        return policy

    def delete_policy(self, site_id: str) -> bool:
        """
        Remove a tenant policy.  Returns True if it existed.

        After deletion, evaluate() will use default policy parameters for
        this site_id until a new policy is created.
        """
        removed = self._store.delete(site_id)
        if removed:
            logger.info("[GovService] Policy deleted for site=%r", site_id)
        return removed

    def list_policies(self) -> list[str]:
        """Return all site_ids that have a stored policy."""
        return self._store.list_site_ids()

    # ── Agent management ──────────────────────────────────────────────────────

    def load_ppo_checkpoint(self, path: str | Path) -> None:
        """Hot-swap the PPO agent from a checkpoint file."""
        self._ppo = PPOPolicyAgent.load(path)
        logger.info("[GovService] PPO checkpoint loaded from %s", path)

    def save_ppo_checkpoint(self, path: str | Path) -> None:
        """Persist the current PPO agent weights."""
        self._ppo.save(path)

    def get_rollout_buffer(self) -> RolloutBuffer:
        """Return a fresh RolloutBuffer for use by the offline trainer."""
        return RolloutBuffer()

    def train_ppo_step(
        self,
        buffer:     RolloutBuffer,
        last_value: float = 0.0,
    ) -> dict:
        """
        Run one PPO update from a filled rollout buffer.

        Returns a dict of loss metrics (policy_loss, value_loss, entropy,
        total_loss) for logging / early stopping.
        """
        return self._ppo.update(buffer, last_value=last_value)