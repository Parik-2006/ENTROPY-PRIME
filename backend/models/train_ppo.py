# Example training script for PPO
from ppo import PPOAgent
import numpy as np

if __name__ == "__main__":
    state_dim = 10
    action_dim = 3
    agent = PPOAgent(state_dim, action_dim)
    # Simulate training loop
    for step in range(10000):
        state = np.random.rand(state_dim)
        # Add PPO training logic here
    print("PPO training complete. Save model as needed.")
