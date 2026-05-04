"""
Unit tests for Stage 2: Honeypot Classifier (MAB)
Tests routing logic, MAB arm selection, and synthetic token generation
"""

import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from models.contracts import (
    BiometricInput,
    BiometricResult,
    HoneypotResult,
    Confidence,
    HoneypotVerdict,
    BOT_THETA_HARD,
    BOT_THETA_SOFT,
)
from models.stage2_honeypot import (
    run,
    update_mab_reward,
    _routing_decision,
    _select_arm,
    _make_synthetic_token,
    DECEPTION_ARMS,
)
from models.mab import MABAgent


class TestRoutingDecision:
    """Test the routing logic (should_shadow decision)"""

    def test_bot_high_confidence_shadows(self):
        """Test: BOT with HIGH confidence → always shadow"""
        bio = BiometricResult(
            theta=0.05,
            h_exp=0.8,
            server_load=0.3,
            verdict=HoneypotVerdict.BOT,
            confidence=Confidence.HIGH,
            is_bot=True,
            is_suspect=False,
        )
        assert _routing_decision(bio) is True

    def test_bot_medium_confidence_shadows(self):
        """Test: BOT with MEDIUM confidence → shadow"""
        bio = BiometricResult(
            theta=0.08,
            h_exp=0.8,
            server_load=0.3,
            verdict=HoneypotVerdict.BOT,
            confidence=Confidence.MEDIUM,
            is_bot=True,
            is_suspect=False,
        )
        assert _routing_decision(bio) is True

    def test_bot_low_confidence_shadows(self):
        """Test: BOT with LOW confidence → still shadow"""
        bio = BiometricResult(
            theta=0.09,
            h_exp=0.8,
            server_load=0.3,
            verdict=HoneypotVerdict.BOT,
            confidence=Confidence.LOW,
            is_bot=True,
            is_suspect=False,
        )
        assert _routing_decision(bio) is True

    def test_suspect_high_confidence_shadows(self):
        """Test: SUSPECT with HIGH confidence → shadow"""
        bio = BiometricResult(
            theta=0.15,
            h_exp=0.7,
            server_load=0.4,
            verdict=HoneypotVerdict.SUSPECT,
            confidence=Confidence.HIGH,
            is_bot=False,
            is_suspect=True,
        )
        assert _routing_decision(bio) is True

    def test_suspect_medium_confidence_passes(self):
        """Test: SUSPECT with MEDIUM confidence → pass through"""
        bio = BiometricResult(
            theta=0.20,
            h_exp=0.7,
            server_load=0.4,
            verdict=HoneypotVerdict.SUSPECT,
            confidence=Confidence.MEDIUM,
            is_bot=False,
            is_suspect=True,
        )
        assert _routing_decision(bio) is False

    def test_suspect_low_confidence_passes(self):
        """Test: SUSPECT with LOW confidence → pass through (benefit of doubt)"""
        bio = BiometricResult(
            theta=0.25,
            h_exp=0.7,
            server_load=0.4,
            verdict=HoneypotVerdict.SUSPECT,
            confidence=Confidence.LOW,
            is_bot=False,
            is_suspect=True,
        )
        assert _routing_decision(bio) is False

    def test_human_never_shadows(self):
        """Test: HUMAN verdict → never shadow"""
        bio = BiometricResult(
            theta=0.8,
            h_exp=0.2,
            server_load=0.5,
            verdict=HoneypotVerdict.HUMAN,
            confidence=Confidence.HIGH,
            is_bot=False,
            is_suspect=False,
        )
        assert _routing_decision(bio) is False


class TestMABArmSelection:
    """Test MAB arm selection and confidence mapping"""

    def test_select_arm_no_agent_returns_default(self):
        """Test: mab_agent=None → arm 0 with LOW confidence"""
        arm, conf = _select_arm(None)
        assert arm == 0
        assert conf == Confidence.LOW

    def test_select_arm_from_agent(self):
        """Test: Agent returns valid arm (0-2)"""
        agent = MABAgent(n_arms=3, epsilon=0.0)
        arm, conf = _select_arm(agent)
        assert 0 <= arm < 3
        assert conf == Confidence.LOW  # counts[arm] starts at 0

    def test_arm_confidence_low_under_10_samples(self):
        """Test: arm with < 10 samples → LOW confidence"""
        agent = MABAgent(n_arms=3, epsilon=0.0)
        # Update arm 0 with 5 samples
        for i in range(5):
            agent.update(0, 0.5)
        arm, conf = _select_arm(agent)
        assert conf == Confidence.LOW

    def test_arm_confidence_medium_10_to_49_samples(self):
        """Test: arm with 10-49 samples → MEDIUM confidence"""
        agent = MABAgent(n_arms=3, epsilon=0.0)
        # Update arm 0 with 25 samples
        for i in range(25):
            agent.update(0, 0.5)
        arm, conf = _select_arm(agent)
        assert conf == Confidence.MEDIUM

    def test_arm_confidence_high_50_plus_samples(self):
        """Test: arm with ≥ 50 samples → HIGH confidence"""
        agent = MABAgent(n_arms=3, epsilon=0.0)
        # Update arm 0 with 50 samples
        for i in range(50):
            agent.update(0, 0.5)
        arm, conf = _select_arm(agent)
        assert conf == Confidence.HIGH

    def test_epsilon_greedy_exploration(self):
        """Test: epsilon-greedy occasionally explores"""
        agent = MABAgent(n_arms=3, epsilon=1.0)  # Always explore
        arms_selected = set()
        for _ in range(30):
            arm, _ = _select_arm(agent)
            arms_selected.add(arm)
        # With epsilon=1.0, should see all 3 arms over time
        assert len(arms_selected) >= 2


class TestSyntheticTokenGeneration:
    """Test synthetic token creation"""

    def test_token_format(self):
        """Test: Token has correct format"""
        token = _make_synthetic_token("secret", "192.168.1.1", 0)
        assert token.startswith("ep_shadow_")
        assert "." in token

    def test_token_includes_hmac(self):
        """Test: Token contains HMAC signature"""
        token = _make_synthetic_token("secret", "192.168.1.1", 0)
        parts = token.split(".")
        assert len(parts) == 2
        signature = parts[1]
        assert len(signature) == 16  # First 16 chars of SHA256 hex

    def test_different_secrets_different_tokens(self):
        """Test: Different secrets produce different tokens"""
        token1 = _make_synthetic_token("secret1", "192.168.1.1", 0)
        token2 = _make_synthetic_token("secret2", "192.168.1.1", 0)
        # May rarely collide, but highly unlikely with different secrets
        assert token1 != token2

    def test_different_arms_different_tokens(self):
        """Test: Different arms produce different tokens"""
        token0 = _make_synthetic_token("secret", "192.168.1.1", 0)
        token1 = _make_synthetic_token("secret", "192.168.1.1", 1)
        token2 = _make_synthetic_token("secret", "192.168.1.1", 2)
        # All should be different
        assert token0 != token1
        assert token1 != token2
        assert token0 != token2

    def test_different_ips_different_tokens(self):
        """Test: Different IPs produce different tokens"""
        token1 = _make_synthetic_token("secret", "192.168.1.1", 0)
        token2 = _make_synthetic_token("secret", "192.168.1.2", 0)
        assert token1 != token2


class TestHoneypotRunBOT:
    """Test Stage 2 run() function with BOT input"""

    def test_bot_should_shadow_true(self):
        """Test: BOT input → should_shadow=True"""
        bio = BiometricResult(
            theta=0.05,
            h_exp=0.8,
            server_load=0.3,
            verdict=HoneypotVerdict.BOT,
            confidence=Confidence.HIGH,
            is_bot=True,
            is_suspect=False,
        )
        result = run(bio, mab_agent=None, shadow_secret="test_secret", ip_address="127.0.0.1")
        
        assert result.should_shadow is True
        assert result.synthetic_token is not None

    def test_bot_preserves_verdict(self):
        """Test: BOT verdict preserved in output"""
        bio = BiometricResult(
            theta=0.05,
            h_exp=0.8,
            server_load=0.3,
            verdict=HoneypotVerdict.BOT,
            confidence=Confidence.HIGH,
            is_bot=True,
            is_suspect=False,
        )
        result = run(bio, mab_agent=None, shadow_secret="test_secret", ip_address="127.0.0.1")
        
        assert result.verdict == HoneypotVerdict.BOT
        assert result.confidence == Confidence.HIGH

    def test_bot_with_mab_agent(self):
        """Test: BOT with MAB agent selects valid arm"""
        bio = BiometricResult(
            theta=0.05,
            h_exp=0.8,
            server_load=0.3,
            verdict=HoneypotVerdict.BOT,
            confidence=Confidence.HIGH,
            is_bot=True,
            is_suspect=False,
        )
        agent = MABAgent(n_arms=3, epsilon=0.0)
        result = run(bio, mab_agent=agent, shadow_secret="test_secret", ip_address="127.0.0.1")
        
        assert 0 <= result.mab_arm_selected < 3
        assert result.mab_confidence in [Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH]


class TestHoneypotRunSUSPECT:
    """Test Stage 2 run() function with SUSPECT input"""

    def test_suspect_high_conf_shadows(self):
        """Test: SUSPECT HIGH → should_shadow=True"""
        bio = BiometricResult(
            theta=0.15,
            h_exp=0.7,
            server_load=0.4,
            verdict=HoneypotVerdict.SUSPECT,
            confidence=Confidence.HIGH,
            is_bot=False,
            is_suspect=True,
        )
        result = run(bio, mab_agent=None, shadow_secret="test_secret", ip_address="127.0.0.1")
        
        assert result.should_shadow is True

    def test_suspect_medium_conf_passes(self):
        """Test: SUSPECT MEDIUM → should_shadow=False"""
        bio = BiometricResult(
            theta=0.20,
            h_exp=0.7,
            server_load=0.4,
            verdict=HoneypotVerdict.SUSPECT,
            confidence=Confidence.MEDIUM,
            is_bot=False,
            is_suspect=True,
        )
        result = run(bio, mab_agent=None, shadow_secret="test_secret", ip_address="127.0.0.1")
        
        assert result.should_shadow is False
        assert result.synthetic_token is None

    def test_suspect_medium_mab_arm_is_negative(self):
        """Test: SUSPECT MEDIUM (no shadow) → mab_arm_selected=-1"""
        bio = BiometricResult(
            theta=0.20,
            h_exp=0.7,
            server_load=0.4,
            verdict=HoneypotVerdict.SUSPECT,
            confidence=Confidence.MEDIUM,
            is_bot=False,
            is_suspect=True,
        )
        result = run(bio, mab_agent=None, shadow_secret="test_secret", ip_address="127.0.0.1")
        
        assert result.mab_arm_selected == -1


class TestHoneypotRunHUMAN:
    """Test Stage 2 run() function with HUMAN input"""

    def test_human_never_shadows(self):
        """Test: HUMAN verdict → should_shadow=False"""
        bio = BiometricResult(
            theta=0.8,
            h_exp=0.2,
            server_load=0.5,
            verdict=HoneypotVerdict.HUMAN,
            confidence=Confidence.HIGH,
            is_bot=False,
            is_suspect=False,
        )
        result = run(bio, mab_agent=None, shadow_secret="test_secret", ip_address="127.0.0.1")
        
        assert result.should_shadow is False
        assert result.synthetic_token is None
        assert result.mab_arm_selected == -1


class TestMABRewardUpdate:
    """Test update_mab_reward() function"""

    def test_update_none_agent_safe(self):
        """Test: update_mab_reward with None agent is safe (no-op)"""
        # Should not raise
        update_mab_reward(None, 0, 1.0)

    def test_update_negative_arm_safe(self):
        """Test: update_mab_reward with negative arm is safe (no-op)"""
        agent = MABAgent(n_arms=3)
        # Should not raise
        update_mab_reward(agent, -1, 1.0)

    def test_update_valid_arm_updates_counts(self):
        """Test: Valid arm/reward updates MAB state"""
        agent = MABAgent(n_arms=3)
        assert agent.counts[0] == 0
        
        update_mab_reward(agent, 0, 1.0)
        assert agent.counts[0] == 1
        
        update_mab_reward(agent, 0, 0.5)
        assert agent.counts[0] == 2

    def test_update_positive_reward_increases_value(self):
        """Test: Positive reward increases arm value estimate"""
        agent = MABAgent(n_arms=3)
        initial_value = agent.values[0]
        
        update_mab_reward(agent, 0, 1.0)
        assert agent.values[0] > initial_value

    def test_update_negative_reward_decreases_value(self):
        """Test: Negative reward decreases arm value estimate"""
        agent = MABAgent(n_arms=3)
        # Warm up with positive rewards
        for _ in range(5):
            update_mab_reward(agent, 0, 1.0)
        warm_value = agent.values[0]
        
        # Then negative reward
        update_mab_reward(agent, 0, -1.0)
        assert agent.values[0] < warm_value


class TestMABIntegration:
    """Test MAB learning over multiple rounds"""

    def test_mab_learns_better_arm(self):
        """Test: MAB learns to prefer higher-reward arm"""
        agent = MABAgent(n_arms=3, epsilon=0.0)  # Pure exploitation
        
        # Arm 0 gets good rewards
        for _ in range(10):
            update_mab_reward(agent, 0, 1.0)
        
        # Arm 1 gets poor rewards
        for _ in range(10):
            update_mab_reward(agent, 1, -0.5)
        
        # Arm 2 gets medium rewards
        for _ in range(10):
            update_mab_reward(agent, 2, 0.0)
        
        # With epsilon=0, should exploit arm 0 (highest value)
        selected_arm, _ = _select_arm(agent)
        assert selected_arm == 0, f"Expected arm 0 (best), got {selected_arm}"

    def test_mab_state_persistence(self):
        """Test: MAB state can be saved and loaded"""
        agent1 = MABAgent(n_arms=3)
        for _ in range(20):
            update_mab_reward(agent1, 0, 1.0)
        
        state = agent1.state_dict()
        
        agent2 = MABAgent()
        agent2.load_state_dict(state)
        
        assert agent2.counts[0] == 20
        assert agent2.values[0] == agent1.values[0]


class TestDeceptionArms:
    """Test deception arm definitions"""

    def test_deception_arms_defined(self):
        """Test: DECEPTION_ARMS has correct structure"""
        assert len(DECEPTION_ARMS) == 3
        assert isinstance(DECEPTION_ARMS, list)
        assert all(isinstance(arm, str) for arm in DECEPTION_ARMS)

    def test_deception_arms_coverage(self):
        """Test: Arms cover main strategies"""
        arm_names = DECEPTION_ARMS
        assert "fake_data_feed" in arm_names
        assert "slow_drip" in arm_names
        assert "canary_token_inject" in arm_names
