"""
DQN (Deep Q-Network) — RL Governor (Phase 2)
Exposes select_action() and q_values() so Stage 3 can measure
Q-spread for confidence estimation.
"""
from __future__ import annotations
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim


class DQN(nn.Module):
    def __init__(self, state_dim: int, action_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 128), nn.ReLU(),
            nn.Linear(128, 128),       nn.ReLU(),
            nn.Linear(128, action_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class DQNAgent:
    """
    Input contract  — select_action / q_values:
        state: np.ndarray[float32, shape=(3,)]
               [theta, h_exp, server_load]  all in [0, 1]

    Output contract — select_action:
        action: int in {0, 1, 2, 3}

    Output contract — q_values:
        np.ndarray[float32, shape=(action_dim,)]
        Used by Stage 3 to derive confidence from Q-spread.
    """

    def __init__(self, state_dim: int = 3, action_dim: int = 4, lr: float = 1e-3):
        self.state_dim  = state_dim
        self.action_dim = action_dim
        self.model      = DQN(state_dim, action_dim)
        self.optimizer  = optim.Adam(self.model.parameters(), lr=lr)
        self.criterion  = nn.MSELoss()

    # ── Inference ─────────────────────────────────────────────────────────────

    def select_action(self, state: np.ndarray) -> int:
        """Greedy action selection (no exploration)."""
        with torch.no_grad():
            q = self.model(torch.FloatTensor(state))
        return int(torch.argmax(q).item())

    def q_values(self, state: np.ndarray) -> np.ndarray:
        """
        Return raw Q-values for all actions.
        Stage 3 uses max(Q) - min(Q) as a confidence proxy.
        """
        with torch.no_grad():
            q = self.model(torch.FloatTensor(state))
        return q.numpy()

    # ── Training ──────────────────────────────────────────────────────────────

    def train_step(
        self,
        state:      np.ndarray,
        action:     int,
        reward:     float,
        next_state: np.ndarray,
        done:       bool,
        gamma:      float = 0.99,
    ) -> float:
        s  = torch.FloatTensor(state)
        s2 = torch.FloatTensor(next_state)
        q  = self.model(s)
        with torch.no_grad():
            nq = self.model(s2)
        target          = q.clone().detach()
        target[action]  = reward + (0.0 if done else gamma * torch.max(nq).item())
        loss = self.criterion(q, target)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        return float(loss.item())

    # ── Checkpoint I/O ────────────────────────────────────────────────────────

    def load_checkpoint(self, path: str) -> None:
        ckpt = torch.load(path, map_location="cpu")
        # Support both bare state_dict and wrapped {"q_net": ...} format
        sd = ckpt.get("q_net", ckpt)
        # Remap keys from train.py's QNetwork (which uses .net.*) to DQN
        self.model.load_state_dict(sd, strict=False)

    def save_checkpoint(self, path: str) -> None:
        torch.save({"q_net": self.model.state_dict()}, path)
