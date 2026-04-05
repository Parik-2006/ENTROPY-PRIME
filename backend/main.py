"""
Entropy Prime — FastAPI Backend (production-ready with MongoDB)
Phases 2, 3, 4 — RL Governor · Honeypot · Session Watchdog · User Authentication
"""
from __future__ import annotations

import hashlib, hmac, logging, os, secrets, time
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import torch, torch.nn as nn, torch.optim as optim
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
    store_honeypot_entry, get_honeypot_signatures, get_honeypot_count
)
from models import (
    UserCreate, UserLogin, UserResponse, AuthResponse,
    PasswordHashResponse
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("entropy_prime")

# ── Database ──────────────────────────────────────────────────────────────────
db_handler = Database()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Entropy Prime", version="2.0.0 (MongoDB)")

app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize MongoDB on startup"""
    await db_handler.connect_to_mongo()
    logger.info("✓ Entropy Prime backend initialized with MongoDB")

@app.on_event("shutdown")
async def shutdown_event():
    """Close MongoDB connection on shutdown"""
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


# ── Modular Model Imports ─────────────────────────────────────────────────────
from models.dqn import DQNAgent
from models.mab import MABAgent
from models.ppo import PPOAgent
from models.cnn1d import CNN1D

# Instantiate models (replace with checkpoint loading as needed)
dqn_agent = DQNAgent(state_dim=3, action_dim=4)
mab_agent = MABAgent(n_arms=3)
ppo_agent = PPOAgent(state_dim=10, action_dim=3)
cnn_model = CNN1D(input_channels=1, out_dim=32)

def rl_reward(theta, h_exp, action, load):
    if theta < 0.3 and action >= 2: return  2.0
    if theta < 0.3 and action <  2: return -2.0
    if theta > 0.7 and h_exp > 0.6 and action == 0: return 1.0
    if theta > 0.7 and action == 3: return -0.5
    if load  > 0.85: return -0.3
    return 0.0

# ── Honeypot ──────────────────────────────────────────────────────────────────
class HoneypotEngine:
    def __init__(self): self._log: list[dict] = []

    def synthetic_token(self, fp: dict) -> str:
        p   = f"shadow:{fp.get('ip','?')}:{time.time()}"
        sig = hmac.new(SHADOW_SECRET.encode(), p.encode(), hashlib.sha256).hexdigest()
        return f"ep_shadow_{secrets.token_urlsafe(32)}.{sig[:16]}"

    def harvest(self, data: dict):
        self._log.append({
            "ts": time.time(), "ua": data.get("user_agent",""),
            "theta": data.get("theta",0), "path": data.get("path","/"),
            "headers": data.get("headers",{})
        })
        logger.warning("[Honeypot] θ=%.3f UA=%s", data.get("theta",0), data.get("user_agent","")[:60])

    def is_shadow(self, token: str) -> bool: return token.startswith("ep_shadow_")
    @property
    def signatures(self): return list(self._log)

# ── Session Token ─────────────────────────────────────────────────────────────
class TokenManager:
    @staticmethod
    def create(uid: str, lv: list) -> str:
        vh  = hashlib.sha256(str(lv).encode()).hexdigest()[:16]
        pay = f"{uid}:{time.time():.0f}:{vh}"
        sig = hmac.new(SESSION_SECRET.encode(), pay.encode(), hashlib.sha256).hexdigest()
        return secrets.token_urlsafe(8) + "." + (pay+":"+sig).encode().hex()

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
        except: return False

# ── Singletons ────────────────────────────────────────────────────────────────
_honeypot = HoneypotEngine()
_argon    = PasswordHasher(memory_cost=65_536, time_cost=2, parallelism=4)
ACTION_LABELS = ["economy","standard","hard","punisher"]

# ── Pydantic models ───────────────────────────────────────────────────────────
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
    stored_hash:    str = ""
    theta:          float = 0.5
    h_exp:          float = 0.5

class SessionVerifyReq(BaseModel):
    session_token: str
    user_id:       str
    latent_vector: list[float]
    e_rec:         float = Field(..., ge=0)
    trust_score:   float = Field(..., ge=0, le=1)

# ── Routes ────────────────────────────────────────────────────────────────────

# ── Authentication Routes ──────────────────────────────────────────────────────
@app.post("/auth/register")
async def register(req: UserCreate, request: Request):
    """Register a new user with email and password"""
    # Check if user already exists
    if await user_exists(db_handler.db, req.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        )
    
    # Hash password with RL-hardened Argon2id params
    state = np.array([0.8, 0.8, 0.5], dtype=np.float32)  # Assume legitimate user
    action = dqn_agent.select_action(state)
    m, t, p = Argon2Params.from_action(action)
    
    ph = PasswordHasher(memory_cost=m, time_cost=t, parallelism=p)
    password_hash = ph.hash(req.plain_password)
    
    # Create user in MongoDB
    try:
        user_id = await create_user(db_handler.db, req.email, password_hash)
        
        # Create initial session
        lv = [0.0] * 32
        session_token = TokenManager.create(user_id, lv)
        await create_session(db_handler.db, user_id, session_token, lv)
        
        logger.info(f"[Auth] New user registered: {req.email}")
        
        return {
            "success": True,
            "user_id": user_id,
            "email": req.email,
            "session_token": session_token,
            "message": "User registered successfully"
        }
    except Exception as e:
        logger.error(f"[Auth] Registration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user"
        )

@app.post("/auth/login")
async def login(req: UserLogin, request: Request):
    """Login user with email and password"""
    try:
        # Get user from MongoDB
        user = await get_user_by_email(db_handler.db, req.email)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        if not user.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive"
            )
        
        # Verify password
        try:
            PasswordHasher().verify(user["password_hash"], req.plain_password)
        except VerifyMismatchError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Update last login
        await update_last_login(db_handler.db, user["_id"])
        
        # Create new session
        lv = [0.0] * 32
        session_token = TokenManager.create(user["_id"], lv)
        await create_session(db_handler.db, user["_id"], session_token, lv)
        
        logger.info(f"[Auth] User login: {req.email}")
        
        return {
            "success": True,
            "session_token": session_token,
            "user_id": user["_id"],
            "email": user["email"],
            "security_level": user.get("security_level", "standard")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Auth] Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@app.post("/auth/logout")
async def logout(session_token: str):
    """Logout user by invalidating session"""
    try:
        await invalidate_session(db_handler.db, session_token)
        return {"success": True, "message": "Logged out successfully"}
    except Exception as e:
        logger.error(f"[Auth] Logout error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

# ── Biometric & Scoring Routes ─────────────────────────────────────────────────
@app.post("/score")
async def score(req: ScoreReq, request: Request):
    state  = np.array([req.theta, req.h_exp, req.server_load], dtype=np.float32)
    action = dqn_agent.select_action(state)
    m, t, p = Argon2Params.from_action(action)

    if req.theta < 0.1:
        # Store bot signature in MongoDB honeypot
        try:
            await store_honeypot_entry(
                db_handler.db,
                user_agent=req.user_agent,
                theta=req.theta,
                ip_address=getattr(request.client, "host", "?"),
                path="/"
            )
        except Exception as e:
            logger.error(f"[Honeypot] Storage error: {str(e)}")
        
        _honeypot.harvest({
            "theta": req.theta, "user_agent": req.user_agent,
            "ip": getattr(request.client, "host", "?"),
        })
        return {
            "session_token":  _honeypot.synthetic_token({"ip": getattr(request.client,"host","?")}),
            "shadow_mode":    True,
            "argon2_params":  {"m":m,"t":t,"p":p},
            "humanity_score": req.theta,
            "entropy_score":  req.h_exp,
            "action_label":   ACTION_LABELS[action],
        }

    uid   = "usr_" + secrets.token_hex(6)
    lv    = req.latent_vector or [0.]*32
    token = TokenManager.create(uid, lv)
    logger.info("[Score] θ=%.3f H=%.3f → %s (m=%d)", req.theta, req.h_exp, ACTION_LABELS[action], m)

    return {
        "session_token":  token,
        "shadow_mode":    False,
        "argon2_params":  {"m":m,"t":t,"p":p},
        "humanity_score": req.theta,
        "entropy_score":  req.h_exp,
        "action_label":   ACTION_LABELS[action],
    }

@app.post("/password/hash")
async def pw_hash(req: PwHashReq, user_id: Optional[str] = None):
    """Hash password with RL-selected Argon2id parameters
    
    Optionally store hash in MongoDB if user_id is provided
    """
    state  = np.array([req.theta, req.h_exp, 0.5], dtype=np.float32)
    action = dqn_agent.select_action(state)
    m, t, p = Argon2Params.from_action(action)
    ph     = PasswordHasher(memory_cost=m, time_cost=t, parallelism=p)
    t0     = time.perf_counter()
    hashed = ph.hash(req.plain_password)
    ms     = (time.perf_counter()-t0)*1000
    rew    = rl_reward(req.theta, req.h_exp, action, 0.5)
    # Optionally train DQN here
    
    # Store in user profile if user_id is provided
    if user_id:
        try:
            await update_user_security_level(db_handler.db, user_id, ACTION_LABELS[action])
        except Exception as e:
            logger.error(f"[Password] Update profile error: {str(e)}")
    
    return {
        "hash": hashed,
        "action": ACTION_LABELS[action],
        "elapsed_ms": ms,
        "argon2_params": {"m":m,"t":t,"p":p}
    }

@app.post("/password/verify")
async def pw_verify(req: PwHashReq):
    try:
        PasswordHasher().verify(req.stored_hash, req.plain_password)
        return {"valid": True}
    except VerifyMismatchError:
        return {"valid": False}

@app.post("/session/verify")
async def session_verify(req: SessionVerifyReq):
    action = "ok"
    if req.trust_score < 0.25:
        action = "disable_sensitive_apis"
        logger.warning("[Watchdog] Severe shift trust=%.2f e_rec=%.4f", req.trust_score, req.e_rec)
    elif req.trust_score < 0.5:
        action = "passive_reauth"
        logger.info("[Watchdog] Passive reauth trust=%.2f", req.trust_score)
    return {"action": action, "trust_score": req.trust_score, "e_rec": req.e_rec}

@app.get("/honeypot/signatures")
async def signatures():
    """Get honeypot bot signatures from MongoDB and in-memory cache"""
    try:
        # Fetch from MongoDB
        db_sigs = await get_honeypot_signatures(db_handler.db, limit=100)
        count = await get_honeypot_count(db_handler.db)
    except Exception as e:
        logger.error(f"[Honeypot] Fetch error: {str(e)}")
        db_sigs = []
        count = 0
    
    # Combine with in-memory cache
    all_sigs = _honeypot.signatures + db_sigs
    return {"signatures": all_sigs, "count": count + len(_honeypot.signatures)}

# ── Biometric Feature Extraction (Phase 1) ────────────────────────────────────
@app.post("/biometric/extract")
async def biometric_extract(raw_signal: list[float]):
    """Extract features using 1D CNN from raw timing signal"""
    try:
        signal_tensor = torch.FloatTensor(raw_signal).unsqueeze(0).unsqueeze(0)
        with torch.no_grad():
            features = cnn_model(signal_tensor)
        return {
            "success": True,
            "features": features.squeeze().tolist(),
            "dim": len(features.squeeze().tolist())
        }
    except Exception as e:
        logger.error(f"[CNN] Extract error: {str(e)}")
        raise HTTPException(status_code=500, detail="Feature extraction failed")

@app.get("/biometric/profile/{user_id}")
async def get_biometric_profile_api(user_id: str):
    """Retrieve user's biometric profile from MongoDB"""
    try:
        profile = await get_biometric_profile(db_handler.db, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"user_id": user_id, "profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Biometric] Profile fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve profile")

# ── DQN Model API (Phase 2) ────────────────────────────────────────────────────
@app.post("/models/dqn/action")
async def dqn_action(state: list[float]):
    """Get DQN action for given state"""
    try:
        if len(state) != 3:
            raise ValueError("State must be 3-dimensional [theta, h_exp, server_load]")
        state_array = np.array(state, dtype=np.float32)
        action = dqn_agent.select_action(state_array)
        return {
            "action": int(action),
            "action_label": ACTION_LABELS[action],
            "state": state
        }
    except Exception as e:
        logger.error(f"[DQN] Action error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# ── MAB Model API (Phase 3 - Deceiver) ─────────────────────────────────────────
@app.post("/models/mab/select")
async def mab_select():
    """Select arm from Multi-Armed Bandit"""
    try:
        arm = mab_agent.select_arm()
        return {
            "selected_arm": int(arm),
            "n_arms": mab_agent.n_arms,
            "arm_values": mab_agent.values.tolist()
        }
    except Exception as e:
        logger.error(f"[MAB] Select error: {str(e)}")
        raise HTTPException(status_code=500, detail="MAB selection failed")

@app.post("/models/mab/update")
async def mab_update(arm: int, reward: float):
    """Update MAB with reward from selected arm"""
    try:
        if arm < 0 or arm >= mab_agent.n_arms:
            raise ValueError(f"Invalid arm {arm}")
        mab_agent.update(arm, reward)
        return {
            "success": True,
            "arm": arm,
            "reward": reward,
            "updated_values": mab_agent.values.tolist()
        }
    except Exception as e:
        logger.error(f"[MAB] Update error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# ── PPO Model API (Phase 4 - Watchdogz) ────────────────────────────────────────
@app.post("/models/ppo/evaluate")
async def ppo_evaluate(state: list[float]):
    """Evaluate session state with PPO for identity shift detection"""
    try:
        if len(state) != 10:
            raise ValueError("State must be 10-dimensional")
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        with torch.no_grad():
            policy_output = ppo_agent.policy(state_tensor)
        action_probs = policy_output.squeeze().tolist()
        return {
            "state": state,
            "action_probabilities": action_probs,
            "recommended_action": int(np.argmax(action_probs))
        }
    except Exception as e:
        logger.error(f"[PPO] Evaluate error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# ── Admin APIs ─────────────────────────────────────────────────────────────────
@app.get("/admin/honeypot/dashboard")
async def honeypot_dashboard():
    """Admin honeypot dashboard with statistics"""
    try:
        count = await get_honeypot_count(db_handler.db)
        sigs = await get_honeypot_signatures(db_handler.db, limit=50)
        return {
            "total_count": count + len(_honeypot.signatures),
            "recent_signatures": sigs,
            "in_memory_count": len(_honeypot.signatures),
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"[Admin] Honeypot dashboard error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard")

@app.get("/admin/models-status")
async def models_status():
    """Get status of all trained models"""
    return {
        "models": {
            "dqn": {
                "status": "loaded",
                "type": "Deep Q-Network",
                "state_dim": 3,
                "action_dim": 4,
                "phase": "Phase 2"
            },
            "mab": {
                "status": "loaded",
                "type": "Multi-Armed Bandit",
                "n_arms": mab_agent.n_arms,
                "arm_values": mab_agent.values.tolist(),
                "phase": "Phase 3"
            },
            "ppo": {
                "status": "loaded",
                "type": "Proximal Policy Optimization",
                "state_dim": 10,
                "action_dim": 3,
                "phase": "Phase 4"
            },
            "cnn1d": {
                "status": "loaded",
                "type": "1D CNN",
                "output_dim": 32,
                "phase": "Phase 1"
            }
        },
        "timestamp": time.time()
    }

@app.get("/health")
async def health():
    return {"status": "ok"}
