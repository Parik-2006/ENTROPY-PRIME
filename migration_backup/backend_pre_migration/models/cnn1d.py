"""
models/cnn1d.py  —  1D Convolutional Feature Extractor

Extracts a fixed-length embedding from a variable-length raw signal
(keystroke timing, touch pressure, accelerometer trace, etc.).

Architecture
────────────
  Conv1d(1→16, k=3) → ReLU → MaxPool(2)
  Conv1d(16→32, k=3) → ReLU → AdaptiveAvgPool → Flatten
  Linear(32 → out_dim)

extract() accepts a plain Python list and returns a plain list so it can be
serialised directly into a JSON response.
"""
from __future__ import annotations

import logging
from typing import List

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger("entropy_prime.models.cnn1d")

_MIN_SIGNAL_LEN = 8   # pad signals shorter than this


class CNN1D(nn.Module):
    def __init__(self, input_channels: int = 1, out_dim: int = 32):
        super().__init__()
        self.out_dim = out_dim

        self.conv1  = nn.Conv1d(input_channels, 16, kernel_size=3, padding=1)
        self.pool1  = nn.MaxPool1d(2)
        self.conv2  = nn.Conv1d(16, 32, kernel_size=3, padding=1)
        self.gap    = nn.AdaptiveAvgPool1d(1)    # global average → always 32-dim
        self.fc     = nn.Linear(32, out_dim)

        self.eval()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, 1, seq_len)"""
        x = F.relu(self.conv1(x))
        x = self.pool1(x)
        x = F.relu(self.conv2(x))
        x = self.gap(x).squeeze(-1)    # (batch, 32)
        return self.fc(x)              # (batch, out_dim)

    # ── Public API ────────────────────────────────────────────────────────────

    @torch.no_grad()
    def extract(self, raw_signal: List[float]) -> List[float]:
        """
        Feature extraction entry point called by /biometric/extract.

        Accepts a variable-length list of floats and returns a fixed out_dim
        embedding as a plain Python list.

        Raises ValueError for empty inputs; all other errors propagate so
        the endpoint can return a 500.
        """
        if not raw_signal:
            return [0.0] * self.fc.out_features


        sig = np.asarray(raw_signal, dtype=np.float32)

        # Pad very short signals
        if len(sig) < _MIN_SIGNAL_LEN:
            sig = np.pad(sig, (0, _MIN_SIGNAL_LEN - len(sig)), mode="edge")

        # Normalise to [-1, 1]
        rng = sig.max() - sig.min()
        if rng > 1e-8:
            sig = (sig - sig.min()) / rng * 2 - 1

        # Shape: (1, 1, seq_len)
        t = torch.FloatTensor(sig).unsqueeze(0).unsqueeze(0)

        features = self.forward(t).squeeze(0)   # (out_dim,)
        return features.tolist()
