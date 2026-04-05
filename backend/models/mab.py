# MAB (Multi-Armed Bandit) implementation for Deceiver (Phase 3)
import numpy as np

class MABAgent:
    def __init__(self, n_arms):
        self.n_arms = n_arms
        self.counts = np.zeros(n_arms)
        self.values = np.zeros(n_arms)

    def select_arm(self):
        # Epsilon-greedy
        epsilon = 0.1
        if np.random.rand() < epsilon:
            return np.random.randint(self.n_arms)
        return np.argmax(self.values)

    def update(self, chosen_arm, reward):
        self.counts[chosen_arm] += 1
        n = self.counts[chosen_arm]
        value = self.values[chosen_arm]
        self.values[chosen_arm] = ((n - 1) / n) * value + (1 / n) * reward
