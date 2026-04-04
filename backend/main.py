"""
Entropy Prime — FastAPI Backend (production-ready)
Phases 2, 3, 4 — RL Governor · Honeypot · Session Watchdog
"""
from __future__ import annotations

import hashlib, hmac, logging, os, secrets, time
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch, torch.nn as nn, torch.optim as optim
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("entropy_prime")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Entropy Prime", version="1.0.0")

app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# ── DQN ───────────────────────────────────────────────────────────────────────
class QNetwork(nn.Module):
    def __init__(self, s=3, a=4):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(s,64), nn.ReLU(), nn.Linear(64,64), nn.ReLU(), nn.Linear(64,a))
    def forward(self, x): return self.net(x)

@dataclass
class Transition:
    state: np.ndarray; action: int; reward: float; next_state: np.ndarray; done: bool

class ReplayBuffer:
    def __init__(self, cap=10_000): self._buf = deque(maxlen=cap)
    def push(self, t): self._buf.append(t)
    def sample(self, n): idx = np.random.choice(len(self._buf), n, replace=False); return [self._buf[i] for i in idx]
    def __len__(self): return len(self._buf)

class RLGovernor:
    GAMMA=.99; LR=1e-3; EPS_START=1.; EPS_END=.05; EPS_DECAY=2000
    BATCH=64; TARGET_UPDATE=200

    def __init__(self):
        self.q = QNetwork(); self.tq = QNetwork()
        self.tq.load_state_dict(self.q.state_dict()); self.tq.eval()
        self.opt = optim.Adam(self.q.parameters(), lr=self.LR)
        self.buf = ReplayBuffer(); self._steps = 0
        ckpt = os.environ.get("EP_RL_CHECKPOINT","")
        if ckpt and os.path.exists(ckpt):
            st = torch.load(ckpt, map_location="cpu")
            self.q.load_state_dict(st.get("q_net", st.get("actor_critic", st)))
            self._steps = st.get("steps", 0)
            logger.info("Checkpoint loaded: %s", ckpt)

    def greedy(self, s: np.ndarray) -> int:
        with torch.no_grad():
            return int(self.q(torch.tensor(s, dtype=torch.float32).unsqueeze(0)).argmax(1).item())

    def epsilon_greedy(self, s):
        self._steps += 1
        eps = self.EPS_END + (self.EPS_START-self.EPS_END)*np.exp(-self._steps/self.EPS_DECAY)
        return np.random.randint(4) if np.random.rand() < eps else self.greedy(s)

    def train_step(self, tr: Transition):
        self.buf.push(tr)
        if len(self.buf) < self.BATCH: return
        batch = self.buf.sample(self.BATCH)
        S  = torch.tensor(np.stack([b.state for b in batch]),      dtype=torch.float32)
        A  = torch.tensor([b.action for b in batch],               dtype=torch.long)
        R  = torch.tensor([b.reward for b in batch],               dtype=torch.float32)
        S2 = torch.tensor(np.stack([b.next_state for b in batch]), dtype=torch.float32)
        D  = torch.tensor([b.done for b in batch],                 dtype=torch.float32)
        q  = self.q(S).gather(1, A.unsqueeze(1)).squeeze()
        with torch.no_grad(): nq = self.tq(S2).max(1).values
        loss = nn.functional.smooth_l1_loss(q, R + self.GAMMA*nq*(1-D))
        self.opt.zero_grad(); loss.backward()
        nn.utils.clip_grad_norm_(self.q.parameters(), 1.); self.opt.step()
        if self._steps % self.TARGET_UPDATE == 0:
            self.tq.load_state_dict(self.q.state_dict())

    @staticmethod
    def reward(theta, h_exp, action, load):
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
_gov      = RLGovernor()
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
@app.post("/score")
async def score(req: ScoreReq, request: Request):
    state  = np.array([req.theta, req.h_exp, req.server_load], dtype=np.float32)
    action = _gov.greedy(state)
    m, t, p = Argon2Params.from_action(action)

    if req.theta < 0.1:
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
async def pw_hash(req: PwHashReq):
    state  = np.array([req.theta, req.h_exp, 0.5], dtype=np.float32)
    action = _gov.greedy(state)
    m, t, p = Argon2Params.from_action(action)
    ph     = PasswordHasher(memory_cost=m, time_cost=t, parallelism=p)
    t0     = time.perf_counter()
    hashed = ph.hash(req.plain_password)
    ms     = (time.perf_counter()-t0)*1000
    rew    = RLGovernor.reward(req.theta, req.h_exp, action, 0.5)
    _gov.train_step(Transition(state, action, rew, state, False))
    return {"hash": hashed, "action": ACTION_LABELS[action],
            "elapsed_ms": ms, "argon2_params": {"m":m,"t":t,"p":p}}

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
    return {"signatures": _honeypot.signatures, "count": len(_honeypot.signatures)}

@app.get("/health")
async def health():
    return {"status": "ok", "rl_steps": _gov._steps}
