"""
services/biometric_service.py  —  Biometric Service (SaaS Orchestrator)

Single entry point for the biometric pipeline in a multi-tenant environment.
Callers (API endpoints, background workers) interact only with this class;
they never touch CNN1D or Stage 1 directly.

Responsibilities
────────────────
1. Load or create the per-(site_id, user_id) UserProfile.
2. Run CNN1D.extract() to obtain a fixed-length embedding.
3. Compute cosine distance between the new embedding and the stored centroid
   (if one exists).
4. Determine whether the user is still in the learning phase.
5. Build a ContextualBiometricInput and hand it to stage1_biometric.run().
6. Update the profile (centroid, sample counts) based on the Stage 1 verdict.
7. Return the BiometricResult to the caller.

Threading / async
─────────────────
BiometricService is designed to be instantiated once (as a singleton or DI
component) and used from multiple threads.  The profile store handles its own
locking.  CNN1D inference is CPU-bound and GIL-held; for async FastAPI
endpoints, run evaluate() inside asyncio.to_thread().

Example (FastAPI)::

    service = BiometricService(
        cnn        = CNN1D(out_dim=32),
        store      = RedisProfileStore(redis_client),
    )

    @router.post("/biometric/evaluate")
    async def evaluate(body: EvaluateRequest):
        ctx     = BiometricContext(site_id=body.site_id, user_id=body.user_id)
        result  = await asyncio.to_thread(
            service.evaluate,
            raw_signal   = body.signal,
            theta        = body.theta,
            h_exp        = body.h_exp,
            server_load  = body.server_load,
            context      = ctx,
        )
        return result
"""
from __future__ import annotations

import logging
import math
from typing import List, Optional

from ..models.cnn1d import CNN1D
from ..models.stage1_biometric import run as stage1_run
from ..pipeline.contracts import (
    BiometricContext,
    BiometricResult,
    ContextualBiometricInput,
    HoneypotVerdict,
    LEARNING_PHASE_MIN_SAMPLES,
    UserProfile,
)
from .biometric_profile_store import AbstractProfileStore, InMemoryProfileStore

logger = logging.getLogger("entropy_prime.biometric_service")


class BiometricService:
    """
    Stateless orchestrator; all mutable state lives in the injected store.

    Parameters
    ──────────
    cnn         — a CNN1D instance (shared, thread-safe under no_grad).
    store       — an AbstractProfileStore implementation.
    out_dim     — embedding dimension; must match cnn.out_dim.
    """

    def __init__(
        self,
        cnn:   Optional[CNN1D]               = None,
        store: Optional[AbstractProfileStore] = None,
        out_dim: int = 32,
    ) -> None:
        self._cnn   = cnn   or CNN1D(out_dim=out_dim)
        self._store = store or InMemoryProfileStore()
        self._out_dim = self._cnn.out_dim

    # ── Public API ─────────────────────────────────────────────────────────────

    def evaluate(
        self,
        *,
        raw_signal:  List[float],
        theta:       float,
        h_exp:       float,
        context:     BiometricContext,
        server_load: float = 0.0,
        latent_vector: Optional[List[float]] = None,
    ) -> BiometricResult:
        """
        Full pipeline: signal → embedding → profile lookup → Stage 1 → profile update.

        Parameters
        ──────────
        raw_signal    — variable-length keystroke / touch / accel trace.
        theta         — humanity score computed upstream (0–1).
        h_exp         — entropy value from the encoder.
        context       — (site_id, user_id) pair.
        server_load   — passed through to downstream stages unchanged.
        latent_vector — optional pre-computed latent from the autoencoder.

        Returns
        ───────
        BiometricResult — verdict + confidence + centroid_dist + context.
        """
        # 1. Extract embedding
        embedding: List[float] = self._cnn.extract(raw_signal)

        # 2. Load (or create) the per-site user profile
        profile, is_new = self._store.get_or_create(context.site_id, context.user_id)
        if is_new:
            logger.info(
                "[Service] New user profile created: site=%r user=%r",
                context.site_id, context.user_id,
            )

        # 3. Validate / set embedding dim on first sample
        if profile.embedding_dim is None:
            profile.embedding_dim = len(embedding)
        elif profile.embedding_dim != len(embedding):
            logger.error(
                "[Service] Embedding dim mismatch: stored=%d got=%d — skipping centroid update",
                profile.embedding_dim, len(embedding),
            )
            embedding = embedding[:profile.embedding_dim]  # truncate to stored dim

        # 4. Compute cosine distance to stored centroid (None if not yet available)
        cdist: Optional[float] = (
            _cosine_distance(embedding, profile.centroid)
            if profile.centroid is not None
            else None
        )

        # 5. Build ContextualBiometricInput for Stage 1
        inp = ContextualBiometricInput(
            theta         = theta,
            h_exp         = h_exp,
            server_load   = server_load,
            latent_vector = latent_vector or [],
            context       = context,
            learning_phase= profile.in_learning_phase,
            centroid_dist = cdist,
        )

        # 6. Run Stage 1
        result = stage1_run(inp)

        # 7. Update profile based on verdict
        self._update_profile(profile, embedding, result)

        logger.debug(
            "[Service] site=%r user=%r verdict=%s conf=%s learning=%s cdist=%s",
            context.site_id, context.user_id,
            result.verdict, result.confidence,
            profile.in_learning_phase,
            f"{cdist:.3f}" if cdist is not None else "n/a",
        )

        return result

    def reset_profile(self, site_id: str, user_id: str) -> bool:
        """
        Delete a user's stored profile (e.g. on explicit user request or GDPR erasure).
        Returns True if a profile existed and was removed.
        """
        removed = self._store.delete(site_id, user_id)
        if removed:
            logger.info("[Service] Profile deleted: site=%r user=%r", site_id, user_id)
        return removed

    def get_profile(self, site_id: str, user_id: str) -> Optional[UserProfile]:
        """Read-only access to a stored profile (admin / debug endpoints)."""
        return self._store.get(site_id, user_id)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _update_profile(
        self,
        profile:   UserProfile,
        embedding: List[float],
        result:    BiometricResult,
    ) -> None:
        """
        Update centroid and counters, then persist.

        Centroid update strategy
        ────────────────────────
        We maintain a running mean of confirmed-HUMAN embeddings using an
        exponential moving average (EMA) once the learning phase is complete,
        and a simple cumulative mean during the learning phase.  This keeps
        the centroid representative without storing all historical embeddings.

        Only HUMAN verdicts update the centroid.  BOT / SUSPECT / LEARNING
        verdicts increment sample_count only (we still want to track volume).
        """
        profile.sample_count += 1

        if result.verdict == HoneypotVerdict.HUMAN:
            profile.human_count += 1
            profile.centroid = _update_centroid(
                old_centroid  = profile.centroid,
                new_embedding = embedding,
                human_count   = profile.human_count,
            )

        self._store.save(profile)


# ── Math utilities ─────────────────────────────────────────────────────────────

def _cosine_distance(a: List[float], b: List[float]) -> float:
    """
    Cosine distance in [0, 1]:  0 = identical direction, 1 = orthogonal / opposite.

    Returns 1.0 on zero-vector edge cases so they never receive a centroid boost.
    """
    if len(a) != len(b):
        return 1.0

    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))

    if mag_a < 1e-9 or mag_b < 1e-9:
        return 1.0

    cosine_sim = dot / (mag_a * mag_b)
    # Clamp to [-1, 1] to guard against floating-point overshoot
    cosine_sim = max(-1.0, min(1.0, cosine_sim))
    return (1.0 - cosine_sim) / 2.0


def _update_centroid(
    old_centroid:  Optional[List[float]],
    new_embedding: List[float],
    human_count:   int,
    ema_alpha:     float = 0.05,
) -> List[float]:
    """
    Update the running centroid with the new human embedding.

    • During learning phase (human_count ≤ LEARNING_PHASE_MIN_SAMPLES):
        cumulative mean — each sample has equal weight.
    • After graduation:
        EMA with ema_alpha — recent samples matter more, handles drift.

    ema_alpha=0.05 means ~20-sample effective window.
    """
    if old_centroid is None:
        # First human sample — centroid IS the embedding
        return list(new_embedding)

    dim = len(new_embedding)

    if human_count <= LEARNING_PHASE_MIN_SAMPLES:
        # Cumulative mean: c_n = c_{n-1} + (x_n - c_{n-1}) / n
        alpha = 1.0 / human_count
    else:
        alpha = ema_alpha

    return [
        (1.0 - alpha) * c + alpha * e
        for c, e in zip(old_centroid, new_embedding)
    ]