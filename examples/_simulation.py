"""
examples._simulation — deterministic behavioral signal synthesis
================================================================

The real humanity score (theta) and 32-dim latent vector are produced by the
browser TensorFlow.js engine (src/services/biometrics.js). For self-contained,
reproducible *offline* demos we synthesize representative signals here:

  * Each user has a stable behavioral "fingerprint" (a unit direction in
    32-dim latent space).
  * Human sessions perturb that fingerprint slightly (day-to-day / stress
    variation) — same identity, small drift.
  * A different human is a different random direction — large drift.
  * A bot exhibits near-zero timing variance — low humanity proxy.

`recon_error` is a transparent stand-in for the autoencoder reconstruction
error: 0.5 * (1 - cosine_similarity), so same-user ≈ 0 and different-user ≈ 0.5
(comfortably above EREC_CRITICAL = 0.35).
"""
from __future__ import annotations

import hashlib

import numpy as np

LATENT_DIM = 32


def _seed(s: str) -> int:
    # Stable across processes (Python's built-in hash() is per-process randomized).
    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)


def user_fingerprint(user_id: str, dim: int = LATENT_DIM) -> np.ndarray:
    """Stable per-user behavioral direction (unit vector)."""
    r = np.random.default_rng(_seed(user_id))
    v = r.standard_normal(dim).astype("float32")
    return v / (np.linalg.norm(v) + 1e-9)


def human_latent(user_id: str, day: int = 0, stress: float = 0.0,
                 dim: int = LATENT_DIM) -> np.ndarray:
    """A human session: the user's fingerprint + small day/stress variation."""
    base = user_fingerprint(user_id, dim)
    r = np.random.default_rng(_seed(f"{user_id}:{day}:{stress}"))
    noise = (0.02 + 0.04 * stress) * r.standard_normal(dim).astype("float32")
    v = base + noise
    return (v / (np.linalg.norm(v) + 1e-9)).astype("float32")


def bot_latent(dim: int = LATENT_DIM) -> np.ndarray:
    """A scripted bot: a fixed, low-entropy direction."""
    r = np.random.default_rng(7)
    v = np.ones(dim, dtype="float32") + 1e-3 * r.standard_normal(dim).astype("float32")
    return (v / (np.linalg.norm(v) + 1e-9)).astype("float32")


def recon_error(baseline: np.ndarray, current: np.ndarray) -> float:
    """Autoencoder-style reconstruction error stand-in in [0, 1]."""
    a = np.asarray(baseline, dtype="float64")
    b = np.asarray(current, dtype="float64")
    cos = float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))
    return float(np.clip(0.5 * (1.0 - cos), 0.0, 1.0))


# ── Keystroke-timing → humanity proxy (stand-in for the CNN theta) ───────────

def human_keystroke_timings(n: int = 40, seed: int = 1) -> list[float]:
    """Natural human typing: jittery dwell times (ms)."""
    r = np.random.default_rng(seed)
    return list(np.clip(r.normal(110, 35, n), 30, 400))


def bot_keystroke_timings(n: int = 40) -> list[float]:
    """Scripted bot typing: near-constant dwell times (ms)."""
    return [100.0] * n


def humanity_from_timings(timings: list[float]) -> float:
    """Coefficient of variation → theta in [0, 1]. Bots ≈ 0; humans ≈ 0.3-0.9."""
    t = np.asarray(timings, dtype="float64")
    if len(t) < 3 or t.mean() <= 0:
        return 0.5
    cv = float(t.std() / t.mean())
    return float(np.clip(cv / 0.35, 0.0, 1.0))
