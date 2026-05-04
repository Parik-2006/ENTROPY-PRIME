"""
Entropy Prime — FastAPI Backend  v3.0.0
All biometric scoring flows through the 4-stage PipelineOrchestrator.

Fixed from draft:
  - /auth/logout: session_token moved from query-param to request body (LogoutReq)
    so it never appears in server logs / proxies.
  - /biometric/extract: bare list[float] body wrapped in BiometricExtractReq so
    FastAPI can deserialize it without a 422.
  - All inline `from pipeline import …` moved to module level; import errors
    surface at startup rather than silently at request time.
  - _load_checkpoints() separated from lifespan so it can be unit-tested in
    isolation without spinning up a full async event loop.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
import torch
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

# ── Database layer ─────────────────────────────────────────────────────────────
from database import Database
from database import (
    user_exists, create_user, get_user_by_email, get_user_by_id,
    update_last_login, update_user_security_level,
    create_session, get_session, invalidate_session, update_session_trust_score,
    store_biometric_sample, get_biometric_profile,
    store_honeypot_entry, get_honeypot_signatures, get_honeypot_count,
)

# ── Pydantic models (auth-related) ─────────────────────────────────────────────
from models.pydantic_models import UserCreate, UserLogin

# ── ML model agents ────────────────────────────────────────────────────────────
from models.dqn   import DQNAgent
from models.mab   import MABAgent
from models.ppo   import PPOAgent
from models.cnn1d import CNN1D

# ── Pipeline (top-level imports; failure here is a startup error, not a 500) ──
from pipeline import PipelineOrchestrator, BiometricInput
from pipeline.contracts  import WatchdogAction, SecurityPreset
from pipeline            import stage1_biometric as s1
from pipeline            import stage3_governor  as s3
from pipeline.orchestrator import _make_session_token

# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("entropy_prime")
logger.info("Starting Entropy Prime v3 (log level: %s)", os.environ.get("LOG_LEVEL", "INFO"))

# ── Module-level secrets ───────────────────────────────────────────────────────
SESSION_SECRET = os.environ.get("EP_SESSION_SECRET", secrets.token_hex(32))
SHADOW_SECRET  = os.environ.get("EP_SHADOW_SECRET",  secrets.token_hex(32))

# ── Singleton DB handler & model agents ───────────────────────────────────────
db_handler = Database()

dqn_agent = DQNAgent(state_dim=3,  action_dim=4)
mab_agent = MABAgent(n_arms=3)
ppo_agent = PPOAgent(state_dim=10, action_dim=3)
cnn_model = CNN1D(input_channels=1, out_dim=32)

# ── Pipeline orchestrator (populated inside lifespan) ─────────────────────────
orchestrator: Optional[PipelineOrchestrator] = None


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint Loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_checkpoints() -> None:
    """
    Attempt to load pre-trained weights for every agent.

    Resolution order for each path (first match wins):
      1. Environment variable  (EP_RL_CHECKPOINT / EP_MAB_CHECKPOINT / EP_PPO_CHECKPOINT)
      2. Default path          (EP_CHECKPOINT_DIR / <name>.pt|json)

    Missing checkpoints are non-fatal: the agent keeps randomly-initialised
    weights and logs an INFO message.  Only genuine load *errors* (corrupt file,
    shape mismatch, …) produce a WARNING — they never abort startup.
    """
    ckpt_dir = os.environ.get("EP_CHECKPOINT_DIR", "checkpoints")

    rl_path  = os.environ.get("EP_RL_CHECKPOINT",  os.path.join(ckpt_dir, "governor.pt"))
    mab_path = os.environ.get("EP_MAB_CHECKPOINT", os.path.join(ckpt_dir, "mab.json"))
    ppo_path = os.environ.get("EP_PPO_CHECKPOINT", os.path.join(ckpt_dir, "watchdog.pt"))

    # ── DQN (Resource Governor) ───────────────────────────────────────────────
    if os.path.exists(rl_path):
        try:
            dqn_agent.load_checkpoint(rl_path)
            logger.info("✓ DQN checkpoint loaded: %s", rl_path)
        except Exception as exc:
            logger.warning(
                "DQN checkpoint at %s is corrupt or incompatible (%s) — "
                "continuing with random weights",
                rl_path, exc,
            )
    else:
        logger.info(
            "DQN checkpoint not found at %s — using random weights (expected on first run)",
            rl_path,
        )

    # ── MAB (Honeypot arm selector) ───────────────────────────────────────────
    if os.path.exists(mab_path):
        try:
            with open(mab_path) as fh:
                mab_agent.load_state_dict(json.load(fh))
            logger.info("✓ MAB checkpoint loaded: %s", mab_path)
        except Exception as exc:
            logger.warning(
                "MAB checkpoint at %s failed to load (%s) — cold-start bandit",
                mab_path, exc,
            )
    else:
        logger.info("MAB checkpoint not found at %s — cold-start bandit", mab_path)

    # ── PPO (Session Watchdog) ────────────────────────────────────────────────
    if os.path.exists(ppo_path):
        try:
            ppo_agent.load_checkpoint(ppo_path)
            logger.info("✓ PPO checkpoint loaded: %s", ppo_path)
        except Exception as exc:
            logger.warning(
                "PPO checkpoint at %s is corrupt or incompatible (%s) — "
                "fallback rules will be used for session watchdog",
                ppo_path, exc,
            )
    else:
        logger.info(
            "PPO checkpoint not found at %s — watchdog will use rule-based fallback",
            ppo_path,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan  (startup → yield → shutdown)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Sequence matters:
      1. Connect to MongoDB (or fall back to mongomock for dev).
      2. Load model checkpoints — agents must exist before the orchestrator
         references them, but they don't need DB access.
      3. Build PipelineOrchestrator — binds the agent instances and secrets.

    If any step raises, FastAPI propagates the exception and the process
    exits with a non-zero code (so container orchestrators restart it).
    """
    global orchestrator

    logger.info("🚀 Entropy Prime v3 starting up…")

    # Step 1 — Database
    await db_handler.connect_to_mongo()

    # Step 2 — Model checkpoints (non-async, CPU-bound, done before first request)
    _load_checkpoints()

    # Step 3 — Pipeline orchestrator
    orchestrator = PipelineOrchestrator(
        dqn_agent     = dqn_agent,
        mab_agent     = mab_agent,
        ppo_agent     = ppo_agent,
        shadow_secret = SHADOW_SECRET,
        session_secret= SESSION_SECRET,
    )

    logger.info("✓ Entropy Prime v3 initialised — 4-stage pipeline active")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("🛑 Entropy Prime shutting down…")
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
    version     = "3.0.0",
    description = "Zero-trust behavioural biometrics engine with multi-agent orchestration",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = os.environ.get(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
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
    """
    Catch-all for any unhandled exception that escapes a route handler.

    Logs the full traceback at ERROR level (so it appears in monitoring) and
    returns a generic 500 body.  The body intentionally omits the exception
    message so internal details are never leaked to callers.
    """
    logger.error(
        "Unhandled %s on %s %s",
        type(exc).__name__, request.method, request.url.path,
        exc_info=True,
    )
    return JSONResponse(
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
        content     = {"detail": "Internal server error"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic request models
# ─────────────────────────────────────────────────────────────────────────────

class ScoreReq(BaseModel):
    theta:         float           = Field(..., ge=0.0, le=1.0)
    h_exp:         float           = Field(..., ge=0.0, le=1.0)
    server_load:   float           = Field(0.5, ge=0.0, le=1.0)
    user_agent:    str             = ""
    latent_vector: list[float]     = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_latent(self):
        if self.latent_vector and len(self.latent_vector) != 32:
            raise ValueError("latent_vector must be empty or exactly 32-dim")
        return self


class PwHashReq(BaseModel):
    plain_password: str
    stored_hash:    str   = ""
    theta:          float = 0.5
    h_exp:          float = 0.5


class SessionVerifyReq(BaseModel):
    session_token: str
    user_id:       str
    latent_vector: list[float]
    e_rec:         float = Field(..., ge=0.0)
    trust_score:   float = Field(..., ge=0.0, le=1.0)


class MabRewardReq(BaseModel):
    arm:    int
    reward: float = Field(..., ge=-1.0, le=1.0)


class LogoutReq(BaseModel):
    """
    Keeps the session token out of the URL (query params appear in logs/proxies).
    """
    session_token: str


class BiometricExtractReq(BaseModel):
    """
    Wrapper so FastAPI can deserialize a JSON array body for /biometric/extract.
    A bare `list[float]` parameter is not supported by FastAPI's body parser.
    """
    raw_signal: list[float]


# ─────────────────────────────────────────────────────────────────────────────
# /score  — main pipeline entry point
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/score")
async def score(req: ScoreReq, request: Request):
    """
    Runs the full 4-stage pipeline:
      S1 Biometric interpretation
      S2 Honeypot classification (MAB)
      S3 Resource Governor (DQN)  → Argon2id preset
      S4 Session Watchdog (PPO)   — skipped for confirmed bots

    Always returns HTTP 200.  Bots receive a synthetic shadow token so they
    cannot distinguish themselves from legitimate users via HTTP status codes.
    """
    # ── Build typed input ─────────────────────────────────────────────────────
    raw = BiometricInput(
        theta         = req.theta,
        h_exp         = req.h_exp,
        server_load   = req.server_load,
        user_agent    = req.user_agent,
        latent_vector = req.latent_vector,
        ip_address    = getattr(request.client, "host", "?"),
    )

    # ── Run pipeline (never raises; always returns PipelineOutput) ────────────
    result = orchestrator.run(raw)

    # ── Persist honeypot entry when bot is shadow-routed ──────────────────────
    if result.shadow_mode:
        try:
            await store_honeypot_entry(
                db_handler.db,
                user_agent  = req.user_agent,
                theta       = req.theta,
                ip_address  = raw.ip_address,
                path        = "/score",
                headers     = dict(request.headers),   # full headers for forensics
            )
        except Exception as exc:
            # Honeypot persistence failure must never affect the response —
            # bots must not learn that logging broke.
            logger.error("[Honeypot] DB write failed: %s", exc)

    logger.info(
        "[Pipeline] shadow=%s preset=%-8s conf=%-6s degraded=%s θ=%.3f",
        result.shadow_mode,
        result.action_label,
        result.pipeline_confidence,
        result.degraded,
        result.humanity_score,
    )

    # ── Compose response ──────────────────────────────────────────────────────
    response: dict = {
        "session_token":       result.session_token,
        "shadow_mode":         result.shadow_mode,
        "argon2_params":       result.argon2_params,       # {m, t, p}
        "humanity_score":      result.humanity_score,
        "entropy_score":       result.entropy_score,
        "action_label":        result.action_label,
        "pipeline_confidence": result.pipeline_confidence.value,
        "degraded":            result.degraded,
    }

    # Watchdog metrics — only present when S4 actually ran (non-bot, 32-dim vector)
    if result.watchdog is not None:
        response["watchdog"] = {
            "action":      result.watchdog.action.value,
            "trust_score": result.watchdog.trust_score,
            "e_rec":       result.watchdog.e_rec,
            "confidence":  result.watchdog.confidence.value,
            "reason":      result.watchdog.reason,
        }

    # MAB arm — only for shadow responses so the caller can close the reward loop
    if result.shadow_mode and result.honeypot.mab_arm_selected >= 0:
        response["mab_arm"] = result.honeypot.mab_arm_selected

    return response


# ─────────────────────────────────────────────────────────────────────────────
# /session/verify  — continuous watchdog heartbeat
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/session/verify")
async def session_verify(req: SessionVerifyReq):
    """
    Runs Stage 4 (Watchdog) in isolation for established sessions.
    Called periodically by the client to detect identity drift mid-session.
    """
    wd = orchestrator.run_watchdog(
        latent_vector = req.latent_vector,
        e_rec         = req.e_rec,
        trust_score   = req.trust_score,
    )

    # Persist updated trust score (non-critical; best-effort)
    try:
        await update_session_trust_score(db_handler.db, req.session_token, wd.trust_score)
    except Exception as exc:
        logger.warning("[SessionVerify] trust-score persist failed: %s", exc)

    return {
        "action":      wd.action.value,
        "trust_score": wd.trust_score,
        "e_rec":       wd.e_rec,
        "confidence":  wd.confidence.value,
        "reason":      wd.reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# /honeypot/reward  — MAB feedback loop
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/honeypot/reward")
async def honeypot_reward(req: MabRewardReq):
    """
    Called after a shadow session ends.
    reward > 0 → deception held; reward < 0 → bot escaped the honeypot.
    """
    orchestrator.report_mab_reward(req.arm, req.reward)
    return {"ok": True, "arm": req.arm, "reward": req.reward}


# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(req: UserCreate, request: Request):
    """
    Register a new user.
    Uses the pipeline governor (DQN) to pick Argon2id strength at registration
    time, binding account security to the server's current load profile.
    """
    if await user_exists(db_handler.db, req.email):
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail      = "An account with that email already exists",
        )

    # Use a high-confidence human signal so we get a real (not economy) preset
    bio_raw = BiometricInput(
        theta=0.9, h_exp=0.9, server_load=0.4,
        user_agent="", latent_vector=[], ip_address="register",
    )
    bio = s1.run(bio_raw)
    gov = s3.run(bio, dqn_agent)

    ph            = PasswordHasher(
        memory_cost = gov.memory_kb,
        time_cost   = gov.time_cost,
        parallelism = gov.parallelism,
    )
    password_hash = ph.hash(req.plain_password)

    try:
        user_id       = await create_user(db_handler.db, req.email, password_hash)
        lv            = [0.0] * 32
        session_token = _make_session_token(user_id, lv, SESSION_SECRET)
        await create_session(db_handler.db, user_id, session_token, lv)
        await update_user_security_level(db_handler.db, user_id, gov.preset.value)
        logger.info("[Auth] Registered %s  preset=%s", req.email, gov.preset.value)
        return {
            "success":        True,
            "user_id":        user_id,
            "email":          req.email,
            "session_token":  session_token,
            "security_level": gov.preset.value,
        }
    except Exception as exc:
        logger.error("[Auth] Register error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to register user")


@app.post("/auth/login")
async def login(req: UserLogin, request: Request):
    """Standard email + password login.  Returns a session token on success."""
    try:
        user = await get_user_by_email(db_handler.db, req.email)
        if not user:
            # Constant-time response to prevent user enumeration via timing
            PasswordHasher().hash("dummy_constant_work")
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not user.get("is_active", False):
            raise HTTPException(status_code=403, detail="Account is inactive")

        try:
            PasswordHasher().verify(user["password_hash"], req.plain_password)
        except VerifyMismatchError:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        await update_last_login(db_handler.db, user["_id"])
        lv            = [0.0] * 32
        session_token = _make_session_token(user["_id"], lv, SESSION_SECRET)
        await create_session(db_handler.db, user["_id"], session_token, lv)
        logger.info("[Auth] Login: %s", req.email)
        return {
            "success":        True,
            "session_token":  session_token,
            "user_id":        user["_id"],
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
    """
    Invalidate a session.

    The session token is accepted in the request body (not as a query parameter)
    so it never appears in server access logs, reverse-proxy logs, or browser
    history — all of which record full URLs including query strings.
    """
    try:
        await invalidate_session(db_handler.db, req.session_token)
        return {"success": True, "message": "Logged out successfully"}
    except Exception as exc:
        logger.error("[Auth] Logout error: %s", exc)
        raise HTTPException(status_code=500, detail="Logout failed")


# ─────────────────────────────────────────────────────────────────────────────
# Password utilities
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/password/hash")
async def pw_hash(req: PwHashReq, user_id: Optional[str] = None):
    """
    Hash a plaintext password using the DQN-selected Argon2id preset.
    Optionally updates the user's stored security_level to reflect the chosen preset.
    """
    bio_raw = BiometricInput(
        theta=req.theta, h_exp=req.h_exp, server_load=0.5,
        user_agent="", latent_vector=[], ip_address="hash",
    )
    bio = s1.run(bio_raw)
    gov = s3.run(bio, dqn_agent)

    ph = PasswordHasher(
        memory_cost = gov.memory_kb,
        time_cost   = gov.time_cost,
        parallelism = gov.parallelism,
    )
    t0     = time.perf_counter()
    hashed = ph.hash(req.plain_password)
    ms     = (time.perf_counter() - t0) * 1000

    if user_id:
        try:
            await update_user_security_level(db_handler.db, user_id, gov.preset.value)
        except Exception:
            pass  # non-critical

    return {
        "hash":          hashed,
        "action":        gov.preset.value,
        "elapsed_ms":    round(ms, 2),
        "argon2_params": {"m": gov.memory_kb, "t": gov.time_cost, "p": gov.parallelism},
        "confidence":    gov.confidence.value,
        "fallback":      gov.fallback,
    }


@app.post("/password/verify")
async def pw_verify(req: PwHashReq):
    """Verify a plaintext password against a stored Argon2id hash."""
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
    theta:       float = 0.5,
    h_exp:       float = 0.5,
    server_load: float = 0.4,
):
    """
    Dry-run the full pipeline with synthetic inputs.
    Returns the per-stage breakdown — useful for smoke-testing without a browser.
    """
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
                "action":     result.watchdog.action.value    if result.watchdog else None,
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
    """
    Run a raw keystroke/touch signal through the CNN1D feature extractor.

    The request body is a JSON object: {"raw_signal": [0.1, 0.3, …]}
    A bare JSON array is not supported by FastAPI's body parser, so we wrap
    it in BiometricExtractReq.
    """
    try:
        features = cnn_model.extract(req.raw_signal)
        return {"success": True, "features": features, "dim": len(features)}
    except Exception as exc:
        logger.error("[CNN] Extract error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Feature extraction failed")


@app.get("/biometric/profile/{user_id}")
async def get_biometric_profile_api(user_id: str):
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


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":    "ok",
        "pipeline":  "active" if orchestrator is not None else "starting",
        "stages":    4,
        "timestamp": time.time(),
    }
