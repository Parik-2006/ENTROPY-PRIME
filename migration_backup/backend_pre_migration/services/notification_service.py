"""
backend/services/notification_service.py — Multi-Channel Notification Router
=============================================================================
Routes security alerts from the Entropy Prime pipeline to outgoing channels:
  • Webhooks (via webhooks.dispatcher)
  • Internal event log (queryable via API)
  • Console / structured logging

Design Principles
-----------------
  - All public methods are async-safe and non-blocking.
  - Callers pass raw pipeline data; the service decides severity and routing.
  - Notification records are stored in a bounded in-memory log (queryable
    by customer_id, event type, severity, and time range).
  - Future: swap _emit_webhook → send to message queue (SQS, Redis Streams).

Severity Levels
---------------
  INFO     — informational, no action required (e.g., reauth recommended)
  WARNING  — moderate risk, soft intervention (trust degraded, drift spike)
  CRITICAL — high risk, hard intervention (force logout, confirmed bot)
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.webhooks import (
    dispatcher,
    emit_anomaly,
    emit_bot_detected,
    emit_force_logout,
    emit_reauth_required,
    emit_trust_degraded,
    WebhookEvent,
)

logger = logging.getLogger("ep.notifications")

MAX_LOG_SIZE = 10_000   # max in-memory notification records


# ── Severity ──────────────────────────────────────────────────────────────────
class Severity(str, Enum):
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


# ── Notification Record ───────────────────────────────────────────────────────
@dataclass
class NotificationRecord:
    id:          str
    event_type:  str
    severity:    Severity
    user_id:     str
    session_id:  str
    data:        dict[str, Any]
    created_at:  str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    customer_id: str          = ""
    delivered:   bool         = False   # True once at least one channel succeeded

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "event_type":  self.event_type,
            "severity":    self.severity.value,
            "user_id":     self.user_id,
            "session_id":  self.session_id,
            "customer_id": self.customer_id,
            "data":        self.data,
            "created_at":  self.created_at,
            "delivered":   self.delivered,
        }


# ── Threshold Configuration ───────────────────────────────────────────────────
@dataclass
class AlertThresholds:
    """
    Per-customer (or global-default) thresholds for triggering notifications.
    Override via customer config stored in DB in production.
    """
    trust_degraded_below:  float = 0.50   # emit ep.trust.degraded when trust < this
    anomaly_e_rec_above:   float = 0.18   # emit ep.anomaly.detected when E_rec > this
    anomaly_drift_above:   float = 3.0    # emit ep.anomaly.detected when drift > this
    bot_theta_below:       float = 0.10   # emit ep.bot.shadow_routed when θ < this

    @classmethod
    def default(cls) -> "AlertThresholds":
        return cls()


# ── Notification Service ──────────────────────────────────────────────────────
class NotificationService:
    """
    Central notification bus.

    Usage
    -----
    Call the appropriate `notify_*` method from pipeline handlers.
    All webhook emission happens asynchronously; the notify methods return
    the NotificationRecord immediately after writing to the internal log.
    """

    def __init__(self):
        self._log: deque[NotificationRecord] = deque(maxlen=MAX_LOG_SIZE)
        self._thresholds: dict[str, AlertThresholds] = {}   # customer_id → thresholds

    # ── Threshold Management ──────────────────────────────────────────────────

    def set_thresholds(self, customer_id: str, thresholds: AlertThresholds):
        self._thresholds[customer_id] = thresholds

    def get_thresholds(self, customer_id: str) -> AlertThresholds:
        return self._thresholds.get(customer_id, AlertThresholds.default())

    # ── Public Notify API ─────────────────────────────────────────────────────

    def notify_anomaly(
        self,
        *,
        user_id:     str,
        session_id:  str,
        e_rec:       float,
        trust_score: float,
        drift:       float,
        reason:      str      = "",
        customer_id: str      = "",
    ) -> NotificationRecord:
        """
        Fired when the autoencoder reconstruction error or behavioral drift
        exceeds the customer's configured thresholds.
        """
        thresholds = self.get_thresholds(customer_id)
        severity   = (
            Severity.CRITICAL
            if e_rec > thresholds.anomaly_e_rec_above * 1.5 or drift > thresholds.anomaly_drift_above * 1.5
            else Severity.WARNING
        )
        rec = self._record(
            event_type  = WebhookEvent.ANOMALY_DETECTED.value,
            severity    = severity,
            user_id     = user_id,
            session_id  = session_id,
            customer_id = customer_id,
            data        = {
                "e_rec":       round(e_rec, 5),
                "trust_score": round(trust_score, 4),
                "drift":       round(drift, 4),
                "reason":      reason,
            },
        )
        emit_anomaly(user_id, session_id, e_rec, trust_score, drift, reason)
        rec.delivered = True
        self._log_event(rec)
        return rec

    def notify_force_logout(
        self,
        *,
        user_id:     str,
        session_id:  str,
        trust_score: float,
        reason:      str  = "",
        customer_id: str  = "",
    ) -> NotificationRecord:
        """
        Fired when the PPO watchdog escalates to force_logout action.
        Always CRITICAL severity.
        """
        rec = self._record(
            event_type  = WebhookEvent.SESSION_FORCE_LOGOUT.value,
            severity    = Severity.CRITICAL,
            user_id     = user_id,
            session_id  = session_id,
            customer_id = customer_id,
            data        = {
                "trust_score": round(trust_score, 4),
                "reason":      reason,
            },
        )
        emit_force_logout(user_id, session_id, trust_score, reason)
        rec.delivered = True
        self._log_event(rec)
        return rec

    def notify_bot_detected(
        self,
        *,
        user_id:    str,
        theta:      float,
        path:       str,
        ua:         str,
        customer_id: str = "",
    ) -> NotificationRecord:
        """
        Fired when θ < threshold → shadow sandbox activated.
        """
        rec = self._record(
            event_type  = WebhookEvent.BOT_SHADOW_ROUTED.value,
            severity    = Severity.CRITICAL,
            user_id     = user_id,
            session_id  = "",
            customer_id = customer_id,
            data        = {
                "theta":      round(theta, 4),
                "path":       path,
                "user_agent": ua,
            },
        )
        emit_bot_detected(user_id, theta, path, ua)
        rec.delivered = True
        self._log_event(rec)
        return rec

    def notify_trust_degraded(
        self,
        *,
        user_id:     str,
        session_id:  str,
        trust_score: float,
        customer_id: str   = "",
    ) -> NotificationRecord:
        """
        Fired when session trust crosses below the customer's configured threshold.
        """
        thresholds = self.get_thresholds(customer_id)
        rec = self._record(
            event_type  = WebhookEvent.TRUST_DEGRADED.value,
            severity    = Severity.WARNING,
            user_id     = user_id,
            session_id  = session_id,
            customer_id = customer_id,
            data        = {
                "trust_score": round(trust_score, 4),
                "threshold":   thresholds.trust_degraded_below,
            },
        )
        emit_trust_degraded(user_id, session_id, trust_score, thresholds.trust_degraded_below)
        rec.delivered = True
        self._log_event(rec)
        return rec

    def notify_reauth_required(
        self,
        *,
        user_id:    str,
        session_id: str,
        reason:     str = "",
        customer_id: str = "",
    ) -> NotificationRecord:
        """
        Fired when passive re-authentication is recommended (soft intervention).
        """
        rec = self._record(
            event_type  = WebhookEvent.REAUTH_REQUIRED.value,
            severity    = Severity.INFO,
            user_id     = user_id,
            session_id  = session_id,
            customer_id = customer_id,
            data        = {"reason": reason},
        )
        emit_reauth_required(user_id, session_id, reason)
        rec.delivered = True
        self._log_event(rec)
        return rec

    # ── Smart Routing from Pipeline Output ───────────────────────────────────

    def route_watchdog_action(
        self,
        *,
        action:      str,           # 'ok' | 'passive_reauth' | 'disable_sensitive_apis' | 'force_logout'
        user_id:     str,
        session_id:  str,
        trust_score: float,
        e_rec:       float,
        drift:       float          = 0.0,
        customer_id: str            = "",
    ) -> NotificationRecord | None:
        """
        Single entry-point called by the /session/verify pipeline stage.
        Routes to the correct notification channel based on action severity.
        """
        thresholds = self.get_thresholds(customer_id)

        if action == "force_logout":
            return self.notify_force_logout(
                user_id=user_id, session_id=session_id,
                trust_score=trust_score,
                reason="PPO watchdog escalated to force_logout",
                customer_id=customer_id,
            )

        if action in ("passive_reauth", "disable_sensitive_apis"):
            # Always emit reauth; also emit anomaly if thresholds breached
            rec = self.notify_reauth_required(
                user_id=user_id, session_id=session_id,
                reason=f"Watchdog action: {action}",
                customer_id=customer_id,
            )
            if e_rec > thresholds.anomaly_e_rec_above or drift > thresholds.anomaly_drift_above:
                self.notify_anomaly(
                    user_id=user_id, session_id=session_id,
                    e_rec=e_rec, trust_score=trust_score, drift=drift,
                    reason=action, customer_id=customer_id,
                )
            if trust_score < thresholds.trust_degraded_below:
                self.notify_trust_degraded(
                    user_id=user_id, session_id=session_id,
                    trust_score=trust_score, customer_id=customer_id,
                )
            return rec

        # action == 'ok' — still check thresholds for silent breaches
        if trust_score < thresholds.trust_degraded_below:
            return self.notify_trust_degraded(
                user_id=user_id, session_id=session_id,
                trust_score=trust_score, customer_id=customer_id,
            )

        return None   # nothing to report

    # ── Log Query API ─────────────────────────────────────────────────────────

    def query_log(
        self,
        *,
        customer_id:  str | None       = None,
        user_id:      str | None       = None,
        severity:     Severity | None  = None,
        event_type:   str | None       = None,
        limit:        int              = 100,
    ) -> list[dict]:
        results = list(self._log)
        if customer_id: results = [r for r in results if r.customer_id == customer_id]
        if user_id:     results = [r for r in results if r.user_id == user_id]
        if severity:    results = [r for r in results if r.severity == severity]
        if event_type:  results = [r for r in results if r.event_type == event_type]
        # Newest first
        results.sort(key=lambda r: r.created_at, reverse=True)
        return [r.to_dict() for r in results[:limit]]

    def stats(self, customer_id: str | None = None) -> dict:
        records = list(self._log)
        if customer_id:
            records = [r for r in records if r.customer_id == customer_id]
        counts: dict[str, int] = {}
        for r in records:
            counts[r.event_type] = counts.get(r.event_type, 0) + 1
        return {
            "total":           len(records),
            "by_event":        counts,
            "by_severity": {
                sev.value: sum(1 for r in records if r.severity == sev)
                for sev in Severity
            },
        }

    # ── Internals ─────────────────────────────────────────────────────────────

    def _record(self, **kwargs) -> NotificationRecord:
        return NotificationRecord(id=str(uuid.uuid4()), **kwargs)

    def _log_event(self, rec: NotificationRecord):
        self._log.append(rec)
        logger.info(
            "[NOTIFY] %s  severity=%s  user=%s  session=%s",
            rec.event_type, rec.severity.value, rec.user_id, rec.session_id,
        )


# ── Module-level singleton ────────────────────────────────────────────────────
notification_service = NotificationService()