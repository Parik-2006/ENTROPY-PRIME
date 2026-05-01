"""
MAB (Multi-Armed Bandit) — Honeypot Deceiver (Phase 3)
Selects deception strategy for shadow-routed bots.
Exposes counts[] so Stage 2 can derive confidence from sample size.
"""
from __future__ import annotations
import numpy as np


class MABAgent:
    """
    Input contract  — select_arm():
        none (stateless selection)

    Output contract — select_arm():
        arm: int in {0 .. n_arms-1}

    Output contract — counts:
        np.ndarray[float64, shape=(n_arms,)]
        Stage 2 reads counts[arm] to assess confidence:
          < 10  → LOW
          < 50  → MEDIUM
          ≥ 50  → HIGH

    Update contract — update(arm, reward):
        arm:    int   — which arm was pulled
        reward: float — observed reward signal
                        Positive = deception succeeded (bot kept engaging).
                        Negative = bot escaped / detected the sandbox.
    """

    def __init__(self, n_arms: int = 3, epsilon: float = 0.1):
        self.n_arms  = n_arms
        self.epsilon = epsilon
        self.counts  = np.zeros(n_arms, dtype=np.float64)
        self.values  = np.zeros(n_arms, dtype=np.float64)

    # ── Inference ─────────────────────────────────────────────────────────────

    def select_arm(self) -> int:
        """Epsilon-greedy selection."""
        if np.random.rand() < self.epsilon:
            return int(np.random.randint(self.n_arms))
        return int(np.argmax(self.values))

    # ── Training ──────────────────────────────────────────────────────────────

    def update(self, chosen_arm: int, reward: float) -> None:
        """Incremental mean update."""
        if not (0 <= chosen_arm < self.n_arms):
            raise ValueError(f"Invalid arm {chosen_arm}; must be in [0, {self.n_arms})")
        self.counts[chosen_arm] += 1
        n     = self.counts[chosen_arm]
        value = self.values[chosen_arm]
        self.values[chosen_arm] = ((n - 1) / n) * value + (1.0 / n) * reward

    # ── Checkpoint I/O ────────────────────────────────────────────────────────

    def state_dict(self) -> dict:
        return {
            "n_arms":  self.n_arms,
            "epsilon": self.epsilon,
            "counts":  self.counts.tolist(),
            "values":  self.values.tolist(),
        }

    def load_state_dict(self, d: dict) -> None:
        self.n_arms  = d["n_arms"]
        self.epsilon = d.get("epsilon", 0.1)
        self.counts  = np.array(d["counts"], dtype=np.float64)
        self.values  = np.array(d["values"], dtype=np.float64)
