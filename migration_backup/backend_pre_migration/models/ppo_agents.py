"""
models/ppo_agent.py — PPO Policy Agent

A minimal but complete Proximal Policy Optimisation implementation for the
Governor's behavioral action selection.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

logger = logging.getLogger("entropy_prime.ppo_agent")

# ── Hyperparameters ───────────────────────────────────────────────────────────

PPO_CLIP_EPS:  float = 0.2    # ε in the clipped surrogate objective
PPO_ENTROPY_C: float = 0.01   # entropy bonus coefficient
PPO_VALUE_C:   float = 0.5    # value loss coefficient
PPO_GAMMA:     float = 0.99   # discount factor
PPO_LAMBDA:    float = 0.95   # GAE lambda
PPO_EPOCHS:    int   = 4      # optimisation epochs per update
PPO_MINIBATCH: int   = 32     # mini-batch size during update


# ── Rollout storage ───────────────────────────────────────────────────────────

@dataclass
class RolloutBuffer:
    """Stores one rollout worth of tuples. Cleared after each PPO update."""
    states:    List[np.ndarray] = field(default_factory=list)
    actions:   List[int]        = field(default_factory=list)
    log_probs: List[float]      = field(default_factory=list)
    rewards:   List[float]      = field(default_factory=list)
    dones:     List[bool]       = field(default_factory=list)
    values:    List[float]      = field(default_factory=list)

    def add(self, state, action, log_prob, reward, done, value) -> None:
        self.states.append(state)
        self.actions.append(action)
        self.log_probs.append(log_prob)
        self.rewards.append(reward)
        self.dones.append(done)
        self.values.append(value)

    def clear(self) -> None:
        self.states.clear()
        self.actions.clear()
        self.log_probs.clear()
        self.rewards.clear()
        self.dones.clear()
        self.values.clear()

    def __len__(self) -> int:
        return len(self.states)


# ── Neural network ────────────────────────────────────────────────────────────

class _ActorCriticNet(nn.Module):
    """Shared trunk + separate actor / critic heads."""
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 64) -> None:
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
        )
        self.actor  = nn.Linear(hidden_dim, action_dim)
        self.critic = nn.Linear(hidden_dim, 1)
        self._init_weights()

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
                nn.init.zeros_(m.bias)
        nn.init.orthogonal_(self.actor.weight, gain=0.01)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        h = self.trunk(x)
        return self.actor(h), self.critic(h).squeeze(-1)

    def get_distribution(self, x: torch.Tensor) -> Categorical:
        logits, _ = self.forward(x)
        return Categorical(logits=logits)


# ── Public agent API ──────────────────────────────────────────────────────────

class PPOPolicyAgent:
    def __init__(self, state_dim: int = 5, action_dim: int = 4, lr: float = 3e-4, device: Optional[str] = None) -> None:
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.net = _ActorCriticNet(state_dim, action_dim).to(self.device)
        self.optimiser = torch.optim.Adam(self.net.parameters(), lr=lr, eps=1e-5)
        self.net.eval()

    @torch.no_grad()
    def select_action(self, state: np.ndarray) -> int:
        t = self._to_tensor(state)
        return int(self.net.get_distribution(t).probs.argmax().item())

    @torch.no_grad()
    def act(self, state: np.ndarray) -> Tuple[int, float, float]:
        t = self._to_tensor(state)
        logits, val = self.net(t)
        dist = Categorical(logits=logits)
        action = dist.sample()
        return int(action.item()), float(dist.log_prob(action).item()), float(val.item())

    def update(self, buffer: RolloutBuffer, last_value: float = 0.0) -> dict:
        advantages, returns = self._compute_gae(buffer, last_value)
        states = torch.FloatTensor(np.array(buffer.states)).to(self.device)
        actions = torch.LongTensor(buffer.actions).to(self.device)
        old_lps = torch.FloatTensor(buffer.log_probs).to(self.device)
        returns_t = torch.FloatTensor(returns).to(self.device)
        adv_t = torch.FloatTensor(advantages).to(self.device)
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

        n, metrics, steps = len(buffer), {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "total_loss": 0.0}, 0
        self.net.train()
        for _ in range(PPO_EPOCHS):
            idx = torch.randperm(n)
            for start in range(0, n, PPO_MINIBATCH):
                mb = idx[start:start + PPO_MINIBATCH]
                loss, info = self._ppo_loss(states[mb], actions[mb], old_lps[mb], returns_t[mb], adv_t[mb])
                self.optimiser.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.net.parameters(), max_norm=0.5)
                self.optimiser.step()
                for k in metrics: metrics[k] += info[k]
                steps += 1
        self.net.eval()
        buffer.clear()
        return {k: v / max(steps, 1) for k, v in metrics.items()}

    def save(self, path: str | Path) -> None:
        torch.save({"state_dim": self.state_dim, "action_dim": self.action_dim, 
                    "net": self.net.state_dict(), "optimiser": self.optimiser.state_dict()}, path)

    @classmethod
    def load(cls, path: str | Path, device: Optional[str] = None) -> PPOPolicyAgent:
        ckpt = torch.load(path, map_location="cpu")
        agent = cls(state_dim=ckpt["state_dim"], action_dim=ckpt["action_dim"], device=device)
        agent.net.load_state_dict(ckpt["net"])
        agent.optimiser.load_state_dict(ckpt["optimiser"])
        return agent

    def _to_tensor(self, state: np.ndarray) -> torch.Tensor:
        return torch.FloatTensor(state).unsqueeze(0).to(self.device)

    def _compute_gae(self, buffer: RolloutBuffer, last_value: float) -> Tuple[List[float], List[float]]:
        advantages, returns = [0.0] * len(buffer), [0.0] * len(buffer)
        gae, next_val = 0.0, last_value
        for t in reversed(range(len(buffer))):
            mask = 0.0 if buffer.dones[t] else 1.0
            delta = buffer.rewards[t] + PPO_GAMMA * next_val * mask - buffer.values[t]
            gae = delta + PPO_GAMMA * PPO_LAMBDA * mask * gae
            advantages[t], returns[t], next_val = gae, gae + buffer.values[t], buffer.values[t]
        return advantages, returns

    def _ppo_loss(self, states, actions, old_lps, returns, adv) -> Tuple[torch.Tensor, dict]:
        logits, values = self.net(states)
        dist = Categorical(logits=logits)
        new_lps, entropy = dist.log_prob(actions), dist.entropy().mean()
        ratio = (new_lps - old_lps).exp()
        policy_loss = -torch.min(ratio * adv, torch.clamp(ratio, 1 - PPO_CLIP_EPS, 1 + PPO_CLIP_EPS) * adv).mean()
        value_loss = F.mse_loss(values, returns)
        total = policy_loss + PPO_VALUE_C * value_loss - PPO_ENTROPY_C * entropy
        return total, {"policy_loss": policy_loss.item(), "value_loss": value_loss.item(), 
                       "entropy": entropy.item(), "total_loss": total.item()}