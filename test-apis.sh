#!/bin/bash
# API Test Script for Entropy Prime
# Production-hardened with validation and error handling

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
FAILED_TESTS=0
PASSED_TESTS=0

echo "🧪 Testing Entropy Prime APIs"
echo "Base URL: $BASE_URL"
echo "===================================="
echo ""

# Check if server is running
if ! curl -s "$BASE_URL/health" &>/dev/null; then
    echo "❌ Backend not responding at $BASE_URL"
    echo "   Start it with: docker-compose up -d"
    exit 1
fi
echo "✓ Backend is responding"
echo ""

# Helper function for API tests
test_api() {
    local test_num=$1
    local test_name=$2
    local method=$3
    local endpoint=$4
    local data=$5
    
    echo -n "$test_num️⃣  $test_name..."
    
    if [ "$method" = "POST" ]; then
        RESPONSE=$(curl -s -X POST "$BASE_URL$endpoint" \
          -H "Content-Type: application/json" \
          -d "$data" 2>&1)
    else
        RESPONSE=$(curl -s "$BASE_URL$endpoint" 2>&1)
    fi
    
    # Check if response is valid JSON
    if echo "$RESPONSE" | jq . &>/dev/null; then
        echo " ✓"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        if [ "$6" != "quiet" ]; then
            echo "$RESPONSE" | jq .
        fi
        echo ""
        return 0
    else
        echo " ❌ (Invalid response)"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo "  Response: $RESPONSE"
        echo ""
        return 1
    fi
}

# Run tests
test_api 1 "Health Check" "GET" "/health" "" "quiet"

test_api 2 "Models Status" "GET" "/admin/models-status" "" "quiet"

test_api 3 "Register User" "POST" "/auth/register" \
  '{"email":"test@example.com","plain_password":"TestPass123!"}'
USER_ID=$(echo "$RESPONSE" | jq -r '.user_id // empty' 2>/dev/null || echo "")
SESSION_TOKEN=$(echo "$RESPONSE" | jq -r '.session_token // empty' 2>/dev/null || echo "")

test_api 4 "Extract Biometrics" "POST" "/biometric/extract" \
  '{"raw_signal":[0.1,0.2,0.15,0.3,0.25,0.18,0.22,0.19,0.21,0.23]}' "quiet"

test_api 5 "Score Biometric" "POST" "/score" \
  '{"theta":0.85,"h_exp":0.70,"server_load":0.45}' "quiet"

test_api 6 "Honeypot Signatures" "GET" "/honeypot/signatures" "" "quiet"

test_api 7 "Honeypot Dashboard" "GET" "/admin/honeypot/dashboard" "" "quiet"

test_api 8 "Hash Password" "POST" "/password/hash" \
  '{"plain_password":"TestPass123!","theta":0.85,"h_exp":0.70}' "quiet"

if [ ! -z "$USER_ID" ]; then
    test_api 9 "Get Biometric Profile" "GET" "/biometric/profile/$USER_ID" "" "quiet"
fi

if [ ! -z "$SESSION_TOKEN" ] && [ ! -z "$USER_ID" ]; then
    test_api 10 "Session Verify" "POST" "/session/verify" \
      "{\"session_token\":\"$SESSION_TOKEN\",\"user_id\":\"$USER_ID\",\"latent_vector\":[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0],\"e_rec\":0.15,\"trust_score\":0.85}" "quiet"
fi

test_api 11 "Pipeline Debug" "GET" "/admin/pipeline-debug" "" "quiet"

# Summary
echo "===================================="
echo "📊 Test Summary"
echo "  ✓ Passed: $PASSED_TESTS"
echo "  ❌ Failed: $FAILED_TESTS"
echo "===================================="

if [ $FAILED_TESTS -gt 0 ]; then
    echo "⚠️  Some tests failed. Check backend logs:"
    echo "   docker-compose logs backend -f"
    exit 1
else
    echo "✅ All tests passed!"
    exit 0
fi

echo "===================================="
echo "✅ All tests completed!"
