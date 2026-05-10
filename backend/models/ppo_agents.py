"""
models/ppo_agent.py  —  PPO Policy Agent

A minimal but complete Proximal Policy Optimisation implementation for the
Governor's behavioral action selection.

Architecture
────────────
  Shared trunk: Linear(state_dim → 64) → Tanh → Linear(64 → 64) → Tanh
  Actor head:   Linear(64 → action_dim) → Categorical distribution
  Critic head:  Linear(64 → 1)

The trunk is shared so the value estimate benefits from the same features as
the policy, which stabilises training on short rollouts.

Inference path (GovernorService)
─────────────────────────────────
  agent = PPOPolicyAgent.load("checkpoints/ppo_governor.pt")
  action_idx = agent.select_action(state_vector)   # pure inference, no_grad

Training path (offline trainer / RL loop)
──────────────────────────────────────────
  agent = PPOPolicyAgent(state_dim=6, action_dim=4)
  ...collect rollouts into RolloutBuffer...
  loss_info = agent.update(buffer)

Reward shaping
──────────────
The reward function is intentionally kept outside this file so the trainer
can experiment with different shapes.  The agent itself is reward-agnostic.

Typical reward signals:
  • +1.0  correctly identified bot was BLOCKed
  • +0.5  suspect user was CHALLENGEd and subsequently confirmed bot
  • -0.5  false positive (human BLOCKed)
  • +0.2  human ALLOWed with no subsequent anomaly
  • -0.1  unnecessary CHALLENGE on a clean human session

The risk_tolerance feature in the state vector lets the agent learn a
single policy that modulates these trade-offs per tenant at inference time.
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

PPO_CLIP_EPS:    float = 0.2    # ε in the clipped surrogate objective
PPO_ENTROPY_C:   float = 0.01   # entropy bonus coefficient
PPO_VALUE_C:     float = 0.5    # value loss coefficient
PPO_GAMMA:       float = 0.99   # discount factor
PPO_LAMBDA:      float = 0.95   # GAE lambda
PPO_EPOCHS:      int   = 4      # optimisation epochs per update
PPO_MINIBATCH:   int   = 32     # mini-batch size during update


# ── Rollout storage ───────────────────────────────────────────────────────────

@dataclass
class RolloutBuffer:
    """
    Stores one rollout worth of (state, action, log_prob, reward, done, value)
    tuples.  Cleared after each PPO update.
    """
    states:    List[np.ndarray] = field(default_factory=list)
    actions:   List[int]        = field(default_factory=list)
    log_probs: List[float]      = field(default_factory=list)
    rewards:   List[float]      = field(default_factory=list)
    dones:     List[bool]       = field(default_factory=list)
    values:    List[float]      = field(default_factory=list)

    def add(
        self,
        state:    np.ndarray,
        action:   int,
        log_prob: float,
        reward:   float,
        done:     bool,
        value:    float,
    ) -> None:
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
        # Smaller init for the final action layer → more uniform initial policy
        nn.init.orthogonal_(self.actor.weight, gain=0.01)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Returns (action_logits, state_value)."""
        h     = self.trunk(x)
        return self.actor(h), self.critic(h).squeeze(-1)

    def get_distribution(self, x: torch.Tensor) -> Categorical:
        logits, _ = self.forward(x)
        return Categorical(logits=logits)


# ── Public agent API ──────────────────────────────────────────────────────────

class PPOPolicyAgent:
    """
    PPO agent for the Governor's behavioral action selection.

    Typical lifecycle:
      1. Instantiate:  agent = PPOPolicyAgent(state_dim=6, action_dim=4)
      2. Collect data: action, log_p, value = agent.act(state)
      3. Store in buffer + compute reward + observe done
      4. After rollout: agent.update(buffer)
      5. Periodically:  agent.save("path/to/checkpoint.pt")

    For inference only:
      agent = PPOPolicyAgent.load("path/to/checkpoint.pt")
      action = agent.select_action(state)
    """

    def __init__(
        self,
        state_dim:  int = 6,
        action_dim: int = 4,
        lr:         float = 3e-4,
        device:     Optional[str] = None,
    ) -> None:
        self.state_dim  = state_dim
        self.action_dim = action_dim
        self.device     = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )

        self.net       = _ActorCriticNet(state_dim, action_dim).to(self.device)
        self.optimiser = torch.optim.Adam(self.net.parameters(), lr=lr, eps=1e-5)
        self.net.eval()

    # ── Inference ─────────────────────────────────────────────────────────────

    @torch.no_grad()
    def select_action(self, state: np.ndarray) -> int:
        """
        Greedy inference: return the most probable action index.
        Called by stage3_governor.run() at request time.
        """
        t    = self._to_tensor(state)
        dist = self.net.get_distribution(t)
        return int(dist.probs.argmax().item())

    @torch.no_grad()
    def act(self, state: np.ndarray) -> Tuple[int, float, float]:
        """
        Stochastic action for training rollouts.

        Returns (action, log_prob, value_estimate).
        """
        t            = self._to_tensor(state)
        logits, val  = self.net(t)
        dist         = Categorical(logits=logits)
        action       = dist.sample()
        return (
            int(action.item()),
            float(dist.log_prob(action).item()),
            float(val.item()),
        )

    # ── Training ──────────────────────────────────────────────────────────────

    def update(self, buffer: RolloutBuffer, last_value: float = 0.0) -> dict:
        """
        Run PPO_EPOCHS of mini-batch optimisation on the collected rollout.

        Parameters
        ──────────
        buffer     — filled RolloutBuffer.
        last_value — bootstrap value for the final state (0 if terminal).

        Returns
        ───────
        dict with keys: policy_loss, value_loss, entropy, total_loss
        (mean across all mini-batches).
        """
        advantages, returns = self._compute_gae(buffer, last_value)

        # Convert buffer to tensors
        states    = torch.FloatTensor(np.array(buffer.states)).to(self.device)
        actions   = torch.LongTensor(buffer.actions).to(self.device)
        old_lps   = torch.FloatTensor(buffer.log_probs).to(self.device)
        returns_t = torch.FloatTensor(returns).to(self.device)
        adv_t     = torch.FloatTensor(advantages).to(self.device)

        # Normalise advantages per mini-batch
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

        n       = len(buffer)
        metrics = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "total_loss": 0.0}
        steps   = 0

        self.net.train()
        for _ in range(PPO_EPOCHS):
            idx = torch.randperm(n)
            for start in range(0, n, PPO_MINIBATCH):
                mb   = idx[start:start + PPO_MINIBATCH]
                loss, info = self._ppo_loss(
                    states[mb], actions[mb], old_lps[mb],
                    returns_t[mb], adv_t[mb],
                )
                self.optimiser.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.net.parameters(), max_norm=0.5)
                self.optimiser.step()

                for k in metrics:
                    metrics[k] += info[k]
                steps += 1

        self.net.eval()
        buffer.clear()
        return {k: v / max(steps, 1) for k, v in metrics.items()}

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Persist weights + hyperparameters to a .pt checkpoint."""
        torch.save(
            {
                "state_dim":   self.state_dim,
                "action_dim":  self.action_dim,
                "net":         self.net.state_dict(),
                "optimiser":   self.optimiser.state_dict(),
            },
            path,
        )
        logger.info("[PPO] Checkpoint saved → %s", path)

    @classmethod
    def load(cls, path: str | Path, device: Optional[str] = None) -> "PPOPolicyAgent":
        """Load a PPOPolicyAgent from a checkpoint file."""
        ckpt  = torch.load(path, map_location="cpu")
        agent = cls(
            state_dim  = ckpt["state_dim"],
            action_dim = ckpt["action_dim"],
            device     = device,
        )
        agent.net.load_state_dict(ckpt["net"])
        agent.optimiser.load_state_dict(ckpt["optimiser"])
        agent.net.eval()
        logger.info("[PPO] Checkpoint loaded ← %s", path)
        return agent

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _to_tensor(self, state: np.ndarray) -> torch.Tensor:
        return torch.FloatTensor(state).unsqueeze(0).to(self.device)

    def _compute_gae(
        self,
        buffer:     RolloutBuffer,
        last_value: float,
    ) -> Tuple[List[float], List[float]]:
        """
        Generalised Advantage Estimation (GAE-λ).

        Computes advantages and discounted returns for the stored rollout.
        """
        advantages = [0.0] * len(buffer)
        returns    = [0.0] * len(buffer)

        gae        = 0.0
        next_val   = last_value

        for t in reversed(range(len(buffer))):
            mask      = 0.0 if buffer.dones[t] else 1.0
            delta     = (
                buffer.rewards[t]
                + PPO_GAMMA * next_val * mask
                - buffer.values[t]
            )
            gae       = delta + PPO_GAMMA * PPO_LAMBDA * mask * gae
            advantages[t] = gae
            returns[t]    = gae + buffer.values[t]
            next_val      = buffer.values[t]

        return advantages, returns

    def _ppo_loss(
        self,
        states:   torch.Tensor,
        actions:  torch.Tensor,
        old_lps:  torch.Tensor,
        returns:  torch.Tensor,
        adv:      torch.Tensor,
    ) -> Tuple[torch.Tensor, dict]:
        """Clipped PPO surrogate + value + entropy loss."""
        logits, values = self.net(states)
        dist    = Categorical(logits=logits)
        new_lps = dist.log_prob(actions)
        entropy = dist.entropy().mean()

        ratio        = (new_lps - old_lps).exp()
        clipped      = torch.clamp(ratio, 1 - PPO_CLIP_EPS, 1 + PPO_CLIP_EPS)
        policy_loss  = -torch.min(ratio * adv, clipped * adv).mean()
        value_loss   = F.mse_loss(values, returns)
        total        = policy_loss + PPO_VALUE_C * value_loss - PPO_ENTROPY_C * entropy

        return total, {
            "policy_loss": policy_loss.item(),
            "value_loss":  value_loss.item(),
            "entropy":     entropy.item(),
            "total_loss":  total.item(),
        }