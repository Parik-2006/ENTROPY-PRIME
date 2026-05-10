"""
backend/services/watchdog_service.py  —  Global Threat Intelligence Service

Cross-site threat propagation layer sitting above Stage 4's per-session
watchdog.  Responsibilities:

  1. Ingest WatchdogResults produced by stage4_watchdog.run() and decide
     whether the triggering fingerprint or IP should be flagged *globally*.
  2. Persist threat records to the shared `threat_intelligence` table (see
     database.py for the schema).
  3. Expose a fast lookup path (`is_globally_flagged`) that every /score and
     /session/verify endpoint calls BEFORE running the per-session PPO, so
     known-bad actors are blocked at the gate.
  4. Provide a cross-site broadcast hook (`broadcast_threat`) that fan-outs
     a newly confirmed threat to all active tenant notification channels.

Design notes
────────────
* The service is intentionally stateless at the class level.  All persistence
  goes through the injected `db` handle so the caller controls the session
  lifecycle (FastAPI dependency injection keeps this clean).
* Threat scoring uses additive weights rather than a boolean: a fingerprint
  that triggers PASSIVE_REAUTH twice across different tenants is less severe
  than one that triggers FORCE_LOGOUT once, but both accumulate toward the
  GLOBAL_FLAG_THRESHOLD.
* TTL-based expiry: threats older than THREAT_TTL_SECONDS are ignored for
  scoring but kept in the table for audit purposes (soft-delete via
  `expired_at`).
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ..models.contracts import WatchdogAction, WatchdogResult
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
# before a global flag is issued (prevents a single rogue tenant from poisoning
# the shared blocklist).
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
    action:           str          # human-readable worst action seen
    timestamp:        float = field(default_factory=time.time)


# ── Service ───────────────────────────────────────────────────────────────────

class WatchdogService:
    """
    Stateless cross-site threat intelligence service.

    Typical FastAPI usage::

        @app.post("/score")
        async def score(req: ScoreRequest, db: Database = Depends(get_db)):
            svc = WatchdogService(db)
            # Fast gate: block known-bad before expensive PPO
            gate = await svc.is_globally_flagged(req.fingerprint, req.ip)
            if gate.globally_flagged:
                raise HTTPException(403, detail=gate.reason)
            # … run per-session PPO …
            result = stage4_watchdog.run(latent_vector, e_rec, trust, agent)
            await svc.ingest(tenant_id, req.fingerprint, req.ip, result)
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── Public API ────────────────────────────────────────────────────────────

    async def ingest(
        self,
        tenant_id:   str,
        fingerprint: str,
        ip_address:  Optional[str],
        result:      WatchdogResult,
    ) -> ThreatIntelResult:
        """
        Record a WatchdogResult and re-evaluate the global threat state for
        this fingerprint.  If the cumulative score crosses GLOBAL_FLAG_THRESHOLD
        and MIN_TENANT_CORROBORATION is satisfied, the fingerprint is promoted
        to globally flagged and broadcast_threat() is called.

        Returns the current ThreatIntelResult for the fingerprint.
        """
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
        Fast read path.  Returns a ThreatIntelResult whose `globally_flagged`
        field indicates whether this identity should be blocked before any
        further pipeline stages run.

        Also checks `ip_address` if provided: an IP that has been associated
        with globally-flagged fingerprints in >= MIN_TENANT_CORROBORATION
        tenants is itself flagged.
        """
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
        """
        cutoff = time.time() - THREAT_TTL_SECONDS
        count  = await self._db.expire_threats_before(cutoff)
        logger.info("[TI] Expired %d stale threat records (cutoff=%.0f)", count, cutoff)
        return count

    async def get_threat_summary(self, fingerprint: str) -> ThreatIntelResult:
        """Convenience wrapper for admin/dashboard endpoints."""
        return await self._evaluate(_hash_fingerprint(fingerprint))

    # ── Internal helpers ──────────────────────────────────────────────────────

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
            else f"score={cumulative:.2f}/{GLOBAL_FLAG_THRESHOLD} tenants={tenant_count}/{MIN_TENANT_CORROBORATION}"
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
        cutoff   = time.time() - THREAT_TTL_SECONDS
        records  = await self._db.get_active_threats_by_ip(ip_address, since=cutoff)

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
            reason           = f"ip_flagged score={cumulative:.2f} tenants={tenant_count}" if flagged else "ip_below_threshold",
        )

    async def _broadcast_threat(
        self,
        intel:      ThreatIntelResult,
        ip_address: Optional[str],
        action:     WatchdogAction,
    ) -> None:
        """
        Fan-out a globally confirmed threat to all tenant notification channels.

        The Database layer owns the actual delivery mechanism (webhook queue,
        pub/sub topic, etc.).  This method builds the payload and delegates.
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


# ── Module-level helpers ───────────────────────────────────────────────────────

def _hash_fingerprint(raw: str) -> str:
    """
    Deterministic, one-way fingerprint hash.
    Using SHA-256 truncated to 64 hex chars keeps the DB column narrow while
    remaining collision-resistant for realistic fleet sizes.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()