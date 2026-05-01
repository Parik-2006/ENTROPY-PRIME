"""
PPO (Proximal Policy Optimization) — Session Watchdog (Phase 4)
Minimal but contract-complete implementation.
Stage 4 calls ppo_agent.policy(state_tensor) and reads output probabilities.
"""
from __future__ import annotations
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from typing import Optional


class PolicyNetwork(nn.Module):
    """
    Input:  FloatTensor[batch, 10]
            [e_rec, trust, trust_delta, latent_norm, latent_mean, latent_std,
             e_rec_gt_warn, e_rec_gt_critical, trust_lt_warn, trust_lt_critical]

    Output: FloatTensor[batch, action_dim]   (softmax probabilities)
            action_dim = 3: {ok, passive_reauth, disable_sensitive_apis}
    """
    def __init__(self, state_dim: int, action_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 128), nn.ReLU(),
            nn.Linear(128, 64),        nn.ReLU(),
            nn.Linear(64, action_dim),
            nn.Softmax(dim=-1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class ValueNetwork(nn.Module):
    def __init__(self, state_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 128), nn.ReLU(),
            nn.Linear(128, 64),        nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class PPOAgent:
    """
    Input contract  — policy(state_tensor):
        state_tensor: FloatTensor[1, 10]

    Output contract — policy(state_tensor):
        FloatTensor[1, 3]  — probability distribution over {ok, reauth, disable}
        Stage 4 reads .squeeze().numpy() and argmax for the recommended action.
        It also reads the max probability as a confidence signal.

    Training:
        collect_step() / train_epoch() — standard PPO clipped objective.
    """

    def __init__(
        self,
        state_dim:  int   = 10,
        action_dim: int   = 3,
        lr:         float = 3e-4,
        clip_eps:   float = 0.2,
        gamma:      float = 0.99,
        lam:        float = 0.95,
    ):
        self.state_dim  = state_dim
        self.action_dim = action_dim
        self.clip_eps   = clip_eps
        self.gamma      = gamma
        self.lam        = lam

        self.policy = PolicyNetwork(state_dim, action_dim)
        self.value  = ValueNetwork(state_dim)

        self.policy_opt = optim.Adam(self.policy.parameters(), lr=lr)
        self.value_opt  = optim.Adam(self.value.parameters(),  lr=lr)

        # Rollout buffer
        self._states:   list = []
        self._actions:  list = []
        self._rewards:  list = []
        self._log_probs:list = []
        self._values:   list = []
        self._dones:    list = []

    # ── Inference (used by Stage 4) ───────────────────────────────────────────

    def select_action(self, state: np.ndarray) -> tuple[int, float]:
        """
        Returns (action_idx, log_prob).
        Stores transition for later training.
        """
        t     = torch.FloatTensor(state).unsqueeze(0)
        probs = self.policy(t).squeeze()
        dist  = torch.distributions.Categorical(probs)
        act   = dist.sample()
        lp    = dist.log_prob(act)
        val   = self.value(t).item()

        self._states.append(state)
        self._actions.append(act.item())
        self._log_probs.append(lp.item())
        self._values.append(val)

        return int(act.item()), float(lp.item())

    # ── Training ──────────────────────────────────────────────────────────────

    def record_reward(self, reward: float, done: bool) -> None:
        self._rewards.append(reward)
        self._dones.append(done)

    def train_epoch(self, epochs: int = 4, batch_size: int = 64) -> Optional[float]:
        """
        Run PPO update over collected rollout. Returns mean policy loss.
        Clears the rollout buffer afterwards.
        """
        n = len(self._rewards)
        if n < batch_size:
            return None

        states   = torch.FloatTensor(np.array(self._states[:n]))
        actions  = torch.LongTensor(self._actions[:n])
        old_lps  = torch.FloatTensor(self._log_probs[:n])
        rewards  = self._rewards[:n]
        dones    = self._dones[:n]
        values   = self._values[:n]

        # GAE advantages
        advantages = self._gae(rewards, values, dones)
        adv_t      = torch.FloatTensor(advantages)
        adv_t      = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)
        returns    = adv_t + torch.FloatTensor(values)

        total_loss = 0.0
        for _ in range(epochs):
            idx   = torch.randperm(n)[:batch_size]
            s_b   = states[idx];  a_b = actions[idx]
            op_b  = old_lps[idx]; adv_b = adv_t[idx]; ret_b = returns[idx]

            probs   = self.policy(s_b)
            dist    = torch.distributions.Categorical(probs)
            new_lps = dist.log_prob(a_b)
            ratio   = torch.exp(new_lps - op_b)
            clip    = torch.clamp(ratio, 1 - self.clip_eps, 1 + self.clip_eps)
            p_loss  = -torch.min(ratio * adv_b, clip * adv_b).mean()

            v_pred  = self.value(s_b).squeeze()
            v_loss  = nn.functional.mse_loss(v_pred, ret_b)

            self.policy_opt.zero_grad(); p_loss.backward(); self.policy_opt.step()
            self.value_opt.zero_grad();  v_loss.backward();  self.value_opt.step()
            total_loss += p_loss.item()

        self._clear_buffer()
        return total_loss / epochs

    def _gae(self, rewards, values, dones) -> list[float]:
        adv, gae = [], 0.0
        for t in reversed(range(len(rewards))):
            nv    = values[t + 1] if t + 1 < len(values) else 0.0
            delta = rewards[t] + self.gamma * nv * (1 - dones[t]) - values[t]
            gae   = delta + self.gamma * self.lam * (1 - dones[t]) * gae
            adv.insert(0, gae)
        return adv

    def _clear_buffer(self) -> None:
        self._states   = []; self._actions  = []
        self._rewards  = []; self._log_probs = []
        self._values   = []; self._dones    = []

    # ── Checkpoint I/O ────────────────────────────────────────────────────────

    def save_checkpoint(self, path: str) -> None:
        torch.save({
            "policy": self.policy.state_dict(),
            "value":  self.value.state_dict(),
        }, path)

    def load_checkpoint(self, path: str) -> None:
        ckpt = torch.load(path, map_location="cpu")
        self.policy.load_state_dict(ckpt["policy"])
        self.value.load_state_dict(ckpt["value"])
