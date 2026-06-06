"""
services/watchdog_services.py — Watchdog Service

This service has two complementary responsibilities that work in sequence on
every scored request:

  Per-session (Stage 4)
  ─────────────────────
  Wraps stage4_watchdog.run() + the session PPOAgent.  Every /score and
  /session/verify request calls verify_session() to evaluate session integrity
  from the biometric latent vector, reconstruction error, and DB-sourced trust
  score.  is_session_valid() is a convenience bool wrapper around that.

  Cross-site threat intelligence
  ──────────────────────────────
  Ingests WatchdogResults produced by Stage 4 and decides whether the
  triggering fingerprint or IP should be flagged *globally* across tenants.
  Persists threat records to the shared `threat_intelligence` table.
  Exposes is_globally_flagged() — called BEFORE the per-session PPO so
  known-bad actors are blocked at the gate without spending compute on them.
  Broadcasts newly confirmed global threats to all active tenant channels.

Typical request flow::

    svc = WatchdogService(db=db, ppo_agent=ppo)

    # 1. Gate: block known-bad actors before any PPO work
    gate = await svc.is_globally_flagged(req.fingerprint, req.ip)
    if gate.globally_flagged:
        raise HTTPException(403, detail=gate.reason)

    # 2. Per-session evaluation
    result = svc.verify_session(latent_vector, e_rec, trust_score)

    # 3. Feed result back into the cross-site layer
    await svc.ingest(tenant_id, req.fingerprint, req.ip, result)

Design notes
────────────
* The DB handle controls session lifecycle; inject via FastAPI Depends.
* Threat scoring is additive, not boolean: multiple PASSIVE_REAUTH events
  across tenants accumulate toward GLOBAL_FLAG_THRESHOLD.
* TTL-based expiry: records older than THREAT_TTL_SECONDS are ignored for
  scoring but retained for audit (soft-delete via `expired_at`).
* PyTorch inference (no_grad) is thread-safe for CPU tensors.  For GPU
  inference use one service instance per thread or add an explicit lock.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ..models.ppo import PPOAgent
from ..pipeline import stage4_watchdog as _s4
from ..pipeline.contracts import WatchdogAction, WatchdogResult
from ..database import Database, ThreatRecord

logger = logging.getLogger("entropy_prime.watchdog_service")


# ── Tunables ──────────────────────────────────────────────────────────────────

# Additive threat-score weights per action severity
_ACTION_WEIGHT: dict[WatchdogAction, float] = {
    WatchdogAction.OK:                    0.0,
    WatchdogAction.PASSIVE_REAUTH:        1.0,
    WatchdogAction.DISABLE_SENSITIVE_API: 3.0,
    WatchdogAction.FORCE_LOGOUT:          8.0,
}

# Cumulative score across tenants required to elevate to global flag
GLOBAL_FLAG_THRESHOLD: float = 10.0

# Threat records older than this are excluded from active scoring
THREAT_TTL_SECONDS: int = 60 * 60 * 24 * 7  # 7 days

# Minimum number of distinct tenants that must have reported a fingerprint
# before a global flag is issued (prevents a single rogue tenant from
# poisoning the shared blocklist).
MIN_TENANT_CORROBORATION: int = 2


# ── DTOs ─────────────────────────────────────────────────────────────────────

@dataclass
class ThreatIntelResult:
    """Returned by ingest() and is_globally_flagged()."""
    globally_flagged: bool
    fingerprint_hash: str
    cumulative_score: float
    tenant_count:     int
    first_seen_ts:    Optional[float]
    last_seen_ts:     Optional[float]
    reason:           str


@dataclass
class BroadcastPayload:
    """Emitted to every tenant notification channel on global flag."""
    fingerprint_hash: str
    ip_address:       Optional[str]
    cumulative_score: float
    tenant_count:     int
    action:           str           # human-readable worst action seen
    timestamp:        float = field(default_factory=time.time)


# ── Service ───────────────────────────────────────────────────────────────────

class WatchdogService:
    """
    Session integrity evaluator and cross-site threat intelligence service.

    Parameters
    ──────────
    db          — Database handle.  Controls session lifecycle; use FastAPI
                  Depends() for clean injection.  Required for the threat
                  intelligence methods (ingest / is_globally_flagged /
                  expire_stale_threats / get_threat_summary).  May be None
                  in unit tests that only exercise the session-evaluation path.
    ppo_agent   — Stage 4 PPOAgent.  Defaults to a freshly initialised
                  (untrained) agent when not provided.
    state_dim   — PPO state dimension (must match checkpoint if loading one).
    action_dim  — PPO action dimension (must match checkpoint if loading one).
    """

    def __init__(
        self,
        db:         Optional[Database]  = None,
        ppo_agent:  Optional[PPOAgent]  = None,
        state_dim:  int = 10,
        action_dim: int = 3,
    ) -> None:
        self._db  = db
        self._ppo = ppo_agent or PPOAgent(state_dim=state_dim, action_dim=action_dim)

    # ── Per-session evaluation (Stage 4) ──────────────────────────────────────

    def verify_session(
        self,
        latent_vector: list[float],
        e_rec:         float,
        trust_score:   float,
    ) -> WatchdogResult:
        """
        Evaluate session integrity via Stage 4.

        Parameters
        ──────────
        latent_vector : biometric embedding (first 8 dims used by Stage 4).
        e_rec         : reconstruction error from the Stage 1 autoencoder.
        trust_score   : DB-sourced trust score in [0, 1].
                        NEVER accept this value from the client.

        Returns
        ───────
        WatchdogResult with action (OK / PASSIVE_REAUTH /
        DISABLE_SENSITIVE_API / FORCE_LOGOUT) and supporting fields.
        Never raises.
        """
        return _s4.run(latent_vector, e_rec, trust_score, self._ppo)

    def is_session_valid(
        self,
        latent_vector: list[float],
        e_rec:         float,
        trust_score:   float,
    ) -> bool:
        """
        Convenience wrapper: returns False on FORCE_LOGOUT, True otherwise.

        Use verify_session() when you need the full WatchdogResult for
        downstream logging or ingest(); use this for a simple gate check.
        """
        result = self.verify_session(latent_vector, e_rec, trust_score)
        return result.action != WatchdogAction.FORCE_LOGOUT

    # ── Cross-site threat intelligence ────────────────────────────────────────

    async def ingest(
        self,
        tenant_id:   str,
        fingerprint: str,
        ip_address:  Optional[str],
        result:      WatchdogResult,
    ) -> ThreatIntelResult:
        """
        Record a WatchdogResult and re-evaluate the global threat state for
        this fingerprint.

        If the cumulative score crosses GLOBAL_FLAG_THRESHOLD and
        MIN_TENANT_CORROBORATION distinct tenants have reported the same
        fingerprint, the fingerprint is promoted to globally flagged and
        _broadcast_threat() is called to fan-out to all tenant channels.

        Returns the current ThreatIntelResult for the fingerprint.

        Raises RuntimeError if no Database was injected.
        """
        self._require_db("ingest")
        fp_hash = _hash_fingerprint(fingerprint)
        weight  = _ACTION_WEIGHT.get(result.action, 0.0)

        if weight > 0.0:
            await self._db.upsert_threat(
                ThreatRecord(
                    fingerprint_hash = fp_hash,
                    ip_address       = ip_address,
                    tenant_id        = tenant_id,
                    action           = result.action.value,
                    weight           = weight,
                    e_rec            = result.e_rec,
                    trust_score      = result.trust_score,
                    reason           = result.reason,
                    ts               = time.time(),
                )
            )
            logger.info(
                "[TI] tenant=%s fp=%.8s action=%s weight=%.1f",
                tenant_id, fp_hash, result.action.value, weight,
            )

        intel = await self._evaluate(fp_hash)

        if intel.globally_flagged:
            await self._broadcast_threat(intel, ip_address, result.action)

        return intel

    async def is_globally_flagged(
        self,
        fingerprint: str,
        ip_address:  Optional[str] = None,
    ) -> ThreatIntelResult:
        """
        Fast read path: returns a ThreatIntelResult whose `globally_flagged`
        field indicates whether this identity should be blocked before any
        further pipeline stages run.

        Also checks `ip_address` if provided: an IP associated with
        globally-flagged fingerprints across >= MIN_TENANT_CORROBORATION
        tenants is itself flagged.

        Raises RuntimeError if no Database was injected.
        """
        self._require_db("is_globally_flagged")
        fp_hash = _hash_fingerprint(fingerprint)
        intel   = await self._evaluate(fp_hash)

        if not intel.globally_flagged and ip_address:
            ip_intel = await self._evaluate_ip(ip_address)
            if ip_intel.globally_flagged:
                return ip_intel

        return intel

    async def expire_stale_threats(self) -> int:
        """
        Soft-delete threat records older than THREAT_TTL_SECONDS.
        Intended to be called from a periodic background task.
        Returns the number of records expired.

        Raises RuntimeError if no Database was injected.
        """
        self._require_db("expire_stale_threats")
        cutoff = time.time() - THREAT_TTL_SECONDS
        count  = await self._db.expire_threats_before(cutoff)
        logger.info("[TI] Expired %d stale threat records (cutoff=%.0f)", count, cutoff)
        return count

    async def get_threat_summary(self, fingerprint: str) -> ThreatIntelResult:
        """
        Convenience wrapper for admin / dashboard endpoints.

        Raises RuntimeError if no Database was injected.
        """
        self._require_db("get_threat_summary")
        return await self._evaluate(_hash_fingerprint(fingerprint))

    # ── Agent lifecycle ───────────────────────────────────────────────────────

    @property
    def ppo_agent(self) -> PPOAgent:
        """Direct access to the managed PPO agent (read-only intent)."""
        return self._ppo

    def load_checkpoint(self, path: str) -> None:
        """Hot-swap the PPO agent from a checkpoint file."""
        self._ppo.load_checkpoint(path)
        logger.info("[WatchdogService] PPO checkpoint loaded from %s", path)

    def save_checkpoint(self, path: str) -> None:
        """Persist the current PPO agent weights."""
        self._ppo.save_checkpoint(path)
        logger.info("[WatchdogService] PPO checkpoint saved to %s", path)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _require_db(self, method: str) -> None:
        """Raise a clear error rather than an AttributeError on None._db."""
        if self._db is None:
            raise RuntimeError(
                f"WatchdogService.{method}() requires a Database instance. "
                "Inject one via __init__(db=...)."
            )

    async def _evaluate(self, fp_hash: str) -> ThreatIntelResult:
        """
        Aggregate all active ThreatRecords for fp_hash and decide whether the
        global-flag threshold has been crossed.
        """
        cutoff  = time.time() - THREAT_TTL_SECONDS
        records = await self._db.get_active_threats(fp_hash, since=cutoff)

        if not records:
            return ThreatIntelResult(
                globally_flagged = False,
                fingerprint_hash = fp_hash,
                cumulative_score = 0.0,
                tenant_count     = 0,
                first_seen_ts    = None,
                last_seen_ts     = None,
                reason           = "no_threat_records",
            )

        cumulative   = sum(r.weight for r in records)
        tenant_set   = {r.tenant_id for r in records}
        tenant_count = len(tenant_set)
        first_seen   = min(r.ts for r in records)
        last_seen    = max(r.ts for r in records)

        flagged = (
            cumulative   >= GLOBAL_FLAG_THRESHOLD
            and tenant_count >= MIN_TENANT_CORROBORATION
        )

        reason = (
            f"cumulative_score={cumulative:.2f} tenants={tenant_count}"
            if flagged
            else (
                f"score={cumulative:.2f}/{GLOBAL_FLAG_THRESHOLD} "
                f"tenants={tenant_count}/{MIN_TENANT_CORROBORATION}"
            )
        )

        return ThreatIntelResult(
            globally_flagged = flagged,
            fingerprint_hash = fp_hash,
            cumulative_score = cumulative,
            tenant_count     = tenant_count,
            first_seen_ts    = first_seen,
            last_seen_ts     = last_seen,
            reason           = reason,
        )

    async def _evaluate_ip(self, ip_address: str) -> ThreatIntelResult:
        """Check whether an IP is associated with globally-flagged fingerprints."""
        cutoff  = time.time() - THREAT_TTL_SECONDS
        records = await self._db.get_active_threats_by_ip(ip_address, since=cutoff)

        if not records:
            return ThreatIntelResult(
                globally_flagged = False,
                fingerprint_hash = f"ip:{ip_address}",
                cumulative_score = 0.0,
                tenant_count     = 0,
                first_seen_ts    = None,
                last_seen_ts     = None,
                reason           = "ip_no_records",
            )

        cumulative   = sum(r.weight for r in records)
        tenant_count = len({r.tenant_id for r in records})
        flagged      = (
            cumulative   >= GLOBAL_FLAG_THRESHOLD
            and tenant_count >= MIN_TENANT_CORROBORATION
        )

        return ThreatIntelResult(
            globally_flagged = flagged,
            fingerprint_hash = f"ip:{ip_address}",
            cumulative_score = cumulative,
            tenant_count     = tenant_count,
            first_seen_ts    = min(r.ts for r in records),
            last_seen_ts     = max(r.ts for r in records),
            reason           = (
                f"ip_flagged score={cumulative:.2f} tenants={tenant_count}"
                if flagged
                else "ip_below_threshold"
            ),
        )

    async def _broadcast_threat(
        self,
        intel:      ThreatIntelResult,
        ip_address: Optional[str],
        action:     WatchdogAction,
    ) -> None:
        """
        Fan-out a globally confirmed threat to all tenant notification channels.

        The Database layer owns the delivery mechanism (webhook queue, pub/sub
        topic, etc.).  This method builds the payload and delegates.  Broadcast
        failures are logged but never propagate to the caller.
        """
        payload = BroadcastPayload(
            fingerprint_hash = intel.fingerprint_hash,
            ip_address       = ip_address,
            cumulative_score = intel.cumulative_score,
            tenant_count     = intel.tenant_count,
            action           = action.value,
        )
        try:
            await self._db.broadcast_global_threat(payload)
            logger.warning(
                "[TI] GLOBAL THREAT BROADCAST fp=%.8s score=%.2f tenants=%d",
                intel.fingerprint_hash,
                intel.cumulative_score,
                intel.tenant_count,
            )
        except Exception as exc:
            # Never let broadcast failure block the caller
            logger.error("[TI] Broadcast failed: %s", exc)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _hash_fingerprint(raw: str) -> str:
    """
    Deterministic, one-way fingerprint hash.
    SHA-256 truncated to 64 hex chars: narrow DB column, collision-resistant
    for realistic fleet sizes.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()