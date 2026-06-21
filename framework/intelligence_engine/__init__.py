"""
framework.intelligence_engine — Cross-Cutting Intelligence
==========================================================

Aggregates signals that span sessions and tenants, and pushes them outward.
Three responsibilities:

  1. Cross-site threat intelligence  — accumulate suspicious-fingerprint weight
     across tenants and globally flag known-bad actors before any compute is
     spent on them.   (backend.services.watchdog_services)
  2. Notifications                   — in-process event log + per-customer alert
     thresholds.       (backend.services.notification_service)
  3. Outgoing webhooks               — signed, retried delivery with circuit
     breaking.          (backend.webhooks)

Facade mapping (v0.1 — re-export, no code moved)
------------------------------------------------
    .WatchdogService       <- backend.services.watchdog_services.WatchdogService
    .notification_service  <- backend.services.notification_service.notification_service
    .NotificationService   <- backend.services.notification_service.NotificationService
    .AlertThresholds       <- backend.services.notification_service.AlertThresholds
    .Severity              <- backend.services.notification_service.Severity
    .webhook_dispatcher    <- backend.webhooks.dispatcher
    .WebhookEndpoint       <- backend.webhooks.WebhookEndpoint
    .WebhookEvent          <- backend.webhooks.WebhookEvent
"""
from __future__ import annotations

# ── Notifications (stdlib; safe) ─────────────────────────────────────────────
from backend.services.notification_service import (
    notification_service,
    NotificationService,
    AlertThresholds,
    Severity,
)

# ── Outgoing webhooks (httpx) ────────────────────────────────────────────────
try:
    from backend.webhooks import (
        dispatcher as webhook_dispatcher,
        WebhookEndpoint,
        WebhookEvent,
    )
    WEBHOOKS_AVAILABLE = True
except Exception as exc:  # pragma: no cover - httpx may be absent
    webhook_dispatcher = None
    WebhookEndpoint = None
    WebhookEvent = None
    WEBHOOKS_AVAILABLE = False
    _WEBHOOKS_ERROR = str(exc)

# ── Cross-site threat intelligence (motor) ───────────────────────────────────
try:
    from backend.services.watchdog_services import WatchdogService
    THREAT_INTEL_AVAILABLE = True
except Exception as exc:  # pragma: no cover - motor may be absent
    WatchdogService = None
    THREAT_INTEL_AVAILABLE = False
    _THREAT_ERROR = str(exc)

__all__ = [
    "notification_service",
    "NotificationService",
    "AlertThresholds",
    "Severity",
    "webhook_dispatcher",
    "WebhookEndpoint",
    "WebhookEvent",
    "WEBHOOKS_AVAILABLE",
    "WatchdogService",
    "THREAT_INTEL_AVAILABLE",
]
