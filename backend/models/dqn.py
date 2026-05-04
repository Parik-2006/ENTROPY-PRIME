"""
models/dqn.py  —  Deep Q-Network Agent (Resource Governor, Stage 3)

A minimal DQN for selecting among 4 Argon2id presets.
State  : [theta, server_load, is_suspect]  (3-dim)
Actions: 0=ECONOMY, 1=STANDARD, 2=HARD, 3=PUNISHER

In production, weights are loaded from a checkpoint trained offline.
When no checkpoint is present the network uses random initialisation
(still functional — the hard overrides in stage3_governor.py handle
the most important cases deterministically).
"""
from __future__ import annotations

import logging
import random
from typing import Optional

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger("entropy_prime.models.dqn")


class _QNetwork(nn.Module):
    def __init__(self, state_dim: int, action_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 64), nn.ReLU(),
            nn.Linear(64, 64),        nn.ReLU(),
            nn.Linear(64, action_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class DQNAgent:
    """
    Greedy-inference DQN (no training loop exposed here — train offline).

    select_action() is called at request time; it is intentionally
    epsilon-greedy with a very small epsilon so the trained policy dominates.
    """

    def __init__(self, state_dim: int = 3, action_dim: int = 4, epsilon: float = 0.05):
        self.state_dim  = state_dim
        self.action_dim = action_dim
        self.epsilon    = epsilon
        self.q_net      = _QNetwork(state_dim, action_dim)
        self.q_net.eval()   # inference mode by default

    # ── Inference ─────────────────────────────────────────────────────────────

    def select_action(self, state: np.ndarray) -> int:
        """
        Return the greedy action (or a random one with probability epsilon).
        Thread-safe: no shared mutable state is written here.
        """
        if random.random() < self.epsilon:
            return random.randrange(self.action_dim)

        with torch.no_grad():
            t = torch.FloatTensor(state).unsqueeze(0)
            q = self.q_net(t)
            return int(q.argmax(dim=1).item())

    # ── Checkpoint I/O ────────────────────────────────────────────────────────

    def load_checkpoint(self, path: str) -> None:
        """
        Load network weights from a .pt file.
        Raises on corrupt or shape-mismatched files so the caller can log and
        fall back to random weights.
        """
        ckpt = torch.load(path, map_location="cpu")
        # Support both raw state_dict and wrapped checkpoints
        state_dict = ckpt.get("q_net", ckpt) if isinstance(ckpt, dict) else ckpt
        self.q_net.load_state_dict(state_dict)
        self.q_net.eval()
        logger.debug("DQN weights loaded from %s", path)

    def save_checkpoint(self, path: str) -> None:
        torch.save({"q_net": self.q_net.state_dict()}, path)
