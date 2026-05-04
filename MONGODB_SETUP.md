# MongoDB Setup for Entropy Prime

Follow these steps to configure MongoDB for local development and Docker deployment.

---

## Step 1: Install MongoDB Community Server (Local Development)

### Option A: Windows Installer (Easiest)

1. Download MongoDB Community Server from: https://www.mongodb.com/try/download/community
2. Choose **Windows** → Download MSI installer
3. Run the installer → Accept license → Choose **Complete** installation
4. **Important:** On the "Service Configuration" page:
   - ✓ Check "Install MongoDB as a Service"
   - ✓ Check "Run the service as Network Service user"
   - Service Name: `MongoDB`
   - Data Directory: `C:\Program Files\MongoDB\Server\7.0\data` (default)
   - Log File: `C:\Program Files\MongoDB\Server\7.0\log\mongod.log` (default)
5. Click **Install** and complete the wizard

### Option B: Docker (Recommended for consistency)

```bash
# Start MongoDB in Docker (if you have Docker installed)
docker run -d -p 27017:27017 --name ep-mongodb \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=changeme \
  mongo:7
```

---

## Step 2: Verify MongoDB is Running

### For Windows Service Installation:

Open PowerShell and run:
```powershell
# Check MongoDB service status
Get-Service MongoDB

# Should output: Running    MongoDB

# Or connect with mongosh
mongosh
```

### For Docker:

```bash
docker ps | grep ep-mongodb
# Should show the running container
```

---

## Step 3: Create Administrator User (First Time Setup)

Open MongoDB shell:
```bash
mongosh
```

Run these commands:
```javascript
// Switch to admin database
use admin

// Create root admin user (if not already created)
db.createUser({
  user: "admin",
  pwd: "changeme",  // CHANGE THIS IN PRODUCTION
  roles: [{ role: "root", db: "admin" }]
})

// Create entropy_prime database user
use entropy_prime

db.createUser({
  user: "ep_user",
  pwd: "ep_password",  // CHANGE THIS IN PRODUCTION
  roles: [{ role: "readWrite", db: "entropy_prime" }]
})

// Verify user was created
db.getUsers()

// Exit
exit
```

---

## Step 4: Create Database Collections and Indexes

Still in `mongosh`, run:

```javascript
use entropy_prime

// Create collections
db.createCollection("users")
db.createCollection("sessions")
db.createCollection("biometric_profiles")
db.createCollection("drift_events")
db.createCollection("feature_selections")
db.createCollection("honeypot")

// Create indexes for performance
db.users.createIndex({ email: 1 }, { unique: true })
db.sessions.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0 })
db.drift_events.createIndex({ timestamp: 1 }, { expireAfterSeconds: 2592000 })
db.biometric_profiles.createIndex({ user_id: 1 })
db.honeypot.createIndex({ timestamp: -1 })

// Verify collections exist
db.getCollectionNames()
// Should output: [ "users", "sessions", "biometric_profiles", "drift_events", "feature_selections", "honeypot" ]

exit
```

---

## Step 5: Configure .env File for Backend

Create a `.env` file in `backend/` directory with these values:

```bash
# MongoDB connection
MONGODB_URL=mongodb://ep_user:ep_password@localhost:27017/entropy_prime
MONGODB_DB_NAME=entropy_prime

# Security secrets (generate with: python -c "import secrets; print(secrets.token_hex(32))")
EP_SESSION_SECRET=your_random_session_secret_here_64_chars
EP_SHADOW_SECRET=your_random_shadow_secret_here_64_chars

# CORS allowed origins
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Logging
LOG_LEVEL=INFO

# ML Model checkpoints
EP_RL_CHECKPOINT=checkpoints/governor.pt
EP_MAB_CHECKPOINT=checkpoints/mab.json
EP_PPO_CHECKPOINT=checkpoints/watchdog.pt
```

---

## Step 6: Verify Backend Connection to MongoDB

Run this test in PowerShell:

```powershell
cd "p:\ENTROPY PRIME\backend"

python -c "
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

async def test_connection():
    url = 'mongodb://ep_user:ep_password@localhost:27017/entropy_prime'
    client = AsyncIOMotorClient(url)
    
    try:
        # Test connection
        await client.admin.command('ping')
        print('✓ MongoDB connection successful')
        
        # List collections
        db = client.entropy_prime
        collections = await db.list_collection_names()
        print(f'✓ Collections in database: {collections}')
        
    except Exception as e:
        print(f'✗ Connection failed: {e}')
    finally:
        client.close()

asyncio.run(test_connection())
"
```

Expected output:
```
✓ MongoDB connection successful
✓ Collections in database: ['users', 'sessions', 'biometric_profiles', 'drift_events', 'feature_selections', 'honeypot']
```

---

## Step 7: Test with Sample Data Insertion

```powershell
python -c "
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime

async def insert_test_user():
    url = 'mongodb://ep_user:ep_password@localhost:27017/entropy_prime'
    client = AsyncIOMotorClient(url)
    db = client.entropy_prime
    
    try:
        # Insert a test user
        result = await db.users.insert_one({
            'email': 'test@entropy-prime.local',
            'password_hash': 'bcrypt_hash_here',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
        })
        print(f'✓ Test user inserted with ID: {result.inserted_id}')
        
        # Read it back
        user = await db.users.find_one({'email': 'test@entropy-prime.local'})
        print(f'✓ Retrieved user: {user[\"email\"]} (ID: {user[\"_id\"]})')
        
    except Exception as e:
        print(f'✗ Insert failed: {e}')
    finally:
        client.close()

asyncio.run(insert_test_user())
"
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `mongosh: command not found` | Add MongoDB `bin/` to PATH or use full path: `"C:\Program Files\MongoDB\Server\7.0\bin\mongosh.exe"` |
| `Connection refused on port 27017` | MongoDB service not running. Start: `net start MongoDB` or check Docker: `docker ps` |
| `Authentication failed` | Check username/password in `.env` matches user created in Step 3 |
| `Database entropy_prime does not exist` | MongoDB creates DB on first write. Collections created in Step 4 will initialize it. |
| `Invalid index specification` | Ensure no duplicate indexes. Check with: `db.collection_name.getIndexes()` |

---

## Quick MongoDB Command Reference

```bash
# Start MongoDB service
net start MongoDB

# Stop MongoDB service
net stop MongoDB

# Connect with authentication
mongosh -u admin -p changeme

# List all databases
show databases

# Switch to a database
use entropy_prime

# List collections in current database
show collections

# Count documents in a collection
db.users.countDocuments()

# Find a single document
db.users.findOne({ email: "test@test.com" })

# Delete all documents (use with caution!)
db.users.deleteMany({})

# Drop a collection
db.users.drop()

# Drop entire database
db.dropDatabase()
```

---

## Docker Compose Integration (Optional)

If using Docker Compose later, MongoDB will be auto-configured. For now, focus on local setup above.

---

**Status:** Once you complete all 7 steps above, MongoDB will be ready for backend Stage 1 implementation.
