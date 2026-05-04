"""
models/mab.py  —  Multi-Armed Bandit Agent (Honeypot Arm Selector, Stage 2)

UCB1 bandit for choosing among n_arms deception strategies.
State is persisted as counts + values (compatible with JSON checkpoint).
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger("entropy_prime.models.mab")


class MABAgent:
    """
    Upper Confidence Bound (UCB1) bandit.

    select_arm()  — picks the arm with the highest UCB score.
    update()      — updates the running average reward for the chosen arm.
    """

    def __init__(self, n_arms: int = 3):
        self.n_arms = n_arms
        self.counts = np.zeros(n_arms, dtype=np.int64)   # pull counts per arm
        self.values = np.zeros(n_arms, dtype=np.float64)  # avg reward per arm
        self._total = 0

    # ── Arm selection ──────────────────────────────────────────────────────────

    def select_arm(self) -> int:
        """
        UCB1 selection.  Arms that have never been pulled are tried first
        (round-robin) to ensure exploration before exploitation.
        """
        # Always try an unpulled arm first
        for arm in range(self.n_arms):
            if self.counts[arm] == 0:
                return arm

        # UCB1 formula: value + sqrt(2 * ln(total) / count)
        ucb_scores = self.values + np.sqrt(
            2.0 * math.log(self._total) / (self.counts + 1e-9)
        )
        return int(np.argmax(ucb_scores))

    def update(self, arm: int, reward: float) -> None:
        """Incremental running-average update (Welford-style)."""
        if arm < 0 or arm >= self.n_arms:
            logger.warning("MAB update: invalid arm %d (n_arms=%d)", arm, self.n_arms)
            return
        self.counts[arm] += 1
        self._total      += 1
        n = self.counts[arm]
        self.values[arm] += (reward - self.values[arm]) / n

    # ── Checkpoint I/O ────────────────────────────────────────────────────────

    def state_dict(self) -> dict:
        return {
            "n_arms": self.n_arms,
            "counts": self.counts.tolist(),
            "values": self.values.tolist(),
            "total":  int(self._total),
        }

    def load_state_dict(self, d: dict) -> None:
        """
        Restore from a previously saved state_dict.
        Raises ValueError on shape mismatch so the caller can fall back
        to cold-start.
        """
        if d.get("n_arms", self.n_arms) != self.n_arms:
            raise ValueError(
                f"MAB checkpoint has n_arms={d['n_arms']} but agent expects {self.n_arms}"
            )
        self.counts  = np.array(d["counts"], dtype=np.int64)
        self.values  = np.array(d["values"], dtype=np.float64)
        self._total  = int(d.get("total", sum(d["counts"])))
        logger.debug("MAB state loaded: total_pulls=%d", self._total)
