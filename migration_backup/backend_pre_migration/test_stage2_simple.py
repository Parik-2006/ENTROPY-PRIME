"""
Quick validation for Stage 2: Honeypot Classifier
Direct import to test without pytest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from models.contracts import (
    BiometricResult,
    Confidence,
    HoneypotVerdict,
)
from models.stage2_honeypot import run, update_mab_reward
from models.mab import MABAgent

print("✓ Stage 2 Honeypot imports successful")

# Test 1: BOT detection routes to honeypot
print("\n=== Test 1: BOT Detection → Shadow ===")
bio_bot = BiometricResult(
    theta=0.05,
    h_exp=0.8,
    server_load=0.3,
    verdict=HoneypotVerdict.BOT,
    confidence=Confidence.HIGH,
    is_bot=True,
    is_suspect=False,
)
result_bot = run(bio_bot, mab_agent=None, shadow_secret="test_secret", ip_address="127.0.0.1")
assert result_bot.should_shadow is True, "BOT should be shadowed"
assert result_bot.synthetic_token is not None, "Token should be generated"
print(f"✓ BOT → should_shadow={result_bot.should_shadow}")
print(f"✓ Token generated: {result_bot.synthetic_token[:30]}...")

# Test 2: HUMAN passes through (no shadow)
print("\n=== Test 2: HUMAN Detection → No Shadow ===")
bio_human = BiometricResult(
    theta=0.8,
    h_exp=0.2,
    server_load=0.5,
    verdict=HoneypotVerdict.HUMAN,
    confidence=Confidence.HIGH,
    is_bot=False,
    is_suspect=False,
)
result_human = run(bio_human, mab_agent=None, shadow_secret="test_secret", ip_address="127.0.0.1")
assert result_human.should_shadow is False, "HUMAN should not be shadowed"
assert result_human.synthetic_token is None, "No token for HUMAN"
print(f"✓ HUMAN → should_shadow={result_human.should_shadow}")

# Test 3: SUSPECT HIGH confidence shadows
print("\n=== Test 3: SUSPECT HIGH Confidence → Shadow ===")
bio_suspect_high = BiometricResult(
    theta=0.15,
    h_exp=0.7,
    server_load=0.4,
    verdict=HoneypotVerdict.SUSPECT,
    confidence=Confidence.HIGH,
    is_bot=False,
    is_suspect=True,
)
result_suspect_high = run(bio_suspect_high, mab_agent=None, shadow_secret="test_secret", ip_address="127.0.0.1")
assert result_suspect_high.should_shadow is True, "HIGH confidence SUSPECT should shadow"
print(f"✓ SUSPECT HIGH → should_shadow={result_suspect_high.should_shadow}")

# Test 4: SUSPECT MEDIUM confidence passes (benefit of doubt)
print("\n=== Test 4: SUSPECT MEDIUM Confidence → Pass (Benefit of Doubt) ===")
bio_suspect_med = BiometricResult(
    theta=0.20,
    h_exp=0.7,
    server_load=0.4,
    verdict=HoneypotVerdict.SUSPECT,
    confidence=Confidence.MEDIUM,
    is_bot=False,
    is_suspect=True,
)
result_suspect_med = run(bio_suspect_med, mab_agent=None, shadow_secret="test_secret", ip_address="127.0.0.1")
assert result_suspect_med.should_shadow is False, "MEDIUM confidence SUSPECT should pass"
print(f"✓ SUSPECT MEDIUM → should_shadow={result_suspect_med.should_shadow}")

# Test 5: MAB arm selection with agent
print("\n=== Test 5: MAB Arm Selection ===")
agent = MABAgent(n_arms=3, epsilon=0.1)
bio_for_mab = BiometricResult(
    theta=0.05,
    h_exp=0.8,
    server_load=0.3,
    verdict=HoneypotVerdict.BOT,
    confidence=Confidence.HIGH,
    is_bot=True,
    is_suspect=False,
)
result_with_mab = run(bio_for_mab, mab_agent=agent, shadow_secret="test_secret", ip_address="127.0.0.1")
assert 0 <= result_with_mab.mab_arm_selected < 3, "MAB should select valid arm (0-2)"
print(f"✓ MAB selected arm: {result_with_mab.mab_arm_selected}")
print(f"✓ MAB confidence: {result_with_mab.mab_confidence.value}")

# Test 6: MAB learning (reward update)
print("\n=== Test 6: MAB Learning (Reward Update) ===")
agent2 = MABAgent(n_arms=3, epsilon=0.0)  # Pure exploitation
# Arm 0 gets positive rewards (deception strategy works well)
for _ in range(10):
    update_mab_reward(agent2, 0, 1.0)

# Arm 1 gets negative rewards (bot escaped)
for _ in range(10):
    update_mab_reward(agent2, 1, -0.5)

# Check that arm 0 has better value than arm 1
assert agent2.values[0] > agent2.values[1], "Arm 0 should learn better than arm 1"
print(f"✓ Arm 0 value: {agent2.values[0]:.4f} (10 positive rewards)")
print(f"✓ Arm 1 value: {agent2.values[1]:.4f} (10 negative rewards)")
print(f"✓ MAB learning working: arm with better rewards has higher value")

# Test 7: Routing policy summary
print("\n=== Routing Policy Summary ===")
policies = {
    "BOT (HIGH conf)": "SHADOW",
    "BOT (MEDIUM conf)": "SHADOW",
    "BOT (LOW conf)": "SHADOW",
    "SUSPECT (HIGH conf)": "SHADOW",
    "SUSPECT (MEDIUM conf)": "PASS (benefit of doubt)",
    "SUSPECT (LOW conf)": "PASS (benefit of doubt)",
    "HUMAN": "PASS",
}
for verdict_type, policy in policies.items():
    print(f"  • {verdict_type:<25} → {policy}")

print("\n" + "="*60)
print("✅ ALL STAGE 2 VALIDATION TESTS PASSED")
print("="*60)
print(f"\nDeception Strategies Available: 3 arms")
print(f"  • Arm 0: fake_data_feed")
print(f"  • Arm 1: slow_drip")
print(f"  • Arm 2: canary_token_inject")
print(f"\nMAB Algorithm: epsilon-greedy")
print(f"  • Exploration rate: configurable epsilon")
print(f"  • Exploitation: greedy selection of best arm")
print(f"  • Learning: incremental mean reward estimation")
