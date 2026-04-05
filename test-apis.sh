#!/bin/bash
# API Test Script for Entropy Prime

BASE_URL="http://localhost:8000"

echo "🧪 Testing Entropy Prime APIs"
echo "===================================="
echo ""

# Test 1: Health Check
echo "1️⃣  Health Check..."
curl -s "$BASE_URL/health" | jq .
echo ""

# Test 2: Get Models Status
echo "2️⃣  Models Status..."
curl -s "$BASE_URL/admin/models-status" | jq .models
echo ""

# Test 3: Register User
echo "3️⃣  Register User..."
REGISTER=$(curl -s -X POST "$BASE_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","plain_password":"TestPass123!"}')
echo "$REGISTER" | jq .
USER_ID=$(echo "$REGISTER" | jq -r '.user_id // empty')
SESSION_TOKEN=$(echo "$REGISTER" | jq -r '.session_token // empty')
echo ""

# Test 4: Extract CNN Biometric Features
echo "4️⃣  Extract CNN Features..."
curl -s -X POST "$BASE_URL/biometric/extract" \
  -H "Content-Type: application/json" \
  -d '{"raw_signal":[0.1,0.2,0.15,0.3,0.25,0.18,0.22,0.19,0.21,0.23]}' | jq .
echo ""

# Test 5: DQN Action
echo "5️⃣  DQN Action..."
curl -s -X POST "$BASE_URL/models/dqn/action" \
  -H "Content-Type: application/json" \
  -d '{"state":[0.85,0.70,0.45]}' | jq .
echo ""

# Test 6: Score Biometric
echo "6️⃣  Score Biometric..."
curl -s -X POST "$BASE_URL/score" \
  -H "Content-Type: application/json" \
  -d '{"theta":0.85,"h_exp":0.70,"server_load":0.45}' | jq .
echo ""

# Test 7: MAB Select Arm
echo "7️⃣  MAB Select Arm..."
curl -s -X POST "$BASE_URL/models/mab/select" | jq .
echo ""

# Test 8: MAB Update
echo "8️⃣  MAB Update..."
curl -s -X POST "$BASE_URL/models/mab/update?arm=1&reward=0.95" | jq .
echo ""

# Test 9: PPO Evaluate
echo "9️⃣  PPO Evaluate..."
curl -s -X POST "$BASE_URL/models/ppo/evaluate" \
  -H "Content-Type: application/json" \
  -d '{"state":[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0]}' | jq .
echo ""

# Test 10: Get Honeypot Signatures
echo "🔟 Honeypot Signatures..."
curl -s "$BASE_URL/honeypot/signatures" | jq '.count'
echo ""

# Test 11: Honeypot Dashboard
echo "1️⃣1️⃣  Honeypot Dashboard..."
curl -s "$BASE_URL/admin/honeypot/dashboard" | jq .
echo ""

# Test 12: Get Biometric Profile (if user exists)
if [ ! -z "$USER_ID" ]; then
  echo "1️⃣2️⃣  Biometric Profile..."
  curl -s "$BASE_URL/biometric/profile/$USER_ID" | jq .
  echo ""
fi

# Test 13: Hash Password
echo "1️⃣3️⃣  Hash Password with RL..."
curl -s -X POST "$BASE_URL/password/hash" \
  -H "Content-Type: application/json" \
  -d '{"plain_password":"TestPass123!","theta":0.85,"h_exp":0.70}' | jq .
echo ""

# Test 14: Session Verify (if session token exists)
if [ ! -z "$SESSION_TOKEN" ] && [ ! -z "$USER_ID" ]; then
  echo "1️⃣4️⃣  Session Verify..."
  curl -s -X POST "$BASE_URL/session/verify" \
    -H "Content-Type: application/json" \
    -d "{\"session_token\":\"$SESSION_TOKEN\",\"user_id\":\"$USER_ID\",\"latent_vector\":[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0],\"e_rec\":0.15,\"trust_score\":0.85}" | jq .
  echo ""
fi

echo "===================================="
echo "✅ All tests completed!"
