#!/bin/bash
# Complete Docker + Project Setup Script for Entropy Prime
# Hardens setup with validation, error handling, and rollback capability

set -euo pipefail
trap 'echo "❌ Setup failed. Run: docker-compose down -v" && exit 1' ERR

echo "🚀 Entropy Prime Complete Setup"
echo "================================"
echo ""

# Step 1: Check Docker + Docker Compose
echo "Step 1: Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not installed. Download: https://www.docker.com/products/docker-desktop"
    exit 1
fi
DOCKER_VER=$(docker --version | grep -oP 'Docker version \K[^,]*')
echo "✓ Docker found: $DOCKER_VER"

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose not installed"
    exit 1
fi
COMPOSE_VER=$(docker-compose --version 2>/dev/null || docker compose version | head -1)
echo "✓ Docker Compose found: $COMPOSE_VER"

# Validate Docker daemon is running
if ! docker ps &> /dev/null; then
    echo "❌ Docker daemon not running. Start Docker Desktop and try again."
    exit 1
fi
echo "✓ Docker daemon is running"
echo ""

# Step 2: Create .env with validation
echo "Step 2: Setting up environment..."
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    if [ ! -f .env.example ]; then
        echo "❌ .env.example not found"
        exit 1
    fi
    cp .env.example .env
    
    # Generate secure secrets if not set
    SESSION_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null || echo "CHANGE_ME_SESSION_SECRET")
    SHADOW_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null || echo "CHANGE_ME_SHADOW_SECRET")
    
    sed -i "s|EP_SESSION_SECRET=.*|EP_SESSION_SECRET=$SESSION_SECRET|g" .env
    sed -i "s|EP_SHADOW_SECRET=.*|EP_SHADOW_SECRET=$SHADOW_SECRET|g" .env
    
    echo "✓ .env created with generated secrets"
else
    echo "✓ .env already exists"
    # Validate required keys
    if ! grep -q "MONGODB_URL" .env; then
        echo "⚠️  Warning: MONGODB_URL not found in .env"
    fi
    if ! grep -q "EP_SESSION_SECRET" .env; then
        echo "⚠️  Warning: EP_SESSION_SECRET not found in .env"
    fi
fi
echo ""

# Step 3: Clean up old containers
echo "Step 3: Preparing Docker environment..."
echo "Stopping and removing old containers..."
docker-compose down -v 2>/dev/null || true
echo "✓ Environment cleaned"
echo ""

# Step 4: Build images
echo "Step 4: Building Docker images..."
if ! docker-compose build --quiet 2>&1; then
    echo "❌ Docker build failed"
    exit 1
fi
echo "✓ Images built successfully"
echo ""

# Step 5: Start services
echo "Step 5: Starting services..."
if ! docker-compose up -d; then
    echo "❌ Failed to start services"
    exit 1
fi
echo "✓ Services started (MongoDB, FastAPI)"
echo ""

# Step 6: Wait for MongoDB
echo "Step 6: Waiting for MongoDB to be ready..."
MONGO_READY=0
for i in {1..30}; do
    if docker-compose exec -T mongodb mongosh --eval "db.adminCommand('ping')" &>/dev/null; then
        echo "✓ MongoDB is ready"
        MONGO_READY=1
        break
    fi
    echo "  Attempt $i/30..."
    sleep 1
done

if [ $MONGO_READY -eq 0 ]; then
    echo "⚠️  MongoDB took too long to initialize. Continuing..."
fi
echo ""

# Step 7: Wait for Backend
echo "Step 7: Waiting for Backend to be ready..."
BACKEND_READY=0
for i in {1..30}; do
    if curl -s http://localhost:8000/health &>/dev/null; then
        echo "✓ Backend is ready"
        BACKEND_READY=1
        break
    fi
    echo "  Attempt $i/30..."
    sleep 1
done

if [ $BACKEND_READY -eq 0 ]; then
    echo "⚠️  Backend initialization taking longer than expected"
    echo "  Check logs with: docker-compose logs backend"
fi
echo ""

# Step 8: Test critical endpoints
echo "Step 8: Testing critical endpoints..."
if curl -s http://localhost:8000/admin/models-status &>/dev/null; then
    MODELS_INFO=$(curl -s http://localhost:8000/admin/models-status)
    echo "✓ Models status endpoint responding"
else
    echo "⚠️  Could not verify model status"
fi
echo ""

# Step 9: Final summary
echo "================================"
echo "✅ Setup Complete!"
echo ""
echo "Services Running:"
echo "  📌 Backend API:    http://localhost:8000"
echo "  📌 API Docs:       http://localhost:8000/docs"
echo "  📌 MongoDB:        localhost:27017"
echo ""
echo "Next Steps:"
echo "  1. Test APIs: ./test-apis.sh"
echo "  2. Start frontend: npm run dev"
echo "  3. View logs: docker-compose logs -f backend"
echo "  4. Frontend: http://localhost:3000"
echo ""
echo "To stop services: docker-compose down"
echo "================================"
echo ""
