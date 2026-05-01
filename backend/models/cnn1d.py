"""
1D CNN for per-user biometric feature extraction.
- 8-channel input (dwell, flight, speed, jitter, accel, rhythm, pause, bigram)
- Produces 32-dim latent features used by autoencoder watchdog
- Supports per-user fine-tuning via freeze/unfreeze of classifier head
"""
import torch
import torch.nn as nn
from typing import Optional, List


class CNN1D(nn.Module):
    """
    8-channel 1D CNN for biometric signal feature extraction.
    Architecture: Conv1d × 3 → GlobalAvgPool → FC head → 32-dim output
    """
    FEATURE_NAMES = [
        "dwell_norm", "flight_norm", "speed_norm", "jitter_norm",
        "accel_norm",  "rhythm_norm", "pause_norm",  "bigram_norm",
    ]

    def __init__(self, input_channels: int = 8, out_dim: int = 32, seq_len: int = 50):
        super().__init__()
        self.input_channels = input_channels
        self.out_dim        = out_dim
        self.seq_len        = seq_len

        # Shared convolutional backbone (frozen during per-user fine-tuning)
        self.backbone = nn.Sequential(
            nn.Conv1d(input_channels, 32, kernel_size=5, stride=1, padding=2),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Conv1d(64, 64, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),  # → [B, 64, 1]
        )

        # Per-user adaptable head (fine-tuned per user)
        self.head = nn.Sequential(
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, out_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [B, input_channels, seq_len]  — raw 8-channel sequence
        Returns:
            [B, out_dim]  — 32-dim latent feature vector
        """
        x = self.backbone(x)        # [B, 64, 1]
        x = x.view(x.size(0), -1)  # [B, 64]
        return self.head(x)         # [B, 32]

    def freeze_backbone(self):
        """Freeze backbone for per-user fine-tuning of head only."""
        for param in self.backbone.parameters():
            param.requires_grad = False

    def unfreeze_backbone(self):
        """Unfreeze backbone for full retraining."""
        for param in self.backbone.parameters():
            param.requires_grad = True

    def get_backbone_features(self, x: torch.Tensor) -> torch.Tensor:
        """Extract backbone features without the head (for downstream tasks)."""
        with torch.no_grad():
            x = self.backbone(x)
            return x.view(x.size(0), -1)


class PerUserCNN1D(nn.Module):
    """
    Per-user CNN wrapper: shared backbone + per-user lightweight adapter.
    Adapter is a small bottleneck that adapts backbone features to the user's
    behavioral manifold without modifying shared weights.

    Usage:
        base_model = CNN1D(input_channels=8, out_dim=32)
        user_model = PerUserCNN1D(base_model, user_id="usr_abc123")
        features   = user_model(x)
    """

    def __init__(self, base_model: CNN1D, user_id: str, adapter_dim: int = 16):
        super().__init__()
        self.user_id     = user_id
        self.base_model  = base_model
        self.adapter_dim = adapter_dim

        # Freeze shared backbone
        self.base_model.freeze_backbone()

        # Per-user lightweight adapter (bottleneck)
        self.adapter = nn.Sequential(
            nn.Linear(64, adapter_dim),
            nn.ReLU(),
            nn.Linear(adapter_dim, 64),
            nn.Sigmoid(),   # scale gate
        )

        # Per-user projection head
        self.user_head = nn.Sequential(
            nn.Linear(64, base_model.out_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [B, 8, seq_len]
        Returns:
            [B, 32]  — user-adapted feature vector
        """
        backbone_feats = self.base_model.get_backbone_features(x)  # [B, 64]
        scale_gate     = self.adapter(backbone_feats)               # [B, 64] gating
        adapted        = backbone_feats * scale_gate                # feature modulation
        return self.user_head(adapted)                              # [B, 32]

    def fine_tune_step(
        self,
        x: torch.Tensor,
        target: torch.Tensor,
        optimizer: torch.optim.Optimizer,
        criterion: nn.Module = None,
    ) -> float:
        """
        Single fine-tuning step on per-user adapter.
        Args:
            x:         [B, 8, seq_len]
            target:    [B, 32] — target latent representation (from known-good sessions)
            optimizer: optimizer over adapter + user_head params only
            criterion: loss function (default: MSE)
        Returns:
            loss scalar
        """
        if criterion is None:
            criterion = nn.MSELoss()
        self.train()
        optimizer.zero_grad()
        out  = self.forward(x)
        loss = criterion(out, target)
        loss.backward()
        optimizer.step()
        self.eval()
        return loss.item()


class FeatureSelector(nn.Module):
    """
    Differentiable per-user feature selector.
    Learns a soft mask over the 8 input channels (features),
    effectively selecting which signals are most discriminative for each user.
    During inference, hard-thresholded mask identifies top-K features.
    """
    def __init__(self, n_features: int = 8, k: int = 6, temperature: float = 1.0):
        super().__init__()
        self.n_features  = n_features
        self.k           = k
        self.temperature = temperature
        # Learnable importance logits (one per feature)
        self.logits = nn.Parameter(torch.zeros(n_features))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Apply soft feature mask during training, hard mask during eval.
        Args:
            x: [B, n_features, seq_len]
        Returns:
            [B, n_features, seq_len]  — masked input
        """
        if self.training:
            mask = torch.sigmoid(self.logits / self.temperature)
        else:
            mask = (torch.sigmoid(self.logits) >= 0.5).float()
        # Broadcast mask: [n_features] → [1, n_features, 1]
        return x * mask.unsqueeze(0).unsqueeze(-1)

    @property
    def selected_indices(self) -> List[int]:
        """Top-K feature indices by learned importance."""
        probs = torch.sigmoid(self.logits).detach()
        return probs.topk(self.k).indices.tolist()

    @property
    def selected_names(self) -> List[str]:
        return [CNN1D.FEATURE_NAMES[i] for i in self.selected_indices]

    def to_dict(self) -> dict:
        probs = torch.sigmoid(self.logits).detach().tolist()
        return {
            "logits":           self.logits.detach().tolist(),
            "probabilities":    probs,
            "selected_indices": self.selected_indices,
            "selected_names":   self.selected_names,
        }


class FullPerUserPipeline(nn.Module):
    """
    End-to-end per-user pipeline:
        FeatureSelector → CNN1D backbone → PerUserAdapter → 32-dim output

    This is the model actually used for per-user fine-tuning.
    """
    def __init__(self, base_model: CNN1D, user_id: str):
        super().__init__()
        self.user_id      = user_id
        self.feat_selector = FeatureSelector(n_features=base_model.input_channels)
        self.user_cnn      = PerUserCNN1D(base_model, user_id)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.feat_selector(x)
        return self.user_cnn(x)

    def get_selection_state(self) -> dict:
        return self.feat_selector.to_dict()
