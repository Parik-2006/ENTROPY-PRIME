# MongoDB Free Setup Guide for Entropy Prime

This guide explains how to set up MongoDB Atlas (free cloud version) or local MongoDB for Entropy Prime.

---

## Option 1: MongoDB Atlas (Recommended - Free Cloud)

### Step 1: Create MongoDB Atlas Account
1. Go to [https://www.mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
2. Click **"Sign Up"** and create a free account
3. Verify your email

### Step 2: Create a Free Cluster
1. After login, click **"Create a Deployment"**
2. Choose **"M0 FREE"** tier
3. Select your preferred cloud provider (AWS, Google Cloud, or Azure)
4. Select your region
5. Click **"Create Deployment"** (wait ~1-2 minutes)

### Step 3: Create Database User
1. In the left sidebar, click **"Security"** > **"Database Access"**
2. Click **"Add New Database User"**
3. Choose **"Password"** authentication
4. Set username: `entropy_user`
5. Set password: Create a strong password (save it!)
6. Select **"Built-in Role"** > **"Read and write to any database"**
7. Click **"Add User"**

### Step 4: Set Network Access
1. In left sidebar, click **"Security"** > **"Network Access"**
2. Click **"Add IP Address"**
3. Choose **"Allow Access from Anywhere"** (for development)
   - For production, add specific IPs
4. Click **"Confirm"**

### Step 5: Get Connection String
1. Go back to the **"Deployments"** section
2. Click **"Connect"** on your cluster
3. Choose **"Python"**
4. Copy the connection string (looks like):
   ```
   mongodb+srv://entropy_user:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
5. Replace `<password>` with your database password

### Step 6: Create `.env` File
In the root of your project, create a `.env` file:

```bash
# MongoDB Atlas Connection
MONGODB_URL=mongodb+srv://entropy_user:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=entropy_prime

# Backend Secrets
EP_SESSION_SECRET=a0bb498cf8819aac115f0deeb8d89b18478447e5b18270e8122f2e37d86f80eb
EP_SHADOW_SECRET=15b2baa3e7234c3ea289e16c7eccb3353f47768f26d85790b2f50ecbd6e17d38

# Optional: Pre-trained RL Model
EP_RL_CHECKPOINT=./checkpoints/governor.pt
```

**Replace:**
- `YOUR_PASSWORD` → your database user password
- `cluster0.xxxxx` → your actual cluster URL

---

## Option 2: Local MongoDB (For Development)

### Linux/Mac Installation

**Using Homebrew (Mac):**
```bash
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community
```

**Using apt (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install -y mongodb-org
sudo systemctl start mongod
sudo systemctl enable mongod
```

**Using Docker (Any OS):**
```bash
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

### Create `.env` File
```bash
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=entropy_prime

# Backend Secrets
EP_SESSION_SECRET=your-random-secret-key-here
EP_SHADOW_SECRET=your-random-shadow-secret-here
```

---

## Step 7: Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

This installs:
- `pymongo` - MongoDB driver
- `motor` - Async MongoDB support
- `python-dotenv` - Load `.env` variables

---

## Step 8: Run the Backend

```bash
cd backend
python main.py
```

Or with uvicorn:
```bash
uvicorn main:app --reload --port 8000
```

You should see:
```
✓ Connected to MongoDB: entropy_prime
✓ Entropy Prime backend initialized with MongoDB
```

---

## Step 9: Test MongoDB Integration

### Create a Test User

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "plain_password": "TestPassword123!"
  }'
```

Expected response:
```json
{
  "success": true,
  "user_id": "ObjectId",
  "email": "test@example.com",
  "session_token": "...",
  "message": "User registered successfully"
}
```

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "plain_password": "TestPassword123!"
  }'
```

---

## MongoDB Collections

Your `entropy_prime` database will automatically create these collections:

| Collection | Purpose |
|-----------|---------|
| `users` | User accounts with emails and hashed passwords |
| `sessions` | Active user sessions with tokens |
| `biometric_profiles` | Biometric data per user (CNN dwell, flight, etc.) |
| `honeypot` | Bot signatures and suspicious activity |

---

## Accessing MongoDB

### Using MongoDB Compass (GUI)
1. Download [MongoDB Compass](https://www.mongodb.com/products/compass)
2. Paste your connection string from Step 5
3. Browse collections and data visually

### Using MongoDB Shell
```bash
# Atlas
mongosh "mongodb+srv://entropy_user:PASSWORD@cluster0.xxxxx.mongodb.net/entropy_prime"

# Local
mongosh entropy_prime
```

Commands:
```javascript
// View all users
db.users.find()

// View a user's sessions
db.sessions.find({ user_id: "ObjectId" })

// Count honeypot entries
db.honeypot.countDocuments()

// View bot signatures
db.honeypot.find({ theta: { $lt: 0.1 } }).limit(5)
```

---

## API Endpoints With MongoDB

### Authentication
- `POST /auth/register` - Create new user
- `POST /auth/login` - Login and get session
- `POST /auth/logout` - Invalidate session

### Password Hashing
- `POST /password/hash` - Hash password with RL-selected Argon2id
- `POST /password/verify` - Verify password

### Session Management
- `POST /session/verify` - Check session trust score
- `POST /score` - Submit biometric score (stores in honeypot if θ < 0.1)

### Data Retrieval
- `GET /honeypot/signatures` - Get bot signatures (from MongoDB + in-memory)
- `GET /health` - Server status and RL step count

---

## Troubleshooting

### Connection Error: "Cannot connect to MongoDB"
- **Check**: Is MongoDB running?
  ```bash
  # Local: Check if mongod is running
  ps aux | grep mongod
  
  # Docker: Check if container is running
  docker ps | grep mongodb
  ```
- **Check**: Is your `.env` file correct?
  ```bash
  cat .env
  ```

### All Passwords Show as "Invalid" After Login Fails
- Check password hashing: Ensure you used `/auth/register` to create users
- Check Argon2 params: May take 1-2 seconds to hash

### MongoDB Atlas Connection Timeout
- **Check**: Add your IP to Network Access (Step 4)
- **Check**: Use correct password in connection string
- **Check**: Allow some time for cluster initialization

### Honeypot Data Not Storing
- Check MongoDB logs:
  ```bash
  # Local MongoDB
  sudo tail -f /var/log/mongodb/mongod.log
  ```
- Verify backend is connected (should log "✓ Connected to MongoDB")

---

## Next Steps

1. **Pre-train RL Model** (optional but recommended):
   ```bash
   cd backend
   python train.py --episodes 100000 --out ../checkpoints/governor.pt
   export EP_RL_CHECKPOINT=../checkpoints/governor.pt
   ```

2. **Run Full Stack**:
   ```bash
   ./start.sh  # Or create sessions manually
   ```

3. **Production Setup**:
   - Use MongoDB Atlas with IP whitelist
   - Enable SSL/TLS for connections
   - Use environment variables for secrets
   - Add HTTPS to FastAPI (use Nginx/reverse proxy)

---

## Free MongoDB Atlas Limits

| Feature | Limit |
|---------|-------|
| Storage | 512 MB |
| Databases | Unlimited |
| Collections | Unlimited |
| Network Connections | Shared Atlas cluster |

**Upgrade anytime** if you exceed limits!

---

## Support Resources

- MongoDB Atlas Docs: https://docs.atlas.mongodb.com/
- PyMongo Docs: https://pymongo.readthedocs.io/
- Motor (Async): https://motor.readthedocs.io/
- FastAPI + MongoDB: https://fastapi.tiangolo.com/

---

**Happy coding with Entropy Prime + MongoDB! 🚀**
