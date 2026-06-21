"""
Stage 3 - Quick Validation Test (no pytest dependency)
Smoke test to verify Stage 3 DQN Governor works correctly
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from models.contracts import (
    BiometricResult, Confidence, HoneypotVerdict, SecurityPreset
)
from models.stage3_governor import run
from models.dqn import DQNAgent
import numpy as np


def test_stage3_validation():
    print("\n" + "="*70)
    print("STAGE 3: RESOURCE GOVERNOR (DQN) - VALIDATION TEST")
    print("="*70)
    
    passed = 0
    total = 0
    
    # Test 1: Basic DQN agent initialization
    total += 1
    try:
        dqn = DQNAgent()
        assert dqn.action_dim == 4
        assert dqn.state_dim == 3
        print(f"✓ Test 1: DQN agent initialized correctly")
        passed += 1
    except Exception as e:
        print(f"✗ Test 1 FAILED: {e}")
    
    # Test 2: DQN action selection
    total += 1
    try:
        dqn = DQNAgent()
        state = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        action = dqn.select_action(state)
        assert 0 <= action <= 3
        print(f"✓ Test 2: DQN action selection works (action={action})")
        passed += 1
    except Exception as e:
        print(f"✗ Test 2 FAILED: {e}")
    
    # Test 3: DQN Q-values computation
    total += 1
    try:
        dqn = DQNAgent()
        state = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        q_vals = dqn.q_values(state)
        assert q_vals.shape == (4,)
        assert isinstance(q_vals, np.ndarray)
        print(f"✓ Test 3: DQN Q-values computation works (shape={q_vals.shape})")
        passed += 1
    except Exception as e:
        print(f"✗ Test 3 FAILED: {e}")
    
    # Test 4: Stage 3 run() with BOT input
    total += 1
    try:
        dqn = DQNAgent()
        bio = BiometricResult(
            theta=0.05, h_exp=0.5, server_load=0.5,
            verdict=HoneypotVerdict.BOT, confidence=Confidence.HIGH,
            is_bot=True, is_suspect=False
        )
        result = run(bio, dqn_agent=dqn)
        assert result.action == 2  # HARD for confirmed bot
        assert result.preset == SecurityPreset.HARD
        print(f"✓ Test 4: Stage 3 BOT routing → HARD preset ✓")
        passed += 1
    except Exception as e:
        print(f"✗ Test 4 FAILED: {e}")
    
    # Test 5: Stage 3 run() with HUMAN input
    total += 1
    try:
        dqn = DQNAgent()
        bio = BiometricResult(
            theta=0.9, h_exp=0.8, server_load=0.3,
            verdict=HoneypotVerdict.HUMAN, confidence=Confidence.HIGH,
            is_bot=False, is_suspect=False
        )
        result = run(bio, dqn_agent=dqn)
        assert 0 <= result.action <= 3
        assert isinstance(result.preset, SecurityPreset)
        print(f"✓ Test 5: Stage 3 HUMAN routing → DQN selected (action={result.action})")
        passed += 1
    except Exception as e:
        print(f"✗ Test 5 FAILED: {e}")
    
    # Test 6: Server overload cap
    total += 1
    try:
        dqn = DQNAgent()
        bio = BiometricResult(
            theta=0.9, h_exp=0.9, server_load=0.9,  # server overloaded
            verdict=HoneypotVerdict.HUMAN, confidence=Confidence.HIGH,
            is_bot=False, is_suspect=False
        )
        result = run(bio, dqn_agent=dqn)
        assert result.action <= 1  # capped at STANDARD
        print(f"✓ Test 6: Server overload caps preset to STANDARD ✓")
        passed += 1
    except Exception as e:
        print(f"✗ Test 6 FAILED: {e}")
    
    # Test 7: DQN training
    total += 1
    try:
        dqn = DQNAgent()
        state = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        action = 0
        reward = 1.0
        next_state = np.array([0.6, 0.6, 0.6], dtype=np.float32)
        loss = dqn.train_step(state, action, reward, next_state, done=False)
        assert isinstance(loss, float)
        assert loss >= 0
        print(f"✓ Test 7: DQN training step works (loss={loss:.4f})")
        passed += 1
    except Exception as e:
        print(f"✗ Test 7 FAILED: {e}")
    
    # Final summary
    print("\n" + "="*70)
    print(f"VALIDATION SUMMARY: {passed}/{total} checks passed")
    if passed == total:
        print("✓ ALL STAGE 3 VALIDATION TESTS PASSED ✓")
    else:
        print(f"✗ {total - passed} test(s) failed")
    print("="*70 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = test_stage3_validation()
    sys.exit(0 if success else 1)
