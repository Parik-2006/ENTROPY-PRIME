# Model Implementations for Entropy Prime

This folder contains minimal implementations for the planned models:

- **dqn.py**: Deep Q-Network (DQN) for RL Governor (Phase 2)
- **mab.py**: Multi-Armed Bandit (MAB) for Deceiver (Phase 3)
- **ppo.py**: Proximal Policy Optimization (PPO) for Watchdogz (Phase 4)
- **cnn1d.py**: 1D CNN for biometric feature extraction (Phase 1)

## Integration Notes
- These are minimal, modular implementations. You should connect them to the backend logic as needed.
- Training and inference code should be added or extended based on your data and requirements.
- For production, consider saving/loading model checkpoints and adding error handling.

## Example Usage
```python
# DQN
from models.dqn import DQNAgent
agent = DQNAgent(state_dim=10, action_dim=3)

# MAB
from models.mab import MABAgent
mab = MABAgent(n_arms=3)

# PPO
from models.ppo import PPOAgent
ppo = PPOAgent(state_dim=10, action_dim=3)

# 1D CNN
from models.cnn1d import CNN1D
cnn = CNN1D(input_channels=1, out_dim=32)
```

---

Extend these models as needed for your application.
