# VED - STAGE 4: WATCHDOG ADVANCED THREAT ENFORCEMENT
**Branch:** `ved-stage4-advanced`
**Assigned Stage:** Stage 4 - Watchdog & Enforcement Mechanism
**Role:** Implement advanced behavioral enforcement, threat response automation, and system lockdown procedures

---

## 📋 5 UNIQUE IDEAS FROM IEEE PAPERS FOR STAGE 4

### Idea 1: **Adaptive Threat Response Engine (ATRE)**
**IEEE Reference:** Based on "Adaptive Machine Learning for Cybersecurity" papers
- **Features:**
  - Real-time threat level assessment
  - Automatic escalation protocols (Warning → Quarantine → Full Lockdown)
  - Dynamic rule engine based on threat patterns
  - Self-healing system that restores services after false positives
  - Threat intelligence feedback loop

### Idea 2: **Distributed Anomaly Enforcement System (DAES)**
**IEEE Reference:** From "Distributed Intrusion Detection Systems"
- **Features:**
  - Multi-node enforcement across microservices
  - Consensus-based decision making for lockdowns
  - Cross-service communication for threat containment
  - Cascading failure prevention
  - Real-time metric aggregation from all stages

### Idea 3: **Behavioral Enforcement & System Resilience (BESR)**
**IEEE Reference:** Based on "Resilience Engineering in Cybersecurity"
- **Features:**
  - User behavior modification triggers
  - Session termination with grace period
  - Resource limitation (CPU, memory, bandwidth throttling)
  - Automatic rollback of suspicious transactions
  - Forensic evidence collection before enforcement

### Idea 4: **Zero-Trust Enforcement Protocol (ZTEP)**
**IEEE Reference:** From "Zero Trust Architecture" papers
- **Features:**
  - Continuous re-verification of all actions
  - Micro-segmentation enforcement
  - Per-request authorization checks
  - Revocation of compromised tokens in real-time
  - Immutable audit trail of all enforcement actions

### Idea 5: **Predictive Threat Neutralization System (PTNS)**
**IEEE Reference:** Based on "Predictive Security Analytics"
- **Features:**
  - ML-based prediction of attack progression
  - Proactive defense mechanisms
  - Preemptive user isolation before confirmed breach
  - Threat trajectory modeling
  - Historical pattern matching with confidence scoring

---

## 🐳 DOCKER STRUCTURE FOR STAGE 4

### What is Docker? (Simple Explanation)
**Docker = Containerization Tool**
- Think of Docker as a **box** that contains everything your Stage 4 service needs
- Box includes: Python, libraries, code files, everything
- You can run this box on any computer and it works the same way
- Helps all team members use same environment (no "works on my machine" issues)

### What You Need to Create:
1. **Dockerfile** = Recipe for creating the box
2. **requirements-stage4.txt** = List of Python packages needed
3. **Docker Compose Configuration** = Settings for running multiple services together
4. **Volume Folders** = Folders for logs, checkpoints, data persistence

---

### Step 1: Create Requirements File
**File: `backend/requirements-stage4.txt`**
```
torch==2.0.1
torchvision==0.15.2
torchaudio==2.0.2
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.4.2
mongodb==4.4.1
pytest==7.4.3
python-multipart==0.0.6
python-dotenv==1.0.0
redis==5.0.1
requests==2.31.0
PyJWT==2.8.1
aioredis==2.0.1
```

### Step 2: Create Dockerfile
**File: `backend/Dockerfile-stage4`**
```dockerfile
# Dockerfile for Watchdog Service
FROM python:3.11-slim

WORKDIR /app

# Copy requirements first (Docker caches this layer)
COPY backend/requirements-stage4.txt .
RUN pip install --no-cache-dir -r requirements-stage4.txt

# Copy your stage 4 code
COPY backend/models/stage4_watchdog.py ./models/
COPY backend/services/watchdog_services.py ./services/
COPY backend/pipeline/stage4_watchdog.py ./pipeline/
COPY backend/main.py ./

# Health check - Docker will verify service is working
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8004/health')"

# Expose port that Stage 4 runs on
EXPOSE 8004

# Start command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
```

### Step 3: Add to Docker Compose File
**File: `docker-compose.yml` (Add this service to existing file)**
```yaml
watchdog-stage4:
  build:
    context: .                          # Build from current folder
    dockerfile: backend/Dockerfile-stage4  # Use this recipe
  container_name: entropy-watchdog-stage4  # Name your container
  
  # Which ports to expose
  ports:
    - "8004:8004"                      # External:Internal port
  
  # Environment variables (Settings for your service)
  environment:
    - MONGODB_URI=mongodb://mongodb:27017
    - REDIS_URL=redis://redis:6379
    - LOG_LEVEL=INFO
    - THREAT_THRESHOLD=0.85
    - STAGE=4
    - SERVICE_NAME=watchdog
  
  # This service needs these services running first
  depends_on:
    - mongodb
    - redis
  
  # Folders that persist data outside container
  volumes:
    - ./checkpoints:/app/checkpoints      # ML model files stay here
    - ./logs/stage4:/app/logs            # Log files stay here
    - ./backend:/app/backend              # Live code sync (development)
  
  # Network - connects to other services
  networks:
    - security-net                       # Same network as other stages
  
  # Resource limits - prevent this box from using all CPU/memory
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 4G
      reservations:
        cpus: '1'
        memory: 2G
  
  # Restart policy
  restart: unless-stopped               # Auto restart if crashes
```

### Step 4: Create Volume Folders
**Run these commands in PowerShell to create folders Docker needs:**
```powershell
# Create checkpoint folder for saving models
New-Item -ItemType Directory -Path "checkpoints" -Force
New-Item -ItemType Directory -Path "checkpoints" -Force

# Create log folder for Stage 4
New-Item -ItemType Directory -Path "logs/stage4" -Force

# Give permissions
icacls "checkpoints" /grant:r "%USERNAME%:(OI)(CI)F"
icacls "logs" /grant:r "%USERNAME%:(OI)(CI)F"
```

### Step 5: Create .env File for Configuration
**File: `.env` (in root folder)**
```env
# Stage 4 Settings
STAGE_4_PORT=8004
THREAT_THRESHOLD=0.85
ENFORCEMENT_LOG_LEVEL=INFO
MAX_CONCURRENT_ENFORCEMENTS=100
ENFORCEMENT_TIMEOUT_SECONDS=60

# Database
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=entropy_stage4

# Redis
REDIS_URL=redis://redis:6379
REDIS_DB=2

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_RETENTION_DAYS=90
```

---

## 🚀 DOCKER WORKFLOW - STEP BY STEP

### What Docker Does:
1. **Build** = Creates a box (image) from Dockerfile recipe
2. **Run** = Starts the box (container) from the image
3. **Connect** = Connects your box to other boxes (databases, other stages)
4. **Persist** = Saves data even when box is turned off

### Workflow for Stage 4:

#### Step A: Build the Docker Image
**What this does:** Creates a box that contains Python, libraries, and your code

```powershell
# Navigate to project folder
cd p:\ENTROPY PRIME

# Build Stage 4 image
docker build -f backend/Dockerfile-stage4 -t entropy-watchdog:latest .

# Check if build succeeded
docker images | grep entropy-watchdog
```

**If build fails:**
- Check error message carefully
- Make sure `requirements-stage4.txt` exists
- Check file paths are correct
- Run: `docker build --no-cache ...` (rebuild without cache)

#### Step B: Start All Services with Docker Compose
**What this does:** Starts your Stage 4 service + MongoDB + Redis + other stages

```powershell
# Start all services in background
docker-compose -f docker-compose.yml up -d

# See which containers are running
docker-compose ps

# Check if Stage 4 is healthy
docker ps | grep watchdog
```

**Expected output:**
```
NAME                    STATUS          PORTS
entropy-watchdog-stage4  Up 10 seconds   0.0.0.0:8004->8004/tcp
```

#### Step C: Check Logs to See if Working
**What this does:** Shows you what's happening inside the box

```powershell
# See last 50 lines of logs
docker logs -f entropy-watchdog-stage4 --tail 50

# See logs since 5 minutes ago
docker logs --since 5m entropy-watchdog-stage4

# Save logs to file
docker logs entropy-watchdog-stage4 > watchdog_logs.txt
```

#### Step D: Test if Service Works
**What this does:** Sends test request to see if service responds

```powershell
# Test health endpoint
curl http://localhost:8004/health

# Expected response:
# {"status": "healthy"}

# Test enforcement endpoint
curl -X POST http://localhost:8004/enforce `
  -Header "Content-Type: application/json" `
  -Body '{"user_id": "test", "threat_level": 0.9}'
```

#### Step E: View Data in Volumes
**What this does:** Checks files that were saved from the box

```powershell
# Check logs folder
Get-ChildItem -Path "logs/stage4"

# Check checkpoints (saved models)
Get-ChildItem -Path "checkpoints"

# View recent log file
Get-Content logs/stage4/latest.log -Tail 20
```

#### Step F: Enter the Running Container
**What this does:** Lets you run commands inside the box while it's running

```powershell
# Open shell inside Stage 4 container
docker exec -it entropy-watchdog-stage4 /bin/bash

# Inside the container, you can:
# - Check files: ls -la
# - Run Python: python -c "print('test')"
# - Check processes: ps aux
# - Exit: type 'exit'
```

#### Step G: Rebuild After Code Changes
**What this does:** Creates new box with your updated code

```powershell
# Stop running container
docker-compose stop watchdog-stage4

# Remove old container (not image)
docker-compose rm watchdog-stage4

# Rebuild image with new code
docker build -f backend/Dockerfile-stage4 -t entropy-watchdog:latest .

# Start new container
docker-compose up -d watchdog-stage4

# Check logs
docker logs -f entropy-watchdog-stage4
```

---

## 📊 DOCKER NETWORKING - How Stages Talk to Each Other

### Network Architecture:
```
┌─────────────────────────────────────────┐
│         Docker Network (security-net)    │
│                                          │
│  ┌─────────────────────────────────┐   │
│  │ Stage 1: Biometric (port 8001)   │   │
│  └─────────────────────────────────┘   │
│                  ↓                       │
│  ┌─────────────────────────────────┐   │
│  │ Stage 2: Honeypot (port 8002)    │   │
│  └─────────────────────────────────┘   │
│                  ↓                       │
│  ┌─────────────────────────────────┐   │
│  │ Stage 3: Governor (port 8003)    │   │
│  └─────────────────────────────────┘   │
│                  ↓                       │
│  ┌─────────────────────────────────┐   │
│  │ Stage 4: Watchdog (port 8004)    │   │
│  └─────────────────────────────────┘   │
│                                          │
│  ┌──────────┐  ┌──────────┐            │
│  │ MongoDB  │  │  Redis   │            │
│  └──────────┘  └──────────┘            │
└─────────────────────────────────────────┘
```

### How Services Call Each Other:
**Inside Docker, services use container names as addresses:**

```python
# Stage 4 calling Governor (Stage 3)
import requests

# Inside Docker
response = requests.get('http://governor-stage3:8003/decision')

# Outside Docker (from your computer)
response = requests.get('http://localhost:8003/decision')
```

### Network Creation in docker-compose.yml:
```yaml
networks:
  security-net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

---

## 🔧 COMMON DOCKER COMMANDS FOR STAGE 4

| Command | What It Does |
|---------|----------|
| `docker build -f backend/Dockerfile-stage4 -t entropy-watchdog:latest .` | Create image |
| `docker-compose up -d watchdog-stage4` | Start Stage 4 |
| `docker-compose down` | Stop all services |
| `docker logs entropy-watchdog-stage4` | See what's happening |
| `docker exec -it entropy-watchdog-stage4 bash` | Go inside container |
| `docker-compose exec watchdog-stage4 python -c "import main"` | Run Python in container |
| `docker ps` | See running containers |
| `docker images` | See all saved images |
| `docker-compose ps` | See status of all services |
| `docker volume ls` | See saved data folders |

---

## ⚠️ TROUBLESHOOTING DOCKER

### Problem: Port 8004 Already in Use
```powershell
# Find what's using port 8004
netstat -ano | findstr :8004

# Kill it (replace PID with number from above)
taskkill /PID <PID> /F

# Or change port in docker-compose.yml:
# ports:
#   - "8005:8004"  (use 8005 instead)
```

### Problem: Container Crashes Immediately
```powershell
# Check logs
docker logs entropy-watchdog-stage4

# Common causes:
# 1. requirements.txt has wrong package name
# 2. Code has import errors
# 3. Environment variables missing
# 4. Port already in use
```

### Problem: Container Can't Connect to MongoDB
```powershell
# Check if MongoDB running
docker-compose ps | grep mongodb

# Check network connection
docker exec entropy-watchdog-stage4 ping mongodb

# Ensure container has depends_on:
# depends_on:
#   - mongodb
#   - redis
```

### Problem: Need to See All Service Logs at Once
```powershell
# See logs from all services
docker-compose logs -f

# See only Stage 4 logs
docker-compose logs -f watchdog-stage4

# Save all logs
docker-compose logs > all_logs.txt
```

---

## 📦 DOCKER BEST PRACTICES FOR STAGE 4

✅ **DO:**
- Put requirements.txt in dockerfile
- Use volumes for logs and models
- Add health checks
- Use environment variables for settings
- Give containers meaningful names
- Use networks to connect stages
- Check logs before debugging

❌ **DON'T:**
- Hardcode settings in code (use .env)
- Store important files inside container (use volumes)
- Run containers with root permissions
- Use latest tag for production (use version tags)
- Ignore error messages in logs
- Leave containers running when not developing

---

## ✅ DOCKER CHECKLIST - Before Starting Implementation

- [ ] Docker Desktop is installed and running
- [ ] docker-compose.yml file exists and updated
- [ ] Dockerfile-stage4 created
- [ ] requirements-stage4.txt created
- [ ] Volume folders created (checkpoints, logs/stage4)
- [ ] .env file created with Stage 4 settings
- [ ] Networks section added to docker-compose
- [ ] Health check added to Dockerfile
- [ ] Test curl commands ready
- [ ] Team understands port mapping (8004)

---

### Key Docker Features for Stage 4:
- **Persistent Volume:** Audit logs and enforcement records stay after restart
- **Network:** Isolated network for security commands and inter-stage communication
- **Health Check:** Docker automatically verifies enforcement capability every 30 seconds
- **Resource Limits:** CPU/Memory constraints prevent resource exhaustion attacks
- **Restart Policy:** Auto restart if service crashes

---

## 🤖 10 CLAUDE PROMPTS FOR VED - STAGE 4 IMPLEMENTATION

### Prompt 1: Core Enforcement Engine Architecture
**File Location:** `backend/models/stage4_watchdog.py`
```
Create a PyTorch-based enforcement decision model for Stage 4 Watchdog that:
1. Takes threat analysis from Stage 3 Governor (threat_score, confidence, threat_type)
2. Determines enforcement level: NO_ACTION (0-0.3), WARNING (0.3-0.6), QUARANTINE (0.6-0.85), LOCKDOWN (0.85-1.0)
3. Outputs enforcement recommendations with JSON structure including:
   - enforcement_action: string (warning/quarantine/lockdown/rollback)
   - duration: integer (seconds)
   - affected_resources: list of strings
   - escalation_path: list of actions if threat continues
4. Use attention mechanism to weight different threat indicators
5. Include historical pattern matching using embeddings

Key Parameters to Output:
- confidence_score: float (0-1)
- resource_impact: dict with cpu_throttle, memory_limit, bandwidth_cap
- user_notifications: dict with message, severity, action_required
- forensic_data: dict for audit trail

Return as PyTorch model with forward() method
```

### Prompt 2: Real-Time Enforcement Service
**File Location:** `backend/services/watchdog_services.py`
```
Build an async FastAPI service for Stage 4 enforcement with:
1. POST /enforce endpoint that:
   - Receives threat alert from Governor (Stage 3)
   - Applies enforcement engine decision
   - Executes enforcement actions (session kill, resource throttle)
   - Logs to audit trail
   - Notifies user (via webhook to frontend)
   - Returns enforcement_id and status

2. GET /enforcement_status/{enforcement_id} endpoint for tracking

3. POST /rollback/{enforcement_id} endpoint for manual override

4. WebSocket /enforcement_stream for real-time updates

5. Implement enforcement actions:
   - Session termination with grace period
   - Token revocation cascade
   - Resource limitation enforcement
   - Database transaction rollback

6. Error handling: Include circuit breaker pattern

Requirements:
- Use Redis for enforcement state caching
- MongoDB for audit logging
- Retry logic with exponential backoff
- Rate limiting on enforcement to prevent DoS
```

### Prompt 3: Multi-Stage Orchestration Integration
**File Location:** `backend/pipeline/stage4_watchdog.py`
```
Create Stage 4 orchestrator that:
1. Receives verdict from Stage 3 Governor
2. Applies Stage 4 enforcement logic
3. Returns final system state with enforcement details

Implement:
- get_enforcement_decision(threat_data) -> enforcement_dict
- execute_enforcement(enforcement_dict) -> enforcement_result
- log_enforcement_action(enforcement_result) -> None
- get_enforcement_history(user_id, limit=100) -> List[dict]

Integration points:
- Input: Stage 3 Governor output (biometric_result, honeypot_result, threat_score)
- Output: Enforcement action, audit log, notification payload
- Feedback: Update threat models with enforcement outcomes for Stage 3 improvement

Response Schema:
{
  "stage": 4,
  "enforcement_action": "quarantine",
  "timestamp": "ISO-8601",
  "user_id": "string",
  "enforcement_id": "UUID",
  "duration_seconds": 3600,
  "escalation_level": 0-5,
  "affected_systems": [],
  "audit_trail_id": "reference",
  "predicted_recovery_time": "ISO-8601"
}
```

### Prompt 4: Advanced Threat Response Decision Tree
**File Location:** `backend/models/stage4_watchdog.py` (decision_tree_module)
```
Implement a hybrid decision tree + neural network model for Stage 4 that:
1. Creates decision tree rules based on threat type:
   - Ransomware: Immediate file system read-only, process isolation
   - Credential Theft: Session termination, password reset flow
   - Data Exfiltration: Network isolation, transaction rollback
   - Account Takeover: Full lockdown + 2FA reset

2. Uses neural network to determine confidence of threat classification

3. Implements rule override with confidence thresholds:
   - <70% confidence: Action required notification only
   - 70-85% confidence: Auto-quarantine with manual review queue
   - >85% confidence: Immediate lockdown

4. Outputs structured enforcement command:
   {
     "command_type": "isolate|throttle|terminate|rollback|lockdown",
     "target": "user|session|service|database",
     "parameters": {...},
     "conditions": [...],
     "rollback_procedure": {...}
   }

Include state machine for enforcement transitions.
```

### Prompt 5: User Communication & Notification System
**File Location:** `backend/services/watchdog_services.py` (notification_module)
```
Create notification system for Stage 4 enforcement that:
1. Sends graduated alerts based on enforcement level:
   - Level 1 (Warning): Email notification
   - Level 2 (Quarantine): Email + SMS + In-app banner
   - Level 3 (Lockdown): All above + Phone call + Slack notification

2. Provides clear user communication:
   - Threat explanation in non-technical language
   - Duration of enforcement
   - Recovery steps
   - Contact for security team

3. Implements dispute/appeal workflow:
   - User can request manual review
   - Queues to security team
   - Time limit for appeal (e.g., 24 hours)

4. Tracks notification delivery and user acknowledgment

5. Webhook integration to frontend:
   - Real-time enforcement status updates
   - User dashboard showing enforcement history
   - Appeal form submission endpoint

Response Model:
{
  "notification_id": "UUID",
  "user_id": "string",
  "enforcement_id": "string",
  "channel": "email|sms|webhook|phone",
  "status": "pending|sent|delivered|read",
  "timestamp": "ISO-8601",
  "content": "string"
}
```

### Prompt 6: Forensic Logging & Audit Trail System
**File Location:** `backend/services/watchdog_services.py` (forensics_module)
```
Build comprehensive forensic logging for Stage 4:
1. Immutable audit trail that records:
   - Timestamp of enforcement decision
   - Threat data that triggered enforcement
   - All executed enforcement actions
   - System state before/after
   - User actions during enforcement
   - Recovery actions taken

2. Forensic data collection:
   - Network traffic snapshot at time of threat
   - Active processes running
   - Database query logs
   - File access patterns
   - Memory state (sanitized)

3. Export formats:
   - JSON for API consumption
   - PDF report for compliance/incidents
   - SIEM integration (syslog format)
   - Timeline visualization data

4. Query interface:
   - Search by enforcement_id
   - Filter by user_id, threat_type, date range
   - Export filtered results

5. Retention policy:
   - Hot storage: 90 days
   - Archive: 7 years (for compliance)
   - Anonymization after 1 year

Implement with MongoDB capped collections for performance.
```

### Prompt 7: Circuit Breaker & Resilience Patterns
**File Location:** `backend/services/watchdog_services.py` (resilience_module)
```
Implement resilience patterns for Stage 4:
1. Circuit breaker pattern for enforcement services:
   - Track enforcement service health
   - If >5% failures in last 100 requests, enter OPEN state
   - Fail safe: Log to file, trigger manual review queue
   - Half-open after 30 seconds, test with single request
   - Reset to CLOSED on success

2. Bulkhead pattern:
   - Separate thread pools for different enforcement types
   - Prevent one slow operation from blocking others

3. Retry logic:
   - Exponential backoff with jitter
   - Max 3 retries for idempotent operations
   - Skip retries for non-idempotent operations

4. Fallback mechanisms:
   - If enforcement service down: queue to Redis, retry when up
   - If database down: in-memory cache with write-back

5. Health check endpoint:
   - Database connectivity
   - Redis connectivity
   - Enforcement service responsiveness
   - Model loading status

Implement using Resilience4j or similar library.
```

### Prompt 8: Machine Learning Model Training Pipeline
**File Location:** `backend/models/train_stage4_watchdog.py`
```
Create training pipeline for Stage 4 enforcement model:
1. Data preparation:
   - Input features: threat_score, threat_type, user_behavior, historical_patterns
   - Labels: enforcement_level (0-4), was_correct (true/false), user_appeal (true/false)
   - Source: Historical enforcement logs with feedback

2. Model architecture:
   - Input layer: 50 features from Stage 3 output
   - Hidden layers: 3 layers with 128, 64, 32 neurons, ReLU activation
   - Attention layer: Weight different threat indicators
   - Output layer: 5 classes (enforcement levels) with softmax

3. Training configuration:
   - Optimizer: Adam with learning rate 0.001
   - Loss: Weighted CrossEntropyLoss (weight enforcement errors more)
   - Batch size: 32
   - Epochs: 100 with early stopping
   - Validation split: 20%

4. Evaluation metrics:
   - Accuracy overall
   - Precision/Recall per enforcement level
   - F1 score (weighted)
   - Confusion matrix analysis
   - False positive/negative rates

5. Model versioning:
   - Save to checkpoints/watchdog_v{version}.pt
   - Store metrics with each version
   - Track feature importance changes

6. Feedback loop:
   - User feedback on enforcement decisions
   - Appeal outcomes
   - Incident post-mortems
   - Retrain monthly with new data

Save trained model to: checkpoints/watchdog.pt
```

### Prompt 9: Integration with Frontend Dashboard
**File Location:** `backend/services/watchdog_services.py` (dashboard_module) + `src/pages/SecurityDashboard.jsx`
```
Create backend endpoints for Stage 4 dashboard:

Backend Endpoints:
1. GET /dashboard/enforcement-stats
   - Returns: Active enforcements count, enforcement timeline, threat heatmap
   
2. GET /dashboard/user-enforcement-history/{user_id}
   - Paginated enforcement history with filtering
   
3. GET /dashboard/enforcement-effectiveness
   - Metrics: True positive rate, false positive rate, mean detection time
   
4. POST /dashboard/enforcement-appeal/{enforcement_id}
   - Accept appeal with reason
   - Queue for manual review
   
5. WebSocket /dashboard/enforcement-stream
   - Real-time stream of enforcement events
   - Filter by severity, user, threat type

Frontend Components (src/pages/):
- EnforcementTimeline: Visual timeline of enforcements
- ThreatHeatmap: Geographic/departmental distribution
- UserEnforcementHistory: Detailed history per user
- AppealForm: Submit appeal for false positive
- LiveMetrics: Real-time enforcement metrics
- IncidentLog: Detailed incident records

Color coding:
- Green: No threat
- Yellow: Warning
- Orange: Quarantine
- Red: Lockdown
```

### Prompt 10: Testing & Validation Framework
**File Location:** `backend/tests/test_stage4_watchdog.py`
```
Create comprehensive test suite for Stage 4:

Unit Tests:
1. test_enforcement_decision_engine():
   - Test all threat levels produce correct decisions
   - Test confidence thresholds
   - Test edge cases

2. test_enforcement_actions_execution():
   - Mock database, Redis, services
   - Verify correct actions executed
   - Verify state consistency

3. test_forensic_logging():
   - Verify all required data logged
   - Test immutability
   - Test export formats

Integration Tests:
1. test_full_pipeline_threat_to_enforcement():
   - Create threat scenario at Stage 1
   - Flow through all stages to Stage 4
   - Verify correct enforcement action

2. test_multi_user_concurrent_enforcements():
   - Simulate 100+ concurrent enforcement requests
   - Verify no data corruption
   - Check performance metrics

3. test_enforcement_rollback():
   - Trigger enforcement
   - Execute rollback
   - Verify system returns to pre-enforcement state

Load Tests:
1. test_enforcement_latency():
   - Ensure <100ms from threat detection to enforcement
   - Test with 1000 concurrent users

2. test_system_recovery():
   - Simulate service failures
   - Verify graceful degradation
   - Measure recovery time

Test Data:
- Create fixtures with various threat scenarios
- Real-world attack patterns from MITRE ATT&CK
- Historical enforcement decisions for validation

Use pytest framework with fixtures for setup/teardown.
Coverage target: >90%
```

---

## 📁 FILE STRUCTURE TO CREATE/MODIFY

```
backend/
├── models/
│   ├── stage4_watchdog.py (MAIN MODEL - Prompt 1, 4)
│   └── train_stage4_watchdog.py (TRAINING - Prompt 8)
├── services/
│   └── watchdog_services.py (SERVICES - Prompts 2, 5, 6, 7, 9)
├── pipeline/
│   └── stage4_watchdog.py (ORCHESTRATION - Prompt 3)
├── tests/
│   └── test_stage4_watchdog.py (TESTING - Prompt 10)
└── Dockerfile-stage4
```

---

## 🚀 IMPLEMENTATION STEPS

1. **Week 1:** Implement Prompts 1 & 3 (Core model and orchestration)
2. **Week 2:** Implement Prompts 2, 5, 6 (Services, notifications, logging)
3. **Week 3:** Implement Prompts 4, 7, 8 (Decision tree, resilience, training)
4. **Week 4:** Implement Prompts 9, 10 (Dashboard, testing)

---

## 📝 IMPORTANT NOTES

✅ **Work on branch:** `ved-stage4-advanced`
✅ **Merge strategy:** Create PR to main after testing
✅ **Documentation:** Add docstrings to all functions
✅ **Logging:** Use structured logging with JSON output
✅ **Error handling:** Comprehensive try-catch with detailed error messages

---

## 🔗 DEPENDENCIES & INTEGRATION

**Receives from Stage 3 (Governor):**
- threat_score: float (0-1)
- threat_type: string
- confidence: float
- recommended_action: string

**Outputs to:**
- Frontend Dashboard (real-time WebSocket)
- Audit Logs (MongoDB)
- Notification Service
- User Communication System

---

**Branch to work on:** `ved-stage4-advanced`
**Merge responsibility:** Parikshith will handle merging to main after review
