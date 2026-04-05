#!/bin/bash
# ENTROPY PRIME - MongoDB Setup Checklist
# Follow these steps to get MongoDB configured and running

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
