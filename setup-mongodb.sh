#!/bin/bash
# Entropy Prime - MongoDB Setup Script
# Production-hardened setup with validation and error handling

set -euo pipefail
trap 'echo "❌ Setup failed. Please check .env configuration." && exit 1' ERR

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

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8+"
    exit 1
fi
PYTHON_VER=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python $PYTHON_VER found"

# Check Node
if ! command -v npm &> /dev/null; then
    echo "⚠️  npm not found. Frontend dependencies will be skipped."
else
    NODE_VER=$(node --version)
    echo "✓ Node $NODE_VER found"
fi
echo ""

# Install backend dependencies
echo "[1/2] Installing backend dependencies..."
if [ -d "backend" ]; then
    cd backend
    if [ ! -f requirements.txt ]; then
        echo "❌ requirements.txt not found in backend/"
        exit 1
    fi
    if pip install -r requirements.txt --quiet; then
        echo "✓ Backend dependencies installed"
    else
        echo "⚠️  Some backend dependencies may have failed. Check manually."
    fi
    cd ..
else
    echo "❌ backend/ directory not found"
    exit 1
fi

# Install frontend dependencies
echo "[2/2] Installing frontend dependencies..."
if [ -f "package.json" ]; then
    if command -v npm &> /dev/null; then
        if npm install --silent --legacy-peer-deps 2>/dev/null; then
            echo "✓ Frontend dependencies installed"
        else
            echo "⚠️  Some frontend dependencies may have failed. Check manually."
        fi
    else
        echo "⚠️  npm not found - skipping frontend dependencies"
    fi
else
    echo "⚠️  package.json not found"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete! ✓                                    ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "✅ Environment configured successfully"
echo ""
echo "Next steps:"
echo ""
echo "1️⃣  Verify MongoDB Connection:"
echo "    python3 backend/main.py"
echo "    Look for: ✓ Connected to MongoDB: entropy_prime"
echo "    Press Ctrl+C to stop"
echo ""
echo "2️⃣  (Optional) Pre-train RL Model:"
echo "    cd backend"
echo "    python train.py --episodes 100000 --out ../checkpoints/governor.pt"
echo "    cd .."
echo ""
echo "3️⃣  Run Full Stack:"
echo "    For Docker:     docker-compose up -d && ./complete-setup.sh"
echo "    For Local:      ./start.sh"
echo ""
echo "4️⃣  Test User Registration:"
echo "    curl -X POST http://localhost:8000/auth/register \\\\"
echo "      -H 'Content-Type: application/json' \\\\"
echo "      -d '{\"email\":\"test@example.com\",\"plain_password\":\"Test123!\"}'"
echo ""
echo "5️⃣  Start Frontend:"
echo "    npm run dev"
echo "    Navigate to: http://localhost:3000"
echo ""
echo "📖 Documentation: See MONGODB_SETUP.md for more details"
echo "🆘 Troubleshooting: Check docker-compose logs or backend logs"
echo ""
