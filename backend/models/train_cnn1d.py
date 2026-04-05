# Example training script for 1D CNN
from cnn1d import CNN1D
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np

if __name__ == "__main__":
    model = CNN1D(input_channels=1, out_dim=32)
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.MSELoss()
    # Simulate random data
    for step in range(1000):
        x = torch.randn(16, 1, 100)  # batch, channels, length
        y = torch.randn(16, 32)
        out = model(x)
        loss = criterion(out, y)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    print("1D CNN training complete. Save model as needed.")
