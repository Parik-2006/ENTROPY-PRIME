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

    def q_values(self, state: np.ndarray) -> np.ndarray:
        """Return raw Q-values for all actions (shape: (action_dim,))."""
        with torch.no_grad():
            t = torch.FloatTensor(state).unsqueeze(0)
            return self.q_net(t).squeeze(0).numpy()

    def train_step(
        self,
        state:      np.ndarray,
        action:     int,
        reward:     float,
        next_state: np.ndarray,
        done:       bool,
        gamma:      float = 0.99,
    ) -> float:
        """
        Single TD-error training step.  Returns the scalar loss value.
        (Used by tests and offline training scripts; not called at request time.)
        """
        import torch.optim as optim
        optimizer = optim.Adam(self.q_net.parameters(), lr=1e-3)
        self.q_net.train()

        s  = torch.FloatTensor(state).unsqueeze(0)
        ns = torch.FloatTensor(next_state).unsqueeze(0)

        with torch.no_grad():
            target_q = reward if done else reward + gamma * self.q_net(ns).max().item()

        current_q = self.q_net(s)[0, action]
        loss = (current_q - target_q) ** 2

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        self.q_net.eval()
        return float(loss.item())


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
