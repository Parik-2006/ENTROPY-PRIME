"""
backend/main.py — Entropy Prime FastAPI Application  v3.2.0
============================================================
Four-stage zero-trust biometric authentication pipeline with full
Integration API and outgoing webhook delivery.

Stages
------
  1  Biological Gateway   — 1D-CNN humanity scoring (θ)
  2  Offensive Deception  — Honeypot injection + MAB shadow sandbox
  3  Resource Governor    — DQN Argon2id parameter selection
  4  Session Watchdog     — Per-user behavioral profile + PPO drift detection

v3.2.0 additions (merged from Integration API layer)
----------------------------------------------------
  POST   /webhooks/endpoints            — Register a signed delivery endpoint
  GET    /webhooks/endpoints            — List endpoints (filterable by customer_id)
  GET    /webhooks/endpoints/{id}       — Fetch one endpoint
  PATCH  /webhooks/endpoints/{id}       — Update url / secret / events / enabled
  DELETE /webhooks/endpoints/{id}       — Unregister endpoint
  POST   /webhooks/endpoints/{id}/test  — Send a test delivery

  POST   /session/trust                 — Gate check before a sensitive transaction
  GET    /session/trust/{session_id}    — Poll current trust posture (SSE-friendly)

  GET    /notifications                 — Query notification log
  GET    /notifications/stats           — Aggregated event counts
  POST   /notifications/thresholds      — Per-customer alert threshold config
  GET    /notifications/thresholds/{id} — Read per-customer thresholds

v3.1.0 changes
──────────────
  • `require_active_session` FastAPI dependency: validates every token against
    the DB before any sensitive route runs.  Rejects expired / inactive
    sessions with HTTP 401.
  • /auth/login and /auth/register call `create_session` explicitly.
  • /session/verify: uses DB-persisted trust score as authoritative baseline;
    writes updated score back; invalidates on FORCE_LOGOUT.
  • /honeypot/reward: validates arm index; clamps reward.
  • Cross-site threat gate via WatchdogService (globally_flagged check).
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

# ── Ensure parent directory is in path for imports ────────────────────────────
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import numpy as np
import torch
from bson import ObjectId
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl, model_validator

# ── Database layer ────────────────────────────────────────────────────────────
from backend.database import Database
from backend.database import (
    user_exists, create_user, get_user_by_email, get_user_by_id,
    update_last_login, update_user_security_level,
    create_session, get_session, invalidate_session, update_session_trust_score,
    store_biometric_sample, get_biometric_profile, upsert_biometric_profile,
    store_honeypot_entry, get_honeypot_signatures, get_honeypot_count,
)

# ── Pydantic auth models ──────────────────────────────────────────────────────
from backend.models.pydantic_models import UserCreate, UserLogin

# ── ML agents ────────────────────────────────────────────────────────────────
from backend.models.dqn   import DQNAgent
from backend.models.mab   import MABAgent
from backend.models.ppo   import PPOAgent
from backend.models.cnn1d import CNN1D

# ── Pipeline ──────────────────────────────────────────────────────────────────
from backend.pipeline import PipelineOrchestrator, BiometricInput
from backend.pipeline.contracts  import WatchdogAction, SecurityPreset
from backend.pipeline            import stage1_biometric as s1
from backend.pipeline            import stage3_governor  as s3
from backend.pipeline.orchestrator import _make_session_token
from backend.middleware.auth import attach_db, SiteCtx
from backend.services.auth_service import load_jwt_public_key
from backend.services.watchdog_services import WatchdogService

# ── Integration API: webhooks + notification service ─────────────────────────
from backend.webhooks import (
    WebhookEndpoint,
    WebhookEvent,
    dispatcher,
)
from backend.services.notification_service import (
    AlertThresholds,
    NotificationService,
    Severity,
    notification_service,
)

# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format  = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("entropy_prime")
logger.info("Starting Entropy Prime v3.2 (log level: %s)", os.environ.get("LOG_LEVEL", "INFO"))

# ── Module-level secrets ──────────────────────────────────────────────────────
SESSION_SECRET = os.environ.get("EP_SESSION_SECRET", secrets.token_hex(32))
SHADOW_SECRET  = os.environ.get("EP_SHADOW_SECRET",  secrets.token_hex(32))

# ── Singleton DB handler & model agents ──────────────────────────────────────
db_handler = Database()

dqn_agent = DQNAgent(state_dim=3,  action_dim=4)
mab_agent = MABAgent(n_arms=3)
ppo_agent = PPOAgent(state_dim=10, action_dim=3)
cnn_model = CNN1D(input_channels=1, out_dim=32)

watchdog_service: Optional[WatchdogService] = None
orchestrator:     Optional[PipelineOrchestrator] = None


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_checkpoints() -> None:
    """
    Load pre-trained weights for every agent.

    Resolution order (first match wins):
      1. Environment variable  (EP_RL_CHECKPOINT / EP_MAB_CHECKPOINT / EP_PPO_CHECKPOINT)
      2. Default path          (EP_CHECKPOINT_DIR/<name>.pt|json)

    Missing checkpoints are non-fatal; agents use random / cold-start weights.
    """
    ckpt_dir = os.environ.get("EP_CHECKPOINT_DIR", "checkpoints")

    rl_path  = os.environ.get("EP_RL_CHECKPOINT",  os.path.join(ckpt_dir, "governor.pt"))
    mab_path = os.environ.get("EP_MAB_CHECKPOINT", os.path.join(ckpt_dir, "mab.json"))
    ppo_path = os.environ.get("EP_PPO_CHECKPOINT", os.path.join(ckpt_dir, "watchdog.pt"))

    for path, loader, label in [
        (rl_path,  lambda p: dqn_agent.load_checkpoint(p),                                  "DQN"),
        (mab_path, lambda p: mab_agent.load_state_dict(json.load(open(p))),                 "MAB"),
        (ppo_path, lambda p: ppo_agent.load_checkpoint(p),                                  "PPO"),
    ]:
        if os.path.exists(path):
            try:
                loader(path)
                logger.debug("✓ %s checkpoint loaded: %s", label, path)
            except Exception as exc:
                logger.debug("%s checkpoint not loaded (%s) — using random weights", label, exc)
        else:
            logger.debug("%s checkpoint not found at %s — using random weights", label, path)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator, watchdog_service

    logger.info("🚀 Entropy Prime v3.2 starting up…")

    await db_handler.connect_to_mongo()
    attach_db(db_handler.db)
    load_jwt_public_key()
    _load_checkpoints()

    watchdog_service = WatchdogService(db_handler)

    # Auto-seed test data in development
    if os.environ.get("ENVIRONMENT") == "development":
        from database import create_tenant, create_site
        import hmac as _hmac, hashlib

        try:
            if not await db_handler.db.tenants.find_one({"admin_email": "admin@test.com"}):
                tenant_id = await create_tenant(db_handler.db, "Test Corp", "admin@test.com", "pro")
                raw_api_key    = "test-sdk-key-123"
                api_key_secret = os.environ.get("EP_API_KEY_SECRET", "dev-only-api-key-secret-change-me")
                key_digest     = _hmac.new(
                    api_key_secret.encode(), raw_api_key.encode(), hashlib.sha256
                ).hexdigest()
                await create_site(db_handler.db, tenant_id, "Test Site", "localhost", key_digest)
                logger.info("🌱 Database seeded with test tenant and site")
        except Exception as exc:
            logger.warning("Seeding failed (likely non-writable DB): %s", exc)

    orchestrator = PipelineOrchestrator(
        dqn_agent      = dqn_agent,
        mab_agent      = mab_agent,
        ppo_agent      = ppo_agent,
        shadow_secret  = SHADOW_SECRET,
        session_secret = SESSION_SECRET,
    )

    # Background task: periodic TTL sweep for stale threats
    import asyncio

    async def _threat_ttl_sweep():
        while True:
            try:
                await asyncio.sleep(6 * 60 * 60)
                if watchdog_service:
                    count = await watchdog_service.expire_stale_threats()
                    logger.info("[TTL Sweep] Expired %d stale threat records", count)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[TTL Sweep] Failed: %s", exc)

    sweep_task = asyncio.create_task(_threat_ttl_sweep())
    logger.info("✓ Entropy Prime v3.2 initialised — 4-stage pipeline + Integration API active")
    yield

    logger.info("🛑 Entropy Prime shutting down…")
    sweep_task.cancel()
    try:
        await sweep_task
    except Exception:
        pass
    try:
        await db_handler.close_mongo_connection()
        logger.info("✓ MongoDB connection closed")
    except Exception as exc:
        logger.error("Error during DB shutdown: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Entropy Prime",
    version     = "3.2.0",
    description = "Zero-trust behavioural biometrics engine — 4-stage pipeline + Integration API",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3001,http://localhost:5173,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001",
    ).split(","),
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── Middleware: per-request timing log ────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed  = time.perf_counter() - start
        logger.debug(
            "%s %s → %d  (%.3fs)",
            request.method, request.url.path, response.status_code, elapsed,
        )
        return response
    except Exception as exc:
        logger.error(
            "Request crashed: %s %s — %s",
            request.method, request.url.path, exc, exc_info=True,
        )
        raise


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled %s on %s %s",
        type(exc).__name__, request.method, request.url.path, exc_info=True,
    )
    return JSONResponse(
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
        content     = {"detail": "Internal server error"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Session Guard — reusable FastAPI dependency
# ─────────────────────────────────────────────────────────────────────────────

class _SessionGuardDep:
    """
    Validates X-Session-Token against MongoDB before any sensitive route runs.

    Raises HTTP 401 when:
      • No X-Session-Token header is present.
      • The token does not exist in the DB.
      • The session is expired or explicitly invalidated (is_active=False).

    Returns the raw session document (ObjectIds already stringified).
    """

    async def __call__(self, request: Any) -> dict:
        token = request.headers.get("X-Session-Token")
        if not token:
            raise HTTPException(
                status_code = status.HTTP_401_UNAUTHORIZED,
                detail      = "Missing X-Session-Token header",
                headers     = {"WWW-Authenticate": "Bearer"},
            )
        try:
            session = await get_session(db_handler.db, token)
        except Exception as exc:
            logger.error("[SessionGuard] DB error: %s", exc)
            raise HTTPException(
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
                detail      = "Session store unavailable",
            )
        if session is None:
            raise HTTPException(
                status_code = status.HTTP_401_UNAUTHORIZED,
                detail      = "Invalid or expired session",
                headers     = {"WWW-Authenticate": "Bearer"},
            )
        return session


require_active_session = _SessionGuardDep()
ActiveSession = Annotated[dict, Depends(require_active_session)]


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic request / response models
# ─────────────────────────────────────────────────────────────────────────────

# ── Pipeline models ───────────────────────────────────────────────────────────

class ScoreReq(BaseModel):
    theta:         float       = Field(..., ge=0.0, le=1.0)
    h_exp:         float       = Field(..., ge=0.0, le=1.0)
    server_load:   float       = Field(0.5, ge=0.0, le=1.0)
    user_agent:    str         = ""
    latent_vector: list[float] = Field(default_factory=list)
    fingerprint:   str         = ""

    @model_validator(mode="after")
    def _validate(self):
        if self.latent_vector and len(self.latent_vector) != 32:
            raise ValueError("latent_vector must be empty or exactly 32-dim")
        if not self.fingerprint:
            import hashlib
            combined        = f"{self.user_agent}:{str(self.latent_vector[:8])}"
            self.fingerprint = hashlib.sha256(combined.encode()).hexdigest()[:32]
        return self


class SessionVerifyReq(BaseModel):
    """
    Heartbeat payload for /session/verify.

    NOTE: `trust_score` is NOT accepted from the client — the authoritative
    value lives in MongoDB so a replayed or inflated value cannot bypass drift
    detection.
    """
    session_token: str
    user_id:       str
    latent_vector: list[float]
    e_rec:         float = Field(..., ge=0.0)
    fingerprint:   str   = ""
    # Watchdog extension fields (informational; not used as authority)
    behavioral_drift:   float | None    = None
    adaptive_threshold: float | None    = None
    selected_features:  list[str]       = Field(default_factory=list)
    sample_count:       int | None      = None

    @model_validator(mode="after")
    def _validate(self):
        if len(self.latent_vector) != 32:
            raise ValueError("latent_vector must be exactly 32-dim")
        if not self.fingerprint:
            import hashlib
            self.fingerprint = hashlib.sha256(
                str(self.latent_vector[:8]).encode()
            ).hexdigest()[:32]
        return self


class PwHashReq(BaseModel):
    plain_password: str
    stored_hash:    str   = ""
    theta:          float = Field(0.5, ge=0.0, le=1.0)
    h_exp:          float = Field(0.5, ge=0.0, le=1.0)


class MabRewardReq(BaseModel):
    arm:    int
    reward: float = Field(..., ge=-1.0, le=1.0)


class HoneypotTriggerReq(BaseModel):
    challenge_id:    str
    arm:             int
    expires_at:      float
    signature:       str
    decoy_ids:       list[str]
    triggered_decoy: str
    trigger_event:   str
    trigger_kind:    str
    session_token:   str


class LogoutReq(BaseModel):
    session_token: str


class TelemetryReq(BaseModel):
    userId:    str
    events:    list[dict]
    timestamp: int


class BiometricExtractReq(BaseModel):
    raw_signal: list[float]


class BiometricProfileSyncReq(BaseModel):
    theta:         float              = Field(..., ge=0.0, le=1.0)
    h_exp:         float              = Field(..., ge=0.0, le=1.0)
    latent_vector: list[float]        = Field(default_factory=list)
    practice_text: str                = ""
    keyboard_stats: dict[str, Any]    = Field(default_factory=dict)
    pointer_stats:  dict[str, Any]    = Field(default_factory=dict)
    profile_stats:  dict[str, Any]    = Field(default_factory=dict)
    live_drift:     float | None      = None
    server_load:    float             = Field(0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate(self):
        if self.latent_vector and len(self.latent_vector) != 32:
            raise ValueError("latent_vector must be empty or exactly 32-dim")
        return self


# ── Webhook endpoint models ───────────────────────────────────────────────────

class EndpointCreate(BaseModel):
    url:         HttpUrl
    secret:      str = Field(min_length=16, description="HMAC signing secret (≥16 chars)")
    events:      list[WebhookEvent]
    customer_id: str
    description: str = ""


class EndpointUpdate(BaseModel):
    url:         HttpUrl | None         = None
    secret:      str | None             = None
    events:      list[WebhookEvent] | None = None
    enabled:     bool | None            = None
    description: str | None             = None


class EndpointOut(BaseModel):
    id:          str
    url:         str
    events:      list[str]
    customer_id: str
    enabled:     bool
    description: str


class TestDeliveryOut(BaseModel):
    delivery_id: str
    success:     bool
    status_code: int | None
    attempts:    int
    latency_ms:  float
    error:       str | None


# ── Session trust models ──────────────────────────────────────────────────────

class SessionTrustRequest(BaseModel):
    """Customer backend sends this before authorising a sensitive transaction."""
    session_token:    str
    user_id:          str
    customer_id:      str         = ""
    trust_score:      float | None = Field(None, ge=0.0, le=1.0)
    e_rec:            float | None = Field(None, ge=0.0)
    latent_vector:    list[float]  = Field(default_factory=list)
    transaction_risk: float        = Field(
        0.5, ge=0.0, le=1.0,
        description="Customer-provided risk level [0, 1]",
    )


class SessionTrustResponse(BaseModel):
    session_id:       str
    user_id:          str
    trust_score:      float
    e_rec:            float
    action:           str    # 'allow' | 'challenge' | 'deny'
    confidence:       str    # 'high' | 'medium' | 'low'
    risk_adjusted:    float
    reasons:          list[str]
    pipeline_version: str = "3.2"
    timestamp:        str


# ── Notification threshold model ──────────────────────────────────────────────

class ThresholdConfig(BaseModel):
    trust_degraded_below: float = Field(0.50, ge=0.0, le=1.0)
    anomaly_e_rec_above:  float = Field(0.18, ge=0.0)
    anomaly_drift_above:  float = Field(3.0,  ge=0.0)
    bot_theta_below:      float = Field(0.10, ge=0.0, le=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    return getattr(request.client, "host", "?") if request.client else "?"


async def _threat_gate(fingerprint: str, ip: str | None) -> bool:
    """
    Returns True when the fingerprint/IP is globally flagged.
    Swallows all errors so a WatchdogService outage never blocks auth.
    """
    if not watchdog_service:
        return False
    try:
        result = await watchdog_service.is_globally_flagged(fingerprint, ip)
        return result.globally_flagged
    except Exception as exc:
        logger.error("[ThreatGate] Check failed: %s — proceeding", exc)
        return False


async def _ingest_watchdog(tenant_id: str, fingerprint: str, ip: str | None, wd_result) -> None:
    """Push a watchdog result into the cross-site threat store (fire-and-forget)."""
    if not watchdog_service:
        return
    try:
        intel = await watchdog_service.ingest(
            tenant_id   = tenant_id,
            fingerprint = fingerprint,
            ip_address  = ip,
            result      = wd_result,
        )
        logger.debug(
            "[ThreatIngest] fp=%.8s action=%s score=%.2f tenants=%d",
            intel.fingerprint_hash, wd_result.action.value,
            intel.cumulative_score, intel.tenant_count,
        )
    except Exception as exc:
        logger.error("[ThreatIngest] Failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1-4: /score  — main pipeline entry point
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/score")
async def score(req: ScoreReq, request: Request):
    """
    Runs the full 4-stage pipeline with cross-site threat intelligence gating.
    Always returns HTTP 200 — bots receive a synthetic shadow token so they
    cannot distinguish rejection from success.

    Flow
    ────
    1. Threat gate: is the fingerprint/IP globally flagged? → instant shadow
    2. 4-stage pipeline (biometric → honeypot → governor → watchdog)
    3. Bot hit → store honeypot entry in DB
    4. Watchdog result → ingest into cross-site threat store
    5. Emit webhook notification if bot detected
    """
    ip  = _client_ip(request)
    raw = BiometricInput(
        theta         = req.theta,
        h_exp         = req.h_exp,
        server_load   = req.server_load,
        user_agent    = req.user_agent,
        latent_vector = req.latent_vector,
        ip_address    = ip,
    )

    # ── 1. Threat gate ────────────────────────────────────────────────────────
    if await _threat_gate(req.fingerprint, ip):
        logger.warning("[/score] Global threat gate tripped: fp=%.8s", req.fingerprint)
        shadow_token = "bot_" + secrets.token_hex(32)
        notification_service.notify_bot_detected(
            user_id    = f"anon_{shadow_token[:8]}",
            theta      = req.theta,
            path       = "/score",
            ua         = req.user_agent or "unknown",
        )
        return {
            "session_token":       shadow_token,
            "shadow_mode":         True,
            "argon2_params":       {"time_cost": 2, "memory_kb": 64, "parallelism": 4},
            "humanity_score":      0.0,
            "entropy_score":       0.0,
            "action_label":        "ECONOMY",
            "pipeline_confidence": "HIGH",
            "degraded":            False,
            "threat_gate":         "GLOBALLY_FLAGGED",
        }

    # ── 2. Full pipeline ──────────────────────────────────────────────────────
    result = orchestrator.run(raw)

    # ── 3. Honeypot DB entry ──────────────────────────────────────────────────
    if result.shadow_mode:
        try:
            await store_honeypot_entry(
                db_handler.db,
                user_agent = req.user_agent,
                theta      = req.theta,
                ip_address = ip,
                path       = "/score",
                headers    = dict(request.headers),
            )
        except Exception as exc:
            logger.error("[Honeypot] DB write failed: %s", exc)

        notification_service.notify_bot_detected(
            user_id    = f"anon_{result.session_token[:8]}",
            theta      = req.theta,
            path       = "/score",
            ua         = req.user_agent or "unknown",
        )

    logger.info(
        "[Pipeline] shadow=%s preset=%-8s conf=%-6s degraded=%s θ=%.3f",
        result.shadow_mode, result.action_label,
        result.pipeline_confidence, result.degraded, result.humanity_score,
    )

    response: dict = {
        "session_token":       result.session_token,
        "shadow_mode":         result.shadow_mode,
        "argon2_params":       result.argon2_params,
        "humanity_score":      result.humanity_score,
        "entropy_score":       result.entropy_score,
        "action_label":        result.action_label,
        "pipeline_confidence": result.pipeline_confidence.value,
        "degraded":            result.degraded,
    }

    # ── 4. Watchdog result + threat ingest ────────────────────────────────────
    if result.watchdog is not None:
        wd = result.watchdog
        response["watchdog"] = {
            "action":      wd.action.value,
            "trust_score": wd.trust_score,
            "e_rec":       wd.e_rec,
            "confidence":  wd.confidence.value,
            "reason":      wd.reason,
        }
        # TODO: derive tenant_id from SiteCtx / API key
        await _ingest_watchdog("default", req.fingerprint, ip, wd)

        # Route through notification service
        notification_service.route_watchdog_action(
            action      = wd.action.value,
            user_id     = f"anon_{result.session_token[:8]}",
            session_id  = result.session_token,
            trust_score = wd.trust_score,
            e_rec       = wd.e_rec,
        )

    if result.shadow_mode and result.honeypot.mab_arm_selected >= 0:
        response["mab_arm"] = result.honeypot.mab_arm_selected

    if result.challenge is not None:
        response["challenge"] = result.challenge.to_dict()

    return response


# ─────────────────────────────────────────────────────────────────────────────
# Telemetry (SDK batch events)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/telemetry")
async def telemetry(req: TelemetryReq, site: SiteCtx):
    """
    Receives batch telemetry from the SDK.
    Authenticated via X-API-Key (SiteCtx middleware).
    """
    logger.info(
        "[Telemetry] %d events  site=%s  tenant=%s  user=%s",
        len(req.events), site.site_id, site.tenant_id, req.userId,
    )
    return {"status": "ok", "received": len(req.events)}


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4: /session/verify  — continuous watchdog heartbeat
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/session/verify")
async def session_verify(req: SessionVerifyReq, request: Request):
    """
    Continuous identity-drift heartbeat called periodically by the client.

    Security model
    ──────────────
    1. Validate session token against MongoDB — dead sessions always get 401.
    2. Trust score baseline from DB, not the request body (replay-safe).
    3. Updated trust score (post-decay / recovery) is written back to the DB.
    4. FORCE_LOGOUT immediately invalidates the session in the DB.
    5. Cross-site threat gate checked; globally flagged sessions are force-
       logged-out even if the local watchdog would allow them.
    6. Watchdog result ingested into the cross-site threat store.
    7. Notification service routes the action to webhooks / log.
    """
    # ── 1. Validate session ───────────────────────────────────────────────────
    try:
        session = await get_session(db_handler.db, req.session_token)
    except Exception as exc:
        logger.error("[SessionVerify] DB read failed: %s", exc)
        raise HTTPException(
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
            detail      = "Session store unavailable",
        )

    if session is None:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Invalid or expired session",
            headers     = {"WWW-Authenticate": "Bearer"},
        )

    if session.get("user_id") != req.user_id:
        logger.warning(
            "[SessionVerify] user_id mismatch: token_owner=%s claimed=%s",
            session.get("user_id"), req.user_id,
        )
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Session / user_id mismatch",
        )

    # ── 2. DB trust score is authoritative ────────────────────────────────────
    db_trust: float = float(session.get("trust_score", 1.0))

    # ── 3. Cross-site threat gate ─────────────────────────────────────────────
    ip = _client_ip(request)
    if await _threat_gate(req.fingerprint, ip):
        logger.warning(
            "[SessionVerify] Global threat gate tripped: user=%s fp=%.8s",
            req.user_id, req.fingerprint,
        )
        try:
            await invalidate_session(db_handler.db, req.session_token)
        except Exception as exc:
            logger.error("[SessionVerify] Session invalidation failed: %s", exc)

        notification_service.notify_force_logout(
            user_id     = req.user_id,
            session_id  = req.session_token,
            trust_score = 0.0,
            reason      = "globally_flagged",
        )
        return {
            "action":             WatchdogAction.FORCE_LOGOUT.value,
            "trust_score":        0.0,
            "e_rec":              req.e_rec,
            "confidence":         "HIGH",
            "reason":             "globally_flagged",
            "session_invalidated": True,
        }

    # ── 4. Run watchdog ───────────────────────────────────────────────────────
    wd = orchestrator.run_watchdog(
        latent_vector = req.latent_vector,
        e_rec         = req.e_rec,
        trust_score   = db_trust,   # ← DB value, not client-supplied
    )

    logger.info(
        "[SessionVerify] user=%s action=%s trust %.3f→%.3f e_rec=%.3f conf=%s",
        req.user_id, wd.action.value, db_trust, wd.trust_score,
        wd.e_rec, wd.confidence.value,
    )

    # ── 5. Persist updated trust score ────────────────────────────────────────
    try:
        await update_session_trust_score(db_handler.db, req.session_token, wd.trust_score)
    except Exception as exc:
        logger.warning("[SessionVerify] trust-score persist failed: %s", exc)

    # ── 6. Invalidate on FORCE_LOGOUT ─────────────────────────────────────────
    session_invalidated = wd.action == WatchdogAction.FORCE_LOGOUT
    if session_invalidated:
        try:
            await invalidate_session(db_handler.db, req.session_token)
            logger.info("[SessionVerify] Session invalidated (FORCE_LOGOUT): user=%s", req.user_id)
        except Exception as exc:
            logger.error("[SessionVerify] Session invalidation failed: %s", exc)

    # ── 7. Cross-site ingest + notification routing ───────────────────────────
    await _ingest_watchdog("default", req.fingerprint, ip, wd)
    notification_service.route_watchdog_action(
        action      = wd.action.value,
        user_id     = req.user_id,
        session_id  = req.session_token,
        trust_score = wd.trust_score,
        e_rec       = wd.e_rec,
        drift       = req.behavioral_drift or 0.0,
    )

    return {
        "action":             wd.action.value,
        "trust_score":        wd.trust_score,
        "e_rec":              wd.e_rec,
        "confidence":         wd.confidence.value,
        "reason":             wd.reason,
        "session_invalidated": session_invalidated,
    }


# ─────────────────────────────────────────────────────────────────────────────
# /honeypot/reward  — MAB feedback loop
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/honeypot/reward")
async def honeypot_reward(req: MabRewardReq):
    """
    Close the MAB reward loop after a shadow session ends.

    reward > 0 → deception held (bot stayed in sandbox)
    reward < 0 → bot escaped (arm strategy was ineffective)

    Arm is validated against the live n_arms so a corrupted / replayed payload
    cannot index out of bounds.
    """
    n_arms = mab_agent.n_arms
    if not (0 <= req.arm < n_arms):
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail      = f"arm must be in [0, {n_arms - 1}]; got {req.arm}",
        )
    reward = max(-1.0, min(1.0, req.reward))   # belt-and-suspenders clamp
    orchestrator.report_mab_reward(req.arm, reward)
    logger.info("[MAB] reward arm=%d  reward=%.3f", req.arm, reward)
    return {"ok": True, "arm": req.arm, "reward": reward}


@app.post("/honeypot/trigger")
async def honeypot_trigger(req: HoneypotTriggerReq, request: Request):
    """
    SDK calls this when a bot interacts with an injected DOM decoy.

    Always returns HTTP 200 with a plausible payload — bots must not learn
    that this endpoint detects them.

    Flow
    ────
    1. Verify HMAC-SHA256 challenge signature (invalid → fake-200, no DB write)
    2. Validate arm index
    3. Log hit to honeypot collection
    4. Issue strong positive MAB reward
    """
    from .models.stage2_honeypot import verify_challenge_signature

    valid = verify_challenge_signature(
        challenge_id  = req.challenge_id,
        arm           = req.arm,
        expires_at    = req.expires_at,
        decoy_ids     = req.decoy_ids,
        signature     = req.signature,
        shadow_secret = SHADOW_SECRET,
    )
    if not valid:
        logger.warning(
            "[Trigger] Invalid/expired challenge: id=%s arm=%d src=%s",
            req.challenge_id, req.arm, _client_ip(request),
        )
        return {"ok": True, "status": "recorded"}

    if not (0 <= req.arm < mab_agent.n_arms):
        logger.warning("[Trigger] Invalid arm %d in trigger payload", req.arm)
        return {"ok": True, "status": "recorded"}

    try:
        await store_honeypot_entry(
            db_handler.db,
            user_agent = request.headers.get("user-agent", ""),
            theta      = 0.0,
            ip_address = _client_ip(request),
            path       = "/honeypot/trigger",
            headers    = dict(request.headers),
        )
    except Exception as exc:
        logger.error("[Trigger] DB write failed: %s", exc)

    orchestrator.report_mab_reward(req.arm, 1.0)
    logger.info(
        "[Trigger] Bot caught: challenge=%s arm=%d decoy=%s event=%s kind=%s",
        req.challenge_id, req.arm,
        req.triggered_decoy, req.trigger_event, req.trigger_kind,
    )
    return {"ok": True, "status": "recorded"}


# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(req: UserCreate, request: Request):
    """
    Register a new user and open an initial session.

    The DQN governor selects the Argon2id preset based on current server load,
    binding account security to real-world conditions.  The initial session has
    a 20-minute window — shorter than normal because no behavioural baseline
    exists yet.
    """
    if await user_exists(db_handler.db, req.email):
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail      = "An account with that email already exists",
        )

    bio_raw = BiometricInput(
        theta=0.9, h_exp=0.9, server_load=0.4,
        user_agent="", latent_vector=[], ip_address="register",
    )
    bio = s1.run_legacy(bio_raw)
    gov = s3.run(bio, dqn_agent, ppo_agent)

    ph            = PasswordHasher(memory_cost=gov.memory_kb, time_cost=gov.time_cost, parallelism=gov.parallelism)
    password_hash = ph.hash(req.plain_password)

    try:
        user_id = await create_user(db_handler.db, req.email, password_hash)
    except Exception as exc:
        logger.error("[Auth] Register — user creation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to register user")

    initial_lv    = [0.0] * 32
    session_token = _make_session_token(user_id, initial_lv, SESSION_SECRET)
    try:
        await create_session(
            db_handler.db,
            user_id            = user_id,
            session_token      = session_token,
            latent_vector      = initial_lv,
            expires_in_minutes = 20,
        )
    except Exception as exc:
        logger.error("[Auth] Register — session creation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create session after registration")

    try:
        await update_user_security_level(db_handler.db, user_id, gov.preset.value)
    except Exception:
        pass  # non-critical

    logger.info("[Auth] Registered %s  preset=%s", req.email, gov.preset.value)
    return {
        "success":        True,
        "user_id":        user_id,
        "email":          req.email,
        "session_token":  session_token,
        "security_level": gov.preset.value,
    }


@app.post("/auth/login")
async def login(req: UserLogin, request: Request):
    """
    Email + password login.

    A fresh session document is always created on successful login — prior
    tokens are never re-used to prevent replay attacks.  Initial trust = 1.0;
    decays on subsequent heartbeats.
    """
    try:
        user = await get_user_by_email(db_handler.db, req.email)
        if not user:
            PasswordHasher().hash("dummy_constant_work")   # constant-time
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not user.get("is_active", False):
            raise HTTPException(status_code=403, detail="Account is inactive")

        try:
            PasswordHasher().verify(user["password_hash"], req.plain_password)
        except VerifyMismatchError:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user_id       = user["_id"]
        initial_lv    = [0.0] * 32
        session_token = _make_session_token(user_id, initial_lv, SESSION_SECRET)
        await update_last_login(db_handler.db, user_id)
        await create_session(
            db_handler.db,
            user_id            = user_id,
            session_token      = session_token,
            latent_vector      = initial_lv,
            expires_in_minutes = 30,
        )

        logger.info("[Auth] Login: %s", req.email)
        return {
            "success":        True,
            "session_token":  session_token,
            "user_id":        user_id,
            "email":          user["email"],
            "security_level": user.get("security_level", "standard"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[Auth] Login error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Login failed")


@app.post("/auth/logout")
async def logout(req: LogoutReq):
    """Invalidate a session.  Token in the request body, never the URL."""
    try:
        await invalidate_session(db_handler.db, req.session_token)
        return {"success": True, "message": "Logged out successfully"}
    except Exception as exc:
        logger.error("[Auth] Logout error: %s", exc)
        raise HTTPException(status_code=500, detail="Logout failed")


# ─────────────────────────────────────────────────────────────────────────────
# Protected: /me
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/me")
async def me(session: ActiveSession):
    """
    Returns the authenticated user's profile.  Demonstrates `require_active_session`.
    """
    user_id = session["user_id"]
    try:
        user = await get_user_by_id(db_handler.db, user_id)
    except Exception as exc:
        logger.error("[Me] DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve profile")

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id":        user_id,
        "email":          user.get("email"),
        "security_level": user.get("security_level", "standard"),
        "last_login":     user.get("last_login"),
        "created_at":     user.get("created_at"),
        "trust_score":    session.get("trust_score", 1.0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Password utilities
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/password/hash")
async def pw_hash(req: PwHashReq, user_id: Optional[str] = None):
    bio_raw = BiometricInput(
        theta=req.theta, h_exp=req.h_exp, server_load=0.5,
        user_agent="", latent_vector=[], ip_address="hash",
    )
    bio = s1.run_legacy(bio_raw)
    gov = s3.run(bio, dqn_agent, ppo_agent)
    ph  = PasswordHasher(memory_cost=gov.memory_kb, time_cost=gov.time_cost, parallelism=gov.parallelism)
    t0  = time.perf_counter()
    h   = ph.hash(req.plain_password)
    ms  = (time.perf_counter() - t0) * 1000

    if user_id:
        try:
            await update_user_security_level(db_handler.db, user_id, gov.preset.value)
        except Exception:
            pass

    return {
        "hash":          h,
        "action":        gov.preset.value,
        "elapsed_ms":    round(ms, 2),
        "argon2_params": {"m": gov.memory_kb, "t": gov.time_cost, "p": gov.parallelism},
        "confidence":    gov.confidence.value,
        "fallback":      gov.fallback,
    }


@app.post("/password/verify")
async def pw_verify(req: PwHashReq):
    try:
        PasswordHasher().verify(req.stored_hash, req.plain_password)
        return {"valid": True}
    except VerifyMismatchError:
        return {"valid": False}


# ─────────────────────────────────────────────────────────────────────────────
# Honeypot / admin
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/honeypot/signatures")
async def signatures():
    try:
        db_sigs = await get_honeypot_signatures(db_handler.db, limit=100)
        count   = await get_honeypot_count(db_handler.db)
        return {"signatures": db_sigs, "count": count}
    except Exception as exc:
        logger.error("[Honeypot] Fetch error: %s", exc)
        return {"signatures": [], "count": 0}


@app.get("/admin/honeypot/dashboard")
async def honeypot_dashboard():
    try:
        count = await get_honeypot_count(db_handler.db)
        sigs  = await get_honeypot_signatures(db_handler.db, limit=50)
        return {"total_count": count, "recent_signatures": sigs, "timestamp": time.time()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/admin/models-status")
async def models_status():
    return {
        "models": {
            "dqn":   {"status": "loaded", "type": "Deep Q-Network",               "stage": 3},
            "mab":   {
                "status":     "loaded",
                "type":       "Multi-Armed Bandit",
                "n_arms":     mab_agent.n_arms,
                "arm_values": mab_agent.values.tolist(),
                "stage":      2,
            },
            "ppo":   {"status": "loaded", "type": "Proximal Policy Optimization", "stage": 4},
            "cnn1d": {"status": "loaded", "type": "1-D Convolutional Network",    "stage": 1},
        },
        "pipeline": {
            "stages":    ["biometric", "honeypot", "governor", "watchdog"],
            "contracts": "pipeline/contracts.py",
        },
        "timestamp": time.time(),
    }


@app.get("/admin/pipeline-debug")
async def pipeline_debug(
    theta:       float = Query(0.5),
    h_exp:       float = Query(0.5),
    server_load: float = Query(0.4),
):
    raw    = BiometricInput(
        theta=theta, h_exp=h_exp, server_load=server_load,
        user_agent="debug", latent_vector=[0.0] * 32, ip_address="127.0.0.1",
    )
    result = orchestrator.run(raw)
    return {
        "shadow_mode":         result.shadow_mode,
        "action_label":        result.action_label,
        "pipeline_confidence": result.pipeline_confidence.value,
        "degraded":            result.degraded,
        "stages": {
            "biometric": {
                "verdict":    result.biometric.verdict.value,
                "confidence": result.biometric.confidence.value,
                "is_bot":     result.biometric.is_bot,
                "note":       result.biometric.note,
            },
            "honeypot": {
                "should_shadow":  result.honeypot.should_shadow,
                "mab_arm":        result.honeypot.mab_arm_selected,
                "mab_confidence": result.honeypot.mab_confidence.value,
            },
            "governor": {
                "preset":     result.governor.preset.value,
                "memory_mb":  result.governor.memory_kb // 1024,
                "time_cost":  result.governor.time_cost,
                "confidence": result.governor.confidence.value,
                "fallback":   result.governor.fallback,
            },
            "watchdog": {
                "action":     result.watchdog.action.value     if result.watchdog else None,
                "confidence": result.watchdog.confidence.value if result.watchdog else None,
                "reason":     result.watchdog.reason           if result.watchdog else None,
            },
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Biometric / CNN
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/biometric/extract")
async def biometric_extract(req: BiometricExtractReq):
    try:
        features = cnn_model.extract(req.raw_signal)
        return {"success": True, "features": features, "dim": len(features)}
    except Exception as exc:
        logger.error("[CNN] Extract error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Feature extraction failed")


@app.get("/biometric/profile/{user_id}")
async def get_biometric_profile_api(user_id: str, session: ActiveSession):
    """
    Protected by the session guard.  Callers may only read their own profile.
    """
    if session.get("user_id") != user_id:
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail      = "Cannot access another user's biometric profile",
        )
    try:
        profile = await get_biometric_profile(db_handler.db, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Biometric profile not found")
        return {"user_id": user_id, "profile": profile}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[Biometric] Profile fetch error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve profile")


@app.post("/biometric/profile")
async def sync_biometric_profile(req: BiometricProfileSyncReq, session: ActiveSession, request: Request):
    """
    Persist the active user's biometric typing pattern.

    The profile-build page calls this while the user types, so MongoDB stores
    both the summary stats and the rolling sample history for that user.
    """
    user_id = session["user_id"]
    ip = _client_ip(request)

    keyboard_stats = req.keyboard_stats or {}
    pointer_stats = req.pointer_stats or {}
    profile_stats = req.profile_stats or {}

    dwell = float(keyboard_stats.get("avgDwell", 0.0) or 0.0)
    flight = float(keyboard_stats.get("avgFlight", 0.0) or 0.0)
    rhythm = float(keyboard_stats.get("rhythm", 0.0) or 0.0)
    pause = float(keyboard_stats.get("avgPause", 0.0) or 0.0)
    speed = float(pointer_stats.get("avgSpeed", 0.0) or 0.0)
    jitter = float(pointer_stats.get("avgJitter", 0.0) or 0.0)
    accel = float(pointer_stats.get("avgAccel", 0.0) or 0.0)
    bigram = float(req.h_exp)

    try:
        await store_biometric_sample(
            db_handler.db,
            user_id   = user_id,
            theta     = req.theta,
            h_exp     = req.h_exp,
            dwell     = dwell,
            flight    = flight,
            speed     = speed,
            jitter    = jitter,
            accel     = accel,
            rhythm    = rhythm,
            pause     = pause,
            bigram    = bigram,
            device_ip = ip,
        )

        summary = {
            "sample_count":       int(profile_stats.get("sampleCount", 0) or 0),
            "last_drift":         float(profile_stats.get("lastDrift", req.live_drift or 0.0) or 0.0),
            "adaptive_threshold":  float(profile_stats.get("adaptiveThreshold", 0.0) or 0.0),
            "selected_features":  profile_stats.get("selectedFeatures", []),
            "feature_means":      profile_stats.get("featureMeans", []),
            "updated_at":         datetime.utcnow(),
            "source":             "profile-build",
        }

        await upsert_biometric_profile(
            db_handler.db,
            user_id            = user_id,
            sample_count       = summary["sample_count"],
            last_drift         = summary["last_drift"],
            adaptive_threshold = summary["adaptive_threshold"],
            feature_means      = summary["feature_means"],
            selected_features  = summary["selected_features"],
            ema_profile        = profile_stats.get("emaProfile"),
            ema_variance       = profile_stats.get("emaVariance"),
        )

        await db_handler.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"biometric_profile": summary, "updated_at": datetime.utcnow()}},
        )

        profile = await get_biometric_profile(db_handler.db, user_id)
        return {
            "success": True,
            "user_id": user_id,
            "profile": profile,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[Biometric] Profile sync failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to store biometric profile")


# ─────────────────────────────────────────────────────────────────────────────
# Integration API — Session Trust Verification
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/session/trust",
    response_model = SessionTrustResponse,
    summary        = "Verify session trust before a sensitive transaction",
    tags           = ["Integration API"],
)
async def verify_session_trust(req: SessionTrustRequest) -> SessionTrustResponse:
    """
    Customer backends call this **before authorising a sensitive transaction**
    (payment, password change, data export, etc.).

    Decision logic
    ──────────────
    1. Retrieve DB-persisted watchdog state for the session.
    2. Take the more pessimistic value between stored and request signals.
    3. Apply risk-adjusted scoring: high-risk transactions demand higher trust.
    4. Emit `ep.anomaly.detected` webhook if action = deny.

    Action mapping
    ──────────────
    allow     — proceed with the transaction
    challenge — step-up MFA recommended before proceeding
    deny      — block the transaction; force re-authentication
    """
    now = datetime.now(timezone.utc).isoformat()

    # Prefer the DB-persisted session state; fall back to request signals
    try:
        db_session = await get_session(db_handler.db, req.session_token)
    except Exception:
        db_session = None

    reasons: list[str] = []

    if db_session:
        stored_trust = float(db_session.get("trust_score", 1.0))
        stored_e_rec = float(db_session.get("e_rec", 0.0))
    else:
        stored_trust = req.trust_score if req.trust_score is not None else 0.7
        stored_e_rec = req.e_rec       if req.e_rec is not None       else 0.0
        reasons.append("no_db_session_data")

    # Take the more pessimistic value
    trust = min(stored_trust, req.trust_score) if req.trust_score is not None else stored_trust
    e_rec = max(stored_e_rec, req.e_rec)       if req.e_rec is not None       else stored_e_rec

    # Risk-adjusted score: trust × (1 − risk × penalty)
    risk_adj = trust * (1 - req.transaction_risk * 0.3)

    # Confidence
    if db_session and req.trust_score is not None:
        confidence = "high"
    elif db_session or req.trust_score is not None:
        confidence = "medium"
    else:
        confidence = "low"
        reasons.append("low_signal")

    # Action decision (using per-customer thresholds)
    thresholds = notification_service.get_thresholds(req.customer_id)

    if e_rec > thresholds.anomaly_e_rec_above * 1.5:
        action = "deny"
        reasons.append(f"e_rec={e_rec:.4f} above hard limit")
    elif risk_adj < 0.25 or trust < 0.2:
        action = "deny"
        reasons.append(f"risk_adjusted={risk_adj:.3f} critically low")
    elif risk_adj < 0.45 or trust < 0.4 or e_rec > thresholds.anomaly_e_rec_above:
        action = "challenge"
        reasons.append(f"risk_adjusted={risk_adj:.3f} requires step-up")
    else:
        action = "allow"
        reasons.append("trust within acceptable bounds")

    if action == "deny":
        notification_service.notify_anomaly(
            user_id     = req.user_id,
            session_id  = req.session_token,
            e_rec       = e_rec,
            trust_score = trust,
            drift       = float(db_session.get("drift", 0.0)) if db_session else 0.0,
            reason      = f"Transaction blocked (risk={req.transaction_risk:.2f}): " + "; ".join(reasons),
            customer_id = req.customer_id,
        )

    logger.info(
        "[Trust] user=%s action=%s trust=%.3f risk_adj=%.3f e_rec=%.4f tx_risk=%.2f",
        req.user_id, action, trust, risk_adj, e_rec, req.transaction_risk,
    )

    return SessionTrustResponse(
        session_id    = req.session_token,
        user_id       = req.user_id,
        trust_score   = round(trust, 4),
        e_rec         = round(e_rec, 5),
        action        = action,
        confidence    = confidence,
        risk_adjusted = round(risk_adj, 4),
        reasons       = reasons,
        timestamp     = now,
    )


@app.get(
    "/session/trust/{session_id}",
    response_model = SessionTrustResponse,
    summary        = "Poll current trust score for a session",
    tags           = ["Integration API"],
)
async def get_session_trust(session_id: str) -> SessionTrustResponse:
    """
    Lightweight poll for the current trust posture without re-running the
    pipeline.  Suitable for SSE polling on the customer dashboard.
    Reads directly from MongoDB so the value is always authoritative.
    """
    try:
        db_session = await get_session(db_handler.db, session_id)
    except Exception as exc:
        logger.error("[Trust/Poll] DB error: %s", exc)
        raise HTTPException(status_code=503, detail="Session store unavailable")

    if not db_session:
        raise HTTPException(
            status_code = 404,
            detail      = f"Session '{session_id}' not found or expired.",
        )

    trust         = float(db_session.get("trust_score", 1.0))
    e_rec         = float(db_session.get("e_rec", 0.0))
    stored_action = db_session.get("last_watchdog_action", "ok")

    action_map = {
        "ok":                     "allow",
        "passive_reauth":         "challenge",
        "disable_sensitive_apis": "challenge",
        "force_logout":           "deny",
    }
    return SessionTrustResponse(
        session_id    = session_id,
        user_id       = db_session.get("user_id", ""),
        trust_score   = round(trust, 4),
        e_rec         = round(e_rec, 5),
        action        = action_map.get(stored_action, "allow"),
        confidence    = "high",
        risk_adjusted = round(trust, 4),
        reasons       = [f"last_watchdog_action={stored_action}"],
        timestamp     = db_session.get("updated_at", datetime.now(timezone.utc).isoformat()),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Integration API — Webhook Endpoint Management
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/webhooks/endpoints",
    status_code    = status.HTTP_201_CREATED,
    response_model = EndpointOut,
    summary        = "Register a webhook delivery endpoint",
    tags           = ["Webhooks"],
)
async def register_endpoint(req: EndpointCreate) -> EndpointOut:
    endpoint = WebhookEndpoint(
        id          = str(uuid.uuid4()),
        url         = str(req.url),
        secret      = req.secret,
        events      = req.events,
        customer_id = req.customer_id,
        description = req.description,
    )
    dispatcher.register_endpoint(endpoint)
    logger.info("Registered webhook endpoint %s for customer %s", endpoint.id, req.customer_id)
    return EndpointOut(
        id          = endpoint.id,
        url         = endpoint.url,
        events      = [e.value for e in endpoint.events],
        customer_id = endpoint.customer_id,
        enabled     = endpoint.enabled,
        description = endpoint.description,
    )


@app.get(
    "/webhooks/endpoints",
    response_model = list[EndpointOut],
    summary        = "List registered webhook endpoints",
    tags           = ["Webhooks"],
)
async def list_endpoints(customer_id: str | None = Query(None)) -> list[EndpointOut]:
    return [
        EndpointOut(
            id          = ep.id,
            url         = ep.url,
            events      = [e.value for e in ep.events],
            customer_id = ep.customer_id,
            enabled     = ep.enabled,
            description = ep.description,
        )
        for ep in dispatcher.list_endpoints(customer_id=customer_id)
    ]


@app.get(
    "/webhooks/endpoints/{endpoint_id}",
    response_model = EndpointOut,
    summary        = "Get a webhook endpoint",
    tags           = ["Webhooks"],
)
async def get_endpoint(endpoint_id: str) -> EndpointOut:
    ep = dispatcher._endpoints.get(endpoint_id)
    if not ep:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")
    return EndpointOut(
        id=ep.id, url=ep.url, events=[e.value for e in ep.events],
        customer_id=ep.customer_id, enabled=ep.enabled, description=ep.description,
    )


@app.patch(
    "/webhooks/endpoints/{endpoint_id}",
    response_model = EndpointOut,
    summary        = "Update a webhook endpoint",
    tags           = ["Webhooks"],
)
async def update_endpoint(endpoint_id: str, req: EndpointUpdate) -> EndpointOut:
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    if "url" in kwargs:
        kwargs["url"] = str(kwargs["url"])
    ep = dispatcher.update_endpoint(endpoint_id, **kwargs)
    if not ep:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")
    return EndpointOut(
        id=ep.id, url=ep.url, events=[e.value for e in ep.events],
        customer_id=ep.customer_id, enabled=ep.enabled, description=ep.description,
    )


@app.delete(
    "/webhooks/endpoints/{endpoint_id}",
    status_code = status.HTTP_204_NO_CONTENT,
    summary     = "Unregister a webhook endpoint",
    tags        = ["Webhooks"],
)
async def delete_endpoint(endpoint_id: str):
    if endpoint_id not in dispatcher._endpoints:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")
    dispatcher.unregister_endpoint(endpoint_id)


@app.post(
    "/webhooks/endpoints/{endpoint_id}/test",
    response_model = TestDeliveryOut,
    summary        = "Send a test webhook delivery",
    tags           = ["Webhooks"],
)
async def test_endpoint_delivery(endpoint_id: str) -> TestDeliveryOut:
    """Fire a synthetic ep.anomaly.detected to verify connectivity and signing."""
    result = await dispatcher.test_endpoint(endpoint_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")
    return TestDeliveryOut(
        delivery_id = result.delivery_id,
        success     = result.success,
        status_code = result.status_code,
        attempts    = result.attempts,
        latency_ms  = round(result.latency_ms, 2),
        error       = result.error,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Integration API — Notifications & Thresholds
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/notifications",
    summary = "Query notification / event log",
    tags    = ["Integration API"],
)
async def query_notifications(
    customer_id: str | None      = Query(None),
    user_id:     str | None      = Query(None),
    severity:    Severity | None = Query(None),
    event_type:  str | None      = Query(None),
    limit:       int             = Query(100, ge=1, le=500),
) -> dict:
    records = notification_service.query_log(
        customer_id = customer_id,
        user_id     = user_id,
        severity    = severity,
        event_type  = event_type,
        limit       = limit,
    )
    return {"notifications": records, "count": len(records)}


@app.get(
    "/notifications/stats",
    summary = "Aggregated notification counts",
    tags    = ["Integration API"],
)
async def notification_stats(customer_id: str | None = Query(None)) -> dict:
    return notification_service.stats(customer_id=customer_id)


@app.post(
    "/notifications/thresholds",
    status_code = status.HTTP_204_NO_CONTENT,
    summary     = "Configure alert thresholds for a customer",
    tags        = ["Integration API"],
)
async def set_thresholds(customer_id: str, config: ThresholdConfig):
    notification_service.set_thresholds(
        customer_id,
        AlertThresholds(
            trust_degraded_below = config.trust_degraded_below,
            anomaly_e_rec_above  = config.anomaly_e_rec_above,
            anomaly_drift_above  = config.anomaly_drift_above,
            bot_theta_below      = config.bot_theta_below,
        ),
    )


@app.get(
    "/notifications/thresholds/{customer_id}",
    summary = "Get alert thresholds for a customer",
    tags    = ["Integration API"],
)
async def get_thresholds(customer_id: str) -> dict:
    t = notification_service.get_thresholds(customer_id)
    return {
        "customer_id":          customer_id,
        "trust_degraded_below": t.trust_degraded_below,
        "anomaly_e_rec_above":  t.anomaly_e_rec_above,
        "anomaly_drift_above":  t.anomaly_drift_above,
        "bot_theta_below":      t.bot_theta_below,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":    "ok",
        "version":   "3.2.0",
        "pipeline":  "active" if orchestrator is not None else "starting",
        "stages":    4,
        "timestamp": time.time(),
    }