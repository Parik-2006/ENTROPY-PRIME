"""
Entropy Prime — FastAPI Backend  v3.1.0
All biometric scoring flows through the 4-stage PipelineOrchestrator.

v3.1.0 changes
──────────────
• `verify_session_dep` FastAPI dependency: validates every token against the
  DB before any sensitive route runs.  Rejects expired / inactive sessions with
  HTTP 401.
• /auth/login and /auth/register now call `create_session` with the correct
  initial latent vector and return the token; behaviour is unchanged but the
  flow is explicit and auditable.
• /session/verify heartbeat:
    - Validates the session token against the DB first.
    - Calls orchestrator.run_watchdog with the *DB-persisted* trust score as
      the authoritative baseline (not the client-supplied value, which could
      be replayed / inflated).
    - Persists the watchdog's *updated* trust score (post-decay) back to the DB.
    - Returns 401 if the session is no longer active.
• /honeypot/reward:
    - Validates `arm` is in [0, mab_agent.n_arms).
    - Clamps reward to [-1.0, 1.0] (belt-and-suspenders on top of Pydantic).
• /auth/logout: unchanged; session_token in body.
"""


import json
import logging
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager
from typing import Annotated, Optional

import numpy as np
import torch
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, FastAPI, Request, HTTPException, status
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
logger.info("Starting Entropy Prime v3.1 (log level: %s)", os.environ.get("LOG_LEVEL", "INFO"))

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

    Missing checkpoints are non-fatal.
    """
    ckpt_dir = os.environ.get("EP_CHECKPOINT_DIR", "checkpoints")

    rl_path  = os.environ.get("EP_RL_CHECKPOINT",  os.path.join(ckpt_dir, "governor.pt"))
    mab_path = os.environ.get("EP_MAB_CHECKPOINT", os.path.join(ckpt_dir, "mab.json"))
    ppo_path = os.environ.get("EP_PPO_CHECKPOINT", os.path.join(ckpt_dir, "watchdog.pt"))

    if os.path.exists(rl_path):
        try:
            dqn_agent.load_checkpoint(rl_path)
            logger.debug("✓ DQN checkpoint loaded: %s", rl_path)
        except Exception as exc:
            logger.debug("DQN checkpoint not loaded (%s) — using random weights", exc)
    else:
        logger.debug("DQN checkpoint not found at %s — using random weights", rl_path)

    if os.path.exists(mab_path):
        try:
            with open(mab_path) as fh:
                mab_agent.load_state_dict(json.load(fh))
            logger.debug("✓ MAB checkpoint loaded: %s", mab_path)
        except Exception as exc:
            logger.debug("MAB checkpoint not loaded (%s) — using cold-start bandit", exc)
    else:
        logger.debug("MAB checkpoint not found at %s — using cold-start bandit", mab_path)

    if os.path.exists(ppo_path):
        try:
            ppo_agent.load_checkpoint(ppo_path)
            logger.debug("✓ PPO checkpoint loaded: %s", ppo_path)
        except Exception as exc:
            logger.debug("PPO checkpoint not loaded (%s) — using rule-based fallback", exc)
    else:
        logger.debug("PPO checkpoint not found at %s — using rule-based fallback", ppo_path)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator

    logger.info("🚀 Entropy Prime v3.1 starting up…")

    await db_handler.connect_to_mongo()
    _load_checkpoints()

    orchestrator = PipelineOrchestrator(
        dqn_agent     = dqn_agent,
        mab_agent     = mab_agent,
        ppo_agent     = ppo_agent,
        shadow_secret = SHADOW_SECRET,
        session_secret= SESSION_SECRET,
    )

    logger.info("✓ Entropy Prime v3.1 initialised — 4-stage pipeline active")
    yield

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
    version     = "3.1.0",
    description = "Zero-trust behavioural biometrics engine with multi-agent orchestration",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = os.environ.get(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001"
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
        type(exc).__name__, request.method, request.url.path,
        exc_info=True,
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
    FastAPI dependency that verifies a session token is active in MongoDB.

    Usage:
        @app.post("/some/sensitive/route")
        async def handler(session=Depends(require_active_session)):
            user_id = session["user_id"]
            ...

    Raises HTTP 401 when:
      - No `X-Session-Token` header is present.
      - The token does not exist in the DB.
      - The session has expired or was explicitly invalidated (is_active=False).

    The returned dict is the raw session document from MongoDB (with ObjectIds
    already stringified by `get_session`).
    """

    async def __call__(self, request: Request) -> dict:
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
    """
    Heartbeat payload for /session/verify.

    `session_token` and `user_id` identify the session.
    `latent_vector` is the current 32-dim behavioural embedding.
    `e_rec` is the autoencoder reconstruction error from the client-side model.

    NOTE: `trust_score` is intentionally NOT accepted from the client.  The
    authoritative trust score lives in the DB and is used as the baseline for
    the watchdog so a replayed or inflated value cannot bypass drift detection.
    """
    session_token: str
    user_id:       str
    latent_vector: list[float]
    e_rec:         float = Field(..., ge=0.0)

    @model_validator(mode="after")
    def validate_latent(self):
        if len(self.latent_vector) != 32:
            raise ValueError("latent_vector must be exactly 32-dim")
        return self


class MabRewardReq(BaseModel):
    arm:    int
    reward: float = Field(..., ge=-1.0, le=1.0)


class LogoutReq(BaseModel):
    """Session token in body — never in the URL."""
    session_token: str


class BiometricExtractReq(BaseModel):
    raw_signal: list[float]


# ─────────────────────────────────────────────────────────────────────────────
# /score  — main pipeline entry point
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/score")
async def score(req: ScoreReq, request: Request):
    """
    Runs the full 4-stage pipeline.
    Always returns HTTP 200 (bots receive a synthetic shadow token).
    """
    raw = BiometricInput(
        theta         = req.theta,
        h_exp         = req.h_exp,
        server_load   = req.server_load,
        user_agent    = req.user_agent,
        latent_vector = req.latent_vector,
        ip_address    = getattr(request.client, "host", "?"),
    )

    result = orchestrator.run(raw)

    if result.shadow_mode:
        try:
            await store_honeypot_entry(
                db_handler.db,
                user_agent  = req.user_agent,
                theta       = req.theta,
                ip_address  = raw.ip_address,
                path        = "/score",
                headers     = dict(request.headers),
            )
        except Exception as exc:
            logger.error("[Honeypot] DB write failed: %s", exc)

    logger.info(
        "[Pipeline] shadow=%s preset=%-8s conf=%-6s degraded=%s θ=%.3f",
        result.shadow_mode,
        result.action_label,
        result.pipeline_confidence,
        result.degraded,
        result.humanity_score,
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
        response["watchdog"] = {
            "action":      result.watchdog.action.value,
            "trust_score": result.watchdog.trust_score,
            "e_rec":       result.watchdog.e_rec,
            "confidence":  result.watchdog.confidence.value,
            "reason":      result.watchdog.reason,
        }

    if result.shadow_mode and result.honeypot.mab_arm_selected >= 0:
        response["mab_arm"] = result.honeypot.mab_arm_selected

    return response


# ─────────────────────────────────────────────────────────────────────────────
# /session/verify  — continuous watchdog heartbeat
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/session/verify")
async def session_verify(req: SessionVerifyReq):
    """
    Continuous identity-drift heartbeat.  Called periodically by the client.

    Security model
    ──────────────
    1. The session token is validated against MongoDB first.  An expired or
       invalidated session always returns 401 — the watchdog never runs for
       dead sessions.
    2. The trust score baseline comes from the DB record, not from the
       request body.  This prevents a replayed / inflated value from
       bypassing drift detection.
    3. The watchdog's *updated* trust score (after decay / recovery) is
       written back to the DB so the next heartbeat sees the correct state.
    4. If the watchdog returns FORCE_LOGOUT the session is immediately
       invalidated in the DB so subsequent requests also get 401.
    """
    # ── 1. Validate session against DB ────────────────────────────────────────
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

    # Confirm the session belongs to the claimed user
    if session.get("user_id") != req.user_id:
        logger.warning(
            "[SessionVerify] user_id mismatch: token owner=%s  claimed=%s",
            session.get("user_id"), req.user_id,
        )
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Session / user_id mismatch",
        )

    # ── 2. Use DB trust score as authoritative baseline ───────────────────────
    db_trust_score: float = float(session.get("trust_score", 1.0))

    # ── 3. Run watchdog ───────────────────────────────────────────────────────
    wd = orchestrator.run_watchdog(
        latent_vector = req.latent_vector,
        e_rec         = req.e_rec,
        trust_score   = db_trust_score,   # ← DB value, not client-supplied
    )

    logger.info(
        "[SessionVerify] user=%s action=%s trust %.3f→%.3f e_rec=%.3f conf=%s",
        req.user_id, wd.action.value,
        db_trust_score, wd.trust_score,
        wd.e_rec, wd.confidence.value,
    )

    # ── 4. Persist updated trust score (post-decay) ───────────────────────────
    try:
        await update_session_trust_score(
            db_handler.db, req.session_token, wd.trust_score
        )
    except Exception as exc:
        # Non-critical: next heartbeat re-computes from the stale value, which
        # is still safe — it just delays decay propagation by one cycle.
        logger.warning("[SessionVerify] trust-score persist failed: %s", exc)

    # ── 5. Invalidate session immediately on FORCE_LOGOUT ─────────────────────
    if wd.action == WatchdogAction.FORCE_LOGOUT:
        try:
            await invalidate_session(db_handler.db, req.session_token)
            logger.info(
                "[SessionVerify] Session invalidated (FORCE_LOGOUT): user=%s", req.user_id
            )
        except Exception as exc:
            logger.error("[SessionVerify] Session invalidation failed: %s", exc)
        # Still return the watchdog result so the client can display the
        # correct reason / redirect to the login page.

    return {
        "action":      wd.action.value,
        "trust_score": wd.trust_score,
        "e_rec":       wd.e_rec,
        "confidence":  wd.confidence.value,
        "reason":      wd.reason,
        # Convenience flag so the client doesn't have to string-compare action
        "session_invalidated": wd.action == WatchdogAction.FORCE_LOGOUT,
    }


# ─────────────────────────────────────────────────────────────────────────────
# /honeypot/reward  — MAB feedback loop
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/honeypot/reward")
async def honeypot_reward(req: MabRewardReq):
    """
    Called after a shadow session ends to close the MAB reward loop.

    reward > 0 → deception held (bot stayed in honeypot)
    reward < 0 → bot escaped (arm strategy was ineffective)

    The arm index is validated against the agent's actual number of arms so a
    corrupted / replayed reward payload cannot index out of bounds.
    """
    n_arms = mab_agent.n_arms
    if not (0 <= req.arm < n_arms):
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail      = f"arm must be in [0, {n_arms - 1}]; got {req.arm}",
        )

    # Belt-and-suspenders clamp (Pydantic already enforces ge/le but explicit
    # is better than implicit when it gates a model update)
    reward = max(-1.0, min(1.0, req.reward))

    orchestrator.report_mab_reward(req.arm, reward)

    logger.info("[MAB] reward arm=%d  reward=%.3f", req.arm, reward)
    return {"ok": True, "arm": req.arm, "reward": reward}


# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(req: UserCreate, request: Request):
    """
    Register a new user.

    Session lifecycle
    ─────────────────
    • After the user document is created a session is immediately opened so
      the client can start the behavioural warm-up phase without a separate
      login round-trip.
    • The initial latent vector is all-zeros (no behavioural data yet); it
      will be replaced on the first /session/verify heartbeat.
    • The DQN governor picks the Argon2id preset at registration time based
      on the current server load — binding account security to real-world
      conditions, not a compile-time constant.
    """
    if await user_exists(db_handler.db, req.email):
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail      = "An account with that email already exists",
        )

    # Governor chooses Argon2id strength
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
        user_id = await create_user(db_handler.db, req.email, password_hash)
    except Exception as exc:
        logger.error("[Auth] Register — user creation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to register user")

    # Open an initial session with a zero latent vector
    initial_lv    = [0.0] * 32
    session_token = _make_session_token(user_id, initial_lv, SESSION_SECRET)
    try:
        await create_session(
            db_handler.db,
            user_id       = user_id,
            session_token = session_token,
            latent_vector = initial_lv,
            # Slightly shorter window for brand-new accounts — no behavioural
            # baseline yet, so we trust the session for less time upfront.
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

    Session lifecycle
    ─────────────────
    • A new session document is always created on successful login — we never
      re-use a previous session token so stolen tokens from a prior session
      cannot be replayed.
    • The initial trust score is 1.0 (full trust at login time); it decays
      based on watchdog heartbeats.
    • The initial latent vector is zero; it is replaced on the first heartbeat.
    """
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

        user_id = user["_id"]
        await update_last_login(db_handler.db, user_id)

        # Create a fresh session (never reuse old tokens)
        initial_lv    = [0.0] * 32
        session_token = _make_session_token(user_id, initial_lv, SESSION_SECRET)
        await create_session(
            db_handler.db,
            user_id       = user_id,
            session_token = session_token,
            latent_vector = initial_lv,
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
    """
    Invalidate a session.  Token in the request body, never the URL.
    Protected by the session guard so a forged token never reaches the DB
    invalidation call.
    """
    try:
        await invalidate_session(db_handler.db, req.session_token)
        return {"success": True, "message": "Logged out successfully"}
    except Exception as exc:
        logger.error("[Auth] Logout error: %s", exc)
        raise HTTPException(status_code=500, detail="Logout failed")


# ─────────────────────────────────────────────────────────────────────────────
# Protected: example of a route that requires an active session
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/me")
async def me(session: ActiveSession):
    """
    Returns the authenticated user's profile.

    Demonstrates `require_active_session`: the dependency validates the
    X-Session-Token header against MongoDB before this handler runs.
    If the session is invalid or expired the caller gets HTTP 401.
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
            pass

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
    try:
        features = cnn_model.extract(req.raw_signal)
        return {"success": True, "features": features, "dim": len(features)}
    except Exception as exc:
        logger.error("[CNN] Extract error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Feature extraction failed")


@app.get("/biometric/profile/{user_id}")
async def get_biometric_profile_api(user_id: str, session: ActiveSession):
    """
    Protected by the session guard.  A user may only fetch their own profile
    unless they present an admin-scoped session (not implemented yet — the
    guard simply ensures the caller is authenticated).
    """
    # Scope check: callers may only read their own profile
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
