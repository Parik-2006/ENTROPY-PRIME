# Entropy Prime - MongoDB Integration Complete! 🚀

## What's New

Your Entropy Prime project now has full **MongoDB integration** for persistent user data storage. All hashed passwords are now stored securely in MongoDB!

---

## New Files Created

### 1. **[backend/models.py](backend/models.py)**
   - Pydantic models for MongoDB documents
   - `User` - User accounts with emails & hashed passwords
   - `Session` - User sessions with tokens
   - `BiometricProfile` - CNN biometric data per user
   - `HoneypotEntry` - Bot signatures and suspicious activity

### 2. **[backend/database.py](backend/database.py)**
   - Async MongoDB connection handler
   - CRUD operations for users, sessions, biometrics, honeypot
   - Automatic index creation
   - TTL (time-to-live) for session expiration

### 3. **[MONGODB_SETUP.md](MONGODB_SETUP.md)**
   - Complete step-by-step MongoDB Atlas setup guide (FREE)
   - Local MongoDB installation options
   - Docker setup instructions
   - Troubleshooting guide
   - API endpoints documentation

### 4. **[.env.example](.env.example)**
   - Template for environment variables
   - Copy to `.env` and fill in your values

### 5. **[setup-mongodb.sh](setup-mongodb.sh)**
   - Interactive setup script
   - Configures MongoDB connection
   - Generates random secrets
   - Installs dependencies

---

## Updated Files

### [backend/main.py](backend/main.py)
**New Endpoints:**
- `POST /auth/register` - Create new user with hashed password
- `POST /auth/login` - Login and get session token
- `POST /auth/logout` - Invalidate session

**Enhanced Endpoints:**
- `/score` - Now stores bot signatures in MongoDB
- `/password/hash` - Optional user profile update
- `/honeypot/signatures` - Fetches from MongoDB + in-memory cache

**New Features:**
- MongoDB startup/shutdown hooks
- User authentication flow
- Session management
- Biometric data persistence

### [backend/requirements.txt](backend/requirements.txt)
**New Dependencies:**
- `pymongo==4.6.1` - MongoDB driver
- `motor==3.3.2` - Async MongoDB support
- `python-dotenv==1.0.0` - Environment variables

---

## Quick Start (3 Steps)

### Step 1: Setup MongoDB

**Option A - Using Interactive Script (Recommended):**
```bash
chmod +x setup-mongodb.sh
./setup-mongodb.sh
```

**Option B - Manual Setup:**

1. Go to https://www.mongodb.com/cloud/atlas
2. Create free account and M0 cluster
3. Create database user and get connection string
4. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
5. Edit `.env` and add your MongoDB connection string

### Step 2: Install Dependencies

```bash
cd backend
pip install -r requirements.txt
cd ..
npm install
```

### Step 3: Run & Test

```bash
# Test MongoDB connection
python backend/main.py

# Expected output:
# ✓ Connected to MongoDB: entropy_prime
# ✓ Entropy Prime backend initialized with MongoDB
```

---

## MongoDB Collections

Your `entropy_prime` database will have these collections:

| Collection | Contains |
|-----------|----------|
| `users` | Email, hashed passwords, security level, profile |
| `sessions` | Active session tokens, trust scores, expiry |
| `biometric_profiles` | CNN scores (theta, h_exp), keystroke/mouse data |
| `honeypot` | Bot signatures, suspicious IPs, low theta scores |

---

## API Usage Examples

### Register New User

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "plain_password": "SecurePassword123!"
  }'
```

Response:
```json
{
  "success": true,
  "user_id": "507f1f77bcf86cd799439011",
  "email": "user@example.com",
  "session_token": "...",
  "message": "User registered successfully"
}
```

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "plain_password": "SecurePassword123!"
  }'
```

### Hash Password (with RL-optimized Argon2id)

```bash
curl -X POST http://localhost:8000/password/hash \
  -H "Content-Type: application/json" \
  -d '{
    "plain_password": "MyPassword123!",
    "theta": 0.85,
    "h_exp": 0.75
  }'
```

Response:
```json
{
  "hash": "$argon2id$v=19$m=131072,t=3,p=4$...",
  "action": "standard",
  "elapsed_ms": 250.5,
  "argon2_params": {"m": 131072, "t": 3, "p": 4}
}
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  Frontend (React/Vite)                  │
│  - Collects biometric: keystroke dwell, mouse velocity  │
│  - 1D-CNN model (TensorFlow.js) → theta score           │
└────────────────────┬────────────────────────────────────┘
                     │ POST /score, /auth/login
                     ▼
┌─────────────────────────────────────────────────────────┐
│                 Backend (FastAPI)                       │
│  ┌──────────────────────────────────────────────────┐   │
│  │  RL Governor (DQN)                               │   │
│  │  - Selects Argon2id hardness (economy→punisher)  │   │
│  └────────────────┬─────────────────────────────────┘   │
│                   │                                      │
│  ┌────────────────▼─────────────────────────────────┐   │
│  │  Honeypot Engine                                 │   │
│  │  - Catches low theta (θ < 0.1): 100% bots       │   │
│  └────────────────┬─────────────────────────────────┘   │
│                   │ Store bot signatures                │
└────────────────┬──┴──────────────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │   MongoDB Atlas (FREE)      │
    │  ┌──────────────────────┐   │
    │  │ users                │   │ Stores hashed passwords
    │  │ sessions             │   │ Stores session tokens
    │  │ biometric_profiles   │   │ Stores CNN scores
    │  │ honeypot             │   │ Stores bot signatures
    │  └──────────────────────┘   │
    └────────────────────────────┘
```

---

## RL-Hardened Password Hashing

The system uses **RL-selected Argon2id parameters** based on biometric confidence (theta):

| Theta Score | Action | Memory (MB) | Time | Parallelism |
|-------------|--------|------------|------|-------------|
| 0.9-1.0 (Human) | ECONOMY | 64 | 2 | 4 |
| 0.7-0.9 | STANDARD | 128 | 3 | 4 |
| 0.3-0.7 | HARD | 512 | 4 | 8 |
| <0.3 (Bot?) | PUNISHER | 1024 | 8 | 16 |

More certainty = lighter hashing. Less certainty = heavier punishment!

---

## What Gets Stored in MongoDB

### Users Collection
```json
{
  "_id": ObjectId,
  "email": "user@example.com",
  "password_hash": "$argon2id$v=19$m=...",
  "created_at": "2026-04-04T10:00:00",
  "updated_at": "2026-04-04T10:00:00",
  "last_login": "2026-04-04T11:30:00",
  "is_active": true,
  "security_level": "standard"
}
```

### Sessions Collection
```json
{
  "_id": ObjectId,
  "user_id": ObjectId,
  "session_token": "...",
  "latent_vector": [0.1, 0.2, ...],  // 32-dim CNN encoding
  "created_at": "2026-04-04T10:00:00",
  "expires_at": "2026-04-04T10:30:00",  // Auto-expires after 30 min
  "trust_score": 0.95,
  "is_active": true
}
```

### Honeypot Collection
```json
{
  "_id": ObjectId,
  "timestamp": "2026-04-04T10:00:00",
  "user_agent": "Mozilla/5.0...",
  "theta": 0.05,  // Very low = bot
  "ip_address": "192.168.1.100",
  "path": "/"
}
```

---

## Next Steps

### 1. Pre-train RL Model (Optional but Recommended)

This takes ~2 minutes and trains the DQN policy for better Argon2id selection:

```bash
cd backend
python train.py --episodes 100000 --out ../checkpoints/governor.pt
export EP_RL_CHECKPOINT=../checkpoints/governor.pt
```

### 2. Run Full Stack

```bash
./start.sh
```

Then open:
- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs

### 3. Test User Registration & Login

Use the frontend login/register forms or curl:

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@mail.com","plain_password":"MyPass123!"}'

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@mail.com","plain_password":"MyPass123!"}'
```

### 4. Monitor MongoDB

Access MongoDB Compass (GUI) or shell:

```bash
# Shell - MongoDB Atlas
mongosh "mongodb+srv://entropy_user:PASSWORD@cluster.mongodb.net/entropy_prime"

# Or local
mongosh entropy_prime

# View all users
db.users.find()

# Count honeypot entries
db.honeypot.countDocuments()
```

---

## Troubleshooting

### "Cannot connect to MongoDB"
Check `.env` file:
```bash
cat .env | grep MONGODB_URL
```

Is MongoDB running? (Atlas/Local/Docker)

### "User already exists"
That email is already registered. Try another email or reset the database.

### Passwords always "Invalid"
- Ensure you use `/auth/register` to create users (not manual inserts)
- Verify password was hashed with Argon2id (starts with `$argon2id$`)

### Sessions not persisting
- Check MongoDB TTL index (auto-deletes expired sessions)
- Verify `expires_at` timestamp is in future

### See complete troubleshooting guide in [MONGODB_SETUP.md](MONGODB_SETUP.md)

---

## Security Notes

✅ **Best Practices Implemented:**
- Passwords hashed with Argon2id (industry standard)
- Session tokens include HMAC signatures
- Sessions auto-expire after 30 minutes
- MongoDB passwords stored in `.env` (git-ignored)
- Biometric data (theta, entropy scores) stored separately from identity

🔐 **For Production:**
1. Use MongoDB Atlas with IP whitelisting (not "Allow Anywhere")
2. Enable TLS/SSL for database connections
3. Rotate `EP_SESSION_SECRET` and `EP_SHADOW_SECRET` regularly
4. Add HTTPS to FastAPI (use Nginx reverse proxy)
5. Monitor honeypot for attack patterns

---

## Support & Resources

- **MongoDB Atlas Free Tier**: https://www.mongodb.com/cloud/atlas
- **PyMongo Docs**: https://pymongo.readthedocs.io/
- **Motor (Async)**: https://motor.readthedocs.io/
- **FastAPI + MongoDB Tutorial**: https://fastapi.tiangolo.com/
- **Argon2id Password Hashing**: https://argon2-cffi.readthedocs.io/

---

## Summary

✨ **Your Entropy Prime now has:**
- ✅ User registration & authentication
- ✅ Persistent password storage (Argon2id)
- ✅ Session management with tokens
- ✅ Biometric profile storage
- ✅ Honeypot bot detection logging
- ✅ RL-optimized password hardening
- ✅ Free MongoDB Atlas integration
- ✅ Production-ready architecture

**Get started now:**
```bash
./setup-mongodb.sh
```

Happy securing! 🔐
