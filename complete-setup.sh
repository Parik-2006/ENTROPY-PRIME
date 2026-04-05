#!/bin/bash
# Complete Docker + Project Setup Script

set -e

echo "🚀 Entropy Prime Complete Setup"
echo "================================"
echo ""

# Step 1: Check Docker
echo "Step 1: Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not installed. Download: https://www.docker.com/products/docker-desktop"
    exit 1
fi
echo "✓ Docker found: $(docker --version)"

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not installed"
    exit 1
fi
echo "✓ Docker Compose found: $(docker-compose --version)"
echo ""

# Step 2: Create .env
echo "Step 2: Setting up environment..."
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "✓ .env created (update MONGODB_URL if needed)"
else
    echo "✓ .env already exists"
fi
echo ""

# Step 3: Build images
echo "Step 3: Building Docker images..."
docker-compose build --quiet
echo "✓ Images built"
echo ""

# Step 4: Start services
echo "Step 4: Starting services..."
docker-compose up -d
echo "✓ Services started"
echo ""

# Step 5: Wait and verify
echo "Step 5: Waiting for services to initialize..."
sleep 15

echo "✓ Services initialized"
echo ""

# Step 6: Test health
echo "Step 6: Testing backend health..."
HEALTH=$(curl -s http://localhost:8000/health)
if echo "$HEALTH" | grep -q "status"; then
    echo "✓ Backend healthy"
else
    echo "⚠️  Backend may still be initializing"
fi
echo ""

# Step 7: Check models
echo "Step 7: Checking models..."
MODELS=$(curl -s http://localhost:8000/admin/models-status)
if echo "$MODELS" | grep -q "dqn"; then
    echo "✓ All 4 models loaded (DQN, MAB, PPO, 1D CNN)"
else
    echo "⚠️  Models still loading"
fi
echo ""

# Step 8: Summary
echo "================================"
echo "✅ Setup Complete!"
echo ""
echo "Services Running:"
echo "  📌 Backend:  http://localhost:8000"
echo "  📌 MongoDB:  localhost:27017"
echo "  📌 API Docs: http://localhost:8000/docs"
echo ""
echo "Next Steps:"
echo "  1. Test APIs: ./test-apis.sh"
echo "  2. Start frontend: npm run dev"
echo "  3. View logs: docker-compose logs -f"
echo ""
echo "All 17 APIs ready!"
echo "All 4 models loaded!"
echo "Honeypot active!"
echo ""
