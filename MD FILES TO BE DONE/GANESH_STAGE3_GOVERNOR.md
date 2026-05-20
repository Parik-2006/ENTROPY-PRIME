# GANESH - STAGE 3: GOVERNOR INTELLIGENT THREAT DECISION ENGINE
**Branch:** `ganesh-stage3-governor-advanced`
**Assigned Stage:** Stage 3 - Governor & Decision Making
**Role:** Implement intelligent threat assessment, risk analysis, decision trees, and adaptive governance policies

---

## 📋 5 UNIQUE IDEAS FROM IEEE PAPERS FOR STAGE 3

### Idea 1: **Intelligent Threat Assessment & Risk Scoring (ITARS)**
**IEEE Reference:** Based on "Machine Learning for Cybersecurity Risk Assessment" papers
- **Features:**
  - Multi-factor risk scoring combining all threat signals
  - Bayesian network for probabilistic inference
  - Dynamic threshold adjustment based on asset value
  - Contextual risk factors (time, location, user role)
  - Historical pattern comparison for normalization

### Idea 2: **Adaptive Access Control & Governance Framework (AACGF)**
**IEEE Reference:** From "Attribute-Based Access Control" and "Zero Trust Architecture"
- **Features:**
  - Attribute-based access decisions
  - Real-time policy evaluation
  - Fine-grained permission modification
  - Role-based and risk-based control fusion
  - Dynamic policy updates based on threat level

### Idea 3: **Ensemble Decision Making System (EDMS)**
**IEEE Reference:** Based on "Ensemble Methods for Classification" papers
- **Features:**
  - Combine decisions from multiple ML models
  - Voting mechanism with confidence weighting
  - Model diversity for robust decisions
  - Fallback decision trees when models disagree
  - Uncertainty quantification

### Idea 4: **Context-Aware Anomaly Scoring (CAAS)**
**IEEE Reference:** From "Contextual Anomaly Detection in Networks"
- **Features:**
  - User behavior profiling
  - Time-based context (working hours, locations)
  - Role-based baseline expectations
  - Peer comparison (similar users)
  - Sequential pattern analysis

### Idea 5: **Governance Policy Optimization Engine (GPOE)**
**IEEE Reference:** Based on "Reinforcement Learning for Security Policy Optimization"
- **Features:**
  - Learn optimal policies from historical decisions
  - Balance security vs usability
  - Dynamic policy recommendation
  - A/B testing of different policies
  - Cost-benefit analysis for enforcement

---

## 🐳 DOCKER STRUCTURE FOR STAGE 3

### What is Docker? (Simple Explanation)
**Docker = Containerization Tool**
- Think of Docker as a **box** that contains everything your Stage 3 service needs
- Box includes: Python, ML libraries, decision-making code, everything
- Stage 3 is the decision maker - receives data from Stage 1 & 2, makes decisions
- Docker ensures your decision engine runs the same on any computer

### What You Need to Create:
1. **Dockerfile** = Recipe for creating the Governor box
2. **requirements-stage3.txt** = List of Python packages (ML libraries)
3. **Docker Compose Configuration** = How to run Governor with databases
4. **Policy Files** = Governance policies stored as JSON
5. **Volume Folders** = Folders for models, policies, logs

---

### Step 1: Create Requirements File
**File: `backend/requirements-stage3.txt`**
```
torch==2.0.1
torchvision==0.15.2
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.4.2
mongodb==4.4.1
pytest==7.4.3
xgboost==2.0.0
scikit-learn==1.3.2
numpy==1.24.3
pandas==2.1.1
redis==5.0.1
requests==2.31.0
python-dotenv==1.0.0
python-jose==3.3.0
aioredis==2.0.1
```

### Step 2: Create Dockerfile
**File: `backend/Dockerfile-stage3`**
```dockerfile
# Dockerfile for Governor Service
FROM python:3.11-slim

WORKDIR /app

# Copy requirements first
COPY backend/requirements-stage3.txt .
RUN pip install --no-cache-dir -r requirements-stage3.txt

# Copy your stage 3 decision-making code
COPY backend/models/stage3_governor.py ./models/
COPY backend/services/governor_services.py ./services/
COPY backend/pipeline/stage3_governor.py ./pipeline/
COPY backend/main.py ./

# Governance policies folder
RUN mkdir -p /app/policies

# Health check - verify decision engine is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8003/health')"

# Expose port for Governor service
EXPOSE 8003

# Start command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
```

### Step 3: Add to Docker Compose File
**File: `docker-compose.yml` (Add this service to existing file)**
```yaml
governor-stage3:
  build:
    context: .                          # Build from current folder
    dockerfile: backend/Dockerfile-stage3  # Use this recipe
  container_name: entropy-governor-stage3  # Name your container
  
  # Which ports to expose
  ports:
    - "8003:8003"                      # Governor API
  
  # Environment variables - Settings for decision engine
  environment:
    - MONGODB_URI=mongodb://mongodb:27017
    - REDIS_URL=redis://redis:6379
    - POLICY_ENGINE=advanced          # Use advanced policy engine
    - DECISION_MODE=ensemble          # Use ensemble voting
    - RISK_SENSITIVITY=0.7            # Sensitivity to threats (0-1)
    - STAGE=3
    - SERVICE_NAME=governor
  
  # Services that must start before Stage 3
  depends_on:
    - mongodb
    - redis
  
  # Folders that store data outside container
  volumes:
    - ./checkpoints:/app/checkpoints   # ML model files
    - ./policies:/app/policies         # Governance policies (JSON)
    - ./logs/stage3:/app/logs          # Decision logs
    - ./backend:/app/backend           # Live code sync (dev)
  
  # Network - connects to other services
  networks:
    - security-net
  
  # Resource limits - Governor needs good CPU for ML
  deploy:
    resources:
      limits:
        cpus: '4'                      # Can use up to 4 CPUs
        memory: 8G                     # Can use up to 8GB RAM
      reservations:
        cpus: '2'
        memory: 4G
  
  # Restart policy
  restart: unless-stopped
```

### Step 4: Create Policy Files
**File: `policies/base_policies.json`**
```json
{
  "policies": [
    {
      "id": "policy_001",
      "name": "Admin Activity Control",
      "target": "admin_users",
      "rule": "role=admin AND time=business_hours THEN allow WITH approval",
      "risk_weight": 0.3,
      "enabled": true
    },
    {
      "id": "policy_002",
      "name": "High Risk Action Control",
      "target": "all_users",
      "rule": "threat_score > 0.8 THEN quarantine",
      "risk_weight": 1.0,
      "enabled": true
    },
    {
      "id": "policy_003",
      "name": "Impossible Travel Detection",
      "target": "all_users",
      "rule": "location_change > 1000km_in_1hour THEN require_mfa",
      "risk_weight": 0.9,
      "enabled": true
    }
  ]
}
```

### Step 5: Create Volume Folders
**Run these commands in PowerShell to create folders Docker needs:**
```powershell
# Create policy folder
New-Item -ItemType Directory -Path "policies" -Force

# Create checkpoint folder for ML models
New-Item -ItemType Directory -Path "checkpoints" -Force

# Create logs folder for Stage 3
New-Item -ItemType Directory -Path "logs/stage3" -Force

# Give permissions
icacls "policies" /grant:r "%USERNAME%:(OI)(CI)F"
icacls "checkpoints" /grant:r "%USERNAME%:(OI)(CI)F"
icacls "logs" /grant:r "%USERNAME%:(OI)(CI)F"
```

### Step 6: Create .env File for Configuration
**File: `.env` (in root folder)**
```env
# Stage 3 Governor Settings
STAGE_3_PORT=8003
POLICY_ENGINE=advanced
DECISION_MODE=ensemble
RISK_SENSITIVITY=0.7
ENSEMBLE_THRESHOLD=0.8         # Confidence threshold for decisions
MAX_POLICY_EVALUATION_TIME=500  # Max 500ms to make decision

# Model Configuration
MODEL_RANDOM_FOREST=true
MODEL_XGBOOST=true
MODEL_NEURAL_NET=true
MODEL_DECISION_TREE=true

# Database
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=entropy_stage3

# Redis
REDIS_URL=redis://redis:6379
REDIS_DB=2

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_RETENTION_DAYS=180
```

---

## 🚀 DOCKER WORKFLOW - STEP BY STEP

### What Docker Does:
1. **Build** = Creates a box with Python, ML libraries, and decision-making code
2. **Run** = Starts the Governor service that makes decisions
3. **Connect** = Connects to MongoDB (policies), Redis (cache), and receives data from Stages 1-2
4. **Persist** = Saves decision logs and policies for audit trail

### Workflow for Stage 3:

#### Step A: Build the Docker Image
**What this does:** Creates the box with all decision-making libraries

```powershell
# Navigate to project folder
cd p:\ENTROPY PRIME

# Build Stage 3 image
docker build -f backend/Dockerfile-stage3 -t entropy-governor:latest .

# Check if build succeeded
docker images | grep entropy-governor
```

**If build fails:**
- Usually it's XGBoost or scikit-learn installation
- Try: `pip install --upgrade --force-reinstall xgboost`
- Check error message for missing dependencies

#### Step B: Start All Services with Docker Compose
**What this does:** Starts Governor + MongoDB + Redis + other stages

```powershell
# Start all services
docker-compose -f docker-compose.yml up -d

# Check if Governor is healthy
docker-compose ps governor-stage3
```

**Expected output:**
```
NAME                      STATUS          PORTS
entropy-governor-stage3   Up 5 seconds    0.0.0.0:8003->8003/tcp
```

#### Step C: Check Logs to See if Working
**What this does:** Shows decision-making logs

```powershell
# Watch logs in real-time
docker logs -f entropy-governor-stage3 --tail 50

# Search logs for specific decisions
docker logs entropy-governor-stage3 | findstr "DECISION"

# See errors only
docker logs entropy-governor-stage3 | findstr "ERROR"
```

#### Step D: Test if Governor Service Works
**What this does:** Tests if decision engine is responding

```powershell
# Test health endpoint
curl http://localhost:8003/health

# Send a sample threat for decision
$body = @{
    user_id = "test_user"
    biometric_score = 0.75
    threat_score = 0.85
    stage = 2
} | ConvertTo-Json

curl -X POST http://localhost:8003/decide `
  -Header "Content-Type: application/json" `
  -Body $body
```

#### Step E: View Policies in MongoDB
**What this does:** Shows governance policies being used

```powershell
# Go inside MongoDB
docker exec -it mongodb mongosh

# Inside MongoDB shell:
use entropy_stage3
db.policies.find().pretty()
db.governance_decisions.find().limit(5).pretty()
exit
```

#### Step F: Check Decision Logs
**What this does:** Shows recent decisions Governor made

```powershell
# See latest decisions
Get-Content logs/stage3/decisions.log -Tail 20

# Count decisions made
(Get-Content logs/stage3/decisions.log | Measure-Object -Line).Lines

# Filter by decision type
Get-Content logs/stage3/decisions.log | findstr "quarantine"
```

#### Step G: Update Policies While Running
**What this does:** Change governance rules without restarting

```powershell
# Edit the policy file
code policies/base_policies.json

# The change takes effect automatically (Governor reloads)
# No need to rebuild!

# Verify change took effect
docker logs entropy-governor-stage3 | grep "policy_reload"
```

#### Step H: Enter Container and Test Models
**What this does:** Test ML models inside the Governor

```powershell
# Go inside container
docker exec -it entropy-governor-stage3 bash

# Inside container:
# Test if XGBoost works
python -c "import xgboost; print('XGBoost OK')"

# Test if models load
python -c "import torch; model = torch.load('/app/checkpoints/governor.pt'); print('Model loaded')"

# Exit
exit
```

#### Step I: Rebuild After Code Changes
**What this does:** Updates Governor with your new decision logic

```powershell
# Stop Governor
docker-compose stop governor-stage3

# Remove old container
docker-compose rm governor-stage3

# Rebuild
docker build -f backend/Dockerfile-stage3 -t entropy-governor:latest .

# Start new container
docker-compose up -d governor-stage3

# Check if working
docker logs -f entropy-governor-stage3
```

---

## 📊 DOCKER NETWORKING - How Stage 3 Receives & Sends Decisions

### Data Flow Architecture:
```
┌─────────────────────────────────────────┐
│         Docker Network (security-net)    │
│                                          │
│  Stage 1: Biometric                      │
│  ↓ (sends: biometric_score, anomaly)    │
│                                          │
│  Stage 2: Honeypot                       │
│  ↓ (sends: threat_score, attack_type)   │
│                                          │
│  ┌─────────────────────────────────┐   │
│  │ Stage 3: Governor ← You work here│   │
│  │ (receives from 1 & 2)            │   │
│  │ (makes DECISION)                 │   │
│  │ (sends to Stage 4)               │   │
│  └─────────────────────────────────┘   │
│  ↓ (sends: decision, confidence)        │
│                                          │
│  Stage 4: Watchdog                       │
│  (executes the decision)                 │
│                                          │
│  Database: MongoDB (policies, logs)      │
│  Cache: Redis (quick decisions)          │
└─────────────────────────────────────────┘
```

### How Governor Calls Other Stages:
**Inside Docker, use container names:**

```python
import requests

# Governor calling other stages inside Docker
stage1_data = requests.get('http://biometric-stage1:8001/profile/user123')
stage2_data = requests.get('http://honeypot-stage2:8002/threat/user123')

# Governor sending decision to Stage 4
requests.post('http://watchdog-stage4:8004/enforce', json=decision)
```

---

## 🔧 COMMON DOCKER COMMANDS FOR STAGE 3

| Command | What It Does |
|---------|----------|
| `docker build -f backend/Dockerfile-stage3 -t entropy-governor:latest .` | Build image |
| `docker-compose up -d governor-stage3` | Start Governor |
| `docker logs -f entropy-governor-stage3` | Watch decisions being made |
| `docker exec -it entropy-governor-stage3 bash` | Go inside |
| `docker-compose exec governor-stage3 python -c "import xgboost"` | Test library |
| `docker volume ls` | See all stored data |
| `docker inspect entropy-governor-stage3` | See detailed info |

---

## ⚠️ TROUBLESHOOTING DOCKER FOR STAGE 3

### Problem: XGBoost Installation Fails
```powershell
# This is a common issue on Windows
# Solution 1: Use prebuilt wheels
pip install xgboost --only-binary :all:

# Solution 2: In Dockerfile, add before pip install
# RUN apt-get install -y build-essential

# Solution 3: Use conda instead of pip
# FROM continuumio/miniconda3
# RUN conda install -c conda-forge xgboost
```

### Problem: Models Not Loading
```powershell
# Check if checkpoint folder exists
Get-ChildItem -Path "checkpoints"

# Check if files are readable
ls -la /app/checkpoints

# Inside container:
docker exec entropy-governor-stage3 ls -la /app/checkpoints

# If missing, copy model files manually
cp backend/checkpoints/*.pt checkpoints/
```

### Problem: Redis Connection Error
```powershell
# Check if Redis is running
docker-compose ps redis

# Test Redis connection
docker exec entropy-governor-stage3 ping redis

# Or manually test:
redis-cli -h redis ping
```

### Problem: Decisions Taking Too Long
```powershell
# Check if Governor is overloaded
docker stats entropy-governor-stage3

# Check logs for slow decisions
docker logs entropy-governor-stage3 | grep "time_ms"

# Solution: Increase CPU/memory limits in docker-compose.yml
# deploy:
#   resources:
#     limits:
#       cpus: '8'      (increase from 4)
#       memory: 16G    (increase from 8G)
```

---

## 📦 DOCKER BEST PRACTICES FOR STAGE 3

✅ **DO:**
- Keep policy files versioned
- Log all decisions for audit
- Test ensemble voting
- Monitor decision latency
- Cache frequent decisions in Redis
- Update policies without restart
- Track model accuracy
- Use structured logging

❌ **DON'T:**
- Hardcode decision thresholds
- Store secrets in Dockerfile
- Delete decision logs
- Change policies without backup
- Run without health checks
- Ignore model drift
- Skip audit logs

---

## ✅ DOCKER CHECKLIST - Before Starting Implementation

- [ ] Docker Desktop is installed and running
- [ ] docker-compose.yml updated with governor-stage3 service
- [ ] Dockerfile-stage3 created
- [ ] requirements-stage3.txt created (with XGBoost, sklearn)
- [ ] Volume folders created (checkpoints, policies, logs/stage3)
- [ ] .env file has Stage 3 settings
- [ ] Policy file created (base_policies.json)
- [ ] Health check configured
- [ ] Resource limits set (4 CPUs, 8GB RAM)
- [ ] Test that decision endpoint responds

---

### Key Docker Features for Stage 3:
- **Policy Volume:** Governance rules saved and persistent
- **Model Checkpoints:** ML models (Random Forest, XGBoost) saved
- **Health Checks:** Docker verifies decision engine responds in <10 seconds
- **Resource Allocation:** 4 CPUs ensures complex ML decisions are fast
- **Network:** Receives data from Stages 1-2, sends decisions to Stage 4

---

## 🤖 10 CLAUDE PROMPTS FOR GANESH - STAGE 3 IMPLEMENTATION

### Prompt 1: Multi-Factor Risk Scoring Engine
**File Location:** `backend/models/stage3_governor.py`
```
Create a comprehensive risk scoring model for Stage 3:
1. Input data from Stages 1 & 2:
   - Stage 1: biometric_score, anomaly_flags, user_profile
   - Stage 2: threat_score, attack_type, attacker_profile, indicators

2. Risk factors to evaluate:
   - Biometric risk: 30% weight
   - Threat detection risk: 40% weight
   - User context risk: 15% weight
   - Asset sensitivity risk: 15% weight

3. Biometric component:
   - Deviation from baseline: high=0.8, medium=0.5, low=0.2
   - Pattern novelty: completely new=1.0, similar=0.3
   - Anomaly count: more anomalies = higher risk

4. Threat component:
   - Attack sophistication: script_kiddie=0.3, advanced=0.9
   - Tool usage: known_malware=0.95, suspicious_tool=0.7
   - Attack phase: reconnaissance=0.4, exploitation=0.8, persistence=0.95

5. Context component:
   - Time context: off-hours activity increases risk
   - Location context: impossible travel flags risk
   - Role-based expectations: what's normal for this user
   - Device history: new device increases risk

6. Asset sensitivity:
   - Data classification: public=0.1, sensitive=0.5, critical=0.95
   - System importance: non-critical=0.2, critical=0.8
   - User privilege level: admin=higher_weight, user=lower_weight

7. Bayesian Risk Calculation:
   - Prior risk probability
   - Likelihood from each factor
   - Posterior probability using Bayes theorem
   - Final risk score = 0-1

8. Output structure:
   {
     "overall_risk_score": 0.75,
     "confidence": 0.92,
     "risk_breakdown": {
       "biometric": 0.65,
       "threat": 0.85,
       "context": 0.55,
       "asset": 0.80
     },
     "risk_level": "high",
     "primary_concerns": ["sophisticated_attack", "privilege_escalation"],
     "contributing_factors": [...],
     "supporting_evidence": {...}
   }

Use PyTorch for neural network components and Bayesian inference.
```

### Prompt 2: Ensemble Decision Making System
**File Location:** `backend/models/stage3_governor.py` (ensemble_module)
```
Build ensemble decision system combining multiple models:
1. Model 1: Random Forest Classifier
   - Input: Risk factors from Stage 1 & 2
   - Output: Decision probability for each action
   - Interpretable: Feature importance for explanation

2. Model 2: Gradient Boosting (XGBoost)
   - Input: Same as Model 1
   - Output: Decision scores
   - Captures non-linear relationships

3. Model 3: Neural Network (MLP)
   - Input: Risk vectors
   - Output: Decision probabilities
   - Captures complex patterns

4. Model 4: Decision Trees (Rule-based)
   - Hand-crafted decision rules from security experts
   - Explainable and auditable
   - Fallback when other models uncertain

5. Voting mechanism:
   - Hard voting: Majority vote determines action
   - Soft voting: Weighted average of probabilities
   - Weighted voting: Models with higher accuracy weighted more
   - Unanimous voting: Only decide if >80% agreement

6. Confidence calculation:
   - Agreement level: Are all models voting same direction?
   - Model uncertainty: Neural network confidence values
   - Data uncertainty: Is this within training distribution?
   - Combined confidence: 0-1 score

7. Disagreement handling:
   - Log cases where models disagree
   - Route to manual review queue if <70% confidence
   - Investigate disagreements for model improvement
   - Separate uncertainty detection from misclassification

8. Ensemble output:
   {
     "recommended_action": "allow|warn|quarantine|lockdown",
     "action_confidence": 0.92,
     "model_votes": {
       "random_forest": {"action": "quarantine", "confidence": 0.95},
       "xgboost": {"action": "quarantine", "confidence": 0.88},
       "neural_network": {"action": "warn", "confidence": 0.75},
       "decision_tree": {"action": "quarantine", "confidence": 0.92}
     },
     "voting_result": "majority_vote",
     "agreement_percentage": 75,
     "requires_manual_review": false,
     "explanation": "3/4 models recommend quarantine due to..."
   }

Include model performance tracking to adjust weights.
```

### Prompt 3: Intelligent Access Control Policy Engine
**File Location:** `backend/services/governor_services.py` (policy_engine_module)
```
Create dynamic access control policy engine:
1. Policy representation:
   - Attribute-based: (subject.role=admin) AND (resource.sensitivity=high) → DENY
   - Role-based: role=accountant → access=[ledgers, statements]
   - Risk-based: risk_score > 0.8 → DENY, 0.5-0.8 → MFA_REQUIRED, <0.5 → ALLOW
   - Temporal: office_hours=true → ALLOW, office_hours=false → REQUIRE_MFA

2. Policy evaluation:
   - Collect all applicable policies
   - Evaluate each policy against request
   - Combine results using logical operators
   - Return final decision: ALLOW/DENY/CONDITIONAL

3. Conditional decisions:
   - REQUIRE_MFA: Must provide additional authentication
   - RATE_LIMIT: Allow but limit action frequency
   - REQUIRE_REASON: Force user to provide justification
   - QUARANTINE_FIRST: Monitor before allowing
   - REQUIRE_APPROVAL: Need manager approval

4. Dynamic policy modification:
   - Base policies defined by security team
   - Risk-based modulation: Higher risk → stricter policies
   - User-specific policies: Learn from history
   - Time-based policies: Adaptive to attack patterns

5. Policy evaluation logic:
   def evaluate_access_request(user, resource, action, context):
     - Gather applicable policies
     - For each policy: evaluate(user, resource, action, context)
     - Combine decisions:
       * If any DENY: return DENY
       * If all ALLOW: return ALLOW
       * If mixed: return highest restriction level
     - Log decision with reasoning
     - Return action with any conditions

6. Policy output:
   {
     "decision": "ALLOW|DENY|CONDITIONAL",
     "action": "string",
     "conditions": [
       {"type": "mfa_required"},
       {"type": "rate_limit", "requests_per_minute": 10}
     ],
     "policies_evaluated": [...],
     "matching_policies": [...],
     "reasoning": "string",
     "confidence": 0.95,
     "can_appeal": true,
     "appeal_deadline": "ISO-8601"
   }

Store policies in MongoDB with version control.
```

### Prompt 4: Context-Aware Anomaly Scoring
**File Location:** `backend/services/governor_services.py` (context_module)
```
Build context-aware anomaly detection:
1. User behavior profiling:
   - Learn baseline behavior from historical data
   - Typical working hours
   - Common locations/IPs
   - Typical actions and sequences
   - Typical time between actions
   - Typical data accessed

2. Baseline calculation:
   - Features: actions, time of day, location, duration, data volume
   - Method 1: Mean/StdDev for each feature
   - Method 2: Clustering for multi-modal behavior
   - Method 3: Markov chains for action sequences
   - Update baseline monthly

3. Anomaly scoring:
   - For each action, calculate deviation from baseline
   - Multiple deviation types:
     * Temporal: Action outside normal hours
     * Spatial: Location impossible travel
     * Behavioral: Action type never done before
     * Volumetric: Data volume abnormally high
     * Sequential: Action sequence unusual

4. Contextual factors:
   - Time of day: Adjust expectations for time
   - Day of week: Different patterns weekday vs weekend
   - User role: Adjust for job function
   - Special events: Scheduled maintenance, high activity periods
   - Peer comparison: Compare against similar users

5. Scoring formula:
   - Base anomaly_score = normalized_deviations
   - Context_multiplier = time_factor × role_factor × event_factor
   - Final_score = base_anomaly_score × context_multiplier
   - Normalize to 0-1 range

6. Output:
   {
     "anomaly_score": 0.75,
     "is_anomalous": true,
     "anomaly_type": "impossible_travel|unusual_time|new_action|high_volume",
     "components": {
       "temporal": 0.8,
       "spatial": 0.9,
       "behavioral": 0.6,
       "volumetric": 0.4,
       "sequential": 0.5
     },
     "context": {
       "time_of_day": "after_hours",
       "user_role": "data_analyst",
       "day": "sunday",
       "is_special_event": false
     },
     "peer_percentile": 95,
     "baseline_behavior": {...},
     "supporting_evidence": [...]
   }

Use statistical methods and LSTM for temporal patterns.
```

### Prompt 5: Governance Decision & Recommendation Engine
**File Location:** `backend/pipeline/stage3_governor.py`
```
Create Stage 3 orchestration pipeline:
1. Main orchestration flow:
   - Receive biometric data from Stage 1
   - Receive threat data from Stage 2
   - Calculate multi-factor risk score
   - Run ensemble models
   - Evaluate policies
   - Calculate anomaly scores
   - Generate final recommendation
   - Pass to Stage 4

2. Data integration:
   - Merge Stage 1 & Stage 2 outputs
   - Handle missing data
   - Normalize different scales
   - Calculate composite features

3. Decision pathway:
   Stage 1 Data + Stage 2 Data
   ↓
   Risk Scoring Engine (Prompt 1)
   ↓
   Ensemble Models (Prompt 2)
   ↓
   Policy Evaluation (Prompt 3)
   ↓
   Anomaly Detection (Prompt 4)
   ↓
   Final Decision = Consensus from all components
   ↓
   Explanation & Recommendations
   ↓
   Stage 4 Enforcement

4. Functions to implement:
   - aggregate_threat_data(stage1_data, stage2_data) -> combined_data
   - calculate_risk_profile(combined_data) -> risk_scores
   - get_ensemble_decision(risk_scores) -> recommendation
   - evaluate_policies(user, action, risk) -> policy_decision
   - calculate_anomaly(user_data) -> anomaly_score
   - synthesize_decision(...) -> final_decision
   - generate_explanation(...) -> decision_explanation

5. Output format:
   {
     "stage": 3,
     "decision_id": "UUID",
     "timestamp": "ISO-8601",
     "user_id": "string",
     "overall_recommendation": "allow|warn|quarantine|lockdown",
     "confidence": 0.92,
     "risk_breakdown": {
       "biometric": 0.65,
       "threat": 0.85,
       "context": 0.55,
       "anomaly": 0.75
     },
     "ensemble_decision": {...},
     "policy_decision": {...},
     "rationale": "string",
     "supporting_evidence": [...],
     "can_appeal": true,
     "stage4_input": {...}
   }

Implement with clear state management.
```

### Prompt 6: Adaptive Policy Learning System
**File Location:** `backend/services/governor_services.py` (learning_module)
```
Create policy learning and optimization system:
1. Historical decision tracking:
   - Store all governance decisions
   - Track outcomes: correct/incorrect, false positive/negative
   - Measure impact: user satisfaction, security improvement
   - Analyze effectiveness over time

2. Feedback collection:
   - User feedback: Was decision fair? Helpful?
   - Security team feedback: Was threat real?
   - Incident investigation: What was actually compromised?
   - Behavioral analysis: Did enforcement prevent attack?

3. Policy effectiveness metrics:
   - True positive rate: Actual threats caught
   - False positive rate: Legitimate users blocked
   - Detection latency: Time to detect threat
   - False negative rate: Threats missed
   - User frustration: Appeal rate

4. Reinforcement learning for policies:
   - State: User, resource, context, risk
   - Action: governance decision
   - Reward: +1 if correct, 0 if missed threat, -1 if false positive
   - Learn optimal policy over time

5. A/B testing:
   - Test new policies on subset of users
   - Compare outcomes vs baseline
   - Statistical significance testing
   - Gradual rollout of effective policies

6. Policy recommendations:
   - Identify policies with high false positive rate
   - Suggest relaxation or refinement
   - Identify gaps where threats aren't caught
   - Recommend new policies based on incidents
   - Cost-benefit analysis for enforcement level

7. Learning output:
   {
     "policy_id": "uuid",
     "current_effectiveness": 0.85,
     "false_positive_rate": 0.05,
     "false_negative_rate": 0.02,
     "user_satisfaction": 0.72,
     "trend": "improving",
     "recommendations": [
       "Relax MFA requirement for known locations",
       "Add additional check for 3AM actions"
     ],
     "suggested_changes": {...}
   }

Store feedback in MongoDB with analysis.
```

### Prompt 7: Explainability & Decision Transparency
**File Location:** `backend/services/governor_services.py` (explainability_module)
```
Create explainable decision system:
1. Decision explanation components:
   - What factors contributed to decision?
   - What was weight of each factor?
   - Which stage provided most important signal?
   - What would change the decision?
   - What are edge cases for this decision?

2. LIME-style explanations:
   - Local interpretable model-agnostic explanations
   - Show which features most important for this decision
   - Create synthetic examples near decision boundary
   - Show counterfactual examples (what would flip decision)

3. Feature importance:
   - Global: Which features most important overall?
   - Local: Which features important for this decision?
   - Temporal: How did importance change?

4. Decision boundary visualization:
   - Show decision regions in feature space
   - Where does this decision fall?
   - How close to decision boundary?
   - What other decisions nearby?

5. Transparency levels:
   - User level: Simple language explanation
   - Security team: Detailed technical explanation
   - Executive: High-level risk summary
   - Audit: Complete decision trail with evidence

6. Explanation structure:
   {
     "decision": "quarantine",
     "confidence": 0.92,
     "brief_summary": "Access denied due to impossible travel + sophisticated attack",
     "detailed_explanation": {
       "main_factors": [
         {
           "factor": "Impossible Travel",
           "weight": 0.35,
           "details": "User was in New York 2 hours ago, now appears in London",
           "severity": "high"
         },
         {
           "factor": "Attack Sophistication",
           "weight": 0.30,
           "details": "Using tools similar to known APT group",
           "severity": "high"
         }
       ],
       "secondary_factors": [...],
       "counterfactual": "If user had normal biometric scores, decision would be WARN instead"
     },
     "can_challenge": true,
     "appeal_process": "..."
   }

Use SHAP values for feature importance.
```

### Prompt 8: Dynamic Threshold Adjustment
**File Location:** `backend/services/governor_services.py` (threshold_module)
```
Create adaptive threshold system:
1. Threshold factors:
   - Asset sensitivity: More sensitive → stricter (lower threshold)
   - User privilege: Admin users → stricter
   - Time: High-risk hours → stricter
   - Threat landscape: More attacks → stricter
   - False positive rate: Too many → relax

2. Baseline thresholds:
   - Allow: risk < 0.3
   - Warn: 0.3 ≤ risk < 0.6
   - Quarantine: 0.6 ≤ risk < 0.85
   - Lockdown: risk ≥ 0.85

3. Dynamic adjustment:
   - For high-value assets: risk < 0.2 triggers warn
   - For admin users: risk < 0.25 triggers warn
   - Off-hours: All thresholds reduced by 10%
   - During incident: All thresholds reduced by 30%

4. Feedback-based adjustment:
   - Track false positive rate
   - If FPR > 5%, increase threshold (relax)
   - If FNR > 2%, decrease threshold (tighten)
   - Monthly review and adjustment
   - A/B test new thresholds

5. User segment thresholds:
   - New employees: Stricter (lower threshold)
   - High-security role: Stricter
   - Remote workers: Medium
   - Office workers: Relaxed
   - Contractors: Strict

6. Threshold adjustment output:
   {
     "base_thresholds": {
       "warn": 0.3,
       "quarantine": 0.6,
       "lockdown": 0.85
     },
     "adjusted_thresholds": {
       "warn": 0.25,
       "quarantine": 0.55,
       "lockdown": 0.80
     },
     "adjustment_factors": [
       {"factor": "high_asset_sensitivity", "adjustment": -0.05},
       {"factor": "off_hours", "adjustment": -0.10}
     ],
     "effective_thresholds": {...}
   }

Store in Redis for real-time lookup.
```

### Prompt 9: Machine Learning Model Training for Stage 3
**File Location:** `backend/models/train_stage3_governor.py`
```
Create training pipeline for Stage 3 models:
1. Data preparation:
   - Source: Historical governance decisions
   - Features: Risk factors from stages 1-2, user context, asset details
   - Labels: Correct/incorrect decision, actual outcome, incident severity
   - Time split: Train on past 6 months, test on recent data

2. Model 1: Decision Classifier (XGBoost)
   - Input: Risk factors (50+ features)
   - Output: Decision class (allow/warn/quarantine/lockdown)
   - Imbalance handling: Class weights (allow >> lockdown)
   - Feature engineering: Polynomial features, interactions

3. Model 2: Risk Regression (Neural Network)
   - Input: Risk factors
   - Output: Risk score (0-1 continuous)
   - Architecture: 3-layer MLP with dropout
   - Loss: Mean Squared Error with penalties

4. Model 3: Policy Effectiveness (Multi-task Learning)
   - Input: Decision + context
   - Outputs:
     * Was decision correct? (binary)
     * Confidence in decision (regression)
     * Impact on user experience (regression)
   - Share feature layers

5. Model 4: Anomaly Score Predictor (Isolation Forest)
   - Input: User behavioral features
   - Output: Anomaly likelihood
   - Unsupervised learning: No labels needed

6. Training configuration:
   - Batch size: 128
   - Epochs: 200 with early stopping
   - Validation split: 20%
   - Test split: 10%
   - Cross-validation: 5-fold

7. Evaluation metrics:
   - F1 scores per decision class
   - ROC-AUC curves
   - Precision-recall curves
   - Calibration plots
   - Confusion matrices

8. Hyperparameter tuning:
   - Use Bayesian optimization
   - Optimize for F1 score
   - Constraints: Inference latency < 100ms

Save models to: checkpoints/governor_*.pt
```

### Prompt 10: Governance Decision Dashboard & Appeal System
**File Location:** `backend/services/governor_services.py` (dashboard_module) + `src/pages/GovernanceDashboard.jsx`
```
Create governance decision dashboard and appeal system:

Backend Endpoints:
1. GET /governance/decisions/{user_id}
   - Decision history with filtering
   - Status of each decision
   
2. GET /governance/decision/{decision_id}
   - Full decision details with explanation
   - Evidence supporting decision
   - Timeline of threat progression
   
3. POST /governance/appeal/{decision_id}
   - Submit appeal with reasoning
   - Queue for manual review
   
4. GET /governance/appeal/{appeal_id}
   - Check appeal status
   - See review notes
   
5. GET /governance/stats
   - Decision statistics
   - Appeal rate, overturn rate
   - Decision effectiveness metrics
   
6. WebSocket /governance/stream
   - Real-time decision notifications
   - Status updates for ongoing decisions

Frontend Components (src/pages/):
- DecisionHistory: Timeline of all decisions with filtering
- DecisionDetail: Full decision explanation and evidence
- AppealForm: Submit appeal with narrative
- AppealTracker: Track appeal status
- PolicyDashboard: Current policies in effect
- EffectivenessMetrics: How well system performing
- RiskScoreBreakdown: Visual breakdown of risk factors

Visual elements:
- Risk score gauge: Current risk level
- Factor importance: Which factors matter most
- Timeline: Threat progression
- Evidence: Supporting logs and data
- Decision path: How decision was made

Appeal workflow:
1. User submits appeal with reasoning
2. Routed to security team queue
3. Review within 24 hours
4. Possible outcomes: Upheld, Overturned, Modified
5. User notification of outcome
6. Feedback used for model improvement
```

---

## 📁 FILE STRUCTURE TO CREATE/MODIFY

```
backend/
├── models/
│   ├── stage3_governor.py (MAIN MODEL - Prompts 1, 2, 4)
│   └── train_stage3_governor.py (TRAINING - Prompt 9)
├── services/
│   └── governor_services.py (SERVICES - Prompts 3, 5-8, 10)
├── pipeline/
│   └── stage3_governor.py (ORCHESTRATION - Prompt 5)
├── tests/
│   └── test_stage3_governor.py (TESTING)
├── policies/
│   ├── base_policies.json
│   └── user_policies.json
└── Dockerfile-stage3

src/pages/
└── GovernanceDashboard.jsx (Prompt 10)
```

---

## 🚀 IMPLEMENTATION STEPS

1. **Week 1:** Implement Prompts 1 & 2 (Risk scoring, ensemble models)
2. **Week 2:** Implement Prompts 3, 4, 5 (Policy engine, context anomaly, orchestration)
3. **Week 3:** Implement Prompts 6, 7, 8 (Learning, explainability, thresholds)
4. **Week 4:** Implement Prompts 9, 10 (Training, dashboard & appeals)

---

## 📝 IMPORTANT NOTES

✅ **Work on branch:** `ganesh-stage3-governor-advanced`
✅ **Merge strategy:** Create PR to main after testing
✅ **Documentation:** Add docstrings to all functions
✅ **Logging:** Use structured logging with JSON output
✅ **Error handling:** Comprehensive try-catch with detailed error messages

---

## 🔗 DEPENDENCIES & INTEGRATION

**Receives from Stage 1 (Biometric Profiling):**
- biometric_profile: dict
- anomaly_flags: list
- risk_indicators: dict
- user_context: dict

**Receives from Stage 2 (Honeypot):**
- threat_score: float (0-1)
- threat_type: string
- attacker_profile: dict
- indicators_of_compromise: list

**Sends to Stage 4 (Watchdog):**
- decision: string (allow/warn/quarantine/lockdown)
- confidence: float
- risk_profile: dict
- enforcement_recommendation: dict
- audit_trail: dict

**Uses:**
- MongoDB for policies and decisions
- Redis for caching thresholds
- PyTorch for ML models
- XGBoost for classification

---

**Branch to work on:** `ganesh-stage3-governor-advanced`
**Merge responsibility:** Parikshith will handle merging to main after review
