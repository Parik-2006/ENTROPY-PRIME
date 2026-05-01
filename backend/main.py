"""
Entropy Prime — FastAPI Backend (production-ready with MongoDB)
Per-User Biometric Intelligence: feature extraction, per-user selection,
drift detection, behavioral profile storage.
"""
from __future__ import annotations

import hashlib, hmac, logging, os, secrets, time
from typing import Any, List, Optional

import numpy as np
import torch
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from database import Database
from database import (
    user_exists, create_user, get_user_by_email, get_user_by_id,
    update_last_login, update_user_security_level,
    create_session, get_session, invalidate_session, update_session_trust_score,
    store_biometric_sample, get_biometric_profile, get_biometric_profile_summary,
    upsert_biometric_profile,
    log_drift_event, get_drift_events, get_drift_summary,
    record_feature_selection, get_feature_selection_history,
    store_honeypot_entry, get_honeypot_signatures, get_honeypot_count,
)
from models import (
    UserCreate, UserLogin, UserResponse, AuthResponse,
    PasswordHashResponse, BiometricProfileUpdateRequest, SessionVerifyRequest,
    FEATURE_NAMES,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("entropy_prime")

# ── Database ──────────────────────────────────────────────────────────────────
db_handler = Database()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Entropy Prime", version="3.0.0 (Per-User Biometrics)")

app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await db_handler.connect_to_mongo()
    logger.info("✓ Entropy Prime backend initialized with per-user biometric profiles")

@app.on_event("shutdown")
async def shutdown_event():
    await db_handler.close_mongo_connection()

SESSION_SECRET = os.environ.get("EP_SESSION_SECRET", secrets.token_hex(32))
SHADOW_SECRET  = os.environ.get("EP_SHADOW_SECRET",  secrets.token_hex(32))

# ── Argon2id Presets ──────────────────────────────────────────────────────────
class Argon2Params:
    ECONOMY  = (65_536,    2,  4)
    STANDARD = (131_072,   3,  4)
    HARD     = (524_288,   4,  8)
    PUNISHER = (1_048_576, 8, 16)

    @classmethod
    def from_action(cls, idx: int):
        return [cls.ECONOMY, cls.STANDARD, cls.HARD, cls.PUNISHER][idx]

ACTION_LABELS = ["economy", "standard", "hard", "punisher"]

# ── Model Imports ─────────────────────────────────────────────────────────────
from models.dqn   import DQNAgent
from models.mab   import MABAgent
from models.ppo   import PPOAgent
from models.cnn1d import CNN1D

dqn_agent = DQNAgent(state_dim=3, action_dim=4)
mab_agent = MABAgent(n_arms=3)
ppo_agent = PPOAgent(state_dim=10, action_dim=3)
cnn_model = CNN1D(input_channels=1, out_dim=32)

# ── Per-User Feature Selector (server-side mirror) ────────────────────────────
class ServerFeatureSelector:
    """
    Server-side mirror of the browser UserFeatureSelector.
    Validates and cross-checks the browser-reported selected_features.
    Uses stored feature_means from MongoDB to confirm selection stability.
    """
    N_FEATURES = 8
    K          = 6

    @staticmethod
    def validate_selection(selected: list, feature_means: list) -> dict:
        """
        Cross-validate browser-reported feature selection against
        the server-stored feature means using CV ranking.
        Returns confidence score and any discrepancies.
        """
        if not feature_means or len(feature_means) != ServerFeatureSelector.N_FEATURES:
            return {"confidence": 0.5, "discrepancies": [], "server_ranking": []}

        # Compute rough CV from means (we don't have variance server-side without history)
        # Use inverse of mean as a proxy for discriminativeness (low mean → high CV potential)
        cvs = [(1.0 / max(m, 0.01)) for m in feature_means]
        server_top_k = sorted(range(len(cvs)), key=lambda i: cvs[i], reverse=True)[:ServerFeatureSelector.K]
        server_names = [FEATURE_NAMES[i] for i in server_top_k]

        selected_set = set(selected)
        server_set   = set(server_names)
        overlap      = len(selected_set & server_set)
        confidence   = overlap / max(len(server_set), 1)
        discrepancies = list(selected_set - server_set)

        return {
            "confidence":    confidence,
            "discrepancies": discrepancies,
            "server_ranking": server_names,
        }

# ── Drift Governor ────────────────────────────────────────────────────────────
class DriftGovernor:
    """
    Server-side per-user drift policy.
    Decides action based on behavioral drift score + e_rec + trust.
    """
    @staticmethod
    def evaluate(
        trust_score: float,
        e_rec: float,
        behavioral_drift: float,
        adaptive_threshold: float,
        sample_count: int,
    ) -> tuple[str, str]:
        """Returns (action, reason)."""
        # Need enough samples before strict enforcement
        if sample_count < 20:
            return "ok", "profile_building"

        drift_ratio = behavioral_drift / max(adaptive_threshold, 0.01)

        if trust_score < 0.25 or (drift_ratio > 3.0 and e_rec > 0.25):
            return "disable_sensitive_apis", "severe_identity_shift"
        if trust_score < 0.5 or drift_ratio > 2.0:
            return "passive_reauth", "identity_drift_elevated"
        if drift_ratio > 1.5 or e_rec > 0.18:
            return "flag_session", "mild_drift"
        return "ok", "identity_stable"

# ── Honeypot ──────────────────────────────────────────────────────────────────
class HoneypotEngine:
    def __init__(self): self._log: list[dict] = []

    def synthetic_token(self, fp: dict) -> str:
        p   = f"shadow:{fp.get('ip','?')}:{time.time()}"
        sig = hmac.new(SHADOW_SECRET.encode(), p.encode(), hashlib.sha256).hexdigest()
        return f"ep_shadow_{secrets.token_urlsafe(32)}.{sig[:16]}"

    def harvest(self, data: dict):
        self._log.append({
            "ts": time.time(), "ua": data.get("user_agent", ""),
            "theta": data.get("theta", 0), "path": data.get("path", "/"),
            "headers": data.get("headers", {}),
        })
        logger.warning("[Honeypot] θ=%.3f UA=%s", data.get("theta", 0), data.get("user_agent", "")[:60])

    def is_shadow(self, token: str) -> bool: return token.startswith("ep_shadow_")
    @property
    def signatures(self): return list(self._log)

# ── Token Manager ─────────────────────────────────────────────────────────────
class TokenManager:
    @staticmethod
    def create(uid: str, lv: list) -> str:
        vh  = hashlib.sha256(str(lv).encode()).hexdigest()[:16]
        pay = f"{uid}:{time.time():.0f}:{vh}"
        sig = hmac.new(SESSION_SECRET.encode(), pay.encode(), hashlib.sha256).hexdigest()
        return secrets.token_urlsafe(8) + "." + (pay + ":" + sig).encode().hex()

    @staticmethod
    def verify(token, uid, lv) -> bool:
        try:
            _, hp = token.split(".", 1)
            raw   = bytes.fromhex(hp).decode()
            pay, sig = raw.rsplit(":", 1)
            exp = hmac.new(SESSION_SECRET.encode(), pay.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, exp): return False
            _, ts, vh = pay.rsplit(":", 2)
            if hashlib.sha256(str(lv).encode()).hexdigest()[:16] != vh: return False
            if time.time() - float(ts) > 1800: return False
            return True
        except:
            return False

_honeypot = HoneypotEngine()
_argon    = PasswordHasher(memory_cost=65_536, time_cost=2, parallelism=4)

def rl_reward(theta, h_exp, action, load):
    if theta < 0.3 and action >= 2: return  2.0
    if theta < 0.3 and action <  2: return -2.0
    if theta > 0.7 and h_exp > 0.6 and action == 0: return 1.0
    if theta > 0.7 and action == 3: return -0.5
    if load  > 0.85: return -0.3
    return 0.0

# ── Pydantic Request Models ───────────────────────────────────────────────────
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

# ── Auth Routes ───────────────────────────────────────────────────────────────
@app.post("/auth/register")
async def register(req: UserCreate, request: Request):
    if await user_exists(db_handler.db, req.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="User with this email already exists")
    state  = np.array([0.8, 0.8, 0.5], dtype=np.float32)
    action = dqn_agent.select_action(state)
    m, t, p = Argon2Params.from_action(action)
    ph     = PasswordHasher(memory_cost=m, time_cost=t, parallelism=p)
    password_hash = ph.hash(req.plain_password)
    try:
        user_id = await create_user(db_handler.db, req.email, password_hash)
        lv      = [0.0] * 32
        session_token = TokenManager.create(user_id, lv)
        await create_session(db_handler.db, user_id, session_token, lv)
        logger.info(f"[Auth] New user registered: {req.email}")
        return {
            "success": True,
            "user_id": user_id,
            "email":   req.email,
            "session_token": session_token,
            "message": "User registered successfully",
        }
    except Exception as e:
        logger.error(f"[Auth] Registration error: {e}")
        raise HTTPException(status_code=500, detail="Failed to register user")

@app.post("/auth/login")
async def login(req: UserLogin, request: Request):
    try:
        user = await get_user_by_email(db_handler.db, req.email)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not user.get("is_active", False):
            raise HTTPException(status_code=403, detail="User account is inactive")
        try:
            PasswordHasher().verify(user["password_hash"], req.plain_password)
        except VerifyMismatchError:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        await update_last_login(db_handler.db, user["_id"])
        lv = [0.0] * 32
        session_token = TokenManager.create(user["_id"], lv)
        await create_session(db_handler.db, user["_id"], session_token, lv)
        logger.info(f"[Auth] User login: {req.email}")
        return {
            "success":        True,
            "session_token":  session_token,
            "user_id":        user["_id"],
            "email":          user["email"],
            "security_level": user.get("security_level", "standard"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Auth] Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

@app.post("/auth/logout")
async def logout(session_token: str):
    try:
        await invalidate_session(db_handler.db, session_token)
        return {"success": True, "message": "Logged out successfully"}
    except Exception as e:
        logger.error(f"[Auth] Logout error: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")

# ── Score Route ───────────────────────────────────────────────────────────────
@app.post("/score")
async def score(req: ScoreReq, request: Request):
    state  = np.array([req.theta, req.h_exp, req.server_load], dtype=np.float32)
    action = dqn_agent.select_action(state)
    m, t, p = Argon2Params.from_action(action)

    if req.theta < 0.1:
        try:
            await store_honeypot_entry(
                db_handler.db,
                user_agent=req.user_agent,
                theta=req.theta,
                ip_address=getattr(request.client, "host", "?"),
                path="/",
            )
        except Exception as e:
            logger.error(f"[Honeypot] Storage error: {e}")
        _honeypot.harvest({
            "theta": req.theta, "user_agent": req.user_agent,
            "ip": getattr(request.client, "host", "?"),
        })
        return {
            "session_token":  _honeypot.synthetic_token({"ip": getattr(request.client, "host", "?")}),
            "shadow_mode":    True,
            "argon2_params":  {"m": m, "t": t, "p": p},
            "humanity_score": req.theta,
            "entropy_score":  req.h_exp,
            "action_label":   ACTION_LABELS[action],
        }

    uid   = "usr_" + secrets.token_hex(6)
    lv    = req.latent_vector or [0.] * 32
    token = TokenManager.create(uid, lv)
    logger.info("[Score] θ=%.3f H=%.3f → %s (m=%d)", req.theta, req.h_exp, ACTION_LABELS[action], m)
    return {
        "session_token":  token,
        "shadow_mode":    False,
        "argon2_params":  {"m": m, "t": t, "p": p},
        "humanity_score": req.theta,
        "entropy_score":  req.h_exp,
        "action_label":   ACTION_LABELS[action],
    }

# ── Password Routes ───────────────────────────────────────────────────────────
@app.post("/password/hash")
async def pw_hash(req: PwHashReq, user_id: Optional[str] = None):
    state  = np.array([req.theta, req.h_exp, 0.5], dtype=np.float32)
    action = dqn_agent.select_action(state)
    m, t, p = Argon2Params.from_action(action)
    ph     = PasswordHasher(memory_cost=m, time_cost=t, parallelism=p)
    t0     = time.perf_counter()
    hashed = ph.hash(req.plain_password)
    ms     = (time.perf_counter() - t0) * 1000
    if user_id:
        try:
            await update_user_security_level(db_handler.db, user_id, ACTION_LABELS[action])
        except Exception as e:
            logger.error(f"[Password] Update profile error: {e}")
    return {"hash": hashed, "action": ACTION_LABELS[action], "elapsed_ms": ms,
            "argon2_params": {"m": m, "t": t, "p": p}}

@app.post("/password/verify")
async def pw_verify(req: PwHashReq):
    try:
        PasswordHasher().verify(req.stored_hash, req.plain_password)
        return {"valid": True}
    except VerifyMismatchError:
        return {"valid": False}

# ── Session Verify (Per-User Drift Aware) ─────────────────────────────────────
@app.post("/session/verify")
async def session_verify(req: SessionVerifyRequest, request: Request):
    """
    Extended watchdog heartbeat.
    Incorporates per-user behavioral drift and adaptive threshold.
    Logs drift events for forensic audit.
    """
    action, reason = DriftGovernor.evaluate(
        trust_score=req.trust_score,
        e_rec=req.e_rec,
        behavioral_drift=req.behavioral_drift,
        adaptive_threshold=req.adaptive_threshold,
        sample_count=req.sample_count,
    )

    if action != "ok":
        logger.warning(
            "[Watchdog] user=%s action=%s reason=%s drift=%.3f e_rec=%.4f trust=%.2f",
            req.user_id, action, reason,
            req.behavioral_drift, req.e_rec, req.trust_score,
        )
        # Log drift event to MongoDB
        try:
            await log_drift_event(
                db_handler.db,
                user_id=req.user_id,
                drift_score=req.behavioral_drift,
                adaptive_threshold=req.adaptive_threshold,
                trust_score=req.trust_score,
                e_rec=req.e_rec,
                selected_features=req.selected_features,
                action=action,
                session_token=req.session_token,
            )
        except Exception as e:
            logger.error(f"[Watchdog] Drift log error: {e}")

    return {
        "action":             action,
        "reason":             reason,
        "trust_score":        req.trust_score,
        "e_rec":              req.e_rec,
        "behavioral_drift":   req.behavioral_drift,
        "adaptive_threshold": req.adaptive_threshold,
    }

# ── Per-User Biometric Profile Routes ─────────────────────────────────────────
@app.post("/biometric/profile/update")
async def update_biometric_profile(req: BiometricProfileUpdateRequest):
    """
    Receive per-user biometric profile sync from browser.
    Stores feature selector state, behavioral EMA, and drift stats.
    """
    try:
        # Validate feature selection consistency
        validation = ServerFeatureSelector.validate_selection(
            req.selected_features, req.feature_means
        )
        logger.info(
            "[Profile] user=%s samples=%d drift=%.3f features=%s confidence=%.2f",
            req.user_id, req.sample_count, req.last_drift,
            req.selected_features, validation["confidence"],
        )

        await upsert_biometric_profile(
            db_handler.db,
            user_id=req.user_id,
            sample_count=req.sample_count,
            last_drift=req.last_drift,
            adaptive_threshold=req.adaptive_threshold,
            feature_means=req.feature_means,
            selected_features=req.selected_features,
            ema_profile=req.ema_profile,
            ema_variance=req.ema_variance,
        )

        # Snapshot feature selection every 50 samples for stability tracking
        if req.sample_count > 0 and req.sample_count % 50 == 0:
            await record_feature_selection(
                db_handler.db,
                user_id=req.user_id,
                selected_features=req.selected_features,
                feature_means=req.feature_means,
                feature_variances=req.ema_variance or [0.0] * 8,
                sample_count=req.sample_count,
            )

        return {
            "success":    True,
            "validation": validation,
            "stored_features": req.selected_features,
        }
    except Exception as e:
        logger.error(f"[Profile] Update error: {e}")
        raise HTTPException(status_code=500, detail="Profile update failed")

@app.get("/biometric/profile/{user_id}")
async def get_biometric_profile_api(user_id: str):
    """Full biometric profile for a user."""
    try:
        profile = await get_biometric_profile(db_handler.db, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"user_id": user_id, "profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Profile] Fetch error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve profile")

@app.get("/biometric/profile/{user_id}/summary")
async def get_biometric_profile_summary_api(user_id: str):
    """Lightweight profile summary (no heavy arrays)."""
    try:
        summary = await get_biometric_profile_summary(db_handler.db, user_id)
        if not summary:
            return {"user_id": user_id, "profile": None, "exists": False}
        return {"user_id": user_id, "profile": summary, "exists": True}
    except Exception as e:
        logger.error(f"[Profile] Summary fetch error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve profile summary")

@app.get("/biometric/profile/{user_id}/drift")
async def get_drift_history(user_id: str, limit: int = 50):
    """Drift event log for a user."""
    try:
        events  = await get_drift_events(db_handler.db, user_id, limit=limit)
        summary = await get_drift_summary(db_handler.db, user_id)
        return {"user_id": user_id, "events": events, "summary": summary}
    except Exception as e:
        logger.error(f"[Drift] History fetch error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve drift history")

@app.get("/biometric/profile/{user_id}/features")
async def get_feature_selection_history_api(user_id: str, limit: int = 20):
    """Feature selection history for a user (stability analysis)."""
    try:
        history = await get_feature_selection_history(db_handler.db, user_id, limit=limit)
        return {"user_id": user_id, "history": history, "count": len(history)}
    except Exception as e:
        logger.error(f"[Features] History fetch error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve feature history")

@app.post("/biometric/extract")
async def biometric_extract(raw_signal: list[float]):
    """Extract features using 1D CNN from raw timing signal."""
    try:
        signal_tensor = torch.FloatTensor(raw_signal).unsqueeze(0).unsqueeze(0)
        with torch.no_grad():
            features = cnn_model(signal_tensor)
        return {
            "success":  True,
            "features": features.squeeze().tolist(),
            "dim":      len(features.squeeze().tolist()),
        }
    except Exception as e:
        logger.error(f"[CNN] Extract error: {e}")
        raise HTTPException(status_code=500, detail="Feature extraction failed")

# ── Honeypot Routes ───────────────────────────────────────────────────────────
@app.get("/honeypot/signatures")
async def signatures():
    try:
        db_sigs = await get_honeypot_signatures(db_handler.db, limit=100)
        count   = await get_honeypot_count(db_handler.db)
    except Exception as e:
        logger.error(f"[Honeypot] Fetch error: {e}")
        db_sigs, count = [], 0
    all_sigs = _honeypot.signatures + db_sigs
    return {"signatures": all_sigs, "count": count + len(_honeypot.signatures)}

# ── Model API Routes ──────────────────────────────────────────────────────────
@app.post("/models/dqn/action")
async def dqn_action(state: list[float]):
    try:
        if len(state) != 3:
            raise ValueError("State must be 3-dimensional [theta, h_exp, server_load]")
        action = dqn_agent.select_action(np.array(state, dtype=np.float32))
        return {"action": int(action), "action_label": ACTION_LABELS[action], "state": state}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/models/mab/select")
async def mab_select():
    try:
        arm = mab_agent.select_arm()
        return {"selected_arm": int(arm), "n_arms": mab_agent.n_arms,
                "arm_values": mab_agent.values.tolist()}
    except Exception as e:
        raise HTTPException(status_code=500, detail="MAB selection failed")

@app.post("/models/mab/update")
async def mab_update(arm: int, reward: float):
    try:
        if arm < 0 or arm >= mab_agent.n_arms:
            raise ValueError(f"Invalid arm {arm}")
        mab_agent.update(arm, reward)
        return {"success": True, "arm": arm, "reward": reward,
                "updated_values": mab_agent.values.tolist()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/models/ppo/evaluate")
async def ppo_evaluate(state: list[float]):
    try:
        if len(state) != 10:
            raise ValueError("State must be 10-dimensional")
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        with torch.no_grad():
            policy_output = ppo_agent.policy(state_tensor)
        action_probs = policy_output.squeeze().tolist()
        return {"state": state, "action_probabilities": action_probs,
                "recommended_action": int(np.argmax(action_probs))}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ── Admin Routes ──────────────────────────────────────────────────────────────
@app.get("/admin/honeypot/dashboard")
async def honeypot_dashboard():
    try:
        count = await get_honeypot_count(db_handler.db)
        sigs  = await get_honeypot_signatures(db_handler.db, limit=50)
        return {
            "total_count":       count + len(_honeypot.signatures),
            "recent_signatures": sigs,
            "in_memory_count":   len(_honeypot.signatures),
            "timestamp":         time.time(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard")

@app.get("/admin/models-status")
async def models_status():
    return {
        "models": {
            "dqn":   {"status": "loaded", "type": "Deep Q-Network",    "state_dim": 3,  "action_dim": 4},
            "mab":   {"status": "loaded", "type": "Multi-Armed Bandit", "n_arms": mab_agent.n_arms,
                      "arm_values": mab_agent.values.tolist()},
            "ppo":   {"status": "loaded", "type": "PPO",               "state_dim": 10, "action_dim": 3},
            "cnn1d": {"status": "loaded", "type": "1D CNN",            "output_dim": 32},
        },
        "feature_names": FEATURE_NAMES,
        "timestamp": time.time(),
    }

@app.get("/health")
async def health():
    return {"status": "ok"}
