"""
Entropy Prime — FastAPI Backend
All biometric scoring now flows through the 4-stage PipelineOrchestrator.
Each stage has explicit I/O contracts, confidence handling, and fallbacks.
"""
from __future__ import annotations

import json, logging, os, secrets, time, signal, sys
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager

import numpy as np
import torch
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from database import Database
from database import (
    user_exists, create_user, get_user_by_email, get_user_by_id,
    update_last_login, update_user_security_level,
    create_session, get_session, invalidate_session, update_session_trust_score,
    store_biometric_sample, get_biometric_profile,
    store_honeypot_entry, get_honeypot_signatures, get_honeypot_count,
)
from models.pydantic_models import UserCreate, UserLogin
from models.dqn   import DQNAgent
from models.mab   import MABAgent
from models.ppo   import PPOAgent
from models.cnn1d import CNN1D

# Pipeline
from pipeline import PipelineOrchestrator, BiometricInput
from pipeline.contracts import WatchdogAction

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("entropy_prime")
logger.info(f"Starting Entropy Prime v3 (log level: {os.environ.get('LOG_LEVEL', 'INFO')})")

# ── Secrets ───────────────────────────────────────────────────────────────────
SESSION_SECRET = os.environ.get("EP_SESSION_SECRET", secrets.token_hex(32))
SHADOW_SECRET  = os.environ.get("EP_SHADOW_SECRET",  secrets.token_hex(32))

# ── Database ──────────────────────────────────────────────────────────────────
db_handler = Database()

# ── Model agents ──────────────────────────────────────────────────────────────
dqn_agent = DQNAgent(state_dim=3, action_dim=4)
mab_agent = MABAgent(n_arms=3)
ppo_agent = PPOAgent(state_dim=10, action_dim=3)
cnn_model = CNN1D(input_channels=1, out_dim=32)


def _load_checkpoints() -> None:
    """Attempt to load pre-trained checkpoints. Missing files are non-fatal."""
    ckpt_dir = os.environ.get("EP_CHECKPOINT_DIR", "checkpoints")

    rl_path  = os.environ.get("EP_RL_CHECKPOINT",  os.path.join(ckpt_dir, "governor.pt"))
    mab_path = os.environ.get("EP_MAB_CHECKPOINT", os.path.join(ckpt_dir, "mab.json"))
    ppo_path = os.environ.get("EP_PPO_CHECKPOINT", os.path.join(ckpt_dir, "watchdog.pt"))

    if os.path.exists(rl_path):
        try:
            dqn_agent.load_checkpoint(rl_path)
            logger.info("✓ DQN checkpoint loaded: %s", rl_path)
        except Exception as e:
            logger.warning("DQN checkpoint load failed (%s) — random weights", e)
    else:
        logger.info("DQN checkpoint not found at %s — using random weights", rl_path)

    if os.path.exists(mab_path):
        try:
            with open(mab_path) as f:
                mab_agent.load_state_dict(json.load(f))
            logger.info("✓ MAB checkpoint loaded: %s", mab_path)
        except Exception as e:
            logger.warning("MAB checkpoint load failed (%s) — cold start", e)

    if os.path.exists(ppo_path):
        try:
            ppo_agent.load_checkpoint(ppo_path)
            logger.info("✓ PPO checkpoint loaded: %s", ppo_path)
        except Exception as e:
            logger.warning("PPO checkpoint load failed (%s) — fallback rules active", e)


# ── Pipeline orchestrator (built after models are ready) ──────────────────────
orchestrator: Optional[PipelineOrchestrator] = None

# ── Lifespan events for graceful startup/shutdown ───────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global orchestrator
    logger.info("🚀 Entropy Prime starting up...")
    try:
        await db_handler.connect_to_mongo()
        _load_checkpoints()
        orchestrator = PipelineOrchestrator(
            dqn_agent=dqn_agent,
            mab_agent=mab_agent,
            ppo_agent=ppo_agent,
            shadow_secret=SHADOW_SECRET,
            session_secret=SESSION_SECRET,
        )
        logger.info("✓ Entropy Prime v3 initialized — 4-stage pipeline active")
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Entropy Prime shutting down...")
    try:
        await db_handler.close_mongo_connection()
        logger.info("✓ Shutdown complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}", exc_info=True)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Entropy Prime",
    version="3.0.0 (Pipeline)",
    description="Zero-trust behavioral biometrics engine with multi-agent orchestration",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Middleware: Request logging ────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start
        logger.debug(f"{request.method} {request.url.path} - {response.status_code} ({duration:.3f}s)")
        return response
    except Exception as e:
        logger.error(f"Request failed: {request.method} {request.url.path} - {str(e)}", exc_info=True)
        raise

# ── Exception handlers ─────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {type(exc).__name__}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


# ── Pydantic request models ────────────────────────────────────────────────────

class ScoreReq(BaseModel):
    theta:         float = Field(..., ge=0, le=1)
    h_exp:         float = Field(..., ge=0, le=1)
    server_load:   float = Field(0.5, ge=0, le=1)
    user_agent:    str   = ""
    latent_vector: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def chk(self):
        if self.latent_vector and len(self.latent_vector) != 32:
            raise ValueError("latent_vector must be 32-dim")
        return self


class PwHashReq(BaseModel):
    plain_password: str
    stored_hash:    str   = ""
    theta:          float = 0.5
    h_exp:          float = 0.5


class SessionVerifyReq(BaseModel):
    session_token:  str
    user_id:        str
    latent_vector:  list[float]
    e_rec:          float = Field(..., ge=0)
    trust_score:    float = Field(..., ge=0, le=1)


class MabRewardReq(BaseModel):
    arm:    int
    reward: float = Field(..., ge=-1.0, le=1.0)


# ── /score — main pipeline entry point ───────────────────────────────────────

@app.post("/score")
async def score(req: ScoreReq, request: Request):
    """
    Runs the full 4-stage pipeline:
      S1: Biometric interpretation
      S2: Honeypot classification (MAB)
      S3: Resource Governor (DQN) → Argon2id preset
      S4: Session Watchdog (PPO)  — skipped for bots

    Always returns HTTP 200. Bots receive a synthetic shadow token.
    """
    raw = BiometricInput(
        theta         = req.theta,
        h_exp         = req.h_exp,
        server_load   = req.server_load,
        user_agent    = req.user_agent or "",
        latent_vector = req.latent_vector,
        ip_address    = getattr(request.client, "host", "?"),
    )

    result = orchestrator.run(raw)

    # Persist honeypot entry to MongoDB when shadow-routed
    if result.shadow_mode:
        try:
            await store_honeypot_entry(
                db_handler.db,
                user_agent  = req.user_agent,
                theta       = req.theta,
                ip_address  = raw.ip_address,
                path        = "/score",
                headers     = {},
            )
        except Exception as e:
            logger.error("[Honeypot] DB write failed: %s", e)

    logger.info(
        "[Pipeline] shadow=%s preset=%s conf=%s degraded=%s θ=%.3f",
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

    # Include watchdog info when available
    if result.watchdog:
        response["watchdog"] = {
            "action":      result.watchdog.action.value,
            "trust_score": result.watchdog.trust_score,
            "e_rec":       result.watchdog.e_rec,
        }

    # Include MAB arm for reward feedback
    if result.shadow_mode and result.honeypot.mab_arm_selected >= 0:
        response["mab_arm"] = result.honeypot.mab_arm_selected

    return response


# ── /session/verify — watchdog heartbeat ─────────────────────────────────────

@app.post("/session/verify")
async def session_verify(req: SessionVerifyReq):
    """
    Runs Stage 4 (Watchdog) in isolation for continuous session monitoring.
    Uses the full PPO → fallback-rules chain.
    """
    wd = orchestrator.run_watchdog(
        latent_vector = req.latent_vector,
        e_rec         = req.e_rec,
        trust_score   = req.trust_score,
    )

    # Persist updated trust score
    try:
        await update_session_trust_score(db_handler.db, req.session_token, wd.trust_score)
    except Exception:
        pass

    return {
        "action":      wd.action.value,
        "trust_score": wd.trust_score,
        "e_rec":       wd.e_rec,
        "confidence":  wd.confidence.value,
        "reason":      wd.reason,
    }


# ── /honeypot/reward — MAB feedback loop ─────────────────────────────────────

@app.post("/honeypot/reward")
async def honeypot_reward(req: MabRewardReq):
    """
    Called after a shadow session ends to close the MAB reward loop.
    reward > 0 = deception held; reward < 0 = bot escaped.
    """
    orchestrator.report_mab_reward(req.arm, req.reward)
    return {"ok": True, "arm": req.arm, "reward": req.reward}


# ── Authentication ────────────────────────────────────────────────────────────

@app.post("/auth/register")
async def register(req: UserCreate, request: Request):
    if await user_exists(db_handler.db, req.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="User with this email already exists")
    # Use pipeline governor to pick Argon2id strength for registration
    from pipeline.contracts import BiometricInput as BI, SecurityPreset
    from pipeline import stage3_governor as s3
    from pipeline import stage1_biometric as s1
    bio_raw = BI(theta=0.9, h_exp=0.9, server_load=0.4,
                 user_agent="", latent_vector=[], ip_address="register")
    bio = s1.run(bio_raw)
    gov = s3.run(bio, dqn_agent)

    ph = PasswordHasher(memory_cost=gov.memory_kb, time_cost=gov.time_cost,
                        parallelism=gov.parallelism)
    password_hash = ph.hash(req.plain_password)

    try:
        user_id       = await create_user(db_handler.db, req.email, password_hash)
        lv            = [0.0] * 32
        from pipeline.orchestrator import _make_session_token
        session_token = _make_session_token(user_id, lv, SESSION_SECRET)
        await create_session(db_handler.db, user_id, session_token, lv)
        await update_user_security_level(db_handler.db, user_id, gov.preset.value)
        logger.info("[Auth] Registered: %s preset=%s", req.email, gov.preset.value)
        return {"success": True, "user_id": user_id, "email": req.email,
                "session_token": session_token, "security_level": gov.preset.value}
    except Exception as e:
        logger.error("[Auth] Register error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to register user")


@app.post("/auth/login")
async def login(req: UserLogin, request: Request):
    try:
        user = await get_user_by_email(db_handler.db, req.email)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not user.get("is_active", False):
            raise HTTPException(status_code=403, detail="Account inactive")
        try:
            PasswordHasher().verify(user["password_hash"], req.plain_password)
        except VerifyMismatchError:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        await update_last_login(db_handler.db, user["_id"])
        lv = [0.0] * 32
        from pipeline.orchestrator import _make_session_token
        session_token = _make_session_token(user["_id"], lv, SESSION_SECRET)
        await create_session(db_handler.db, user["_id"], session_token, lv)
        logger.info("[Auth] Login: %s", req.email)
        return {"success": True, "session_token": session_token,
                "user_id": user["_id"], "email": user["email"],
                "security_level": user.get("security_level", "standard")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Auth] Login error: %s", e)
        raise HTTPException(status_code=500, detail="Login failed")


@app.post("/auth/logout")
async def logout(session_token: str):
    try:
        await invalidate_session(db_handler.db, session_token)
        return {"success": True, "message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Logout failed")


# ── Password utilities ────────────────────────────────────────────────────────

@app.post("/password/hash")
async def pw_hash(req: PwHashReq, user_id: Optional[str] = None):
    from pipeline.contracts import BiometricInput as BI
    from pipeline import stage1_biometric as s1, stage3_governor as s3
    bio_raw = BI(theta=req.theta, h_exp=req.h_exp, server_load=0.5,
                 user_agent="", latent_vector=[], ip_address="hash")
    bio = s1.run(bio_raw)
    gov = s3.run(bio, dqn_agent)

    import time as _t
    ph = PasswordHasher(memory_cost=gov.memory_kb, time_cost=gov.time_cost,
                        parallelism=gov.parallelism)
    t0     = _t.perf_counter()
    hashed = ph.hash(req.plain_password)
    ms     = (_t.perf_counter() - t0) * 1000

    if user_id:
        try:
            await update_user_security_level(db_handler.db, user_id, gov.preset.value)
        except Exception:
            pass

    return {
        "hash":          hashed,
        "action":        gov.preset.value,
        "elapsed_ms":    ms,
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


# ── Honeypot / admin ──────────────────────────────────────────────────────────

@app.get("/honeypot/signatures")
async def signatures():
    try:
        db_sigs = await get_honeypot_signatures(db_handler.db, limit=100)
        count   = await get_honeypot_count(db_handler.db)
    except Exception as e:
        logger.error("[Honeypot] Fetch error: %s", e)
        db_sigs, count = [], 0
    return {"signatures": db_sigs, "count": count}


@app.get("/admin/honeypot/dashboard")
async def honeypot_dashboard():
    try:
        count = await get_honeypot_count(db_handler.db)
        sigs  = await get_honeypot_signatures(db_handler.db, limit=50)
        return {"total_count": count, "recent_signatures": sigs, "timestamp": time.time()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/models-status")
async def models_status():
    return {
        "models": {
            "dqn":   {"status": "loaded", "type": "Deep Q-Network",                "phase": 2},
            "mab":   {"status": "loaded", "type": "Multi-Armed Bandit",
                      "n_arms": mab_agent.n_arms, "arm_values": mab_agent.values.tolist(), "phase": 3},
            "ppo":   {"status": "loaded", "type": "Proximal Policy Optimization",  "phase": 4},
            "cnn1d": {"status": "loaded", "type": "1D CNN",                        "phase": 1},
        },
        "pipeline": {
            "stages": ["biometric", "honeypot", "governor", "watchdog"],
            "contracts": "pipeline/contracts.py",
        },
        "timestamp": time.time(),
    }


@app.get("/admin/pipeline-debug")
async def pipeline_debug(
    theta: float = 0.5, h_exp: float = 0.5, server_load: float = 0.4
):
    """
    Dry-run the pipeline with synthetic inputs and return full stage outputs.
    Useful for testing without a real browser session.
    """
    raw = BiometricInput(
        theta=theta, h_exp=h_exp, server_load=server_load,
        user_agent="debug", latent_vector=[0.0]*32, ip_address="127.0.0.1",
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
                "should_shadow":    result.honeypot.should_shadow,
                "mab_arm":          result.honeypot.mab_arm_selected,
                "mab_confidence":   result.honeypot.mab_confidence.value,
            },
            "governor": {
                "preset":     result.governor.preset.value,
                "memory_mb":  result.governor.memory_kb // 1024,
                "confidence": result.governor.confidence.value,
                "fallback":   result.governor.fallback,
            },
            "watchdog": {
                "action":     result.watchdog.action.value if result.watchdog else None,
                "confidence": result.watchdog.confidence.value if result.watchdog else None,
                "reason":     result.watchdog.reason if result.watchdog else None,
            },
        },
    }


# ── Biometric / CNN ───────────────────────────────────────────────────────────

@app.post("/biometric/extract")
async def biometric_extract(raw_signal: list[float]):
    try:
        features = cnn_model.extract(raw_signal)
        return {"success": True, "features": features, "dim": len(features)}
    except Exception as e:
        logger.error("[CNN] Extract error: %s", e)
        raise HTTPException(status_code=500, detail="Feature extraction failed")


@app.get("/biometric/profile/{user_id}")
async def get_biometric_profile_api(user_id: str):
    try:
        profile = await get_biometric_profile(db_handler.db, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"user_id": user_id, "profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve profile")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":    "ok",
        "pipeline":  "active",
        "stages":    4,
        "timestamp": time.time(),
    }
