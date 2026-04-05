# DQN (Deep Q-Network) implementation for RL Governor (Phase 2)
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np

class DQN(nn.Module):
    def __init__(self, state_dim, action_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Linear(128, action_dim)
        )

    def forward(self, x):
        return self.net(x)

# Minimal agent wrapper
class DQNAgent:
    def __init__(self, state_dim, action_dim, lr=1e-3):
        self.model = DQN(state_dim, action_dim)
        self.optimizer = optim.Adam(self.model.parameters(), lr=lr)
        self.criterion = nn.MSELoss()

    def select_action(self, state):
        with torch.no_grad():
            q_values = self.model(torch.FloatTensor(state))
            return int(torch.argmax(q_values).item())

    def train_step(self, state, action, reward, next_state, done, gamma=0.99):
        state = torch.FloatTensor(state)
        next_state = torch.FloatTensor(next_state)
        q_values = self.model(state)
        next_q_values = self.model(next_state)
        target = q_values.clone().detach()
        target[action] = reward + (0 if done else gamma * torch.max(next_q_values).item())
        loss = self.criterion(q_values, target)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        return loss.item()
