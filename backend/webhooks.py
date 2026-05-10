"""
backend/webhooks.py — Outgoing Webhook Delivery System
=======================================================
Delivers signed, retry-capable event payloads to customer-registered
endpoints when Entropy Prime detects high-risk biometric anomalies.

Webhook Event Types
-------------------
  ep.anomaly.detected      — E_rec or drift threshold breach
  ep.session.force_logout  — PPO watchdog escalated to force-logout
  ep.bot.shadow_routed     — θ < 0.1 → shadow sandbox activated
  ep.trust.degraded        — Trust score drops below customer threshold
  ep.reauth.required       — Passive re-auth recommended

Delivery Guarantees
-------------------
  - HMAC-SHA256 signature in X-Entropy-Signature header
  - Exponential backoff: 3 retries (5s, 25s, 125s)
  - Per-endpoint circuit breaker (opens after 5 consecutive failures)
  - Idempotency key in X-Entropy-Delivery-Id header
  - 5-second connect / 10-second read timeout

Signature Verification (customer side)
---------------------------------------
  sig = HMAC-SHA256(secret, f"{delivery_id}.{timestamp}.{body}")
  Compare with X-Entropy-Signature header (constant-time compare)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger("ep.webhooks")

# ── Defaults ──────────────────────────────────────────────────────────────────
CONNECT_TIMEOUT   = 5.0    # seconds
READ_TIMEOUT      = 10.0   # seconds
RETRY_DELAYS      = [5, 25, 125]        # seconds between retry attempts
CB_FAILURE_THRESH = 5                   # consecutive failures to open circuit
CB_HALF_OPEN_TTL  = 300                 # seconds before circuit half-opens


# ── Event Types ───────────────────────────────────────────────────────────────
class WebhookEvent(str, Enum):
    ANOMALY_DETECTED    = "ep.anomaly.detected"
    SESSION_FORCE_LOGOUT = "ep.session.force_logout"
    BOT_SHADOW_ROUTED   = "ep.bot.shadow_routed"
    TRUST_DEGRADED      = "ep.trust.degraded"
    REAUTH_REQUIRED     = "ep.reauth.required"


# ── Endpoint Registration ─────────────────────────────────────────────────────
@dataclass
class WebhookEndpoint:
    """Customer-registered delivery target."""
    id:            str
    url:           str
    secret:        str                    # used for HMAC signing
    events:        list[WebhookEvent]     # subscribed event types
    customer_id:   str
    enabled:       bool = True
    description:   str  = ""

    # Circuit-breaker state (not persisted)
    _failures:    int   = field(default=0,     repr=False)
    _opened_at:   float = field(default=0.0,   repr=False)
    _is_open:     bool  = field(default=False, repr=False)

    def is_subscribed(self, event: WebhookEvent) -> bool:
        return event in self.events

    def circuit_open(self) -> bool:
        if not self._is_open:
            return False
        import time
        if time.monotonic() - self._opened_at > CB_HALF_OPEN_TTL:
            logger.info("[CB] Half-opening circuit for %s", self.id)
            self._is_open = False
            self._failures = 0
            return False
        return True

    def record_success(self):
        self._failures = 0
        self._is_open  = False

    def record_failure(self):
        import time
        self._failures += 1
        if self._failures >= CB_FAILURE_THRESH:
            self._is_open  = True
            self._opened_at = time.monotonic()
            logger.warning("[CB] Circuit OPENED for endpoint %s after %d failures",
                           self.id, self._failures)


# ── Delivery Result ───────────────────────────────────────────────────────────
@dataclass
class DeliveryResult:
    delivery_id:  str
    endpoint_id:  str
    event:        WebhookEvent
    success:      bool
    status_code:  int | None
    attempts:     int
    latency_ms:   float
    error:        str | None = None


# ── Signer ────────────────────────────────────────────────────────────────────
def _sign(secret: str, delivery_id: str, timestamp: str, body: bytes) -> str:
    """
    Produces HMAC-SHA256 signature.
    Payload: f"{delivery_id}.{timestamp}.{body_bytes}"
    """
    msg = f"{delivery_id}.{timestamp}.".encode() + body
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


# ── Payload Builder ───────────────────────────────────────────────────────────
def build_payload(
    event:       WebhookEvent,
    delivery_id: str,
    data:        dict[str, Any],
    api_version: str = "2025-01",
) -> dict:
    return {
        "id":          delivery_id,
        "api_version": api_version,
        "event":       event.value,
        "created":     datetime.now(timezone.utc).isoformat(),
        "data":        data,
    }


# ── Core Dispatcher ───────────────────────────────────────────────────────────
class WebhookDispatcher:
    """
    Dispatches signed webhook payloads with exponential backoff retry
    and per-endpoint circuit breaking.
    """

    def __init__(self):
        # In production, endpoints are stored in the database.
        # Here we maintain an in-process registry for simplicity.
        self._endpoints: dict[str, WebhookEndpoint] = {}
        # Background task set (avoids GC cancellation)
        self._tasks: set[asyncio.Task] = set()

    # ── Endpoint Management ───────────────────────────────────────────────────

    def register_endpoint(self, endpoint: WebhookEndpoint):
        self._endpoints[endpoint.id] = endpoint
        logger.info("Registered webhook endpoint %s → %s", endpoint.id, endpoint.url)

    def unregister_endpoint(self, endpoint_id: str):
        self._endpoints.pop(endpoint_id, None)

    def list_endpoints(self, customer_id: str | None = None) -> list[WebhookEndpoint]:
        eps = list(self._endpoints.values())
        if customer_id:
            eps = [e for e in eps if e.customer_id == customer_id]
        return eps

    def update_endpoint(self, endpoint_id: str, **kwargs) -> WebhookEndpoint | None:
        ep = self._endpoints.get(endpoint_id)
        if not ep:
            return None
        for k, v in kwargs.items():
            if hasattr(ep, k):
                setattr(ep, k, v)
        return ep

    # ── Fire & Forget ─────────────────────────────────────────────────────────

    def fire(self, event: WebhookEvent, data: dict[str, Any]):
        """
        Enqueue async delivery for all subscribed, enabled endpoints.
        Non-blocking — callers never wait on network I/O.
        """
        candidates = [
            ep for ep in self._endpoints.values()
            if ep.enabled and ep.is_subscribed(event) and not ep.circuit_open()
        ]
        if not candidates:
            return

        for ep in candidates:
            task = asyncio.create_task(self._deliver(ep, event, data))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    # ── Delivery Pipeline ─────────────────────────────────────────────────────

    async def _deliver(
        self,
        endpoint: WebhookEndpoint,
        event:    WebhookEvent,
        data:     dict[str, Any],
    ) -> DeliveryResult:
        import time

        delivery_id = str(uuid.uuid4())
        payload     = build_payload(event, delivery_id, data)
        body        = json.dumps(payload, separators=(",", ":")).encode()
        timestamp   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        signature   = _sign(endpoint.secret, delivery_id, timestamp, body)

        headers = {
            "Content-Type":            "application/json",
            "User-Agent":              "EntropyPrime-Webhook/1.0",
            "X-Entropy-Delivery-Id":   delivery_id,
            "X-Entropy-Timestamp":     timestamp,
            "X-Entropy-Signature":     signature,
            "X-Entropy-Event":         event.value,
        }

        attempts    = 0
        last_error  = None
        last_status = None
        t0          = time.monotonic()

        delays = [0] + RETRY_DELAYS        # first attempt has no pre-delay

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=5.0, pool=5.0)
        ) as client:
            for delay in delays:
                if delay:
                    await asyncio.sleep(delay)
                attempts += 1
                try:
                    resp = await client.post(endpoint.url, content=body, headers=headers)
                    last_status = resp.status_code
                    if 200 <= resp.status_code < 300:
                        endpoint.record_success()
                        latency = (time.monotonic() - t0) * 1000
                        logger.info("[WH] ✓ %s → %s  status=%d  attempts=%d  %.0fms",
                                    event.value, endpoint.url, resp.status_code, attempts, latency)
                        return DeliveryResult(
                            delivery_id=delivery_id, endpoint_id=endpoint.id,
                            event=event, success=True, status_code=last_status,
                            attempts=attempts, latency_ms=latency,
                        )
                    # 4xx: client error — don't retry
                    if 400 <= resp.status_code < 500:
                        last_error = f"HTTP {resp.status_code} (client error, no retry)"
                        logger.warning("[WH] 4xx %s → %s: %s", event.value, endpoint.url, resp.status_code)
                        break
                    # 5xx: server error — retry
                    last_error = f"HTTP {resp.status_code}"
                    logger.warning("[WH] %d %s → %s  attempt=%d", resp.status_code, event.value, endpoint.url, attempts)

                except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as exc:
                    last_error = str(exc)
                    logger.warning("[WH] Network error %s → %s  attempt=%d: %s",
                                   event.value, endpoint.url, attempts, exc)

        endpoint.record_failure()
        latency = (time.monotonic() - t0) * 1000
        logger.error("[WH] ✗ %s → %s  failed after %d attempts: %s",
                     event.value, endpoint.url, attempts, last_error)
        return DeliveryResult(
            delivery_id=delivery_id, endpoint_id=endpoint.id,
            event=event, success=False, status_code=last_status,
            attempts=attempts, latency_ms=latency, error=last_error,
        )

    # ── Test Delivery ─────────────────────────────────────────────────────────

    async def test_endpoint(self, endpoint_id: str) -> DeliveryResult | None:
        ep = self._endpoints.get(endpoint_id)
        if not ep:
            return None
        return await self._deliver(
            ep,
            WebhookEvent.ANOMALY_DETECTED,
            {
                "test": True,
                "user_id": "test_user",
                "message": "This is a test delivery from Entropy Prime.",
                "trust_score": 0.42,
                "e_rec": 0.21,
            },
        )


# ── Module-level singleton ────────────────────────────────────────────────────
dispatcher = WebhookDispatcher()


# ── Convenience Emitters ──────────────────────────────────────────────────────

def emit_anomaly(
    user_id:     str,
    session_id:  str,
    e_rec:       float,
    trust_score: float,
    drift:       float,
    reason:      str = "",
):
    dispatcher.fire(WebhookEvent.ANOMALY_DETECTED, {
        "user_id":     user_id,
        "session_id":  session_id,
        "e_rec":       round(e_rec, 5),
        "trust_score": round(trust_score, 4),
        "drift":       round(drift, 4),
        "reason":      reason,
    })


def emit_force_logout(user_id: str, session_id: str, trust_score: float, reason: str = ""):
    dispatcher.fire(WebhookEvent.SESSION_FORCE_LOGOUT, {
        "user_id":     user_id,
        "session_id":  session_id,
        "trust_score": round(trust_score, 4),
        "reason":      reason,
    })


def emit_bot_detected(user_id: str, theta: float, path: str, ua: str):
    dispatcher.fire(WebhookEvent.BOT_SHADOW_ROUTED, {
        "user_id":    user_id,
        "theta":      round(theta, 4),
        "path":       path,
        "user_agent": ua,
    })


def emit_trust_degraded(user_id: str, session_id: str, trust_score: float, threshold: float):
    dispatcher.fire(WebhookEvent.TRUST_DEGRADED, {
        "user_id":     user_id,
        "session_id":  session_id,
        "trust_score": round(trust_score, 4),
        "threshold":   threshold,
    })


def emit_reauth_required(user_id: str, session_id: str, reason: str):
    dispatcher.fire(WebhookEvent.REAUTH_REQUIRED, {
        "user_id":    user_id,
        "session_id": session_id,
        "reason":     reason,
    })