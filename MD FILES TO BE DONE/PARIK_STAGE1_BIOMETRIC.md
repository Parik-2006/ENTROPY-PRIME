# PARIKSHITH - STAGE 1: BIOMETRIC PROFILING & ANOMALY DETECTION
**Branch:** `parik-stage1-biometric-advanced`
**Assigned Stage:** Stage 1 - Biometric Profiling & User Behavior Analysis
**Role:** Implement user profiling, behavioral analysis, biometric anomaly detection, and real-time threat scoring

---

## 📋 5 UNIQUE IDEAS FROM IEEE PAPERS FOR STAGE 1

### Idea 1: **Behavioral Biometric Analysis System (BBAS)**
**IEEE Reference:** Based on "Behavioral Biometrics for Continuous Authentication" papers
- **Features:**
  - Keystroke dynamics analysis (typing speed, rhythm, patterns)
  - Mouse movement patterns (speed, acceleration, pressure)
  - Device interaction profiling
  - Gait analysis if mobile device
  - Voice pattern recognition (if available)
  - Multi-modal biometric fusion

### Idea 2: **Real-Time User Profiling & Anomaly Baseline (RUPAB)**
**IEEE Reference:** From "Online Behavioral Profiling" research
- **Features:**
  - Build behavioral baseline from first 30 days
  - Continuous profile updates
  - Time-based baseline variations (work hours vs off-hours)
  - Seasonal pattern detection
  - Deviation threshold calculation
  - Outlier detection using Isolation Forest

### Idea 3: **Risk Scoring & Feature Importance Engine (RSFIE)**
**IEEE Reference:** Based on "Anomaly Scoring in User Behavior"
- **Features:**
  - Multi-factor risk scoring (10+ features)
  - Feature importance ranking
  - Adaptive weighting based on historical accuracy
  - Confidence interval calculation
  - Risk explosion detection
  - Trend analysis (is risk increasing?)

### Idea 4: **Contextual User Behavior Analysis (CUBA)**
**IEEE Reference:** From "Context-Aware Anomaly Detection"
- **Features:**
  - Time context (working hours, lunch, after-hours)
  - Location context (office, home, traveling)
  - Device context (company device, BYOD, new device)
  - Role-based expectations
  - Peer comparison (similar users baseline)
  - Calendar-aware (meetings, time off)

### Idea 5: **Adaptive Learning & Model Retraining (ALMR)**
**IEEE Reference:** Based on "Concept Drift in Anomaly Detection"
- **Features:**
  - Monthly model retraining with new data
  - Automatic feature engineering
  - Concept drift detection
  - User feedback incorporation
  - False positive feedback loop
  - Graceful model degradation

---

## 🐳 DOCKER STRUCTURE FOR STAGE 1

### What is Docker? (Simple Explanation)
**Docker = Containerization Tool**
- Think of Docker as a **box** that contains everything your Stage 1 service needs
- Box includes: Python, libraries, biometric analysis code, everything
- Stage 1 is the **first line of defense** - analyzes user behavior before anything else
- Docker ensures consistent environment across your team

### What You Need to Create:
1. **Dockerfile** = Recipe for creating the biometric box
2. **requirements-stage1.txt** = List of Python packages
3. **Docker Compose Configuration** = Settings for running with databases
4. **Volume Folders** = Folders for models, profiles, logs

---

### Step 1: Create Requirements File
**File: `backend/requirements-stage1.txt`**
```
torch==2.0.1
torchvision==0.15.2
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.4.2
mongodb==4.4.1
pytest==7.4.3
python-multipart==0.0.6
python-dotenv==1.0.0
redis==5.0.1
scikit-learn==1.3.2
pandas==2.1.1
numpy==1.24.3
scipy==1.11.4
requests==2.31.0
aioredis==2.0.1
python-jose==3.3.0
```

### Step 2: Create Dockerfile
**File: `backend/Dockerfile-stage1`**
```dockerfile
# Dockerfile for Biometric Profiling Service
FROM python:3.11-slim

WORKDIR /app

# Copy requirements first
COPY backend/requirements-stage1.txt .
RUN pip install --no-cache-dir -r requirements-stage1.txt

# Copy your stage 1 biometric code
COPY backend/models/stage1_biometric.py ./models/
COPY backend/services/biometric_services.py ./services/
COPY backend/pipeline/stage1_biometric.py ./pipeline/
COPY backend/main.py ./

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8001/health')"

# Expose port
EXPOSE 8001

# Start command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Step 3: Add to Docker Compose File
**File: `docker-compose.yml` (Add this service to existing file)**
```yaml
biometric-stage1:
  build:
    context: .                          # Build from current folder
    dockerfile: backend/Dockerfile-stage1  # Use this recipe
  container_name: entropy-biometric-stage1  # Name your container
  
  # Port for Stage 1 API
  ports:
    - "8001:8001"                      # Biometric Analysis API
  
  # Environment variables - Settings for biometric analysis
  environment:
    - MONGODB_URI=mongodb://mongodb:27017
    - REDIS_URL=redis://redis:6379
    - LOG_LEVEL=INFO
    - BASELINE_DAYS=30                 # Days to establish baseline
    - ANOMALY_THRESHOLD=0.7            # Anomaly sensitivity
    - STAGE=1
    - SERVICE_NAME=biometric
  
  # Services that must start before Stage 1
  depends_on:
    - mongodb
    - redis
  
  # Folders that store data outside container
  volumes:
    - ./user-profiles:/app/profiles    # User behavior profiles
    - ./checkpoints:/app/checkpoints   # ML models
    - ./logs/stage1:/app/logs          # Biometric analysis logs
    - ./backend:/app/backend           # Live code sync (dev)
  
  # Network - connects to other services
  networks:
    - security-net
  
  # Resource limits
  deploy:
    resources:
      limits:
        cpus: '2'                      # Can use up to 2 CPUs
        memory: 4G                     # Can use up to 4GB RAM
      reservations:
        cpus: '1'
        memory: 2G
  
  # Restart policy
  restart: unless-stopped
```

### Step 4: Create Volume Folders
**Run these commands in PowerShell to create folders Docker needs:**
```powershell
# Create user profiles folder
New-Item -ItemType Directory -Path "user-profiles" -Force

# Create checkpoint folder for ML models
New-Item -ItemType Directory -Path "checkpoints" -Force

# Create logs folder for Stage 1
New-Item -ItemType Directory -Path "logs/stage1" -Force

# Give permissions
icacls "user-profiles" /grant:r "%USERNAME%:(OI)(CI)F"
icacls "checkpoints" /grant:r "%USERNAME%:(OI)(CI)F"
icacls "logs" /grant:r "%USERNAME%:(OI)(CI)F"
```

### Step 5: Create .env File for Configuration
**File: `.env` (in root folder)**
```env
# Stage 1 Biometric Settings
STAGE_1_PORT=8001
BASELINE_DAYS=30
ANOMALY_THRESHOLD=0.7
KEYSTROKE_WEIGHT=0.2
MOUSE_WEIGHT=0.2
DEVICE_WEIGHT=0.15
TIME_WEIGHT=0.15
LOCATION_WEIGHT=0.15
CONTEXT_WEIGHT=0.15

# Database
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=entropy_stage1

# Redis
REDIS_URL=redis://redis:6379
REDIS_DB=0

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_RETENTION_DAYS=90

# Feature Engineering
AUTO_FEATURE_ENGINEERING=true
FEATURE_SELECTION=mutual_information
```

---

## 🚀 DOCKER WORKFLOW - STEP BY STEP

### What Docker Does:
1. **Build** = Creates a box with Python, ML libraries, and your biometric code
2. **Run** = Starts Stage 1 service that analyzes user behavior
3. **Connect** = Connects to MongoDB (user profiles) and Redis (cache)
4. **Persist** = Saves user profiles and analysis logs forever

### Workflow for Stage 1:

#### Step A: Build the Docker Image
**What this does:** Creates the box with all biometric analysis libraries

```powershell
# Navigate to project folder
cd p:\ENTROPY PRIME

# Build Stage 1 image
docker build -f backend/Dockerfile-stage1 -t entropy-biometric:latest .

# Check if build succeeded
docker images | grep entropy-biometric
```

**If build fails:**
- Check error message carefully
- Make sure `requirements-stage1.txt` exists
- Check file paths are correct
- scikit-learn sometimes has issues on Windows (try pip cache clean)

#### Step B: Start All Services with Docker Compose
**What this does:** Starts Stage 1 + MongoDB + Redis + other stages

```powershell
# Start all services in background
docker-compose -f docker-compose.yml up -d

# See which containers are running
docker-compose ps

# Check if Stage 1 is healthy
docker ps | grep biometric
```

**Expected output:**
```
NAME                        STATUS          PORTS
entropy-biometric-stage1    Up 5 seconds    0.0.0.0:8001->8001/tcp
```

#### Step C: Check Logs to See if Working
**What this does:** Shows biometric analysis logs in real-time

```powershell
# See last 50 lines of logs
docker logs -f entropy-biometric-stage1 --tail 50

# See logs since 5 minutes ago
docker logs --since 5m entropy-biometric-stage1

# Check for errors
docker logs entropy-biometric-stage1 | findstr "ERROR"
```

#### Step D: Test if Biometric Service Works
**What this does:** Tests if service responds to profile requests

```powershell
# Test health endpoint
curl http://localhost:8001/health

# Test getting user profile
curl http://localhost:8001/profile/test_user

# Test uploading biometric data
$body = @{
    user_id = "test_user"
    keystroke_speed = 75
    mouse_acceleration = 120
    device_id = "laptop_001"
    timestamp = "2024-05-20T10:30:00Z"
} | ConvertTo-Json

curl -X POST http://localhost:8001/analyze `
  -Header "Content-Type: application/json" `
  -Body $body
```

#### Step E: View User Profiles in MongoDB
**What this does:** Shows user behavior baselines stored in database

```powershell
# Go inside MongoDB
docker exec -it mongodb mongosh

# Inside MongoDB shell:
use entropy_stage1
db.user_profiles.find().pretty()
db.biometric_baselines.find().limit(5).pretty()
db.anomaly_logs.count()
exit
```

#### Step F: Check User Profile Files
**What this does:** Shows saved biometric profiles

```powershell
# See what profiles are saved
Get-ChildItem -Path "user-profiles"

# View a specific user profile
Get-Content user-profiles/test_user_profile.json | ConvertFrom-Json | Format-Table

# See profile statistics
(Get-ChildItem -Path "user-profiles" | Measure-Object).Count
```

#### Step G: Test Profile Analysis
**What this does:** Manually test biometric analysis on a user

```powershell
# Go inside Stage 1 container
docker exec -it entropy-biometric-stage1 bash

# Inside container:
# Test if libraries work
python -c "import sklearn; print('sklearn OK')"

# Run test analysis
python -c "from models.stage1_biometric import analyze_biometrics; print('Module loaded')"

# Exit
exit
```

#### Step H: Train Model with Sample Data
**What this does:** Create initial user profiles for testing

```powershell
# Generate sample biometric data
docker exec entropy-biometric-stage1 python -c "
from services.biometric_services import generate_sample_profile
profile = generate_sample_profile('test_user', days=30)
print('Profile created:', profile['user_id'])
"

# Check if profile was created
docker exec entropy-biometric-stage1 ls -la /app/profiles/
```

#### Step I: Rebuild After Code Changes
**What this does:** Updates Stage 1 with your new biometric analysis code

```powershell
# Stop Stage 1
docker-compose stop biometric-stage1

# Remove old container
docker-compose rm biometric-stage1

# Rebuild
docker build -f backend/Dockerfile-stage1 -t entropy-biometric:latest .

# Start new container
docker-compose up -d biometric-stage1

# Check if working
docker logs -f entropy-biometric-stage1
```

---

## 📊 DOCKER NETWORKING - How Stage 1 Sends Data to Other Stages

### Network Architecture:
```
┌─────────────────────────────────────────────────────────────┐
│         Docker Network (security-net)                       │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Stage 1: Biometric ◄─ You work here                │ │
│  │ (analyzes user behavior)                           │ │
│  │ ↓ (sends: biometric_score, anomaly_flags)          │ │
│  └───────────────────────────────────────────────────────┘ │
│                  ↓                                           │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Stage 2: Honeypot (port 8002)                     │ │
│  │ ↓ (sends: threat_score, attack_data)              │ │
│  └───────────────────────────────────────────────────────┘ │
│                  ↓                                           │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Stage 3: Governor (port 8003)                     │ │
│  │ ↓ (sends: decision, confidence)                   │ │
│  └───────────────────────────────────────────────────────┘ │
│                  ↓                                           │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Stage 4: Watchdog (port 8004)                     │ │
│  │ (executes enforcement)                             │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │ MongoDB (users)  │  │ Redis (cache)   │               │
│  └──────────────────┘  └──────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### How Stage 1 Calls Other Services:
**Inside Docker, use container names:**

```python
import requests

# Stage 1 analyzing user behavior
user_profile = get_user_profile("user123")
biometric_score = analyze_biometrics(user_profile)

# Send to Stage 2 for threat analysis
stage2_response = requests.post(
    'http://honeypot-stage2:8002/analyze',
    json={
        'user_id': 'user123',
        'biometric_score': biometric_score,
        'stage1_data': user_profile
    }
)
```

---

## 🔧 COMMON DOCKER COMMANDS FOR STAGE 1

| Command | What It Does |
|---------|----------|
| `docker build -f backend/Dockerfile-stage1 -t entropy-biometric:latest .` | Create image |
| `docker-compose up -d biometric-stage1` | Start Stage 1 |
| `docker logs -f entropy-biometric-stage1` | Watch logs |
| `docker exec -it entropy-biometric-stage1 bash` | Go inside |
| `docker-compose ps biometric-stage1` | Check status |
| `docker volume ls` | See all storage |
| `docker inspect entropy-biometric-stage1` | See details |
| `docker stats entropy-biometric-stage1` | See CPU/Memory usage |

---

## ⚠️ TROUBLESHOOTING DOCKER FOR STAGE 1

### Problem: Port 8001 Already in Use
```powershell
# Find what's using port 8001
netstat -ano | findstr :8001

# Kill it (replace PID with number from above)
taskkill /PID <PID> /F

# Or change port in docker-compose.yml:
# ports:
#   - "8002:8001"  (use 8002 instead)
```

### Problem: scikit-learn Installation Fails
```powershell
# Common on Windows - solution 1
pip install --only-binary :all: scikit-learn

# Solution 2: Use pip upgrade
pip install --upgrade setuptools wheel

# Solution 3: In Dockerfile, add system libraries
# RUN apt-get install -y python3-dev build-essential
```

### Problem: MongoDB Connection Error
```powershell
# Check if MongoDB is running
docker-compose ps | grep mongodb

# Try connecting manually
docker exec -it mongodb mongosh
show databases
exit
```

### Problem: User Profiles Not Being Saved
```powershell
# Check if user-profiles folder exists
Get-ChildItem -Path "user-profiles"

# Check MongoDB
docker exec -it mongodb mongosh
use entropy_stage1
db.user_profiles.count()
exit

# Check logs for errors
docker logs entropy-biometric-stage1 | findstr "ERROR"
```

---

## 📋 DOCKER BEST PRACTICES FOR STAGE 1

✅ **DO:**
- Build baselines for 30 days before using
- Store all user profiles (privacy-aware)
- Log all biometric analyses
- Monitor anomaly detection accuracy
- Update baselines monthly
- Test with synthetic data first
- Keep old profiles for historical comparison

❌ **DON'T:**
- Store plain passwords (use hashes)
- Delete user profile history
- Process PII without encryption
- Run without health checks
- Skip biometric analysis
- Hardcode thresholds
- Ignore false positives

---

## ✅ DOCKER CHECKLIST - Before Starting Implementation

- [ ] Docker Desktop is installed and running
- [ ] docker-compose.yml updated with biometric-stage1 service
- [ ] Dockerfile-stage1 created
- [ ] requirements-stage1.txt created
- [ ] Volume folders created (user-profiles, checkpoints, logs/stage1)
- [ ] .env file has Stage 1 settings
- [ ] Health check configured
- [ ] Test that API endpoint responds
- [ ] MongoDB is running
- [ ] Redis is running

---

## 🤖 10 CLAUDE PROMPTS FOR PARIKSHITH - STAGE 1 IMPLEMENTATION

### Prompt 1: Core Biometric Profiling Model
**File Location:** `backend/models/stage1_biometric.py`
```
Create a biometric profiling PyTorch model for Stage 1:
1. Input features:
   - Keystroke dynamics: typing_speed (0-200 WPM), error_rate (0-1), key_press_duration
   - Mouse patterns: movement_speed (0-500 px/s), acceleration, jitter
   - Device info: device_id, OS, browser, screen_resolution
   - Temporal: hour_of_day (0-23), day_of_week (0-6), is_business_hours (bool)
   - Interaction: time_on_page, clicks_per_minute, scroll_speed

2. Output:
   - User profile embedding (128-dim vector)
   - Baseline behavior model per user
   - Confidence scores for profile

3. Model architecture:
   - Input layer: concatenate all features (normalize to 0-1)
   - Feature extraction: 2 dense layers (256 → 128 neurons)
   - Embedding layer: 128 dimensions
   - Bottleneck layer: 64 dimensions (captures essence of user behavior)
   - Output: user profile embedding

4. Key functions:
   - build_profile(user_id, biometric_data_list) -> profile_embedding
   - get_user_baseline(user_id) -> baseline_vector
   - extract_features(raw_biometric_data) -> normalized_features
   - save_profile(user_id, profile) -> None
   - load_profile(user_id) -> profile_embedding

5. Profile structure:
   {
     "user_id": "string",
     "embedding": [128 floats],
     "baseline_mean": [10 floats for main features],
     "baseline_std": [10 floats for variability],
     "samples_count": 500,
     "created_date": "ISO-8601",
     "last_updated": "ISO-8601",
     "feature_importance": {...}
   }

Use PyTorch with persistent model checkpointing.
```

### Prompt 2: Real-Time Anomaly Detection Engine
**File Location:** `backend/models/stage1_biometric.py` (anomaly_module)
```
Build real-time anomaly detection system for Stage 1:
1. Baseline calculation:
   - For each user, calculate baseline from first 30 days
   - Calculate mean and std deviation for each feature
   - Identify multi-modal behaviors (different work patterns)
   - Use Gaussian mixture model for complex behaviors

2. Real-time anomaly scoring:
   - For each new activity, compare against baseline
   - Calculate z-score: (value - mean) / std_dev
   - Features to compare:
     * Keystroke speed deviation
     * Mouse movement patterns
     * Typing errors (unexpected increase)
     * Time-of-day patterns (working at 3 AM?)
     * Device anomalies (new device, unusual OS)

3. Isolation Forest for outlier detection:
   - Also use Isolation Forest in parallel to z-score
   - Detect complex anomalies that z-score misses
   - Combine both methods: if either flags anomaly, investigate

4. Anomaly confidence:
   - How sure are we this is anomalous?
   - Use ensemble of methods (z-score, IF, statistical test)
   - Output: anomaly_score (0-1), confidence (0-1)

5. Output structure:
   {
     "user_id": "string",
     "anomaly_score": 0.85,
     "confidence": 0.92,
     "anomaly_flags": [
       "keystroke_speed_unusual",
       "late_night_activity",
       "new_device"
     ],
     "component_scores": {
       "keystroke": 0.9,
       "mouse": 0.6,
       "device": 0.95,
       "timing": 0.7
     },
     "historical_baseline": {...},
     "is_anomalous": true
   }

6. Temporal analysis:
   - Is anomaly increasing over time?
   - Trend: normal → warning → alert
   - Rate of change matters (sudden vs gradual)

Use scikit-learn Isolation Forest + statistical methods.
```

### Prompt 3: User Profile Storage & Retrieval Service
**File Location:** `backend/services/biometric_services.py`
```
Create user profile management service:
1. Profile storage operations:
   - save_user_profile(user_id, profile_data) -> profile_id
   - load_user_profile(user_id) -> profile_data
   - update_user_baseline(user_id, new_data) -> updated_profile
   - get_profile_history(user_id, limit=100) -> List[profiles]

2. Baseline management:
   - create_baseline(user_id, training_data_30_days) -> baseline
   - update_baseline(user_id, new_sample) -> updated_baseline
   - get_baseline(user_id) -> baseline_stats
   - baseline_ready(user_id) -> bool (true if >30 days data)

3. Database operations:
   - Use MongoDB for profile storage
   - Collections:
     * user_profiles: main profile data
     * baselines: statistical baselines per user
     * biometric_history: daily aggregations
     * anomaly_logs: flagged anomalies

4. Caching strategy:
   - Cache hot profiles in Redis (recently active users)
   - TTL: 24 hours for active users
   - Update cache when profile changes
   - Fall back to MongoDB if cache miss

5. Operations:
   - Store with timestamp for tracking
   - Support versioning of profiles
   - Allow historical queries
   - Enable user privacy features

6. Response format:
   {
     "user_id": "string",
     "profile": {...},
     "baseline_days": 30,
     "baseline_ready": true,
     "last_activity": "ISO-8601",
     "profile_version": 1,
     "cached": true/false
   }

Use MongoDB and Redis integration.
```

### Prompt 4: Behavioral Anomaly Scoring System
**File Location:** `backend/models/stage1_biometric.py` (scoring_module)
```
Create comprehensive behavioral risk scoring:
1. Risk factors to evaluate:
   - Keystroke anomaly: 25% weight
   - Device anomaly: 25% weight
   - Timing anomaly: 20% weight
   - Location anomaly: 15% weight
   - Context anomaly: 15% weight

2. Keystroke analysis:
   - Typing speed deviation from baseline
   - Error rate increase (hunt-and-peck vs normal)
   - Key press duration patterns
   - Dwell time between keys
   - Pressure if available (touch devices)

3. Device anomalies:
   - Unknown device (new device)
   - Device from different location
   - Unusual OS/browser combo
   - Screen resolution changes
   - IP address change

4. Timing anomalies:
   - Access outside normal work hours
   - Weekend activity (if not normal)
   - Holiday activity
   - After-hours access (unusual)
   - Access pattern breaking routine

5. Location anomalies:
   - IP geolocation outside normal area
   - Impossible travel (location change too fast)
   - VPN/Proxy detection
   - Mobile vs desktop mismatch

6. Context anomalies:
   - User role expectations (accountant accessing code?)
   - Data sensitivity (accessing what they shouldn't)
   - Behavioral escalation (slow accumulation)
   - Peer comparison (very different from similar users)

7. Scoring formula:
   - Calculate z-score for each factor
   - Weight by importance
   - Apply confidence multiplier
   - Combine with historical trend
   - Final score: 0-1 range

8. Output:
   {
     "risk_score": 0.72,
     "confidence": 0.88,
     "risk_level": "medium",
     "component_breakdown": {
       "keystroke": 0.8,
       "device": 0.6,
       "timing": 0.9,
       "location": 0.4,
       "context": 0.5
     },
     "trend": "increasing",
     "supporting_evidence": [...]
   }

Include trend analysis and temporal patterns.
```

### Prompt 5: Stage 1 Pipeline Orchestration
**File Location:** `backend/pipeline/stage1_biometric.py`
```
Create Stage 1 orchestration pipeline:
1. Main orchestration flow:
   - receive_biometric_event(raw_event) -> None
   - extract_biometric_features(raw_event) -> features_dict
   - load_or_create_user_profile(user_id) -> profile
   - check_baseline_ready(user_id) -> bool
   - analyze_biometrics(features, profile) -> analysis_result
   - calculate_risk_score(analysis) -> risk_score
   - generate_stage2_input(analysis, risk) -> output_data
   - log_analysis(user_id, analysis, risk) -> None

2. Data flow:
   Raw Event Input
   ↓
   Feature Extraction
   ↓
   Profile Loading
   ↓
   Baseline Check (is 30 days passed?)
   ├─ No: Still building baseline
   └─ Yes: Proceed with anomaly detection
   ↓
   Biometric Analysis
   ↓
   Risk Scoring
   ↓
   Generate Stage 2 Input
   ↓
   Logging & Storage

3. Functions to implement:
   - aggregate_user_activities(user_id, time_window) -> aggregated_data
   - detect_anomalies(current_data, baseline) -> anomalies
   - calculate_overall_risk(anomalies) -> risk_score
   - prepare_stage2_input(...) -> json_output
   - log_to_database(...) -> None
   - send_to_redis_cache(...) -> None

4. Output format to Stage 2:
   {
     "stage": 1,
     "analysis_id": "UUID",
     "timestamp": "ISO-8601",
     "user_id": "string",
     "biometric_score": 0.72,
     "confidence": 0.88,
     "risk_level": "medium",
     "anomaly_flags": [
       "keystroke_speed_unusual",
       "new_device",
       "off_hours_access"
     ],
     "baseline_ready": true,
     "baseline_days": 30,
     "user_profile": {...},
     "stage2_input": {...}
   }

5. Error handling:
   - Missing baseline: Log and skip anomaly detection
   - Corrupted profile: Regenerate from history
   - Database error: Cache in Redis, retry later
   - Invalid features: Log and skip this event

Include proper error handling and fallbacks.
```

### Prompt 6: Feature Engineering & Selection
**File Location:** `backend/services/biometric_services.py` (feature_engineering_module)
```
Build feature engineering system for Stage 1:
1. Raw biometric features from user interaction:
   - Keystroke speed: characters per minute
   - Error rate: corrections per 100 characters
   - Key dwell time: ms key is held down
   - Inter-key delay: ms between key releases and next press
   - Mouse velocity: pixels per second
   - Mouse acceleration: pixel/sec²
   - Click interval: ms between clicks
   - Scroll speed: pixels per second

2. Derived features:
   - Keystroke consistency: std dev of speed (low=consistent)
   - Typing pattern hash: sequence of key intervals (unique signature)
   - Device fingerprint: OS + browser + resolution combo
   - Time since baseline: days since profile created
   - Activity frequency: actions per hour
   - Session duration: time on site per session
   - Unique IP count: how many IPs used
   - Device change frequency: new devices per week

3. Temporal features:
   - Hour of day: 0-23 (when user active)
   - Day of week: 0-6 (Mon-Sun)
   - Is weekend: boolean
   - Is business hours: 9-5 weekday?
   - Days since last activity: temporal gap
   - Activity change rate: sudden increase/decrease?

4. Context features:
   - User role: admin/user/guest
   - Data classification: what data accessed
   - Resource sensitivity: important system access?
   - Peer baseline: similar users' behavior
   - Department: which team
   - Tenure: days as employee

5. Feature preprocessing:
   - Normalize to 0-1 range (MinMaxScaler)
   - Handle missing values (mean imputation)
   - Outlier detection and handling (IQR method)
   - Feature scaling (StandardScaler for ML)

6. Feature selection:
   - Use mutual information to rank features
   - Remove low-importance features
   - Check for multicollinearity (correlation)
   - Validate with domain experts

7. Output:
   {
     "selected_features": [10-20 feature names],
     "feature_importance": {
       "keystroke_speed": 0.15,
       "device_id": 0.12,
       "hour_of_day": 0.10,
       ...
     },
     "feature_vectors": [...],
     "feature_stats": {
       "mean": [...],
       "std": [...],
       "min": [...],
       "max": [...]
     }
   }

Use scikit-learn for feature selection.
```

### Prompt 7: Adaptive Learning & Model Updates
**File Location:** `backend/services/biometric_services.py` (learning_module)
```
Create adaptive learning system for Stage 1:
1. Monthly model retraining:
   - Collect all user interactions from past month
   - Recalculate baselines with new data
   - Retrain anomaly detection models
   - Evaluate model performance against ground truth

2. Concept drift detection:
   - Monitor if user behavior changing over time
   - If significant change, flag as legitimate evolution
   - Gradually shift baseline (don't overfit to noise)
   - Detect gradual vs sudden changes

3. Feedback incorporation:
   - User feedback: "That was me, not anomalous"
   - Admin feedback: "This user should be flagged"
   - Incident feedback: "This activity was a breach"
   - Use feedback to adjust thresholds

4. Model evaluation metrics:
   - True positive rate: Actual anomalies caught
   - False positive rate: Legitimate users blocked
   - Detection latency: Time to detect threat
   - Model stability: Does it change too much?

5. Retraining pipeline:
   - Extract training data from past 30 days
   - Split: 70% train, 15% validation, 15% test
   - Train new models
   - Compare to old models (is performance better?)
   - If better, deploy new models
   - If worse, keep old models

6. A/B testing:
   - Run new model on subset of users
   - Compare metrics with old model
   - If significantly better, rollout
   - Track performance over time

7. Learning output:
   {
     "retraining_date": "ISO-8601",
     "models_trained": ["isolation_forest", "neural_net"],
     "baseline_updated": true,
     "performance_metrics": {
       "accuracy": 0.94,
       "precision": 0.92,
       "recall": 0.89,
       "f1_score": 0.90
     },
     "concept_drift_detected": false,
     "feedback_incorporated": 23,
     "deployment_status": "ready"
   }

Include versioning for all models.
```

### Prompt 8: API Service & Endpoints
**File Location:** `backend/services/biometric_services.py` (api_module)
```
Build FastAPI endpoints for Stage 1:
1. Endpoints to implement:
   POST /analyze
   - Accept biometric event: keystroke, mouse, device info
   - Return: biometric_score, anomaly_flags, confidence
   - Response time: <100ms

   GET /profile/{user_id}
   - Return: User's biometric profile
   - Include baseline, history, trend

   GET /baseline/{user_id}
   - Return: User's baseline stats
   - Include mean, std, created_date

   GET /anomaly-history/{user_id}
   - Return: Paginated list of flagged anomalies
   - With timestamps and explanations

   POST /feedback
   - Accept user/admin feedback
   - user: "That was me"
   - admin: "User is compromised"
   - Update models based on feedback

   GET /health
   - Return: Service health status
   - Database connectivity, model loaded, etc.

   WebSocket /profile-stream/{user_id}
   - Real-time profile updates
   - Streaming anomaly detection

2. Request/Response formats:
   POST /analyze request:
   {
     "user_id": "string",
     "keystroke_speed": 75,
     "error_rate": 0.02,
     "device_id": "laptop_001",
     "ip_address": "192.168.1.100",
     "timestamp": "ISO-8601"
   }

   Response:
   {
     "biometric_score": 0.72,
     "confidence": 0.88,
     "anomaly_flags": [...],
     "risk_level": "medium"
   }

3. Error handling:
   - 400: Invalid input (missing fields)
   - 404: User not found
   - 503: Database unavailable
   - Return meaningful error messages

4. Rate limiting:
   - 1000 requests per hour per user
   - 100 concurrent requests
   - Graceful degradation under load

5. Authentication:
   - All endpoints require API key
   - Or JWT token from auth service
   - CORS enabled for frontend

Use FastAPI with proper validation (Pydantic).
```

### Prompt 9: Machine Learning Model Training
**File Location:** `backend/models/train_stage1_biometric.py`
```
Create training pipeline for Stage 1 ML models:
1. Data preparation:
   - Source: Biometric interaction logs
   - Features: keystroke, mouse, device, temporal, context
   - Labels: normal_user (0) or anomalous (1)
   - Time split: Train on past 60 days, test on recent 7 days

2. Model 1: Isolation Forest (Unsupervised)
   - No labels needed
   - Detect anomalies based on feature isolation
   - Training: fit on normal user data
   - Prediction: anomaly score (distance from normal)

3. Model 2: Gaussian Mixture Model (Unsupervised)
   - Model normal behavior as mixture of Gaussians
   - Probability density: how likely is this event?
   - Multi-modal behavior support (work vs home patterns)

4. Model 3: Neural Network (Supervised or Self-Supervised)
   - Input: biometric features (20-dim)
   - Output: anomaly score (0-1)
   - Architecture: 3 dense layers with dropout
   - Loss: If unsupervised: reconstruction error (autoencoder)

5. Model 4: Ensemble
   - Combine all three models
   - Majority voting
   - Weighted average by model accuracy

6. Training configuration:
   - Batch size: 32
   - Epochs: 100 with early stopping
   - Validation split: 20%
   - Optimizer: Adam (lr=0.001)
   - Loss: Cross-entropy or reconstruction error

7. Evaluation:
   - Accuracy, Precision, Recall, F1-score
   - ROC-AUC curve
   - Confusion matrix per user
   - False positive vs false negative analysis

8. Hyperparameter tuning:
   - Grid search for best parameters
   - Cross-validation for robustness
   - Optimize for F1-score
   - Constraint: Inference latency < 50ms

9. Model persistence:
   - Save to: checkpoints/biometric_model_v{version}.pt
   - Include: training date, accuracy metrics, feature names
   - Version control: track model changes

10. Output:
    {
      "model_type": "ensemble",
      "training_date": "ISO-8601",
      "accuracy": 0.96,
      "precision": 0.94,
      "recall": 0.92,
      "f1_score": 0.93,
      "roc_auc": 0.98,
      "inference_latency_ms": 45,
      "false_positive_rate": 0.03,
      "false_negative_rate": 0.05
    }

Use PyTorch and scikit-learn.
```

### Prompt 10: Monitoring & Analytics Dashboard
**File Location:** `backend/services/biometric_services.py` (dashboard_module) + `src/pages/BiometricDashboard.jsx`
```
Create monitoring system and dashboard:

Backend Endpoints:
1. GET /dashboard/stats
   - Total users profiled
   - Baseline completion percentage
   - Anomaly detection accuracy
   - Average biometric score

2. GET /dashboard/anomalies
   - Recent anomalies across all users
   - Heat map of anomaly types
   - Trend over time

3. GET /dashboard/user-risk/{user_id}
   - User's current risk score
   - Risk trend over time
   - Comparison to peer average

4. GET /dashboard/model-health
   - Model accuracy metrics
   - Model latency
   - Last retrain date
   - Performance drift detection

5. GET /dashboard/features-importance
   - Which features matter most
   - Feature correlations
   - Feature engineering suggestions

6. WebSocket /dashboard/live-stream
   - Real-time anomalies as detected
   - Live user activity

Frontend Components (src/pages/):
- BiometricOverview: Summary stats
- UserRiskScore: Individual user risk visualization
- AnomalyTimeline: Timeline of detected anomalies
- FeatureImportance: Visual importance ranking
- ModelPerformance: Training metrics and trends
- BaselineStatus: Which users have completed baseline
- AnomalyHeatmap: Which anomaly types most common

Visualizations:
- Gauge chart: User risk score (0-1)
- Line chart: Risk score trend over time
- Heat map: Anomaly type distribution
- Box plot: Feature distributions per user
- Scatter: Feature correlations
- Bar chart: Feature importance
- Timeline: Anomaly events with details

Filtering:
- By time range (1 day - 1 year)
- By user/department
- By anomaly type
- By confidence threshold

Export:
- CSV of anomalies
- PDF report of user risk
- JSON of profiles for archive
```

---

## 📁 FILE STRUCTURE TO CREATE/MODIFY

```
backend/
├── models/
│   ├── stage1_biometric.py (MAIN MODEL - Prompts 1, 2, 4)
│   └── train_stage1_biometric.py (TRAINING - Prompt 9)
├── services/
│   └── biometric_services.py (SERVICES - Prompts 3, 6-8, 10)
├── pipeline/
│   └── stage1_biometric.py (ORCHESTRATION - Prompt 5)
├── tests/
│   └── test_stage1_biometric.py (TESTING)
└── Dockerfile-stage1

src/pages/
└── BiometricDashboard.jsx (Prompt 10)
```

---

## 🚀 IMPLEMENTATION STEPS

1. **Week 1:** Implement Prompts 1 & 2 (Core model, anomaly detection)
2. **Week 2:** Implement Prompts 3, 4, 5 (Services, scoring, orchestration)
3. **Week 3:** Implement Prompts 6, 7, 8 (Features, learning, API)
4. **Week 4:** Implement Prompts 9, 10 (Training, dashboard)

---

## 📝 IMPORTANT NOTES

✅ **Work on branch:** `parik-stage1-biometric-advanced`
✅ **Merge strategy:** Create PR to main after testing
✅ **Documentation:** Add docstrings to all functions
✅ **Logging:** Use structured logging with JSON output
✅ **Error handling:** Comprehensive try-catch with detailed error messages

---

## 🔗 DEPENDENCIES & INTEGRATION

**Outputs to Stage 2 (Honeypot):**
- biometric_score: float (0-1)
- anomaly_flags: list of strings
- user_profile: dict
- confidence: float
- risk_level: string

**Uses:**
- MongoDB for user profiles
- Redis for caching hot profiles
- PyTorch for models
- scikit-learn for anomaly detection

---

**Branch to work on:** `parik-stage1-biometric-advanced`
**As the main coordinator:** You'll merge all team member PRs to main after review
