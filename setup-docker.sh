#!/bin/bash
# Automated Docker setup script for Entropy Prime

set -e

echo "🚀 Entropy Prime Docker Setup Script"
echo "======================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please download it from https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please download it from https://www.docker.com/"
    exit 1
fi

echo "✓ Docker and Docker Compose are installed"

# Build and start services
echo ""
echo "Starting Entropy Prime services..."
docker-compose down -v 2>/dev/null || true
docker-compose build
docker-compose up -d

# Wait for services to be ready
echo ""
echo "⏳ Waiting for services to initialize (15 seconds)..."
sleep 15

# Test MongoDB
echo ""
echo "Testing MongoDB connection..."
if docker-compose exec -T mongodb mongosh --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo "✓ MongoDB is running"
else
    echo "⚠️  MongoDB may still be initializing"
fi

# Test Backend
echo ""
echo "Testing Backend health..."
HEALTH=$(curl -s http://localhost:8000/health)
if echo "$HEALTH" | grep -q "status"; then
    echo "✓ Backend is running"
    echo "  Response: $HEALTH"
else
    echo "⚠️  Backend may still be initializing"
fi

echo ""
echo "======================================"
echo "🎉 Setup Complete!"
echo ""
echo "Services are now running:"
echo "  - MongoDB:  localhost:27017"
echo "  - Backend:  http://localhost:8000"
echo ""
echo "Next steps:"
echo "  1. View logs:      docker-compose logs -f"
echo "  2. Stop services:  docker-compose down"
echo "  3. Access honeypot: curl http://localhost:8000/honeypot/signatures"
echo ""
