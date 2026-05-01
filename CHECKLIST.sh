#!/bin/bash
# Entropy Prime - Setup Checklist & Automated Validation
# Run with: bash CHECKLIST.sh [--auto] [--verbose]
# Use --auto flag to run automated checks instead of manual checklist

AUTO_MODE=0
VERBOSE=0

# Parse arguments
for arg in "$@"; do
    case $arg in
        --auto) AUTO_MODE=1 ;;
        --verbose) VERBOSE=1 ;;
    esac
done

if [ $AUTO_MODE -eq 1 ]; then
    # Run automated validation
    echo "🔍 Running Entropy Prime Setup Validation..."
    echo ""
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python 3 not found"
        exit 1
    fi
    echo "✓ Python 3: $(python3 --version)"
    
    # Check Node
    if ! command -v node &> /dev/null; then
        echo "❌ Node.js not found"
        exit 1
    fi
    echo "✓ Node: $(node --version)"
    
    # Check .env
    if [ ! -f .env ]; then
        echo "❌ .env file not found. Run: cp .env.example .env"
        exit 1
    fi
    echo "✓ .env file exists"
    
    # Check MongoDB
    if ! grep -q "MONGODB_URL" .env; then
        echo "⚠️  MONGODB_URL not configured in .env"
    else
        MONGO_URL=$(grep "MONGODB_URL" .env | cut -d'=' -f2)
        echo "✓ MongoDB URL configured: $MONGO_URL"
    fi
    
    # Check dependencies
    if [ -d "backend" ] && [ -f "backend/requirements.txt" ]; then
        echo "✓ Backend requirements.txt found"
        if [ $VERBOSE -eq 1 ]; then
            PIP_PKGS=$(python3 -m pip list 2>/dev/null | grep -c "torch\|fastapi\|pymongo" || echo "0")
            echo "  Installed packages: $PIP_PKGS/3 core packages"
        fi
    fi
    
    if [ -f "package.json" ]; then
        echo "✓ package.json found"
        if [ -d "node_modules" ]; then
            echo "✓ node_modules installed"
        fi
    fi
    
    # Check ports
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "✓ Port 8000 is in use (backend running)"
    else
        echo "⚠️  Port 8000 not in use - backend may not be running"
    fi
    
    if lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "✓ Port 3000 is in use (frontend running)"
    else
        echo "⚠️  Port 3000 not in use - frontend may not be running"
    fi
    
    # Test MongoDB connection
    if command -v mongosh &> /dev/null; then
        if mongosh --quiet "$(grep MONGODB_URL .env | cut -d'=' -f2)" --eval "db.adminCommand('ping')" &>/dev/null; then
            echo "✓ MongoDB connection successful"
        else
            echo "⚠️  MongoDB connection failed"
        fi
    fi
    
    echo ""
    echo "✅ Validation complete"
    exit 0
fi

# Manual checklist mode
cat << 'EOF'
╔══════════════════════════════════════════════════════════════════════════════╗
║                  ENTROPY PRIME - MongoDB Integration Checklist               ║
║                          Complete in 10-15 minutes                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Choose MongoDB Setup (Pick ONE)                                     │
└──────────────────────────────────────────────────────────────────────────────┘

Option A: CloudMongoDB Atlas (Recommended - Free Tier)
  ☐ Go to https://www.mongodb.com/cloud/atlas
  ☐ Create free account
  ☐ Create M0 FREE cluster (wait 1-2 min)
  ☐ Create database user (entropy_user)
  ☐ Set Network Access to "Allow Anywhere"
  ☐ Get connection string: mongodb+srv://entropy_user:PASSWORD@cluster0...
  ⏱️  Time: ~5 minutes

Option B: Local MongoDB
  ☐ Mac: brew install mongodb-community && brew services start mongodb-community
  ☐ Linux: sudo apt-get install mongodb-org && sudo systemctl start mongod
  ☐ Docker: docker run -d -p 27017:27017 mongo:latest
  ⏱️  Time: ~2 minutes

Option C: Docker (Fastest)
  ☐ docker run -d -p 27017:27017 mongo:latest
  ⏱️  Time: ~1 minute

┌──────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Configure Environment                                               │
└──────────────────────────────────────────────────────────────────────────────┘

  ☐ Copy template: cp .env.example .env
  ☐ Edit .env with MongoDB URL:
    
    For Atlas:
    MONGODB_URL=mongodb+srv://entropy_user:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
    MONGODB_DB_NAME=entropy_prime
    
    For Local/Docker:
    MONGODB_URL=mongodb://localhost:27017
    MONGODB_DB_NAME=entropy_prime

  ☐ Verify .env exists and .gitignore includes it (prevents committing secrets)

┌──────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Install Dependencies                                                │
└──────────────────────────────────────────────────────────────────────────────┘

  ☐ Backend: cd backend && pip install -r requirements.txt
  ☐ Frontend: cd .. && npm install
  ☐ Verify no errors during install

┌──────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Test MongoDB Connection                                             │
└──────────────────────────────────────────────────────────────────────────────┘

  ☐ Run: python backend/main.py
  ☐ Look for output:
    ✓ Connected to MongoDB: entropy_prime
    ✓ Entropy Prime backend initialized with MongoDB
  ☐ Press Ctrl+C to stop

  If connection fails:
    ☐ Check .env file: cat .env | grep MONGODB_URL
    ☐ Verify MongoDB is running (Atlas/local/Docker)
    ☐ For Atlas: Did you add your IP to Network Access?

┌──────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: Test User Registration (Create Test User)                           │
└──────────────────────────────────────────────────────────────────────────────┘

  Start backend (in separate terminal):
  ☐ cd backend && python main.py

  Test registration:
  ☐ Run this curl command:

    curl -X POST http://localhost:8000/auth/register \
      -H "Content-Type: application/json" \
      -d '{"email":"test@example.com","plain_password":"TestPass123!"}'

  ☐ Expected response (success):
    {
      "success": true,
      "user_id": "507f...",
      "email": "test@example.com",
      "message": "User registered successfully"
    }

  ☐ If error: Check backend console for details

┌──────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: Verify Data in MongoDB (Optional but Recommended)                    │
└──────────────────────────────────────────────────────────────────────────────┘

  Download MongoDB Compass (GUI):
  ☐ Get it from: https://www.mongodb.com/products/compass
  ☐ Paste your MongoDB connection string
  ☐ Look for "entropy_prime" database
  ☐ In "users" collection, find your test@example.com entry
  ☐ Verify password_hash starts with "$argon2id$"

  OR use MongoDB shell:
  ☐ mongosh "mongodb+srv://entropy_user:PASSWORD@cluster..."
  ☐ use entropy_prime
  ☐ db.users.find()

┌──────────────────────────────────────────────────────────────────────────────┐
│ STEP 7: Run Full Application                                                │
└──────────────────────────────────────────────────────────────────────────────┘

  ☐ Run: ./start.sh
  ☐ Wait for both services to start:
    ► Frontend → http://localhost:3000
    ► Backend → http://localhost:8000
  ☐ Open http://localhost:3000 in browser
  ☐ Test login/register with frontend
  ☐ Data is now stored in MongoDB!

┌──────────────────────────────────────────────────────────────────────────────┐
│ OPTIONAL: Pre-train RL Model (Recommended for Better Performance)            │
└──────────────────────────────────────────────────────────────────────────────┘

  ☐ cd backend
  ☐ python train.py --episodes 100000 --out ../checkpoints/governor.pt
  ☐ Wait ~2 minutes
  ☐ export EP_RL_CHECKPOINT=../checkpoints/governor.pt
  ☐ Restart backend (run ./start.sh again)

  This makes Argon2id parameter selection smarter!

╔══════════════════════════════════════════════════════════════════════════════╗
║                            ✅ YOU'RE DONE!                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

📋 Summary of What Was Set Up:
  ✅ MongoDB connection configured
  ✅ User registration/login endpoints
  ✅ Passwords hashed with Argon2id
  ✅ Biometric data storage
  ✅ Session management
  ✅ Bot detection honeypot
  ✅ All data persisted in MongoDB

📚 Documentation:
  • QUICK_START_MONGODB.md → 5-minute quick reference
  • MONGODB_SETUP.md → Detailed step-by-step guide
  • MONGODB_INTEGRATION.md → Architecture & API details
  • SETUP_SUMMARY.md → Complete overview

🚀 Next Steps:
  1. Start server: ./start.sh
  2. Visit: http://localhost:3000
  3. Test register/login
  4. Monitor in MongoDB Compass

🔗 Resources:
  • MongoDB Atlas: https://www.mongodb.com/cloud/atlas
  • API Docs: http://localhost:8000/docs
  • Compass: https://www.mongodb.com/products/compass

🆘 Need Help?
  • See QUICK_START_MONGODB.md
  • Check MONGODB_SETUP.md Troubleshooting
  • Verify .env file has correct MongoDB URL
  • Make sure MongoDB is running

═══════════════════════════════════════════════════════════════════════════════

Questions? Check the documentation files or GitHub issues.
Happy building with Entropy Prime! 🎉

EOF
