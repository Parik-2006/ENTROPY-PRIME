"""
Quick validation that Stage 1 Biometric Interpreter works
Direct import to avoid torch dependency chain
"""

import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent))

from models.contracts import (
    BiometricInput,
    Confidence,
    HoneypotVerdict,
    BOT_THETA_HARD,
    BOT_THETA_SOFT,
)
from models.stage1_biometric import run

print("✓ Contracts imported")
print("✓ Stage1 Biometric imported")

# Test 1: BOT detection (theta < 0.10)
print("\n=== Test 1: BOT Detection ===")
inp1 = BiometricInput(
    theta=0.05,
    h_exp=0.8,
    server_load=0.3,
    user_agent="Mozilla/5.0",
    latent_vector=[0.1]*32
)
result1 = run(inp1)
print(f"  Result: verdict={result1.verdict}, confidence={result1.confidence}, is_bot={result1.is_bot}")
assert result1.verdict == HoneypotVerdict.BOT, f"Expected BOT, got {result1.verdict}"
assert result1.is_bot is True
# Note: theta=0.05 is < 0.05, so based on stage1 logic it's HIGH, but let's check
print(f"✓ theta={inp1.theta:.2f} → BOT with {result1.confidence.value} confidence")

# Test 2: SUSPECT detection (0.10 < theta < 0.30)
print("\n=== Test 2: SUSPECT Detection ===")
inp2 = BiometricInput(
    theta=0.20,
    h_exp=0.7,
    server_load=0.4,
    user_agent="Mozilla/5.0",
    latent_vector=[0.2]*32
)
result2 = run(inp2)
assert result2.verdict == HoneypotVerdict.SUSPECT, f"Expected SUSPECT, got {result2.verdict}"
assert result2.is_suspect is True
assert result2.confidence == Confidence.LOW  # In contested band
print(f"✓ theta={inp2.theta:.2f} → SUSPECT with LOW confidence")

# Test 3: HUMAN detection (theta > 0.30)
print("\n=== Test 3: HUMAN Detection ===")
inp3 = BiometricInput(
    theta=0.8,
    h_exp=0.2,
    server_load=0.5,
    user_agent="Mozilla/5.0",
    latent_vector=[0.5]*32
)
result3 = run(inp3)
assert result3.verdict == HoneypotVerdict.HUMAN, f"Expected HUMAN, got {result3.verdict}"
assert result3.is_bot is False
assert result3.is_suspect is False
assert result3.confidence == Confidence.HIGH
print(f"✓ theta={inp3.theta:.2f} → HUMAN with HIGH confidence")

# Test 4: Missing latent vector degrades confidence
print("\n=== Test 4: Missing Latent Vector ===")
inp4 = BiometricInput(
    theta=0.05,
    h_exp=0.9,
    server_load=0.2,
    user_agent="Mozilla/5.0",
    latent_vector=None
)
result4 = run(inp4)
assert result4.verdict == HoneypotVerdict.BOT
assert result4.confidence == Confidence.MEDIUM  # Degraded from HIGH
assert "no latent vector" in result4.note
print(f"✓ Missing latent vector degrades confidence: HIGH → MEDIUM")

# Test 5: Server load annotation
print("\n=== Test 5: Server Load Annotation ===")
inp5 = BiometricInput(
    theta=0.5,
    h_exp=0.5,
    server_load=0.90,
    user_agent="Mozilla/5.0",
    latent_vector=[0.5]*32
)
result5 = run(inp5)
assert "server_load=0.90" in result5.note
print(f"✓ High server load (0.90) noted in result")

print("\n" + "="*60)
print("✅ ALL STAGE 1 TESTS PASSED")
print("="*60)
print(f"\nThreshold Summary:")
print(f"  BOT_THETA_HARD: {BOT_THETA_HARD}")
print(f"  BOT_THETA_SOFT: {BOT_THETA_SOFT}")
print(f"  Zones:")
print(f"    - BOT: [0.00, {BOT_THETA_HARD:.2f}]")
print(f"    - SUSPECT: ({BOT_THETA_HARD:.2f}, {BOT_THETA_SOFT:.2f}]")
print(f"    - HUMAN: ({BOT_THETA_SOFT:.2f}, 1.00]")
