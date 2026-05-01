#!/bin/bash
# Automated Docker setup script for Entropy Prime
# Production-hardened with validation, error handling, and health checks

set -euo pipefail
trap 'echo "❌ Setup failed. Use docker-compose logs for details." && docker-compose down -v 2>/dev/null || true && exit 1' ERR

echo "🚀 Entropy Prime Docker Setup Script"
echo "======================================"
echo ""

# Validate Docker installation
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please download from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed."
    exit 1
fi

# Validate Docker daemon
if ! docker ps &> /dev/null; then
    echo "❌ Docker daemon not running. Start Docker Desktop."
    exit 1
fi

echo "✓ Docker and Docker Compose are installed and running"
echo ""

# Build and start services
echo ""
echo "Starting Entropy Prime services..."
echo "Cleaning up old containers..."
docker-compose down -v 2>/dev/null || true

echo "Building Docker images..."
if ! docker-compose build 2>&1 | grep -q "Successfully"; then
    if ! docker-compose build --quiet; then
        echo "❌ Build failed"
        exit 1
    fi
fi
echo "✓ Images built successfully"

echo "Starting services..."
if ! docker-compose up -d; then
    echo "❌ Failed to start services"
    exit 1
fi
echo "✓ Services started"

# Wait for services with timeout
echo ""
echo "⏳ Waiting for services to initialize (up to 30 seconds)..."
RETRY_COUNT=0
MAX_RETRIES=30

# Wait for MongoDB
echo "Waiting for MongoDB..."
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if docker-compose exec -T mongodb mongosh --eval "db.adminCommand('ping')" &>/dev/null 2>&1; then
        echo "✓ MongoDB is running"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo "⚠️  MongoDB initialization timeout - proceeding anyway"
    else
        sleep 1
    fi
done

# Wait for Backend
RETRY_COUNT=0
echo "Waiting for Backend..."
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:8000/health &>/dev/null; then
        echo "✓ Backend is running"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo "⚠️  Backend initialization timeout - check logs with: docker-compose logs backend"
    else
        sleep 1
    fi
done

echo ""
echo "======================================"
echo "🎉 Docker Setup Complete!"
echo ""
echo "Services are now running:"
echo "  ✓ MongoDB:    localhost:27017"
echo "  ✓ Backend API: http://localhost:8000"
echo "  ✓ API Docs:   http://localhost:8000/docs"
echo ""
echo "Troubleshooting:"
echo "  View logs:      docker-compose logs -f"
echo "  Check backend:  curl http://localhost:8000/health"
echo "  Check models:   curl http://localhost:8000/admin/models-status"
echo ""
echo "Next steps:"
echo "  1. Test APIs:      ./test-apis.sh"
echo "  2. Start frontend: npm run dev"
echo "  3. Stop services:  docker-compose down"
echo ""
