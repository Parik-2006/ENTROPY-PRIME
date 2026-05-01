"""
Entropy Prime — PPO Watchdog Trainer
Trains the session watchdog on synthetic identity-drift episodes.

State (10-dim, mirrors pipeline/stage4_watchdog.py _build_state()):
    [e_rec, trust, trust_delta, latent_norm, latent_mean, latent_std,
     e_rec_gt_warn, e_rec_gt_critical, trust_lt_warn, trust_lt_critical]

Actions:
    0: ok
    1: passive_reauth
    2: disable_sensitive_apis

Reward shaping:
    Correct action for context → +1.0
    Unnecessary reauth on clean session → -0.3
    Missing a drift event → -1.5
    Over-triggering on clean session → -0.5

Usage:
    cd backend/models
    python train_ppo.py
    python train_ppo.py --episodes 5000 --out ../checkpoints/watchdog.pt
"""
from __future__ import annotations

import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from models.ppo import PPOAgent

# ── Thresholds (mirror contracts.py) ──────────────────────────────────────────
EREC_WARN      = 0.18
EREC_CRITICAL  = 0.35
TRUST_WARN     = 0.50
TRUST_CRITICAL = 0.25

# ── Synthetic session environment ─────────────────────────────────────────────
class WatchdogEnv:
    """
    Generates session states spanning:
      - Clean sessions (e_rec low, trust high)
      - Gradual drift (e_rec slowly rising)
      - Sudden hijack (e_rec spikes, trust drops hard)
    """

    SCENARIO_WEIGHTS = [0.60, 0.25, 0.15]   # clean, drift, hijack

    def reset(self):
        self._scenario = np.random.choice(3, p=self.SCENARIO_WEIGHTS)
        self._step     = 0
        self._e_rec    = np.random.uniform(0.02, 0.08)
        self._trust    = np.random.uniform(0.85, 1.00)
        return self._obs()

    def step(self, action: int):
        self._step += 1

        # Advance scenario
        if self._scenario == 0:    # clean
            self._e_rec  = np.clip(self._e_rec  + np.random.normal(0, 0.005), 0, 0.15)
            self._trust  = np.clip(self._trust  + np.random.normal(0, 0.01),  0.7, 1.0)
        elif self._scenario == 1:  # drift
            self._e_rec  = np.clip(self._e_rec  + np.random.uniform(0.005, 0.02), 0, 0.50)
            self._trust  = np.clip(self._trust  - np.random.uniform(0.01,  0.05), 0.0, 1.0)
        else:                      # sudden hijack
            if self._step == 1:
                self._e_rec = np.random.uniform(0.30, 0.55)
                self._trust = np.random.uniform(0.10, 0.30)
            else:
                self._e_rec = np.clip(self._e_rec + np.random.normal(0, 0.01), 0, 0.60)
                self._trust = np.clip(self._trust - np.random.normal(0, 0.02), 0.0, 1.0)

        reward = self._reward(action)
        done   = self._step >= 20
        return self._obs(), reward, done

    def _obs(self) -> np.ndarray:
        lv   = np.random.randn(32).astype(np.float32) * 0.1
        norm = float(np.linalg.norm(lv))
        return np.array([
            self._e_rec,
            self._trust,
            1.0 - self._trust,
            min(norm / 10.0, 1.0),
            float(np.mean(lv)),
            float(np.std(lv)),
            float(self._e_rec > EREC_WARN),
            float(self._e_rec > EREC_CRITICAL),
            float(self._trust < TRUST_WARN),
            float(self._trust < TRUST_CRITICAL),
        ], dtype=np.float32)

    def _reward(self, action: int) -> float:
        e, t = self._e_rec, self._trust
        clean    = e < EREC_WARN   and t > TRUST_WARN
        warn     = e >= EREC_WARN  or  t <= TRUST_WARN
        critical = e >= EREC_CRITICAL or t <= TRUST_CRITICAL

        if critical:
            return  1.0 if action == 2 else -1.5
        if warn:
            return  1.0 if action == 1 else (-0.5 if action == 0 else -0.3)
        if clean:
            return  1.0 if action == 0 else -0.5
        return 0.0


# ── Training loop ─────────────────────────────────────────────────────────────
def train(episodes: int = 3_000, out: str = "checkpoints/watchdog.pt") -> None:
    env   = WatchdogEnv()
    agent = PPOAgent(state_dim=10, action_dim=3)

    total_rewards: list[float] = []

    for ep in range(1, episodes + 1):
        state    = env.reset()
        ep_r     = 0.0
        done     = False

        while not done:
            action, _ = agent.select_action(state)
            next_state, reward, done = env.step(action)
            agent.record_reward(reward, done)
            ep_r  += reward
            state  = next_state

        total_rewards.append(ep_r)

        # Train every 20 episodes
        if ep % 20 == 0:
            agent.train_epoch(epochs=4, batch_size=min(64, len(agent._rewards)))

        if ep % 500 == 0:
            window = total_rewards[-200:]
            print(
                f"  ep {ep:>6,} / {episodes:,}"
                f" | mean_reward {sum(window)/len(window):+.2f}"
                f" | last_ep_r {ep_r:+.2f}"
            )

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    agent.save_checkpoint(out)
    print(f"\n✓ PPO watchdog checkpoint saved → {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Pre-train the Entropy Prime PPO watchdog")
    p.add_argument("--episodes", type=int, default=3_000)
    p.add_argument("--out",      type=str, default="checkpoints/watchdog.pt")
    args = p.parse_args()

    print(f"\nTraining PPO watchdog — {args.episodes:,} episodes")
    print("─" * 60)
    train(args.episodes, args.out)
