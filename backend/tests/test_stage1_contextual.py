"""
tests/test_stage1_contextual.py  —  Stage 1 context-aware behaviour

Run with:   pytest tests/test_stage1_contextual.py -v
"""
from __future__ import annotations

import pytest

from backend.pipeline.contracts import (
    HoneypotVerdict,
    Confidence,
    BOT_THETA_HARD,
    BOT_THETA_SOFT,
    BiometricContext,
    ContextualBiometricInput,
    LEARNING_PHASE_MIN_SAMPLES,
)
from backend.models.stage1_biometric import run, CENTROID_CLOSE_THRESHOLD, CENTROID_DRIFT_THRESHOLD
from backend.services.biometric_service import BiometricService, _cosine_distance, _update_centroid
from backend.services.biometric_profile_store import InMemoryProfileStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _ctx(site="site_a", user="user_1") -> BiometricContext:
    return BiometricContext(site_id=site, user_id=user)


def _inp(**kwargs) -> ContextualBiometricInput:
    defaults = dict(
        theta=0.9, h_exp=0.5, server_load=0.0,
        latent_vector=[0.1, 0.2], context=_ctx(),
        learning_phase=False, centroid_dist=None,
    )
    defaults.update(kwargs)
    return ContextualBiometricInput(**defaults)


# ── Learning phase ────────────────────────────────────────────────────────────

class TestLearningPhase:
    def test_learning_phase_always_returns_learning_verdict(self):
        result = run(_inp(theta=0.02, learning_phase=True))
        assert result.verdict == HoneypotVerdict.LEARNING
        assert result.is_bot is False

    def test_learning_phase_with_high_theta_still_learning(self):
        result = run(_inp(theta=0.99, learning_phase=True))
        assert result.verdict == HoneypotVerdict.LEARNING

    def test_learning_phase_confidence_is_low(self):
        result = run(_inp(theta=0.8, learning_phase=True))
        assert result.confidence == Confidence.LOW

    def test_learning_phase_exposes_context(self):
        ctx = _ctx(site="acme", user="bob")
        result = run(_inp(context=ctx, learning_phase=True))
        assert result.context.site_id == "acme"
        assert result.context.user_id == "bob"


# ── Hard bot ──────────────────────────────────────────────────────────────────

class TestHardBot:
    def test_below_hard_threshold_is_bot(self):
        result = run(_inp(theta=BOT_THETA_HARD - 0.01, learning_phase=False))
        assert result.verdict == HoneypotVerdict.BOT
        assert result.is_bot is True
        assert result.confidence == Confidence.HIGH

    def test_bot_carries_context(self):
        ctx = _ctx(site="shop", user="suspicious_ua")
        result = run(_inp(theta=0.01, context=ctx, learning_phase=False))
        assert result.context.site_id == "shop"


# ── Suspect band ──────────────────────────────────────────────────────────────

class TestSuspectBand:
    def test_lower_suspect_is_medium_confidence(self):
        # theta between BOT_THETA_HARD and midpoint
        theta = BOT_THETA_HARD + 0.01
        result = run(_inp(theta=theta, learning_phase=False))
        assert result.verdict == HoneypotVerdict.SUSPECT
        assert result.confidence == Confidence.MEDIUM

    def test_upper_suspect_is_low_confidence(self):
        # theta between midpoint and BOT_THETA_SOFT
        theta = BOT_THETA_SOFT - 0.01
        result = run(_inp(theta=theta, learning_phase=False))
        assert result.verdict == HoneypotVerdict.SUSPECT
        assert result.confidence == Confidence.LOW


# ── Human confidence with centroid distance ───────────────────────────────────

class TestHumanWithCentroid:
    def test_high_theta_close_centroid_latent_is_high(self):
        result = run(_inp(
            theta=0.90, latent_vector=[1.0],
            centroid_dist=CENTROID_CLOSE_THRESHOLD - 0.01,
            learning_phase=False,
        ))
        assert result.verdict == HoneypotVerdict.HUMAN
        assert result.confidence == Confidence.HIGH

    def test_high_theta_far_centroid_demotes_to_medium(self):
        result = run(_inp(
            theta=0.90, latent_vector=[1.0],
            centroid_dist=CENTROID_DRIFT_THRESHOLD + 0.01,
            learning_phase=False,
        ))
        assert result.verdict == HoneypotVerdict.HUMAN
        assert result.confidence == Confidence.MEDIUM

    def test_mid_theta_close_centroid_is_medium(self):
        result = run(_inp(
            theta=0.65, latent_vector=[1.0],
            centroid_dist=CENTROID_CLOSE_THRESHOLD - 0.01,
            learning_phase=False,
        ))
        assert result.verdict == HoneypotVerdict.HUMAN
        assert result.confidence == Confidence.MEDIUM

    def test_borderline_human_always_low(self):
        # [BOT_THETA_SOFT, 0.50) → LOW regardless of centroid
        result = run(_inp(
            theta=BOT_THETA_SOFT + 0.01,
            centroid_dist=0.01,   # very close centroid
            latent_vector=[1.0],
            learning_phase=False,
        ))
        assert result.verdict == HoneypotVerdict.HUMAN
        assert result.confidence == Confidence.LOW

    def test_no_centroid_no_latent_mid_theta_is_low(self):
        result = run(_inp(
            theta=0.70, latent_vector=[],
            centroid_dist=None,
            learning_phase=False,
        ))
        assert result.verdict == HoneypotVerdict.HUMAN
        assert result.confidence == Confidence.LOW


# ── BiometricService integration ──────────────────────────────────────────────

class TestBiometricService:
    def _service(self):
        return BiometricService(store=InMemoryProfileStore(), out_dim=32)

    def _evaluate(self, service, theta=0.9, site="s1", user="u1", signal=None):
        return service.evaluate(
            raw_signal  = signal or [float(i) for i in range(20)],
            theta       = theta,
            h_exp       = 0.5,
            context     = BiometricContext(site_id=site, user_id=user),
        )

    def test_new_user_is_in_learning_phase(self):
        svc = self._service()
        result = self._evaluate(svc, theta=0.9)
        assert result.verdict == HoneypotVerdict.LEARNING

    def test_profile_graduates_after_enough_human_samples(self):
        svc = self._service()
        # Feed LEARNING_PHASE_MIN_SAMPLES confirmed-human evaluations
        for _ in range(LEARNING_PHASE_MIN_SAMPLES):
            self._evaluate(svc, theta=0.95)

        # One more evaluation — should now be past learning phase
        result = self._evaluate(svc, theta=0.95)
        assert result.verdict == HoneypotVerdict.HUMAN

    def test_profiles_are_isolated_by_site_id(self):
        svc = self._service()
        # Graduate user on site_a
        for _ in range(LEARNING_PHASE_MIN_SAMPLES):
            self._evaluate(svc, theta=0.95, site="site_a", user="u1")

        # Same user on site_b — still in learning phase
        result = self._evaluate(svc, theta=0.95, site="site_b", user="u1")
        assert result.verdict == HoneypotVerdict.LEARNING

    def test_reset_profile_removes_profile(self):
        svc = self._service()
        self._evaluate(svc)   # creates profile
        removed = svc.reset_profile("s1", "u1")
        assert removed is True
        # Next call starts learning phase again
        result = self._evaluate(svc)
        assert result.verdict == HoneypotVerdict.LEARNING

    def test_bot_during_learning_phase_does_not_graduate(self):
        """Bot signals should not advance the human_count."""
        svc = self._service()
        for _ in range(LEARNING_PHASE_MIN_SAMPLES):
            self._evaluate(svc, theta=0.01)  # all bots

        # Still learning because human_count never grew
        result = self._evaluate(svc, theta=0.99)
        assert result.verdict == HoneypotVerdict.LEARNING


# ── Math utilities ────────────────────────────────────────────────────────────

class TestCosineDistance:
    def test_identical_vectors_distance_is_zero(self):
        v = [1.0, 0.5, -0.3]
        assert _cosine_distance(v, v) == pytest.approx(0.0, abs=1e-6)

    def test_orthogonal_vectors_distance_is_half(self):
        assert _cosine_distance([1, 0], [0, 1]) == pytest.approx(0.5, abs=1e-6)

    def test_opposite_vectors_distance_is_one(self):
        assert _cosine_distance([1, 0], [-1, 0]) == pytest.approx(1.0, abs=1e-6)

    def test_zero_vector_returns_one(self):
        assert _cosine_distance([0, 0], [1, 0]) == pytest.approx(1.0)

    def test_mismatched_lengths_return_one(self):
        assert _cosine_distance([1, 2], [1, 2, 3]) == 1.0


class TestUpdateCentroid:
    def test_first_sample_equals_embedding(self):
        emb = [0.1, 0.2, 0.3]
        result = _update_centroid(None, emb, human_count=1)
        assert result == pytest.approx(emb)

    def test_cumulative_mean_during_learning(self):
        c = [1.0, 1.0]
        e = [0.0, 0.0]
        n = LEARNING_PHASE_MIN_SAMPLES  # still in learning phase
        updated = _update_centroid(c, e, human_count=n)
        alpha = 1.0 / n
        expected = [(1 - alpha) * 1.0 + alpha * 0.0] * 2
        assert updated == pytest.approx(expected)

    def test_ema_after_graduation(self):
        c = [1.0, 1.0]
        e = [0.0, 0.0]
        n = LEARNING_PHASE_MIN_SAMPLES + 5   # graduated
        updated = _update_centroid(c, e, human_count=n, ema_alpha=0.05)
        expected = [0.95, 0.95]
        assert updated == pytest.approx(expected)