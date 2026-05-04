"""
models/ppo.py  —  Proximal Policy Optimisation Agent (Session Watchdog, Stage 4)

Actor-Critic PPO for continuous session identity verification.
State  : 10-dim vector (see stage4_watchdog._build_state)
Actions: 0=OK, 1=PASSIVE_REAUTH, 2=DISABLE_SENSITIVE_API

select_action() returns (action_index, action_probability) so the caller
can derive a confidence band from the max probability.
"""
from __future__ import annotations

import logging

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger("entropy_prime.models.ppo")


class _Actor(nn.Module):
    def __init__(self, state_dim: int, action_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 64), nn.Tanh(),
            nn.Linear(64, 64),        nn.Tanh(),
            nn.Linear(64, action_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.softmax(self.net(x), dim=-1)


class _Critic(nn.Module):
    def __init__(self, state_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 64), nn.Tanh(),
            nn.Linear(64, 64),        nn.Tanh(),
            nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class PPOAgent:
    """
    Inference-only PPO agent.

    select_action() is the only method called at request time.
    Training is performed offline and weights loaded from a checkpoint.
    """

    def __init__(self, state_dim: int = 10, action_dim: int = 3):
        self.state_dim  = state_dim
        self.action_dim = action_dim
        self.actor      = _Actor(state_dim, action_dim)
        self.critic     = _Critic(state_dim)
        self.actor.eval()
        self.critic.eval()

    # ── Inference ─────────────────────────────────────────────────────────────

    def select_action(self, state: np.ndarray) -> tuple[int, float]:
        """
        Returns (action_index, action_probability).

        Greedy (argmax) — no stochastic sampling at inference time.
        Returns the max action probability so stage4 can derive a confidence band.
        """
        with torch.no_grad():
            t     = torch.FloatTensor(state).unsqueeze(0)
            probs = self.actor(t).squeeze(0)          # shape: (action_dim,)
            idx   = int(probs.argmax().item())
            prob  = float(probs[idx].item())
        return idx, prob

    # ── Checkpoint I/O ────────────────────────────────────────────────────────

    def load_checkpoint(self, path: str) -> None:
        ckpt = torch.load(path, map_location="cpu")
        if isinstance(ckpt, dict):
            if "actor" in ckpt:
                self.actor.load_state_dict(ckpt["actor"])
            if "critic" in ckpt:
                self.critic.load_state_dict(ckpt["critic"])
        else:
            # Bare state dict assumed to belong to the actor
            self.actor.load_state_dict(ckpt)
        self.actor.eval()
        self.critic.eval()
        logger.debug("PPO weights loaded from %s", path)

    def save_checkpoint(self, path: str) -> None:
        torch.save(
            {"actor": self.actor.state_dict(), "critic": self.critic.state_dict()},
            path,
        )
