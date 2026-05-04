"""
Stage 4 - Quick Validation Test (no pytest dependency)
Smoke test to verify Stage 4 Session Watchdog works correctly
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from models.contracts import WatchdogResult, WatchdogAction, Confidence
from models.stage4_watchdog import run
from models.ppo import PPOAgent


def test_stage4_validation():
    print("\n" + "="*70)
    print("STAGE 4: SESSION WATCHDOG (PPO) - VALIDATION TEST")
    print("="*70)
    
    passed = 0
    total = 0
    
    # Test 1: PPO agent initialization
    total += 1
    try:
        ppo = PPOAgent(state_dim=10, action_dim=3)
        assert ppo.state_dim == 10
        assert ppo.action_dim == 3
        print(f"✓ Test 1: PPO agent initialized correctly")
        passed += 1
    except Exception as e:
        print(f"✗ Test 1 FAILED: {e}")
    
    # Test 2: PPO action selection
    total += 1
    try:
        ppo = PPOAgent()
        import numpy as np
        state = np.random.randn(10).astype(np.float32)
        action, log_prob = ppo.select_action(state)
        assert 0 <= action <= 2
        print(f"✓ Test 2: PPO action selection works (action={action})")
        passed += 1
    except Exception as e:
        print(f"✗ Test 2 FAILED: {e}")
    
    # Test 3: Stage 4 run() with healthy session
    total += 1
    try:
        ppo = PPOAgent()
        result = run(
            latent_vector=[0.5] * 32,
            e_rec=0.1,  # healthy
            trust_score=0.9,  # high trust
            ppo_agent=ppo
        )
        assert isinstance(result, WatchdogResult)
        assert result.action in [WatchdogAction.OK, WatchdogAction.PASSIVE_REAUTH]
        print(f"✓ Test 3: Stage 4 healthy session → {result.action.value}")
        passed += 1
    except Exception as e:
        print(f"✗ Test 3 FAILED: {e}")
    
    # Test 4: Stage 4 run() with suspicious session
    total += 1
    try:
        ppo = PPOAgent()
        result = run(
            latent_vector=[],
            e_rec=0.25,  # warning level
            trust_score=0.4,  # warning level
            ppo_agent=ppo
        )
        assert isinstance(result, WatchdogResult)
        assert result.action in [WatchdogAction.PASSIVE_REAUTH, WatchdogAction.DISABLE_SENSITIVE_API]
        print(f"✓ Test 4: Stage 4 suspect session → {result.action.value}")
        passed += 1
    except Exception as e:
        print(f"✗ Test 4 FAILED: {e}")
    
    # Test 5: Stage 4 run() with critical session
    total += 1
    try:
        ppo = PPOAgent()
        result = run(
            latent_vector=[],
            e_rec=0.36,  # critical level (> 0.35)
            trust_score=0.24,  # critical level (< 0.25)
            ppo_agent=ppo
        )
        assert isinstance(result, WatchdogResult)
        assert result.action == WatchdogAction.FORCE_LOGOUT
        print(f"✓ Test 5: Stage 4 critical session → FORCE_LOGOUT")
        passed += 1
    except Exception as e:
        print(f"✗ Test 5 FAILED: {e}")
    
    # Test 6: Stage 4 with None agent (fallback rules)
    total += 1
    try:
        result = run(
            latent_vector=[],
            e_rec=0.2,
            trust_score=0.7,
            ppo_agent=None
        )
        assert isinstance(result, WatchdogResult)
        assert result.confidence == Confidence.HIGH  # fallback rules always HIGH
        print(f"✓ Test 6: Stage 4 fallback rules work (no PPO agent)")
        passed += 1
    except Exception as e:
        print(f"✗ Test 6 FAILED: {e}")
    
    # Test 7: WatchdogResult structure valid
    total += 1
    try:
        result = run([], 0.2, 0.7, ppo_agent=None)
        assert hasattr(result, "action")
        assert hasattr(result, "trust_score")
        assert hasattr(result, "e_rec")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reason")
        print(f"✓ Test 7: WatchdogResult structure valid ✓")
        passed += 1
    except Exception as e:
        print(f"✗ Test 7 FAILED: {e}")
    
    # Final summary
    print("\n" + "="*70)
    print(f"VALIDATION SUMMARY: {passed}/{total} checks passed")
    if passed == total:
        print("✓ ALL STAGE 4 VALIDATION TESTS PASSED ✓")
    else:
        print(f"✗ {total - passed} test(s) failed")
    print("="*70 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = test_stage4_validation()
    sys.exit(0 if success else 1)
