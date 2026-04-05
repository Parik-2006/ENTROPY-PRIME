# Entropy Prime API Documentation

## Complete API Reference

All endpoints are now fully implemented and ready to use!

---

## ✅ Authentication APIs

### 1. Register User
```bash
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "plain_password": "SecurePass123!"
}
```

**Response:**
```json
{
  "success": true,
  "user_id": "507f1f77bcf86cd799439011",
  "email": "user@example.com",
  "session_token": "...",
  "message": "User registered successfully"
}
```

---

### 2. Login User
```bash
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "plain_password": "SecurePass123!"
}
```

**Response:**
```json
{
  "success": true,
  "session_token": "...",
  "user_id": "507f1f77bcf86cd799439011",
  "email": "user@example.com",
  "security_level": "standard"
}
```

---

### 3. Logout User
```bash
POST /auth/logout
Content-Type: application/json

{
  "session_token": "..."
}
```

---

## ✅ Phase 1: Biometric Feature Extraction (CNN)

### 4. Extract Biometric Features (1D CNN)
```bash
POST /biometric/extract
Content-Type: application/json

{
  "raw_signal": [0.1, 0.2, 0.15, 0.3, 0.25, 0.18, 0.22, 0.19, 0.21, 0.23]
}
```

**Response:**
```json
{
  "success": true,
  "features": [0.456, 0.234, 0.567, ..., 0.123],
  "dim": 32
}
```

---

### 5. Get User's Biometric Profile
```bash
GET /biometric/profile/507f1f77bcf86cd799439011
```

**Response:**
```json
{
  "user_id": "507f1f77bcf86cd799439011",
  "profile": {
    "_id": "...",
    "user_id": "507f1f77bcf86cd799439011",
    "samples": [...],
    "avg_theta": 0.75,
    "avg_h_exp": 0.68,
    "last_updated": 1712282400
  }
}
```

---

## ✅ Phase 2: RL Governor Decision (DQN)

### 6. Score Submission & DQN Action
```bash
POST /score
Content-Type: application/json

{
  "theta": 0.85,
  "h_exp": 0.70,
  "server_load": 0.45,
  "user_agent": "Mozilla/5.0...",
  "latent_vector": [0.1, 0.2, ..., 0.3]
}
```

**Response:**
```json
{
  "session_token": "...",
  "shadow_mode": false,
  "argon2_params": {"m": 131072, "t": 3, "p": 4},
  "humanity_score": 0.85,
  "entropy_score": 0.70,
  "action_label": "standard"
}
```

---

### 7. Get DQN Action for State
```bash
POST /models/dqn/action
Content-Type: application/json

{
  "state": [0.85, 0.70, 0.45]
}
```

**Response:**
```json
{
  "action": 1,
  "action_label": "standard",
  "state": [0.85, 0.70, 0.45]
}
```

---

### 8. Hash Password with RL-Selected Argon2id
```bash
POST /password/hash
Content-Type: application/json

{
  "plain_password": "SecurePass123!",
  "theta": 0.85,
  "h_exp": 0.70
}
```

**Response:**
```json
{
  "hash": "$argon2id$v=19$m=131072,t=3,p=4$...",
  "action": "standard",
  "elapsed_ms": 125.45,
  "argon2_params": {"m": 131072, "t": 3, "p": 4}
}
```

---

### 9. Verify Password
```bash
POST /password/verify
Content-Type: application/json

{
  "plain_password": "SecurePass123!",
  "stored_hash": "$argon2id$v=19$m=131072,t=3,p=4$..."
}
```

**Response:**
```json
{
  "valid": true
}
```

---

## ✅ Phase 3: Honeypot & Deceiver (MAB)

### 10. Select MAB Arm (Deceiver Strategy)
```bash
POST /models/mab/select
```

**Response:**
```json
{
  "selected_arm": 1,
  "n_arms": 3,
  "arm_values": [0.45, 0.78, 0.52]
}
```

---

### 11. Update MAB with Reward
```bash
POST /models/mab/update?arm=1&reward=0.95
```

**Response:**
```json
{
  "success": true,
  "arm": 1,
  "reward": 0.95,
  "updated_values": [0.45, 0.82, 0.52]
}
```

---

### 12. Get Honeypot Signatures
```bash
GET /honeypot/signatures
```

**Response:**
```json
{
  "signatures": [
    {
      "ts": 1712282400,
      "theta": 0.05,
      "user_agent": "SqlMap/1.0",
      "ip": "192.168.1.100"
    },
    ...
  ],
  "count": 42
}
```

---

### 13. Admin Honeypot Dashboard
```bash
GET /admin/honeypot/dashboard
```

**Response:**
```json
{
  "total_count": 42,
  "recent_signatures": [...],
  "in_memory_count": 5,
  "timestamp": 1712282400
}
```

---

## ✅ Phase 4: Session Watchdog (PPO)

### 14. Verify Session (Watchdog)
```bash
POST /session/verify
Content-Type: application/json

{
  "session_token": "...",
  "user_id": "507f1f77bcf86cd799439011",
  "latent_vector": [0.1, 0.2, ..., 0.3],
  "e_rec": 0.15,
  "trust_score": 0.85
}
```

**Response:**
```json
{
  "action": "ok",
  "trust_score": 0.85,
  "e_rec": 0.15
}
```

---

### 15. Evaluate Session with PPO
```bash
POST /models/ppo/evaluate
Content-Type: application/json

{
  "state": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
}
```

**Response:**
```json
{
  "state": [...],
  "action_probabilities": [0.2, 0.5, 0.3],
  "recommended_action": 1
}
```

---

## ✅ Admin & Health APIs

### 16. Get All Models Status
```bash
GET /admin/models-status
```

**Response:**
```json
{
  "models": {
    "dqn": {
      "status": "loaded",
      "type": "Deep Q-Network",
      "state_dim": 3,
      "action_dim": 4,
      "phase": "Phase 2"
    },
    "mab": {
      "status": "loaded",
      "type": "Multi-Armed Bandit",
      "n_arms": 3,
      "arm_values": [0.45, 0.78, 0.52],
      "phase": "Phase 3"
    },
    "ppo": {
      "status": "loaded",
      "type": "Proximal Policy Optimization",
      "state_dim": 10,
      "action_dim": 3,
      "phase": "Phase 4"
    },
    "cnn1d": {
      "status": "loaded",
      "type": "1D CNN",
      "output_dim": 32,
      "phase": "Phase 1"
    }
  },
  "timestamp": 1712282400
}
```

---

### 17. Health Check
```bash
GET /health
```

**Response:**
```json
{
  "status": "ok"
}
```

---

## 🚀 Quick Test (Copy & Paste)

```bash
# Health check
curl http://localhost:8000/health

# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","plain_password":"Pass123!"}'

# Score biometric
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"theta":0.85,"h_exp":0.70,"server_load":0.45}'

# Get model status
curl http://localhost:8000/admin/models-status

# Get honeypot dashboard
curl http://localhost:8000/admin/honeypot/dashboard

# Extract features with 1D CNN
curl -X POST http://localhost:8000/biometric/extract \
  -H "Content-Type: application/json" \
  -d '{"raw_signal":[0.1,0.2,0.15,0.3,0.25,0.18,0.22,0.19,0.21,0.23]}'

# DQN action
curl -X POST http://localhost:8000/models/dqn/action \
  -H "Content-Type: application/json" \
  -d '{"state":[0.85,0.70,0.45]}'

# MAB select arm
curl -X POST http://localhost:8000/models/mab/select

# PPO evaluate
curl -X POST http://localhost:8000/models/ppo/evaluate \
  -H "Content-Type: application/json" \
  -d '{"state":[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0]}'
```

---

## Summary: All 17 APIs ✅

| # | Endpoint | Method | Purpose |
|---|----------|--------|---------|
| 1 | `/auth/register` | POST | Register new user |
| 2 | `/auth/login` | POST | Login user |
| 3 | `/auth/logout` | POST | Logout user |
| 4 | `/biometric/extract` | POST | Extract CNN features (Phase 1) |
| 5 | `/biometric/profile/{user_id}` | GET | Get user biometric profile |
| 6 | `/score` | POST | Score request (Phase 2 DQN) |
| 7 | `/models/dqn/action` | POST | DQN action for state |
| 8 | `/password/hash` | POST | Hash with RL Argon2id |
| 9 | `/password/verify` | POST | Verify password |
| 10 | `/models/mab/select` | POST | Select MAB arm (Phase 3) |
| 11 | `/models/mab/update` | POST | Update MAB reward |
| 12 | `/honeypot/signatures` | GET | Get honeypot bot signatures |
| 13 | `/admin/honeypot/dashboard` | GET | Admin honeypot dashboard |
| 14 | `/session/verify` | POST | Verify session (Phase 4 PPO) |
| 15 | `/models/ppo/evaluate` | POST | PPO evaluate session |
| 16 | `/admin/models-status` | GET | Get all models status |
| 17 | `/health` | GET | Health check |

---

**All APIs are production-ready and connected to MongoDB, all 4 models (DQN, MAB, PPO, 1D CNN), and the honeypot!**
