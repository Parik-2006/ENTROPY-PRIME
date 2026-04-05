#!/bin/bash

# Entropy Prime - MongoDB Setup Script
# This script sets up MongoDB connection and initializes the project

set -e

echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║       Entropy Prime + MongoDB Initialization Script                    ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""

# Check if .env exists
if [ -f ".env" ]; then
    echo "✓ .env file already exists"
    read -p "Do you want to reconfigure MongoDB? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping MongoDB configuration..."
        skip_env=true
    fi
fi

if [ "$skip_env" != "true" ]; then
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════════╗"
    echo "║              MongoDB Configuration                                      ║"
    echo "╚════════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Choose MongoDB setup option:"
    echo "  1) MongoDB Atlas (Cloud - Recommended)"
    echo "  2) Local MongoDB"
    echo "  3) Docker MongoDB"
    echo ""
    read -p "Enter option (1/2/3): " mongo_option
    
    case $mongo_option in
        1)
            echo ""
            echo "📍 MongoDB Atlas Setup:"
            echo "  1. Go to https://www.mongodb.com/cloud/atlas"
            echo "  2. Sign up for free account"
            echo "  3. Create M0 FREE cluster"
            echo "  4. Create database user"
            echo "  5. Add your IP to Network Access"
            echo "  6. Get connection string and copy below"
            echo ""
            read -p "Enter MongoDB Atlas Connection String: " mongodb_url
            ;;
        2)
            echo ""
            echo "📍 Local MongoDB Setup:"
            echo "  Make sure MongoDB is running:"
            echo "  - Mac:   brew services start mongodb-community"
            echo "  - Linux: sudo systemctl start mongod"
            echo ""
            mongodb_url="mongodb://localhost:27017"
            echo "Using: $mongodb_url"
            ;;
        3)
            echo ""
            echo "📍 Docker MongoDB Setup:"
            echo "  Starting MongoDB in Docker..."
            docker run -d -p 27017:27017 --name entropy-mongodb mongo:latest || true
            sleep 2
            mongodb_url="mongodb://localhost:27017"
            echo "✓ MongoDB running in Docker"
            echo "✓ URL: $mongodb_url"
            ;;
        *)
            echo "Invalid option"
            exit 1
            ;;
    esac
    
    # Generate random secrets
    session_secret=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    shadow_secret=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    
    # Create .env file
    cat > .env << EOF
# MongoDB Configuration
MONGODB_URL=$mongodb_url
MONGODB_DB_NAME=entropy_prime

# Backend Secrets (Auto-generated)
EP_SESSION_SECRET=$session_secret
EP_SHADOW_SECRET=$shadow_secret

# Optional: RL Checkpoint
EP_RL_CHECKPOINT=./checkpoints/governor.pt
EOF
    
    echo ""
    echo "✓ Created .env file with:"
    echo "  - MongoDB URL configured"
    echo "  - Session secrets generated"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║              Installing Dependencies                                    ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""

# Install backend dependencies
echo "[1/2] Installing backend dependencies..."
cd backend
pip install -r requirements.txt --quiet
echo "✓ Backend dependencies installed"

# Install frontend dependencies
echo "[2/2] Installing frontend dependencies..."
cd ..
npm install --silent --legacy-peer-deps 2>/dev/null || true
echo "✓ Frontend dependencies installed"

echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete! ✓                                    ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo ""
echo "1️⃣  Test MongoDB Connection (optional):"
echo "    python backend/main.py"
echo ""
echo "2️⃣  Pre-train RL Model (optional but recommended):"
echo "    cd backend"
echo "    python train.py --episodes 100000 --out ../checkpoints/governor.pt"
echo ""
echo "3️⃣  Run Full Stack:"
echo "    ./start.sh"
echo ""
echo "4️⃣  Create Test User:"
echo "    curl -X POST http://localhost:8000/auth/register \\\\"
echo "      -H 'Content-Type: application/json' \\\\"
echo "      -d '{\"email\": \"test@example.com\", \"plain_password\": \"TestPass123!\"}'"
echo ""
echo "📖 More info: See MONGODB_SETUP.md"
echo ""
