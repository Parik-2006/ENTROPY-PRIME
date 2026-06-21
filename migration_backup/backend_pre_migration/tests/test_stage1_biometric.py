"""
Unit tests for Stage 1: Biometric Interpreter
Tests pure logic classification with edge cases
"""

import sys
from pathlib import Path

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from models.contracts import (
    BiometricInput,
    BiometricResult,
    Confidence,
    HoneypotVerdict,
    BOT_THETA_HARD,
    BOT_THETA_SOFT,
)
from models.stage1_biometric import run


class TestBiometricInterpreterVerdicts:
    """Test verdict classification based on theta thresholds"""

    def test_clear_bot_detection(self):
        """Test theta << BOT_THETA_HARD → BOT verdict"""
        inp = BiometricInput(
            theta=0.02,  # < 0.05, so HIGH confidence
            h_exp=0.8,
            server_load=0.3,
            user_agent="Mozilla/5.0",
            latent_vector=[0.1] * 32,
        )
        result = run(inp)
        
        assert result.verdict == HoneypotVerdict.BOT
        assert result.is_bot is True
        assert result.is_suspect is False
        assert result.confidence == Confidence.HIGH

    def test_bot_boundary(self):
        """Test theta at BOT_THETA_HARD boundary (exclusive)"""
        inp = BiometricInput(
            theta=0.09,  # < 0.10, so still BOT
            h_exp=0.8,
            server_load=0.3,
            user_agent="Mozilla/5.0",
            latent_vector=[0.1] * 32,
        )
        result = run(inp)
        
        # At 0.09, still BOT (boundary is exclusive)
        assert result.verdict == HoneypotVerdict.BOT
        assert result.is_bot is True

    def test_suspect_detection(self):
        """Test BOT_THETA_HARD < theta < BOT_THETA_SOFT → SUSPECT"""
        inp = BiometricInput(
            theta=0.20,  # Between 0.10 and 0.30
            h_exp=0.7,
            server_load=0.4,
            user_agent="Mozilla/5.0",
            latent_vector=[0.2] * 32,
        )
        result = run(inp)
        
        assert result.verdict == HoneypotVerdict.SUSPECT
        assert result.is_bot is False
        assert result.is_suspect is True

    def test_human_detection(self):
        """Test theta >> BOT_THETA_SOFT → HUMAN"""
        inp = BiometricInput(
            theta=0.8,
            h_exp=0.2,
            server_load=0.5,
            user_agent="Mozilla/5.0",
            latent_vector=[0.5] * 32,
        )
        result = run(inp)
        
        assert result.verdict == HoneypotVerdict.HUMAN
        assert result.is_bot is False
        assert result.is_suspect is False
        assert result.confidence == Confidence.HIGH

    def test_human_boundary(self):
        """Test theta just above BOT_THETA_SOFT"""
        inp = BiometricInput(
            theta=BOT_THETA_SOFT + 0.01,
            h_exp=0.3,
            server_load=0.5,
            user_agent="Mozilla/5.0",
            latent_vector=[0.3] * 32,
        )
        result = run(inp)
        
        assert result.verdict == HoneypotVerdict.HUMAN
        assert result.is_bot is False


class TestConfidenceAssignment:
    """Test confidence level assignment based on theta position"""

    def test_high_confidence_bot_clear(self):
        """Test HIGH confidence for theta << BOT_THETA_HARD"""
        inp = BiometricInput(
            theta=0.02,
            h_exp=0.9,
            server_load=0.2,
            user_agent="Mozilla/5.0",
            latent_vector=[0.1] * 32,
        )
        result = run(inp)
        
        assert result.confidence == Confidence.HIGH
        assert result.verdict == HoneypotVerdict.BOT

    def test_high_confidence_human_clear(self):
        """Test HIGH confidence for theta > 0.60"""
        inp = BiometricInput(
            theta=0.75,
            h_exp=0.1,
            server_load=0.6,
            user_agent="Mozilla/5.0",
            latent_vector=[0.7] * 32,
        )
        result = run(inp)
        
        assert result.confidence == Confidence.HIGH
        assert result.verdict == HoneypotVerdict.HUMAN

    def test_medium_confidence_near_bot_boundary(self):
        """Test MEDIUM confidence for theta in [0.05, 0.15)"""
        inp = BiometricInput(
            theta=0.12,
            h_exp=0.7,
            server_load=0.3,
            user_agent="Mozilla/5.0",
            latent_vector=[0.1] * 32,
        )
        result = run(inp)
        
        assert result.confidence == Confidence.MEDIUM

    def test_medium_confidence_near_human_boundary(self):
        """Test MEDIUM confidence for theta in [0.50, 0.60)"""
        inp = BiometricInput(
            theta=0.55,
            h_exp=0.4,
            server_load=0.5,
            user_agent="Mozilla/5.0",
            latent_vector=[0.5] * 32,
        )
        result = run(inp)
        
        assert result.confidence == Confidence.MEDIUM

    def test_low_confidence_contested_band(self):
        """Test LOW confidence for theta in [0.15, 0.50)"""
        inp = BiometricInput(
            theta=0.25,  # In range [0.15, 0.50), so LOW confidence
            h_exp=0.6,
            server_load=0.5,
            user_agent="Mozilla/5.0",
            latent_vector=[0.3] * 32,
        )
        result = run(inp)
        
        assert result.confidence == Confidence.LOW
        assert result.verdict == HoneypotVerdict.SUSPECT

    def test_low_confidence_middle_range(self):
        """Test LOW confidence for theta around 0.40"""
        inp = BiometricInput(
            theta=0.40,
            h_exp=0.5,
            server_load=0.5,
            user_agent="Mozilla/5.0",
            latent_vector=[0.4] * 32,
        )
        result = run(inp)
        
        assert result.confidence == Confidence.LOW


class TestLatentVectorHandling:
    """Test handling of missing latent vector"""

    def test_missing_latent_vector_degrades_confidence(self):
        """Test HIGH→MEDIUM confidence when latent vector missing"""
        inp = BiometricInput(
            theta=0.02,  # Would be HIGH confidence normally
            h_exp=0.9,
            server_load=0.2,
            user_agent="Mozilla/5.0",
            latent_vector=None,  # Missing
        )
        result = run(inp)
        
        # Confidence degraded from HIGH to MEDIUM due to missing latent
        assert result.confidence == Confidence.MEDIUM
        assert result.verdict == HoneypotVerdict.BOT

    def test_missing_latent_vector_noted(self):
        """Test that missing latent vector is noted in result"""
        inp = BiometricInput(
            theta=0.05,
            h_exp=0.8,
            server_load=0.3,
            user_agent="Mozilla/5.0",
            latent_vector=None,
        )
        result = run(inp)
        
        assert "no latent vector" in result.note

    def test_wrong_latent_vector_size(self):
        """Test latent vector with wrong size treated as missing"""
        inp = BiometricInput(
            theta=0.05,
            h_exp=0.8,
            server_load=0.3,
            user_agent="Mozilla/5.0",
            latent_vector=[0.1] * 16,  # Should be 32
        )
        result = run(inp)
        
        # Should degrade confidence like missing vector
        assert result.confidence == Confidence.MEDIUM


class TestServerLoadAnnotation:
    """Test server load impact on notes"""

    def test_high_server_load_noted(self):
        """Test server_load > 0.85 triggers note"""
        inp = BiometricInput(
            theta=0.5,
            h_exp=0.5,
            server_load=0.90,
            user_agent="Mozilla/5.0",
            latent_vector=[0.5] * 32,
        )
        result = run(inp)
        
        assert "server_load=0.90" in result.note

    def test_normal_server_load_not_noted(self):
        """Test server_load ≤ 0.85 not noted"""
        inp = BiometricInput(
            theta=0.5,
            h_exp=0.5,
            server_load=0.80,
            user_agent="Mozilla/5.0",
            latent_vector=[0.5] * 32,
        )
        result = run(inp)
        
        assert "server_load" not in result.note


class TestEdgeCases:
    """Test boundary and edge case scenarios"""

    def test_theta_exactly_zero(self):
        """Test theta = 0 (impossible but should handle gracefully)"""
        inp = BiometricInput(
            theta=0.0,
            h_exp=0.9,
            server_load=0.2,
            user_agent="Mozilla/5.0",
            latent_vector=[0.0] * 32,
        )
        result = run(inp)
        
        assert result.verdict == HoneypotVerdict.BOT
        assert result.confidence == Confidence.HIGH

    def test_theta_exactly_one(self):
        """Test theta = 1.0 (perfect human confidence)"""
        inp = BiometricInput(
            theta=1.0,
            h_exp=0.0,
            server_load=1.0,
            user_agent="Mozilla/5.0",
            latent_vector=[1.0] * 32,
        )
        result = run(inp)
        
        assert result.verdict == HoneypotVerdict.HUMAN
        assert result.confidence == Confidence.HIGH

    def test_input_data_preservation(self):
        """Test all input data preserved in BiometricResult"""
        inp = BiometricInput(
            theta=0.42,
            h_exp=0.88,
            server_load=0.67,
            user_agent="Mozilla/5.0",
            latent_vector=[0.5] * 32,
        )
        result = run(inp)
        
        assert result.theta == 0.42
        assert result.h_exp == 0.88
        assert result.server_load == 0.67


class TestThresholdConsistency:
    """Test consistency with contract thresholds"""

    def test_bot_theta_hard_constant(self):
        """Verify BOT_THETA_HARD value"""
        assert BOT_THETA_HARD == 0.10

    def test_bot_theta_soft_constant(self):
        """Verify BOT_THETA_SOFT value"""
        assert BOT_THETA_SOFT == 0.30

    def test_threshold_ordering(self):
        """Verify thresholds are properly ordered"""
        assert BOT_THETA_HARD < BOT_THETA_SOFT
