# Example training script for MAB (Multi-Armed Bandit)
from mab import MABAgent
import numpy as np

if __name__ == "__main__":
    n_arms = 3
    mab = MABAgent(n_arms)
    # Simulate rewards for each arm
    for step in range(10000):
        arm = mab.select_arm()
        reward = np.random.binomial(1, 0.5)  # Replace with real reward logic
        mab.update(arm, reward)
    print("MAB training complete. Save state as needed.")
