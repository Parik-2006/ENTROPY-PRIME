"""
Entropy Prime — RL Governor Pre-Trainer (DQN)
Warm-starts the DQN policy before the server starts.

Usage:
    python backend/train.py
    python backend/train.py --episodes 200000 --bot-ratio 0.35 --out checkpoints/governor.pt
"""
from __future__ import annotations

import argparse, os, time
from collections import deque
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

# ── Thresholds (mirror pipeline/contracts.py without importing it) ─────────────
BOT_THETA_HARD   = 0.10
BOT_THETA_SOFT   = 0.30
SERVER_LOAD_HIGH = 0.85

# ── Q-Network (same architecture as models/dqn.py) ────────────────────────────
class QNetwork(nn.Module):
    def __init__(self, s: int = 3, a: int = 4):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(s, 128), nn.ReLU(),
            nn.Linear(128, 128), nn.ReLU(),
            nn.Linear(128, a),
        )
    def forward(self, x): return self.net(x)


# ── Synthetic auth environment ────────────────────────────────────────────────
class AuthEnv:
    """
    Simulates the distribution of requests the server will see.
    State:  [theta, h_exp, server_load]   all in [0, 1]
    Action: {0:economy, 1:standard, 2:hard, 3:punisher}
    Reward: defined by _reward()
    """

    def __init__(self, bot_ratio: float = 0.30):
        self.bot_ratio   = bot_ratio
        self.server_load = 0.4

    # ── Reward function (single source of truth for training) ─────────────────
    @staticmethod
    def _reward(theta: float, h_exp: float, load: float, action: int) -> float:
        is_bot     = theta < BOT_THETA_HARD
        is_suspect = BOT_THETA_HARD <= theta < BOT_THETA_SOFT
        is_human   = theta >= BOT_THETA_SOFT
        is_strong  = h_exp > 0.6
        overloaded = load > SERVER_LOAD_HIGH

        if is_bot and action >= 2:                 return  2.0   # waste bot CPU
        if is_bot and action <  2:                 return -2.0   # too easy on bot
        if is_suspect and action >= 1:             return  0.5   # prudent hardening
        if is_human and is_strong and action == 0: return  1.0   # efficient for strong human
        if is_human and action == 3:               return -0.5   # punisher wastes server
        if overloaded and action >= 2:             return -0.3 * (action + 1)
        return 0.1

    def _sample(self):
        is_bot = np.random.rand() < self.bot_ratio
        if is_bot:
            theta = np.clip(np.random.beta(1.5, 6), 0, 1)
            h_exp = np.clip(np.random.beta(2, 5),   0, 1)
        else:
            theta = np.clip(np.random.beta(6, 1.5), 0, 1)
            h_exp = np.clip(np.random.beta(4, 2),   0, 1)
        self.server_load = np.clip(self.server_load + np.random.normal(0, 0.05), 0.1, 0.95)
        return np.array([theta, h_exp, self.server_load], dtype=np.float32)

    def reset(self):
        self._s = self._sample()
        return self._s

    def step(self, action: int):
        theta, h_exp, load = self._s
        reward = self._reward(theta, h_exp, load, action)
        self._s = self._sample()
        return self._s, float(reward), False


@dataclass
class Transition:
    s: np.ndarray; a: int; r: float; s2: np.ndarray; d: bool


class ReplayBuffer:
    def __init__(self, cap: int = 50_000):
        self._b: deque = deque(maxlen=cap)

    def push(self, t: Transition):
        self._b.append(t)

    def sample(self, n: int) -> list[Transition]:
        idx = np.random.choice(len(self._b), n, replace=False)
        return [self._b[i] for i in idx]

    def __len__(self): return len(self._b)


# ── Training loop ─────────────────────────────────────────────────────────────
def train(
    episodes:  int   = 100_000,
    bot_ratio: float = 0.30,
    out:       str   = "checkpoints/governor.pt",
):
    env = AuthEnv(bot_ratio)
    q   = QNetwork()
    tq  = QNetwork()
    tq.load_state_dict(q.state_dict())
    tq.eval()
    opt = optim.Adam(q.parameters(), lr=1e-3)
    buf = ReplayBuffer()

    GAMMA        = 0.99
    EPS_START    = 1.0
    EPS_END      = 0.05
    EPS_DECAY    = 5_000
    BATCH        = 128
    TARGET_UPDATE = 500

    s          = env.reset()
    total_r    = 0.0
    count      = 0
    t0         = time.time()

    for step in range(1, episodes + 1):
        eps = EPS_END + (EPS_START - EPS_END) * np.exp(-step / EPS_DECAY)
        if np.random.rand() < eps:
            a = np.random.randint(4)
        else:
            with torch.no_grad():
                a = int(q(torch.tensor(s, dtype=torch.float32).unsqueeze(0)).argmax(1).item())

        s2, r, done = env.step(a)
        buf.push(Transition(s, a, r, s2, done))
        total_r += r
        count   += 1
        s        = s2

        if len(buf) >= BATCH:
            batch = buf.sample(BATCH)
            S  = torch.tensor(np.stack([b.s  for b in batch]), dtype=torch.float32)
            A  = torch.tensor([b.a for b in batch],            dtype=torch.long)
            R  = torch.tensor([b.r for b in batch],            dtype=torch.float32)
            S2 = torch.tensor(np.stack([b.s2 for b in batch]), dtype=torch.float32)
            D  = torch.tensor([b.d for b in batch],            dtype=torch.float32)

            qv = q(S).gather(1, A.unsqueeze(1)).squeeze()
            with torch.no_grad():
                nq = tq(S2).max(1).values
            loss = nn.functional.smooth_l1_loss(qv, R + GAMMA * nq * (1 - D))
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(q.parameters(), 1.0)
            opt.step()

            if step % TARGET_UPDATE == 0:
                tq.load_state_dict(q.state_dict())

        if step % 10_000 == 0:
            elapsed = time.time() - t0
            print(
                f"  step {step:>8,} / {episodes:,}"
                f" | mean_reward {total_r / max(count, 1):+.3f}"
                f" | ε {eps:.3f}"
                f" | buf {len(buf):,}"
                f" | {elapsed:.0f}s"
            )
            total_r, count = 0.0, 0

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    # Save in the format DQNAgent.load_checkpoint() expects: {"q_net": state_dict}
    torch.save({"q_net": q.state_dict(), "steps": episodes}, out)
    print(f"\n✓ Checkpoint saved → {out}")
    print(f"  Set EP_RL_CHECKPOINT={out} before starting the server.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Pre-train the Entropy Prime DQN governor")
    p.add_argument("--episodes",  type=int,   default=100_000)
    p.add_argument("--bot-ratio", type=float, default=0.30)
    p.add_argument("--out",       type=str,   default="checkpoints/governor.pt")
    args = p.parse_args()

    print(f"\nTraining RL governor — {args.episodes:,} steps, bot_ratio={args.bot_ratio}")
    print("─" * 60)
    train(args.episodes, args.bot_ratio, args.out)
