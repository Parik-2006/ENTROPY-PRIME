"""
backend/main.py — Entropy Prime FastAPI Application  v4.0.0
============================================================
Four-stage zero-trust biometric authentication pipeline with full
Integration API, outgoing webhook delivery, and multi-tenant
profile-build onboarding state machine.

Stages
------
  1  Biological Gateway   — 1D-CNN humanity scoring (θ)
  2  Offensive Deception  — Honeypot injection + MAB shadow sandbox
  3  Resource Governor    — DQN Argon2id parameter selection
  4  Session Watchdog     — Per-user behavioral profile + PPO drift detection

v4.0.0 additions
-----------------
  Profile-build onboarding state machine
  ───────────────────────────────────────
  Every user now progresses through a well-defined lifecycle:
    collecting → syncing → stable → drifted

  The state is stored in `biometric_profiles.onboarding_state` and is the
  single authoritative flag that suppresses or arms drift detection.  The
  watchdog heartbeat reads this flag before running; sessions in `collecting`
  or `syncing` skip the drift check so a fresh account never gets a false-
  positive force-logout.

  New / changed endpoints
  ───────────────────────
  POST   /biometric/profile          — sync payload now writes onboarding_state;
                                       response embeds ProfileBuildStatus
  GET    /biometric/profile/{id}/status — lightweight state-machine status poll
  POST   /biometric/profile/reset    — re-auth path: wipe profile → collecting
  GET    /admin/onboarding-summary   — per-tenant state-machine counts

  /session/verify now reads onboarding_state from MongoDB and suppresses the
  watchdog drift check when the profile is not yet `stable`.

v3.2.0 additions (unchanged)
-----------------------------
  POST   /webhooks/endpoints            — Register a signed delivery endpoint
  GET    /webhooks/endpoints            — List endpoints (filterable by customer_id)
  GET    /webhooks/endpoints/{id}       — Fetch one endpoint
  PATCH  /webhooks/endpoints/{id}       — Update url / secret / events / enabled
  DELETE /webhooks/endpoints/{id}       — Unregister endpoint
  POST   /webhooks/endpoints/{id}/test  — Send a test delivery
  POST   /session/trust                 — Gate check before a sensitive transaction
  GET    /session/trust/{session_id}    — Poll current trust posture
  GET    /notifications                 — Query notification log
  GET    /notifications/stats           — Aggregated event counts
  POST   /notifications/thresholds      — Per-customer alert threshold config
  GET    /notifications/thresholds/{id} — Read per-customer thresholds
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

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import numpy as np
import torch
from bson import ObjectId
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl, model_validator
from starlette.requests import Request

# ── Database layer ────────────────────────────────────────────────────────────
from backend.database import (
    Database,
    ONBOARDING_COLLECTING,
    ONBOARDING_SYNCING,
    ONBOARDING_STABLE,
    ONBOARDING_DRIFTED,
    STABLE_SAMPLE_THRESHOLD,
)
from backend.database import (
    user_exists, create_user, get_user_by_email, get_user_by_id,
    update_last_login, update_user_security_level,
    create_session, get_session, invalidate_session, update_session_trust_score,
    store_biometric_sample, get_biometric_profile, upsert_biometric_profile,
    get_biometric_profile_summary, get_onboarding_state, set_onboarding_state,
    reset_biometric_profile, profile_build_summary,
    store_honeypot_entry, get_honeypot_signatures, get_honeypot_count,
    log_drift_event,
)

# ── Pydantic models ───────────────────────────────────────────────────────────
from backend.models.pydantic_models import UserCreate, UserLogin
from backend.models import OnboardingState, ProfileBuildStatus, STABLE_SAMPLE_THRESHOLD

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

# ── Integration API ───────────────────────────────────────────────────────────
from backend.webhooks import WebhookEndpoint, WebhookEvent, dispatcher
from backend.services.notification_service import (
    AlertThresholds, NotificationService, Severity, notification_service,
)

# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level  = getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("entropy_prime")
logger.info("Starting Entropy Prime v4.0 (log level: %s)", os.environ.get("LOG_LEVEL", "INFO"))

SESSION_SECRET = os.environ.get("EP_SESSION_SECRET", secrets.token_hex(32))
SHADOW_SECRET  = os.environ.get("EP_SHADOW_SECRET",  secrets.token_hex(32))

db_handler = Database()

dqn_agent     = DQNAgent(state_dim=3,  action_dim=4)
mab_agent     = MABAgent(n_arms=3)
gov_ppo_agent = PPOAgent(state_dim=5,  action_dim=4)
ppo_agent     = PPOAgent(state_dim=10, action_dim=3)
cnn_model     = CNN1D(input_channels=8, out_dim=32)

watchdog_service: Optional[WatchdogService] = None
orchestrator:     Optional[PipelineOrchestrator] = None


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint loading  (unchanged from v3.2.0)
# ─────────────────────────────────────────────────────────────────────────────

def _load_checkpoints() -> None:
    ckpt_dir     = os.environ.get("EP_CHECKPOINT_DIR", "checkpoints")
    rl_path      = os.environ.get("EP_RL_CHECKPOINT",      os.path.join(ckpt_dir, "governor.pt"))
    mab_path     = os.environ.get("EP_MAB_CHECKPOINT",     os.path.join(ckpt_dir, "mab.json"))
    gov_ppo_path = os.environ.get("EP_GOV_PPO_CHECKPOINT", os.path.join(ckpt_dir, "governor_ppo.pt"))
    ppo_path     = os.environ.get("EP_PPO_CHECKPOINT",     os.path.join(ckpt_dir, "watchdog.pt"))

    for path, loader, label in [
        (rl_path,      lambda p: dqn_agent.load_checkpoint(p),                                "DQN"),
        (mab_path,     lambda p: mab_agent.load_state_dict(json.load(open(p))),               "MAB"),
        (gov_ppo_path, lambda p: gov_ppo_agent.load_checkpoint(p),                            "GOV_PPO"),
        (ppo_path,     lambda p: ppo_agent.load_checkpoint(p),                                "WATCHDOG_PPO"),
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

    logger.info("🚀 Entropy Prime v4.0 starting up…")

    await db_handler.connect_to_mongo()
    attach_db(db_handler.db)
    load_jwt_public_key()
    _load_checkpoints()

    watchdog_service = WatchdogService(db_handler)

    if os.environ.get("ENVIRONMENT") == "development":
        from database import create_tenant, create_site
        import hmac as _hmac, hashlib

        try:
            if not await db_handler.db.tenants.find_one({"admin_email": "admin@test.com"}):
                tenant_id   = await create_tenant(db_handler.db, "Test Corp", "admin@test.com", "pro")
                raw_api_key = "test-sdk-key-123"
                api_key_secret = os.environ.get("EP_API_KEY_SECRET", "dev-only-api-key-secret-change-me")
                key_digest  = _hmac.new(
                    api_key_secret.encode(), raw_api_key.encode(), hashlib.sha256
                ).hexdigest()
                await create_site(db_handler.db, tenant_id, "Test Site", "localhost", key_digest)
                logger.info("🌱 Database seeded with test tenant and site")
        except Exception as exc:
            logger.warning("Seeding failed (likely non-writable DB): %s", exc)

    orchestrator = PipelineOrchestrator(
        dqn_agent      = dqn_agent,
        mab_agent      = mab_agent,
        gov_ppo_agent  = gov_ppo_agent,
        ppo_agent      = ppo_agent,
        shadow_secret  = SHADOW_SECRET,
        session_secret = SESSION_SECRET,
    )

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
    logger.info("✓ Entropy Prime v4.0 initialised — 4-stage pipeline + onboarding state machine")
    yield

    logger.info("🛑 Entropy Prime shutting down…")
    sweep_task.cancel()
    try:
        await sweep_task
    except Exception:
        pass
    try:
        await db_handler.close_mongo_connection()
    except Exception as exc:
        logger.error("Error during DB shutdown: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Entropy Prime",
    version     = "4.0.0",
    description = (
        "Zero-trust behavioural biometrics engine — "
        "4-stage pipeline + Integration API + multi-tenant onboarding state machine"
    ),
    lifespan = lifespan,
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
# Session Guard dependency  (unchanged from v3.2.0)
# ─────────────────────────────────────────────────────────────────────────────

class _SessionGuardDep:
    async def __call__(self, request) -> dict:
        token = request.headers.get("X-Session-Token")
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(
                status_code = status.HTTP_401_UNAUTHORIZED,
                detail      = "Missing session token (expected X-Session-Token or Authorization: Bearer)",
                headers     = {"WWW-Authenticate": "Bearer"},
            )
        try:
            session = await get_session(db_handler.db, token)
        except Exception as exc:
            logger.error("[SessionGuard] DB error: %s", exc)
            raise HTTPException(status_code=503, detail="Session store unavailable")
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
            combined         = f"{self.user_agent}:{str(self.latent_vector[:8])}"
            self.fingerprint = hashlib.sha256(combined.encode()).hexdigest()[:32]
        return self


class SessionVerifyReq(BaseModel):
    """
    Heartbeat payload for /session/verify.

    `onboarding_state` is now required so the server can suppress drift
    detection for users who have not yet completed profile-build.  If the
    client sends an unknown state, the server defaults to `collecting`
    (safe side: drift detection suppressed).

    `trust_score` from the client is never used as authority — the DB
    value is always preferred.
    """
    session_token:      str
    user_id:            str
    latent_vector:      list[float]
    e_rec:              float = Field(..., ge=0.0)
    fingerprint:        str   = ""
    behavioral_drift:   float | None    = None
    adaptive_threshold: float | None    = None
    selected_features:  list[str]       = Field(default_factory=list)
    sample_count:       int | None      = None
    onboarding_state:   OnboardingState = OnboardingState.COLLECTING

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


class BiometricProfileSyncReq(BaseModel):
    """
    Sync payload from the profile-build page.

    Only aggregated statistics are accepted — raw signals must be stripped
    before transmission.  The client may pass `onboarding_state=stable` to
    request a state transition once its local EMA has stabilised; the server
    validates the sample_count claim before honouring it.
    """
    theta:          float              = Field(0.5, ge=0.0, le=1.0)
    h_exp:          float              = Field(0.0, ge=0.0, le=1.0)
    latent_vector:  list[float]        = Field(default_factory=list)
    practice_text:  str                = ""
    keyboard_stats: dict[str, Any]     = Field(default_factory=dict)
    pointer_stats:  dict[str, Any]     = Field(default_factory=dict)
    profile_stats:  dict[str, Any]     = Field(default_factory=dict)
    live_drift:     float | None       = None
    server_load:    float              = Field(0.5, ge=0.0, le=1.0)
    # Client-requested state transition (only `stable` is honoured; see endpoint)
    requested_state: OnboardingState | None = None

    @model_validator(mode="after")
    def _validate(self):
        if self.latent_vector:
            if len(self.latent_vector) < 32:
                padded = list(self.latent_vector[:32])
                padded.extend([0.0] * (32 - len(padded)))
                object.__setattr__(self, "latent_vector", padded)
            elif len(self.latent_vector) > 32:
                object.__setattr__(self, "latent_vector", list(self.latent_vector[:32]))
        return self


class ProfileResetReq(BaseModel):
    """
    Re-auth re-onboarding: wipes the aggregated profile back to `collecting`.
    Requires an active session (the user must be authenticated).
    """
    reason: str = "reauth"  # e.g. "reauth", "admin_reset", "user_request"


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


# ── Webhook endpoint models  (unchanged from v3.2.0) ─────────────────────────

class EndpointCreate(BaseModel):
    url:         HttpUrl
    secret:      str = Field(min_length=16)
    events:      list[WebhookEvent]
    customer_id: str
    description: str = ""


class EndpointUpdate(BaseModel):
    url:         HttpUrl | None            = None
    secret:      str | None               = None
    events:      list[WebhookEvent] | None = None
    enabled:     bool | None              = None
    description: str | None               = None


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


class SessionTrustRequest(BaseModel):
    session_token:    str
    user_id:          str
    customer_id:      str         = ""
    trust_score:      float | None = Field(None, ge=0.0, le=1.0)
    e_rec:            float | None = Field(None, ge=0.0)
    latent_vector:    list[float]  = Field(default_factory=list)
    transaction_risk: float        = Field(0.5, ge=0.0, le=1.0)


class SessionTrustResponse(BaseModel):
    session_id:       str
    user_id:          str
    trust_score:      float
    e_rec:            float
    action:           str
    confidence:       str
    risk_adjusted:    float
    reasons:          list[str]
    pipeline_version: str = "4.0"
    timestamp:        str


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
    if not watchdog_service:
        return False
    try:
        result = await watchdog_service.is_globally_flagged(fingerprint, ip)
        return result.globally_flagged
    except Exception as exc:
        logger.error("[ThreatGate] Check failed: %s — proceeding", exc)
        return False


async def _ingest_watchdog(tenant_id: str, fingerprint: str, ip: str | None, wd_result) -> None:
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


def _safe_onboarding_state(raw: str) -> str:
    """
    Convert a client-supplied state string to a known constant.
    Falls back to `collecting` for unknown values (safe side).
    """
    known = {
        ONBOARDING_COLLECTING,
        ONBOARDING_SYNCING,
        ONBOARDING_STABLE,
        ONBOARDING_DRIFTED,
    }
    return raw if raw in known else ONBOARDING_COLLECTING


# ─────────────────────────────────────────────────────────────────────────────
# /score  — main pipeline entry point  (unchanged from v3.2.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/score")
async def score(req: ScoreReq, request: Request):
    ip  = _client_ip(request)
    raw = BiometricInput(
        theta         = req.theta,
        h_exp         = req.h_exp,
        server_load   = req.server_load,
        user_agent    = req.user_agent,
        latent_vector = req.latent_vector,
        ip_address    = ip,
    )

    if await _threat_gate(req.fingerprint, ip):
        logger.warning("[/score] Global threat gate tripped: fp=%.8s", req.fingerprint)
        shadow_token = "bot_" + secrets.token_hex(32)
        notification_service.notify_bot_detected(
            user_id = f"anon_{shadow_token[:8]}",
            theta   = req.theta,
            path    = "/score",
            ua      = req.user_agent or "unknown",
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

    result = orchestrator.run(raw)

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
            user_id = f"anon_{result.session_token[:8]}",
            theta   = req.theta,
            path    = "/score",
            ua      = req.user_agent or "unknown",
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

    if result.watchdog is not None:
        wd = result.watchdog
        response["watchdog"] = {
            "action":      wd.action.value,
            "trust_score": wd.trust_score,
            "e_rec":       wd.e_rec,
            "confidence":  wd.confidence.value,
            "reason":      wd.reason,
        }
        await _ingest_watchdog("default", req.fingerprint, ip, wd)
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
# /telemetry  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/telemetry")
async def telemetry(req: TelemetryReq, site: SiteCtx):
    logger.info(
        "[Telemetry] %d events  site=%s  tenant=%s  user=%s",
        len(req.events), site.site_id, site.tenant_id, req.userId,
    )
    return {"status": "ok", "received": len(req.events)}


# ─────────────────────────────────────────────────────────────────────────────
# /session/verify  — continuous watchdog heartbeat (updated)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/session/verify")
async def session_verify(req: SessionVerifyReq, request: Request):
    """
    Continuous identity-drift heartbeat.

    Drift detection is gated on the profile's `onboarding_state`.
    When the state is `collecting` or `syncing`, the watchdog still runs
    (for latent-vector anomaly detection) but FORCE_LOGOUT is suppressed
    and the trust score decay is dampened so a fresh account is never
    falsely logged out before its EMA baseline has stabilised.

    The server re-reads the onboarding state from MongoDB rather than
    trusting the client-supplied value, which prevents a malicious client
    from permanently suppressing drift detection by always sending
    `onboarding_state=collecting`.
    """
    # ── 1. Validate session ───────────────────────────────────────────────────
    try:
        session = await get_session(db_handler.db, req.session_token)
    except Exception as exc:
        logger.error("[SessionVerify] DB read failed: %s", exc)
        raise HTTPException(status_code=503, detail="Session store unavailable")

    if session is None:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Invalid or expired session",
            headers     = {"WWW-Authenticate": "Bearer"},
        )

    if session.get("user_id") != req.user_id:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Session / user_id mismatch",
        )

    # ── 2. Read authoritative onboarding state from DB ────────────────────────
    db_onboarding_state = await get_onboarding_state(db_handler.db, req.user_id)

    # ── 3. DB trust score is authoritative ────────────────────────────────────
    db_trust: float = float(session.get("trust_score", 1.0))

    # ── 4. Cross-site threat gate ─────────────────────────────────────────────
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
            "onboarding_state":   db_onboarding_state,
        }

    # ── 5. Run watchdog ───────────────────────────────────────────────────────
    wd = orchestrator.run_watchdog(
        latent_vector = req.latent_vector,
        e_rec         = req.e_rec,
        trust_score   = db_trust,
    )

    # ── 6. Apply onboarding gate ──────────────────────────────────────────────
    # If the profile is still being built, demote FORCE_LOGOUT to a softer
    # action so the user is never kicked out during initial calibration.
    # PASSIVE_REAUTH and OK are passed through unchanged.
    drift_armed = db_onboarding_state == ONBOARDING_STABLE
    if not drift_armed and wd.action == WatchdogAction.FORCE_LOGOUT:
        logger.info(
            "[SessionVerify] FORCE_LOGOUT suppressed (onboarding=%s) for user=%s",
            db_onboarding_state, req.user_id,
        )
        # Downgrade to passive_reauth so the UX asks rather than kicks
        from backend.pipeline.contracts import WatchdogResult, WatchdogAction as WA, Confidence
        wd = WatchdogResult(
            action      = WA.PASSIVE_REAUTH,
            trust_score = wd.trust_score,
            e_rec       = wd.e_rec,
            confidence  = wd.confidence,
            reason      = f"drift_detection_suppressed(onboarding={db_onboarding_state})",
        )

    logger.info(
        "[SessionVerify] user=%s action=%s trust %.3f→%.3f e_rec=%.3f conf=%s onboarding=%s",
        req.user_id, wd.action.value, db_trust, wd.trust_score,
        wd.e_rec, wd.confidence.value, db_onboarding_state,
    )

    # ── 7. Persist updated trust score ────────────────────────────────────────
    try:
        await update_session_trust_score(db_handler.db, req.session_token, wd.trust_score)
    except Exception as exc:
        logger.warning("[SessionVerify] trust-score persist failed: %s", exc)

    # ── 8. Invalidate on FORCE_LOGOUT (only when drift is armed) ──────────────
    session_invalidated = wd.action == WatchdogAction.FORCE_LOGOUT and drift_armed
    if session_invalidated:
        try:
            await invalidate_session(db_handler.db, req.session_token)
            # Mark the profile as drifted so subsequent logins know to reset
            await set_onboarding_state(db_handler.db, req.user_id, ONBOARDING_DRIFTED)
            logger.info(
                "[SessionVerify] Session invalidated + profile→drifted: user=%s",
                req.user_id,
            )
        except Exception as exc:
            logger.error("[SessionVerify] Session invalidation failed: %s", exc)

    # ── 9. Log drift event when profile is stable and action is not OK ─────────
    if drift_armed and wd.action != WatchdogAction.OK:
        try:
            await log_drift_event(
                db_handler.db,
                user_id            = req.user_id,
                drift_score        = req.behavioral_drift or 0.0,
                adaptive_threshold = req.adaptive_threshold or 1.8,
                trust_score        = wd.trust_score,
                e_rec              = wd.e_rec,
                selected_features  = req.selected_features,
                action             = wd.action.value,
                session_token      = req.session_token,
            )
        except Exception as exc:
            logger.warning("[SessionVerify] Drift event log failed: %s", exc)

    # ── 10. Cross-site ingest + notification routing ───────────────────────────
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
        "onboarding_state":   db_onboarding_state,
        "drift_detection_armed": drift_armed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# /honeypot  (unchanged from v3.2.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/honeypot/reward")
async def honeypot_reward(req: MabRewardReq):
    n_arms = mab_agent.n_arms
    if not (0 <= req.arm < n_arms):
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail      = f"arm must be in [0, {n_arms - 1}]; got {req.arm}",
        )
    reward = max(-1.0, min(1.0, req.reward))
    orchestrator.report_mab_reward(req.arm, reward)
    return {"ok": True, "arm": req.arm, "reward": reward}


@app.post("/honeypot/trigger")
async def honeypot_trigger(req: HoneypotTriggerReq, request: Request):
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
        return {"ok": True, "status": "recorded"}

    if not (0 <= req.arm < mab_agent.n_arms):
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
    return {"ok": True, "status": "recorded"}


# ─────────────────────────────────────────────────────────────────────────────
# Authentication  (unchanged from v3.2.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(req: UserCreate, request: Request):
    if await user_exists(db_handler.db, req.email):
        raise HTTPException(status_code=409, detail="An account with that email already exists")

    bio_raw = BiometricInput(
        theta=0.9, h_exp=0.9, server_load=0.4,
        user_agent="", latent_vector=[], ip_address="register",
    )
    bio = s1.run_legacy(bio_raw)
    gov = s3.run(bio, dqn_agent, gov_ppo_agent)

    ph            = PasswordHasher(memory_cost=gov.memory_kb, time_cost=gov.time_cost, parallelism=gov.parallelism)
    password_hash = ph.hash(req.plain_password)

    try:
        user_id = await create_user(db_handler.db, req.email, password_hash)
    except Exception as exc:
        logger.error("[Auth] Register failed: %s", exc, exc_info=True)
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
        logger.error("[Auth] Session creation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create session after registration")

    # Seed an empty profile in `collecting` state so /session/verify has a
    # document to read immediately — avoids a missing-document race on the
    # very first heartbeat.
    try:
        await upsert_biometric_profile(
            db_handler.db,
            user_id            = user_id,
            sample_count       = 0,
            last_drift         = 0.0,
            adaptive_threshold = 1.8,
            feature_means      = [0.5] * 8,
            selected_features  = [],
            onboarding_state   = ONBOARDING_COLLECTING,
        )
    except Exception as exc:
        logger.warning("[Auth] Profile seed failed (non-fatal): %s", exc)

    try:
        await update_user_security_level(db_handler.db, user_id, gov.preset.value)
    except Exception:
        pass

    logger.info("[Auth] Registered %s  preset=%s", req.email, gov.preset.value)
    return {
        "success":          True,
        "user_id":          user_id,
        "email":            req.email,
        "session_token":    session_token,
        "security_level":   gov.preset.value,
        "onboarding_state": ONBOARDING_COLLECTING,
    }


@app.post("/auth/login")
async def login(req: UserLogin, request: Request):
    try:
        user = await get_user_by_email(db_handler.db, req.email)
        if not user:
            PasswordHasher().hash("dummy_constant_work")
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

        # Fetch the current onboarding state to return to the client
        # so the router can decide which page to land on.
        ob_state = await get_onboarding_state(db_handler.db, user_id)

        # A drifted profile means the last session ended abnormally.
        # Reset to collecting so the user rebuilds a clean baseline.
        if ob_state == ONBOARDING_DRIFTED:
            await reset_biometric_profile(db_handler.db, user_id)
            ob_state = ONBOARDING_COLLECTING
            logger.info("[Auth] Login: drifted profile reset for user=%s", user_id)

        logger.info("[Auth] Login: %s  onboarding=%s", req.email, ob_state)
        return {
            "success":          True,
            "session_token":    session_token,
            "user_id":          user_id,
            "email":            user["email"],
            "security_level":   user.get("security_level", "standard"),
            "onboarding_state": ob_state,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[Auth] Login error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Login failed")


@app.post("/auth/logout")
async def logout(req: Optional[LogoutReq] = None, session_token: Optional[str] = None):
    token = session_token
    if not token and req:
        token = req.session_token
    if not token:
        raise HTTPException(status_code=422, detail="session_token required")

    try:
        await invalidate_session(db_handler.db, token)
        return {"success": True, "message": "Logged out successfully"}
    except Exception as exc:
        logger.error("[Auth] Logout error: %s", exc)
        raise HTTPException(status_code=500, detail="Logout failed")


# ─────────────────────────────────────────────────────────────────────────────
# Protected: /me  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/me")
async def me(session: dict = Depends(require_active_session)):
    user_id = session["user_id"]
    try:
        user = await get_user_by_id(db_handler.db, user_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to retrieve profile")

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    ob_state = await get_onboarding_state(db_handler.db, user_id)

    return {
        "user_id":          user_id,
        "email":            user.get("email"),
        "security_level":   user.get("security_level", "standard"),
        "last_login":       user.get("last_login"),
        "created_at":       user.get("created_at"),
        "trust_score":      session.get("trust_score", 1.0),
        "onboarding_state": ob_state,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Password utilities  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/password/hash")
async def pw_hash(req: PwHashReq, user_id: Optional[str] = None):
    bio_raw = BiometricInput(
        theta=req.theta, h_exp=req.h_exp, server_load=0.5,
        user_agent="", latent_vector=[], ip_address="hash",
    )
    bio = s1.run_legacy(bio_raw)
    gov = s3.run(bio, dqn_agent, gov_ppo_agent)
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


@app.get("/biometric/profile/{user_id}/status")
async def get_profile_status(
    user_id: str,
    session: dict = Depends(require_active_session),
):
    """
    Lightweight onboarding state poll.  Returns only the ProfileBuildStatus
    fields — not the full profile document.  Called frequently by the
    ProfileBuildPage to update its progress bar and state machine.
    """
    if session.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's profile status")

    try:
        profile = await get_biometric_profile_summary(db_handler.db, user_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to read profile status")

    if not profile:
        # Return a default collecting status for new users
        return ProfileBuildStatus(
            user_id               = user_id,
            tenant_id             = None,
            onboarding_state      = OnboardingState.COLLECTING,
            sample_count          = 0,
            progress              = 0.0,
            drift_detection_armed = False,
            last_drift            = 0.0,
            adaptive_threshold    = 1.8,
            selected_features     = [],
            updated_at            = None,
        )

    return ProfileBuildStatus.from_profile(profile)


@app.get("/biometric/profile/{user_id}")
async def get_biometric_profile_api(
    user_id: str,
    session: dict = Depends(require_active_session),
):
    if session.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's biometric profile")
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
async def sync_biometric_profile(
    req: BiometricProfileSyncReq,
    session: dict = Depends(require_active_session),
):
    """
    Persist the active user's aggregated biometric typing pattern.

    State machine transitions allowed from the client:
      collecting  →  syncing   (automatic, server sets it before the write)
      syncing     →  stable    (client may request this when sample_count >= threshold)
      stable      →  stable    (updates EMA and drift; may transition to drifted if
                                last_drift > adaptive_threshold)

    Disallowed client transitions (silently ignored):
      collecting  →  drifted   (only the watchdog can set drifted)
      stable      →  collecting (use POST /biometric/profile/reset instead)
      drifted     →  any        (use POST /biometric/profile/reset instead)

    Raw keystroke / mouse coordinate data must be stripped before this
    payload is constructed — only aggregated metrics are accepted.
    """
    user_id    = session["user_id"]
    tenant_id  = session.get("tenant_id")
    site_id    = session.get("site_id")

    keyboard_stats = req.keyboard_stats or {}
    pointer_stats  = req.pointer_stats  or {}
    profile_stats  = req.profile_stats  or {}

    dwell  = float(keyboard_stats.get("avgDwell",  0.0) or 0.0)
    flight = float(keyboard_stats.get("avgFlight", 0.0) or 0.0)
    rhythm = float(keyboard_stats.get("rhythm",    0.0) or 0.0)
    pause  = float(keyboard_stats.get("avgPause",  0.0) or 0.0)
    speed  = float(pointer_stats.get("avgSpeed",   0.0) or 0.0)
    jitter = float(pointer_stats.get("avgJitter",  0.0) or 0.0)
    accel  = float(pointer_stats.get("avgAccel",   0.0) or 0.0)
    bigram = float(req.h_exp)

    client_sample_count = int(profile_stats.get("sampleCount", 0) or 0)
    last_drift         = float(profile_stats.get("lastDrift",       req.live_drift or 0.0) or 0.0)
    adaptive_threshold = float(profile_stats.get("adaptiveThreshold", 0.0) or 0.0)
    selected_features  = profile_stats.get("selectedFeatures", [])
    feature_means      = profile_stats.get("featureMeans", [])
    ema_profile        = profile_stats.get("emaProfile")
    ema_variance       = profile_stats.get("emaVariance")

    # ── Resolve requested state transition ─────────────────────────────────────
    # Fetch the current DB state before we decide what to write.
    existing_profile = await get_biometric_profile_summary(db_handler.db, user_id)
    current_state    = (existing_profile or {}).get("onboarding_state", ONBOARDING_COLLECTING)
    existing_sample_count = int((existing_profile or {}).get("sample_count", 0) or 0)

    # Server-authoritative sample count: each completed sync advances the
    # profile by exactly one aggregated sample, independent of the client's claim.
    sample_count = existing_sample_count + 1

    if client_sample_count and client_sample_count != sample_count:
        logger.warning(
            "[Biometric] sample_count claim mismatch: client=%d server=%d user=%s",
            client_sample_count, sample_count, user_id,
        )

    # We set syncing first (transient flag that the write is in progress)
    # and then resolve to the correct terminal state.
    target_state: str
    if current_state in (ONBOARDING_DRIFTED,):
        # Drifted profiles cannot be updated via sync — use /reset endpoint.
        raise HTTPException(
            status_code = 409,
            detail      = (
                "Profile is in 'drifted' state. "
                "Use POST /biometric/profile/reset after re-authentication."
            ),
        )
    elif current_state == ONBOARDING_STABLE:
        # Stay stable unless drift says otherwise; _derive_onboarding_state
        # handles the stable→drifted transition inside upsert_biometric_profile.
        target_state = ONBOARDING_STABLE
    elif (
        req.requested_state == OnboardingState.STABLE
        and sample_count >= STABLE_SAMPLE_THRESHOLD
    ):
        # Client explicitly requested stable and has enough samples
        target_state = ONBOARDING_STABLE
    elif sample_count >= STABLE_SAMPLE_THRESHOLD:
        # Threshold crossed; transition via syncing
        target_state = ONBOARDING_SYNCING
    else:
        target_state = ONBOARDING_COLLECTING

    try:
        # EMA update for rolling averages
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
            device_ip = "?",
        )

        # Full summary upsert — this is what the watchdog reads
        await upsert_biometric_profile(
            db_handler.db,
            user_id            = user_id,
            sample_count       = sample_count,
            last_drift         = last_drift,
            adaptive_threshold = adaptive_threshold,
            feature_means      = feature_means,
            selected_features  = selected_features,
            tenant_id          = tenant_id,
            site_id            = site_id,
            ema_profile        = ema_profile,
            ema_variance       = ema_variance,
            onboarding_state   = target_state,
        )

        # Reflect stable back to syncing→stable: if we wrote syncing, now
        # confirm stable immediately (syncing is only needed within a write
        # race window that doesn't exist here since we await the upsert).
        if target_state == ONBOARDING_SYNCING:
            await set_onboarding_state(db_handler.db, user_id, ONBOARDING_STABLE)
            target_state = ONBOARDING_STABLE

        # Sync the condensed summary onto the user document as well
        await db_handler.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {
                "biometric_profile": {
                    "sample_count":       sample_count,
                    "last_drift":         last_drift,
                    "adaptive_threshold": adaptive_threshold,
                    "selected_features":  selected_features,
                    "onboarding_state":   target_state,
                    "updated_at":         datetime.utcnow(),
                    "source":             "profile-build",
                },
                "updated_at": datetime.utcnow(),
            }},
        )

        profile = await get_biometric_profile_summary(db_handler.db, user_id)
        status_obj = ProfileBuildStatus.from_profile(profile) if profile else ProfileBuildStatus(
            user_id=user_id, tenant_id=tenant_id, onboarding_state=OnboardingState(target_state),
            sample_count=sample_count, progress=min(sample_count / STABLE_SAMPLE_THRESHOLD, 1.0),
            drift_detection_armed=(target_state == ONBOARDING_STABLE),
            last_drift=last_drift, adaptive_threshold=adaptive_threshold,
            selected_features=selected_features, updated_at=None,
        )

        logger.info(
            "[Biometric] Sync: user=%s samples=%d state=%s drift=%.3f",
            user_id, sample_count, target_state, last_drift,
        )

        return {
            "success":         True,
            "user_id":         user_id,
            "profile_status":  status_obj.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[Biometric] Profile sync failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to store biometric profile")


@app.post("/biometric/profile/reset")
async def reset_biometric_profile_endpoint(
    req: ProfileResetReq,
    session: dict = Depends(require_active_session),
):
    """
    Re-onboarding endpoint.  Wipes the aggregated EMA and resets the profile
    to `collecting` so the user builds a fresh baseline after re-auth.

    Should be called:
      • Automatically by the login handler when a `drifted` profile is detected.
      • By the ProfileBuildPage's "start over" button in the `drifted` panel.

    Returns the empty ProfileBuildStatus that the client uses to reset its
    local state machine.
    """
    user_id   = session["user_id"]
    tenant_id = session.get("tenant_id")
    site_id   = session.get("site_id")

    try:
        await reset_biometric_profile(
            db_handler.db,
            user_id   = user_id,
            tenant_id = tenant_id,
            site_id   = site_id,
        )
    except Exception as exc:
        logger.error("[Biometric] Reset failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reset biometric profile")

    logger.info("[Biometric] Profile reset: user=%s reason=%s", user_id, req.reason)
    return {
        "success":        True,
        "user_id":        user_id,
        "onboarding_state": ONBOARDING_COLLECTING,
        "reason":         req.reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Admin
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/honeypot/signatures")
async def signatures():
    try:
        db_sigs = await get_honeypot_signatures(db_handler.db, limit=100)
        count   = await get_honeypot_count(db_handler.db)
        return {"signatures": db_sigs, "count": count}
    except Exception as exc:
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


@app.get("/admin/onboarding-summary")
async def onboarding_summary(
    tenant_id: str = Query(..., description="Tenant ID to aggregate for"),
):
    """
    Per-tenant breakdown of how many users are in each onboarding state.
    Useful for monitoring cold-start funnel health.
    """
    try:
        summary = await profile_build_summary(db_handler.db, tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "tenant_id": tenant_id,
        "states":    summary,
        "threshold": STABLE_SAMPLE_THRESHOLD,
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
# Integration API — Session Trust  (unchanged from v3.2.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/session/trust",
    response_model = SessionTrustResponse,
    summary        = "Verify session trust before a sensitive transaction",
    tags           = ["Integration API"],
)
async def verify_session_trust(req: SessionTrustRequest) -> SessionTrustResponse:
    now = datetime.now(timezone.utc).isoformat()

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

    trust    = min(stored_trust, req.trust_score) if req.trust_score is not None else stored_trust
    e_rec    = max(stored_e_rec, req.e_rec)       if req.e_rec is not None       else stored_e_rec
    risk_adj = trust * (1 - req.transaction_risk * 0.3)

    if db_session and req.trust_score is not None:
        confidence = "high"
    elif db_session or req.trust_score is not None:
        confidence = "medium"
    else:
        confidence = "low"
        reasons.append("low_signal")

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
            reason      = f"Transaction blocked: " + "; ".join(reasons),
            customer_id = req.customer_id,
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
    tags           = ["Integration API"],
)
async def get_session_trust(session_id: str) -> SessionTrustResponse:
    try:
        db_session = await get_session(db_handler.db, session_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Session store unavailable")

    if not db_session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found or expired.")

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
# Integration API — Webhooks  (unchanged from v3.2.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/webhooks/endpoints", status_code=201, response_model=EndpointOut, tags=["Webhooks"])
async def register_endpoint(req: EndpointCreate) -> EndpointOut:
    endpoint = WebhookEndpoint(
        id=str(uuid.uuid4()), url=str(req.url), secret=req.secret,
        events=req.events, customer_id=req.customer_id, description=req.description,
    )
    dispatcher.register_endpoint(endpoint)
    return EndpointOut(id=endpoint.id, url=endpoint.url, events=[e.value for e in endpoint.events],
                       customer_id=endpoint.customer_id, enabled=endpoint.enabled, description=endpoint.description)


@app.get("/webhooks/endpoints", response_model=list[EndpointOut], tags=["Webhooks"])
async def list_endpoints(customer_id: str | None = Query(None)) -> list[EndpointOut]:
    return [
        EndpointOut(id=ep.id, url=ep.url, events=[e.value for e in ep.events],
                    customer_id=ep.customer_id, enabled=ep.enabled, description=ep.description)
        for ep in dispatcher.list_endpoints(customer_id=customer_id)
    ]


@app.get("/webhooks/endpoints/{endpoint_id}", response_model=EndpointOut, tags=["Webhooks"])
async def get_endpoint(endpoint_id: str) -> EndpointOut:
    ep = dispatcher._endpoints.get(endpoint_id)
    if not ep:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")
    return EndpointOut(id=ep.id, url=ep.url, events=[e.value for e in ep.events],
                       customer_id=ep.customer_id, enabled=ep.enabled, description=ep.description)


@app.patch("/webhooks/endpoints/{endpoint_id}", response_model=EndpointOut, tags=["Webhooks"])
async def update_endpoint(endpoint_id: str, req: EndpointUpdate) -> EndpointOut:
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    if "url" in kwargs:
        kwargs["url"] = str(kwargs["url"])
    ep = dispatcher.update_endpoint(endpoint_id, **kwargs)
    if not ep:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")
    return EndpointOut(id=ep.id, url=ep.url, events=[e.value for e in ep.events],
                       customer_id=ep.customer_id, enabled=ep.enabled, description=ep.description)


@app.delete("/webhooks/endpoints/{endpoint_id}", status_code=204, tags=["Webhooks"])
async def delete_endpoint(endpoint_id: str):
    if endpoint_id not in dispatcher._endpoints:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")
    dispatcher.unregister_endpoint(endpoint_id)


@app.post("/webhooks/endpoints/{endpoint_id}/test", response_model=TestDeliveryOut, tags=["Webhooks"])
async def test_endpoint_delivery(endpoint_id: str) -> TestDeliveryOut:
    result = await dispatcher.test_endpoint(endpoint_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")
    return TestDeliveryOut(delivery_id=result.delivery_id, success=result.success,
                           status_code=result.status_code, attempts=result.attempts,
                           latency_ms=round(result.latency_ms, 2), error=result.error)


# ─────────────────────────────────────────────────────────────────────────────
# Integration API — Notifications  (unchanged from v3.2.0)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/notifications", tags=["Integration API"])
async def query_notifications(
    customer_id: str | None      = Query(None),
    user_id:     str | None      = Query(None),
    severity:    Severity | None = Query(None),
    event_type:  str | None      = Query(None),
    limit:       int             = Query(100, ge=1, le=500),
) -> dict:
    records = notification_service.query_log(
        customer_id=customer_id, user_id=user_id,
        severity=severity, event_type=event_type, limit=limit,
    )
    return {"notifications": records, "count": len(records)}


@app.get("/notifications/stats", tags=["Integration API"])
async def notification_stats(customer_id: str | None = Query(None)) -> dict:
    return notification_service.stats(customer_id=customer_id)


@app.post("/notifications/thresholds", status_code=204, tags=["Integration API"])
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


@app.get("/notifications/thresholds/{customer_id}", tags=["Integration API"])
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
        "version":   "4.0.0",
        "pipeline":  "active" if orchestrator is not None else "starting",
        "stages":    4,
        "timestamp": time.time(),
    }