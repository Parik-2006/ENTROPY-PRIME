"""
Entropy Prime — MAB Deception Strategy Trainer
Simulates bot engagement rewards for each deception arm.

Arm definitions (must match pipeline/stage2_honeypot.py DECEPTION_ARMS):
    0: fake_data_feed       — plausible fake JSON
    1: slow_drip            — artificial latency + partial data
    2: canary_token_inject  — trackable canary tokens

Reward signal:
    +1.0  bot kept engaging (deception held)
    -0.5  bot escaped / detected sandbox
     0.0  inconclusive

Usage:
    cd backend/models
    python train_mab.py
    python train_mab.py --steps 50000 --out ../checkpoints/mab.json
"""
from __future__ import annotations

import argparse, json, os, sys

# Allow running from models/ subdirectory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from models.mab import MABAgent

# ── Simulated reward distributions per arm ────────────────────────────────────
# Based on expected real-world bot behaviour:
#   arm 0 (fake_data): bots usually fall for it → high reward
#   arm 1 (slow_drip): many bots timeout → medium reward
#   arm 2 (canary):    sophisticated bots detect it → lower mean reward
ARM_REWARD_PROFILES = [
    dict(mean=0.70, std=0.20),   # arm 0
    dict(mean=0.55, std=0.25),   # arm 1
    dict(mean=0.40, std=0.30),   # arm 2
]


def simulate_reward(arm: int, profile: dict) -> float:
    """Sample a reward from the arm's true distribution (clipped to [-1, 1])."""
    r = np.random.normal(profile["mean"], profile["std"])
    return float(np.clip(r, -1.0, 1.0))


def train(steps: int = 20_000, out: str = "checkpoints/mab.json") -> None:
    mab = MABAgent(n_arms=3, epsilon=0.1)
    reward_history: list[float] = []

    for step in range(1, steps + 1):
        arm    = mab.select_arm()
        reward = simulate_reward(arm, ARM_REWARD_PROFILES[arm])
        mab.update(arm, reward)
        reward_history.append(reward)

        if step % 5_000 == 0:
            window = reward_history[-1_000:]
            print(
                f"  step {step:>7,} / {steps:,}"
                f" | mean_reward(1k) {sum(window)/len(window):+.3f}"
                f" | arm_values {[f'{v:.3f}' for v in mab.values]}"
                f" | counts {mab.counts.astype(int).tolist()}"
            )

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        json.dump(mab.state_dict(), f, indent=2)

    print(f"\n✓ MAB state saved → {out}")
    print(f"  Final arm values: {[f'{v:.4f}' for v in mab.values]}")
    print(f"  Best arm: {int(np.argmax(mab.values))} "
          f"({['fake_data_feed','slow_drip','canary_token_inject'][int(np.argmax(mab.values))]})")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Pre-train the Entropy Prime MAB deceiver")
    p.add_argument("--steps", type=int, default=20_000)
    p.add_argument("--out",   type=str, default="checkpoints/mab.json")
    args = p.parse_args()

    print(f"\nTraining MAB deceiver — {args.steps:,} steps")
    print("─" * 60)
    train(args.steps, args.out)
