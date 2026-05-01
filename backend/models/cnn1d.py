"""
1D CNN — Biometric Feature Extractor (Phase 1)
Processes raw timing signal tensors from the browser.

Input contract:
    FloatTensor[batch, 1, signal_length]
    signal_length must be > kernel_size (≥ 5 recommended)

Output contract:
    FloatTensor[batch, out_dim]   (default out_dim=32)
    These 32-dim vectors are the latent representation sent to the Watchdog.
"""
from __future__ import annotations
import torch
import torch.nn as nn


class CNN1D(nn.Module):
    """
    Architecture:
        Conv1d(1→16, k=3) → ReLU
        Conv1d(16→32, k=3) → ReLU
        AdaptiveAvgPool1d(1)          ← handles any input length
        Linear(32 → out_dim)
    """

    def __init__(self, input_channels: int = 1, out_dim: int = 32):
        super().__init__()
        self.out_dim = out_dim
        self.conv = nn.Sequential(
            nn.Conv1d(input_channels, 16, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.Conv1d(16, 32, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fc = nn.Linear(32, out_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: FloatTensor[batch, channels, length]
        returns: FloatTensor[batch, out_dim]
        """
        x = self.conv(x)
        x = x.view(x.size(0), -1)
        return self.fc(x)

    # ── Convenience ───────────────────────────────────────────────────────────

    def extract(self, signal: list[float]) -> list[float]:
        """
        Convenience wrapper: raw Python list → feature list.
        Returns out_dim floats. Safe to call without torch.no_grad context.
        """
        t = torch.FloatTensor(signal).unsqueeze(0).unsqueeze(0)   # [1, 1, L]
        with torch.no_grad():
            out = self.forward(t)
        return out.squeeze().tolist()

    # ── Checkpoint I/O ────────────────────────────────────────────────────────

    def save_checkpoint(self, path: str) -> None:
        torch.save({"cnn1d": self.state_dict(), "out_dim": self.out_dim}, path)

    def load_checkpoint(self, path: str) -> None:
        ckpt = torch.load(path, map_location="cpu")
        self.load_state_dict(ckpt.get("cnn1d", ckpt))
