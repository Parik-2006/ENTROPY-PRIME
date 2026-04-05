# QUICK START - MongoDB Setup (5 Minutes)

## 🚀 Fastest Path: Use Interactive Script

```bash
chmod +x setup-mongodb.sh
./setup-mongodb.sh
```

This will:
1. Ask you to choose MongoDB (Atlas/Local/Docker)
2. Create `.env` file with connection details
3. Generate random secrets
4. Install all dependencies

**Done!** Your MongoDB is configured.

---

## ⚡ Manual Setup (If Script Doesn't Work)

### 1️⃣ Create `.env` File

```bash
cp .env.example .env
```

### 2️⃣ MongoDB Atlas (FREE Cloud) - Recommended

1. Visit: https://www.mongodb.com/cloud/atlas
2. Sign up (free)
3. Create M0 FREE cluster (2 min)
4. Create user: username `entropy_user`
5. Get connection string: `mongodb+srv://entropy_user:PASSWORD@cluster0.xxxxx.mongodb.net/...`
6. Add your IP to Network Access → "Allow Anywhere"
7. Edit `.env`:

```
MONGODB_URL=mongodb+srv://entropy_user:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=entropy_prime
```

### OR Local MongoDB

**Mac:**
```bash
brew install mongodb-community
brew services start mongodb-community
```

**Linux:**
```bash
sudo apt-get install mongodb-org
sudo systemctl start mongod
```

**Docker:**
```bash
docker run -d -p 27017:27017 mongo:latest
```

Edit `.env`:
```
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=entropy_prime
```

### 3️⃣ Install Dependencies

```bash
cd backend
pip install -r requirements.txt
cd ..
npm install
```

---

## ✅ Test Your Setup

```bash
cd backend
python main.py
```

**Expected output:**
```
✓ Connected to MongoDB: entropy_prime
Uvicorn running on http://127.0.0.1:8000
```

Press Ctrl+C to stop.

---

## 📝 Test User Registration

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","plain_password":"Test123!"}'
```

**Expected response:**
```json
{
  "success": true,
  "user_id": "507f1f77bcf86cd799439011",
  "email": "test@test.com",
  "message": "User registered successfully"
}
```

---

## 🎮 Run Full Stack

```bash
./start.sh
```

Then open:
- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

---

## 🗂️ What Gets Stored in MongoDB

| Collection | What | Example |
|-----------|------|---------|
| `users` | Email + hashed password | Has `password_hash: "$argon2id$..."` |
| `sessions` | Login tokens | `session_token: "ep_xyz..."` |
| `biometric_profiles` | CNN scores (theta, h_exp) | `theta: 0.85, h_exp: 0.72` |
| `honeypot` | Bot signatures | `theta: 0.05` (detected bot) |

---

## 🔍 View Data in MongoDB

### Using MongoDB Compass (Easiest)
1. Download: https://www.mongodb.com/products/compass
2. Paste your connection string
3. Browse collections visually

### Using Shell
```bash
# MongoDB Atlas
mongosh "mongodb+srv://entropy_user:PASSWORD@cluster0.xxxxx.mongodb.net/entropy_prime"

# Local
mongosh entropy_prime
```

Commands:
```javascript
// See all users
db.users.find()

// See all sessions
db.sessions.find()

// Count honeypot entries
db.honeypot.countDocuments()

// See low-confidence/bot activity
db.honeypot.find({ theta: { $lt: 0.1 } })
```

---

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot connect" | Check `.env` URL, is MongoDB running? |
| "Email already exists" | Use different email or delete user from DB |
| "Password invalid" | Must use `/auth/register`, not manual inserts |
| "Connection timeout" | Add your IP to MongoDB Atlas Network Access |

---

## 📚 Full Documentation

See [MONGODB_SETUP.md](MONGODB_SETUP.md) for deep dive.

See [MONGODB_INTEGRATION.md](MONGODB_INTEGRATION.md) for architecture.

---

## 🎯 Next Steps After Setup

1. **Pre-train RL** (optional, ~2 min):
   ```bash
   cd backend
   python train.py --episodes 100000
   ```

2. **Run frontend + backend**:
   ```bash
   ./start.sh
   ```

3. **Test login/register** on frontend

4. **Monitor MongoDB** with Compass or shell

---

## 💡 Pro Tips

- **Free MongoDB Atlas**: 512 MB storage limit  
- **Auto-cleanup**: Sessions auto-delete after 30 min
- **RL Optimization**: Password hardness adapts to biometric confidence
- **Bot Detection**: theta < 0.1 = honeypot entry

---

**That's it! MongoDB is ready to secure your passwords.** 🔐
