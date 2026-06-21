"""
Entropy Prime — Pipeline Test Suite
Run with:  pytest backend/tests/test_pipeline.py -v

All tests are deterministic (no randomness, no network, no DB).
Each stage is tested in isolation, then the orchestrator end-to-end.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import numpy as np

from pipeline.contracts import (
    BiometricInput, Confidence, HoneypotVerdict,
    SecurityPreset, WatchdogAction,
    BOT_THETA_HARD, BOT_THETA_SOFT, EREC_WARN, EREC_CRITICAL,
    TRUST_WARN, TRUST_CRITICAL,
)
from pipeline import stage1_biometric as s1
from pipeline import stage2_honeypot  as s2
from pipeline import stage3_governor  as s3
from pipeline import stage4_watchdog  as s4
from pipeline.orchestrator import PipelineOrchestrator

from models.dqn import DQNAgent
from models.mab import MABAgent
from models.ppo import PPOAgent


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def dqn():  return DQNAgent(state_dim=3, action_dim=4)

@pytest.fixture
def mab():  return MABAgent(n_arms=3)

@pytest.fixture
def ppo():  return PPOAgent(state_dim=10, action_dim=3)

@pytest.fixture
def orch(dqn, mab, ppo):
    return PipelineOrchestrator(
        dqn_agent=dqn, mab_agent=mab, ppo_agent=ppo,
        shadow_secret="test_shadow", session_secret="test_session",
    )

def _bio(theta=0.8, h_exp=0.7, server_load=0.4, lv=None, ip="1.2.3.4"):
    return BiometricInput(
        theta=theta, h_exp=h_exp, server_load=server_load,
        user_agent="test-agent",
        latent_vector=lv if lv is not None else [0.0]*32,
        ip_address=ip,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Stage 1 — Biometric Interpreter
# ═════════════════════════════════════════════════════════════════════════════

class TestStage1:

    def test_definite_bot(self):
        result = s1.run(_bio(theta=0.03))
        assert result.verdict    == HoneypotVerdict.BOT
        assert result.is_bot     is True
        assert result.confidence == Confidence.HIGH

    def test_bot_boundary(self):
        """Exactly at BOT_THETA_HARD should still be BOT."""
        result = s1.run(_bio(theta=BOT_THETA_HARD))
        assert result.verdict == HoneypotVerdict.BOT

    def test_suspect_range(self):
        result = s1.run(_bio(theta=0.20))
        assert result.verdict    == HoneypotVerdict.SUSPECT
        assert result.is_suspect is True

    def test_human(self):
        result = s1.run(_bio(theta=0.85))
        assert result.verdict    == HoneypotVerdict.HUMAN
        assert result.is_bot     is False
        assert result.is_suspect is False

    def test_high_confidence_human(self):
        result = s1.run(_bio(theta=0.90, lv=[0.1]*32))
        assert result.confidence == Confidence.HIGH

    def test_contested_band_low_confidence(self):
        """θ in [0.15, 0.50) → LOW confidence regardless of verdict."""
        result = s1.run(_bio(theta=0.35))
        assert result.confidence == Confidence.LOW

    def test_missing_latent_degrades_confidence(self):
        """No latent vector on a HIGH-confidence signal → capped at MEDIUM."""
        result = s1.run(_bio(theta=0.95, lv=[]))
        assert result.confidence == Confidence.MEDIUM

    def test_output_fields_present(self):
        result = s1.run(_bio())
        assert hasattr(result, "theta")
        assert hasattr(result, "verdict")
        assert hasattr(result, "confidence")
        assert hasattr(result, "is_bot")
        assert hasattr(result, "is_suspect")


# ═════════════════════════════════════════════════════════════════════════════
# Stage 2 — Honeypot Classifier
# ═════════════════════════════════════════════════════════════════════════════

class TestStage2:

    def _bio_result(self, **kw):
        raw = _bio(**kw)
        return s1.run(raw)

    def test_bot_gets_shadowed(self):
        bio    = self._bio_result(theta=0.03)
        result = s2.run(bio, None, "secret", "1.2.3.4")
        assert result.should_shadow   is True
        assert result.synthetic_token is not None
        assert result.synthetic_token.startswith("ep_shadow_")

    def test_human_not_shadowed(self):
        bio    = self._bio_result(theta=0.90, lv=[0.1]*32)
        result = s2.run(bio, None, "secret", "1.2.3.4")
        assert result.should_shadow  is False
        assert result.synthetic_token is None

    def test_suspect_low_confidence_not_shadowed(self):
        """Low-confidence suspect → benefit of doubt, no shadow."""
        bio    = self._bio_result(theta=0.25, lv=[])  # low conf suspect
        result = s2.run(bio, None, "secret", "1.2.3.4")
        assert result.should_shadow is False

    def test_mab_fallback_when_none(self):
        bio    = self._bio_result(theta=0.03)
        result = s2.run(bio, None, "secret")
        assert result.mab_arm_selected == 0
        assert result.mab_confidence   == Confidence.LOW

    def test_mab_used_when_present(self, mab):
        bio    = self._bio_result(theta=0.03)
        result = s2.run(bio, mab, "secret")
        assert 0 <= result.mab_arm_selected < 3

    def test_synthetic_tokens_are_unique(self):
        bio    = self._bio_result(theta=0.03)
        tokens = {s2.run(bio, None, "secret").synthetic_token for _ in range(10)}
        assert len(tokens) == 10

    def test_mab_reward_update_safe_with_none(self):
        """update_mab_reward with None agent must not raise."""
        s2.update_mab_reward(None, 0, 1.0)  # no exception

    def test_mab_reward_update_works(self, mab):
        before = mab.values[0]
        s2.update_mab_reward(mab, 0, 1.0)
        # After first update counts[0]=1, values[0] = 1.0
        assert mab.counts[0] == 1


# ═════════════════════════════════════════════════════════════════════════════
# Stage 3 — Resource Governor (DQN)
# ═════════════════════════════════════════════════════════════════════════════

class TestStage3:

    def _s1(self, **kw):
        return s1.run(_bio(**kw))

    def test_returns_valid_preset(self, dqn):
        bio    = self._s1(theta=0.8)
        result = s3.run(bio, dqn)
        assert result.preset in list(SecurityPreset)

    def test_bot_overloaded_server_economy(self):
        """Confirmed bot + server overloaded → ECONOMY to save resources."""
        bio    = self._s1(theta=0.03, server_load=0.90, lv=[0.1]*32)
        result = s3.run(bio, None)
        assert result.preset   == SecurityPreset.ECONOMY
        assert result.fallback is True

    def test_bot_healthy_server_hard(self):
        """Confirmed bot + server fine → HARD to burn attacker CPU."""
        bio    = self._s1(theta=0.03, server_load=0.40, lv=[0.1]*32)
        result = s3.run(bio, None)
        assert result.preset == SecurityPreset.HARD

    def test_server_load_caps_at_standard(self, dqn):
        """Heavy server load must cap preset at STANDARD max."""
        bio    = self._s1(theta=0.8, h_exp=0.9, server_load=0.90)
        result = s3.run(bio, dqn)
        assert result.action <= 1   # 0=economy or 1=standard

    def test_fallback_when_dqn_none(self):
        bio    = self._s1(theta=0.8)
        result = s3.run(bio, None)
        assert result.fallback is True
        assert result.preset   == SecurityPreset.STANDARD

    def test_low_bio_conf_hedges_governor_conf(self, dqn):
        """LOW biometric confidence must not let governor claim HIGH confidence."""
        bio    = self._s1(theta=0.35, lv=[])   # LOW bio conf
        result = s3.run(bio, dqn)
        assert result.confidence != Confidence.HIGH

    def test_argon2_params_populated(self, dqn):
        bio    = self._s1(theta=0.8)
        result = s3.run(bio, dqn)
        assert result.memory_kb   > 0
        assert result.time_cost   > 0
        assert result.parallelism > 0


# ═════════════════════════════════════════════════════════════════════════════
# Stage 4 — Session Watchdog (PPO)
# ═════════════════════════════════════════════════════════════════════════════

class TestStage4:

    def test_clean_session_ok(self, ppo):
        result = s4.run([0.1]*32, e_rec=0.05, trust_score=0.95, ppo_agent=ppo)
        # PPO might vary, but fallback rules give OK for clean session
        assert result.e_rec       == pytest.approx(0.05)
        assert result.trust_score == pytest.approx(0.95)
        assert result.action in list(WatchdogAction)

    def test_critical_drift_force_logout(self):
        """Critical e_rec + critical trust → FORCE_LOGOUT hard override (no PPO)."""
        result = s4.run(
            [0.1]*32,
            e_rec=EREC_CRITICAL + 0.05,
            trust_score=TRUST_CRITICAL - 0.05,
            ppo_agent=None,
        )
        assert result.action     == WatchdogAction.FORCE_LOGOUT
        assert result.confidence == Confidence.HIGH

    def test_warn_level_triggers_reauth(self):
        """e_rec above warn threshold with no PPO → passive_reauth."""
        result = s4.run(
            [0.0]*32,
            e_rec=EREC_WARN + 0.05,
            trust_score=0.80,
            ppo_agent=None,
        )
        assert result.action == WatchdogAction.PASSIVE_REAUTH

    def test_fallback_rules_when_ppo_none(self):
        result = s4.run([0.0]*32, e_rec=0.05, trust_score=0.95, ppo_agent=None)
        assert result.action     == WatchdogAction.OK
        assert result.confidence == Confidence.HIGH
        assert "fallback" in result.reason

    def test_hard_override_before_ppo(self, ppo):
        """Hard override must fire even when PPO is available."""
        result = s4.run(
            [0.0]*32,
            e_rec=EREC_CRITICAL + 0.1,
            trust_score=TRUST_CRITICAL - 0.1,
            ppo_agent=ppo,
        )
        assert result.action == WatchdogAction.FORCE_LOGOUT

    def test_output_contract(self, ppo):
        result = s4.run([0.0]*32, e_rec=0.1, trust_score=0.8, ppo_agent=ppo)
        assert hasattr(result, "action")
        assert hasattr(result, "trust_score")
        assert hasattr(result, "e_rec")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reason")


# ═════════════════════════════════════════════════════════════════════════════
# Orchestrator — end-to-end
# ═════════════════════════════════════════════════════════════════════════════

class TestOrchestrator:

    def test_human_full_pipeline(self, orch):
        result = orch.run(_bio(theta=0.85, h_exp=0.7, lv=[0.1]*32))
        assert result.shadow_mode    is False
        assert result.session_token  != ""
        assert result.action_label   in [p.value for p in SecurityPreset]
        assert result.humanity_score == pytest.approx(0.85)

    def test_bot_short_circuits(self, orch):
        """Bot must be shadow-routed; governor should use ECONOMY."""
        result = orch.run(_bio(theta=0.03, lv=[0.0]*32))
        assert result.shadow_mode is True
        assert result.session_token.startswith("ep_shadow_")
        assert result.governor.preset == SecurityPreset.ECONOMY
        assert result.watchdog is None   # watchdog skipped for bots

    def test_degraded_flag_set_on_agent_failure(self, mab, ppo):
        """Passing dqn=None should set degraded=True on a human request."""
        orch = PipelineOrchestrator(
            dqn_agent=None, mab_agent=mab, ppo_agent=ppo,
            shadow_secret="s", session_secret="s",
        )
        result = orch.run(_bio(theta=0.85, lv=[0.1]*32))
        assert result.degraded is True

    def test_pipeline_always_returns_output(self, orch):
        """Pipeline must never raise — even with degenerate inputs."""
        result = orch.run(_bio(theta=0.0, h_exp=0.0, server_load=1.0, lv=[]))
        assert result is not None
        assert result.session_token != ""

    def test_pipeline_confidence_is_minimum(self, orch):
        """Overall confidence must not exceed the weakest stage."""
        result = orch.run(_bio(theta=0.35, lv=[]))   # LOW bio conf
        from pipeline.contracts import _CONF_RANK   # type: ignore
        # overall conf rank ≤ bio conf rank
        bio_rank    = {"high": 2, "medium": 1, "low": 0}[result.biometric.confidence.value]
        overall_rank = {"high": 2, "medium": 1, "low": 0}[result.pipeline_confidence.value]
        assert overall_rank <= bio_rank

    def test_watchdog_standalone(self, orch):
        result = orch.run_watchdog([0.1]*32, e_rec=0.05, trust_score=0.9)
        assert result.action in list(WatchdogAction)

    def test_mab_reward_feedback(self, orch, mab):
        before = mab.counts[0]
        orch.report_mab_reward(arm=0, reward=1.0)
        assert mab.counts[0] == before + 1

    def test_session_tokens_unique(self, orch):
        tokens = {orch.run(_bio(theta=0.85)).session_token for _ in range(20)}
        assert len(tokens) == 20

    def test_bot_tokens_unique(self, orch):
        tokens = {orch.run(_bio(theta=0.01)).session_token for _ in range(10)}
        assert len(tokens) == 10


# ═════════════════════════════════════════════════════════════════════════════
# DQN model unit tests
# ═════════════════════════════════════════════════════════════════════════════

class TestDQNAgent:

    def test_select_action_in_range(self, dqn):
        state  = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        action = dqn.select_action(state)
        assert 0 <= action <= 3

    def test_q_values_shape(self, dqn):
        state  = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        qv     = dqn.q_values(state)
        assert qv.shape == (4,)

    def test_train_step_returns_loss(self, dqn):
        s  = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        loss = dqn.train_step(s, 1, 0.5, s, False)
        assert isinstance(loss, float)


# ═════════════════════════════════════════════════════════════════════════════
# MAB model unit tests
# ═════════════════════════════════════════════════════════════════════════════

class TestMABAgent:

    def test_select_arm_in_range(self, mab):
        for _ in range(50):
            assert 0 <= mab.select_arm() < 3

    def test_update_increments_count(self, mab):
        mab.update(1, 0.8)
        assert mab.counts[1] == 1

    def test_invalid_arm_raises(self, mab):
        with pytest.raises(ValueError):
            mab.update(5, 1.0)

    def test_state_dict_roundtrip(self, mab):
        mab.update(0, 1.0)
        mab.update(1, 0.5)
        sd  = mab.state_dict()
        mab2 = MABAgent(n_arms=3)
        mab2.load_state_dict(sd)
        assert list(mab2.counts) == list(mab.counts)
        assert list(mab2.values) == list(mab.values)


# ═════════════════════════════════════════════════════════════════════════════
# PPO model unit tests
# ═════════════════════════════════════════════════════════════════════════════

class TestPPOAgent:

    def test_policy_output_shape(self, ppo):
        import torch
        state = torch.FloatTensor([[0.1]*10])
        probs = ppo.policy(state)
        assert probs.shape == (1, 3)

    def test_policy_sums_to_one(self, ppo):
        import torch
        state = torch.FloatTensor([[0.1]*10])
        probs = ppo.policy(state).squeeze()
        assert abs(float(probs.sum()) - 1.0) < 1e-5

    def test_select_action_in_range(self, ppo):
        state = np.zeros(10, dtype=np.float32)
        act, lp = ppo.select_action(state)
        assert 0 <= act < 3
        assert isinstance(lp, float)
