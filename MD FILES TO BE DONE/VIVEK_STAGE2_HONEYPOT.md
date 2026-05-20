# VIVEK - STAGE 2: HONEYPOT ADVANCED THREAT DETECTION
**Branch:** `vivek-stage2-honeypot-advanced`
**Assigned Stage:** Stage 2 - Honeypot & Threat Detection
**Role:** Implement intelligent honeypots, decoy systems, attack pattern recognition, and threat intelligence gathering

---

## 📋 5 UNIQUE IDEAS FROM IEEE PAPERS FOR STAGE 2

### Idea 1: **Interactive Honeypot Network (IHN)**
**IEEE Reference:** Based on "Interactive Honeypots for Threat Intelligence" papers
- **Features:**
  - Distributed honeypot nodes mimicking real services
  - Intelligent response generation to attacker interactions
  - Behavioral honeypots that simulate user activities
  - Deception tactics (fake credentials, false paths)
  - Automatic attack pattern extraction and classification

### Idea 2: **Deep Packet Inspection & Anomaly Detection (DPIAD)**
**IEEE Reference:** From "Deep Learning for Network Intrusion Detection"
- **Features:**
  - Real-time packet analysis with CNN/LSTM models
  - Payload inspection for malicious code signatures
  - Protocol anomaly detection (HTTP, SSH, DNS)
  - Encrypted traffic pattern analysis
  - Zero-day attack detection via behavioral patterns

### Idea 3: **Deception-Based Attack Response System (DBARS)**
**IEEE Reference:** Based on "Cyber Deception and Defensive Countermeasures"
- **Features:**
  - Generate realistic fake systems to redirect attackers
  - Adaptive honeypot responses based on attacker skill level
  - Polymorphic honeypots (appearance changes)
  - False evidence injection to mislead attackers
  - Attacker engagement tracking and profiling

### Idea 4: **Graph-Based Threat Pattern Recognition (GTPR)**
**IEEE Reference:** From "Graph Analytics for Cybersecurity"
- **Features:**
  - Build attack graphs from reconnaissance data
  - Identify multi-stage attack chains
  - Predict next attacker action
  - Community detection in threat actors
  - Relationship mapping (tools, targets, tactics)

### Idea 5: **Intelligent Honeypot Orchestration & Feedback Loop (IHOFL)**
**IEEE Reference:** Based on "Adaptive Security Systems"
- **Features:**
  - Auto-deploy honeypots based on threat landscape
  - Real-time feedback loop to update defense rules
  - Machine learning model retraining from honeypot data
  - Threat intelligence sharing with other stages
  - Cost-effective resource allocation for decoys

---

## 🐳 DOCKER STRUCTURE FOR STAGE 2

### What is Docker? (Simple Explanation)
**Docker = Containerization Tool**
- Think of Docker as a **box** that contains everything your Stage 2 service needs
- Box includes: Python, libraries, network tools, code files
- You can run this box on any computer and it works the same way
- Stage 2 needs extra tools (tcpdump, wireshark) that Docker installs automatically

### What You Need to Create:
1. **Dockerfile** = Recipe for creating the box with honeypot tools
2. **requirements-stage2.txt** = List of Python packages
3. **Docker Compose Configuration** = Settings for running with databases
4. **Volume Folders** = Folders for logs, packet captures, honeypotatterns

---

### Step 1: Create Requirements File
**File: `backend/requirements-stage2.txt`**
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
scapy==2.5.0
dpkt==1.9.7
paramiko==3.3.1
requests==2.31.0
aioredis==2.0.1
```

### Step 2: Create Dockerfile
**File: `backend/Dockerfile-stage2`**
```dockerfile
# Dockerfile for Honeypot Service
FROM python:3.11-slim

WORKDIR /app

# Install system tools for network packet capture and analysis
# This is what makes this Dockerfile special - it installs network tools
RUN apt-get update && apt-get install -y \
    tcpdump \
    wireshark-common \
    tshark \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY backend/requirements-stage2.txt .
RUN pip install --no-cache-dir -r requirements-stage2.txt

# Copy your stage 2 honeypot code
COPY backend/models/stage2_honeypot.py ./models/
COPY backend/services/honeypot_services.py ./services/
COPY backend/pipeline/stage2_honeypot.py ./pipeline/
COPY backend/main.py ./

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8002/health || exit 1

# Expose ports
# 8002 = Main Honeypot API
# 9000 = SSH Honeypot
# 9001 = HTTP Honeypot
# 9002 = FTP Honeypot
EXPOSE 8002 9000 9001 9002

# Start command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
```

### Step 3: Add to Docker Compose File
**File: `docker-compose.yml` (Add this service to existing file)**
```yaml
honeypot-stage2:
  build:
    context: .                          # Build from current folder
    dockerfile: backend/Dockerfile-stage2  # Use this recipe
  container_name: entropy-honeypot-stage2  # Name your container
  
  # Honeypot needs multiple ports for different services
  ports:
    - "8002:8002"        # Main API
    - "9000:9000"        # SSH Honeypot (fake SSH)
    - "9001:9001"        # HTTP Honeypot (fake web)
    - "9002:9002"        # FTP Honeypot (fake files)
  
  # Environment variables - Settings for honeypot
  environment:
    - MONGODB_URI=mongodb://mongodb:27017
    - REDIS_URL=redis://redis:6379
    - LOG_LEVEL=DEBUG
    - HONEYPOT_SENSITIVITY=0.8       # How sensitive to attacks
    - MAX_INTERACTIONS=1000          # Max attack interactions to track
    - CAPTURE_PACKETS=true           # Record network packets
    - STAGE=2
    - SERVICE_NAME=honeypot
  
  # Services that must start before Stage 2
  depends_on:
    - mongodb
    - redis
  
  # Folders that store data outside container
  volumes:
    - ./honeypot-logs:/app/logs       # Interaction logs
    - ./honeypot-captures:/app/captures  # Packet captures (pcap files)
    - ./checkpoints:/app/checkpoints  # ML models
    - ./backend:/app/backend          # Live code sync (dev mode)
  
  # Network - connects to other services
  networks:
    - security-net
  
  # Resource limits
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

### Step 4: Create Volume Folders
**Run these commands in PowerShell to create folders Docker needs:**
```powershell
# Create honeypot logs folder
New-Item -ItemType Directory -Path "honeypot-logs" -Force

# Create honeypot captures folder (for packet captures)
New-Item -ItemType Directory -Path "honeypot-captures" -Force

# Create checkpoint folder for ML models
New-Item -ItemType Directory -Path "checkpoints" -Force

# Give permissions
icacls "honeypot-logs" /grant:r "%USERNAME%:(OI)(CI)F"
icacls "honeypot-captures" /grant:r "%USERNAME%:(OI)(CI)F"
icacls "checkpoints" /grant:r "%USERNAME%:(OI)(CI)F"
```

### Step 5: Create .env File for Configuration
**File: `.env` (in root folder)**
```env
# Stage 2 Honeypot Settings
STAGE_2_PORT=8002
HONEYPOT_SENSITIVITY=0.8
HONEYPOT_SSH_PORT=9000
HONEYPOT_HTTP_PORT=9001
HONEYPOT_FTP_PORT=9002
CAPTURE_PACKETS=true
MAX_INTERACTIONS=1000

# Database
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=entropy_stage2

# Redis
REDIS_URL=redis://redis:6379
REDIS_DB=1

# Logging
LOG_LEVEL=DEBUG
LOG_FORMAT=json
```

---

## 🚀 DOCKER WORKFLOW - STEP BY STEP

### What Docker Does:
1. **Build** = Creates a box with Python, network tools, and your code
2. **Run** = Starts the box and opens all the honeypot ports
3. **Connect** = Connects to MongoDB and Redis
4. **Persist** = Saves attack logs and packet captures forever

### Workflow for Stage 2:

#### Step A: Build the Docker Image
**What this does:** Creates a box with network analysis tools installed

```powershell
# Navigate to project folder
cd p:\ENTROPY PRIME

# Build Stage 2 image
docker build -f backend/Dockerfile-stage2 -t entropy-honeypot:latest .

# Check if build succeeded
docker images | grep entropy-honeypot
```

**If build fails:**
- Check error message carefully
- Make sure `requirements-stage2.txt` exists
- Check file paths are correct
- Usually it's because package name is wrong - check PyPI for correct names

#### Step B: Start All Services with Docker Compose
**What this does:** Starts Stage 2 with all ports + MongoDB + Redis

```powershell
# Start all services in background
docker-compose -f docker-compose.yml up -d

# See which containers are running
docker-compose ps

# Check if Stage 2 is healthy
docker ps | grep honeypot
```

**Expected output - you should see these ports:**
```
NAME                       STATUS          PORTS
entropy-honeypot-stage2    Up 5 seconds    0.0.0.0:8002->8002/tcp, 
                                          0.0.0.0:9000->9000/tcp,
                                          0.0.0.0:9001->9001/tcp,
                                          0.0.0.0:9002->9002/tcp
```

#### Step C: Check Logs to See if Working
**What this does:** Shows what's happening inside the honeypot box

```powershell
# See last 50 lines of logs
docker logs -f entropy-honeypot-stage2 --tail 50

# See logs since 10 minutes ago
docker logs --since 10m entropy-honeypot-stage2
```

#### Step D: Test if Honeypots Are Working
**What this does:** Tests if fake services are responding

```powershell
# Test main API
curl http://localhost:8002/health

# Test if SSH honeypot is listening
Test-NetConnection -ComputerName localhost -Port 9000

# Test if HTTP honeypot is listening
Test-NetConnection -ComputerName localhost -Port 9001

# Test if FTP honeypot is listening
Test-NetConnection -ComputerName localhost -Port 9002
```

#### Step E: Try to Attack Your Own Honeypot
**What this does:** Tests if honeypot catches attacks (for testing)

```powershell
# Try to SSH to honeypot (will fail but get logged)
puTTY -ssh honeypot-user@localhost:9000

# Or try with Python
python -c "import paramiko; ssh = paramiko.SSHClient(); ssh.connect('localhost', port=9000, username='test', password='test')"

# This should be logged in MongoDB!
```

#### Step F: Check Captured Data
**What this does:** Shows attacks that were caught

```powershell
# Check honeypot logs
Get-ChildItem -Path "honeypot-logs"
Get-Content honeypot-logs/latest.log -Tail 20

# Check packet captures
Get-ChildItem -Path "honeypot-captures"

# Read pcap file with Wireshark (on Windows)
& 'C:\Program Files\Wireshark\wireshark.exe' honeypot-captures/captures.pcap
```

#### Step G: View MongoDB Data from Docker
**What this does:** Shows honeypot interactions stored in database

```powershell
# Go inside MongoDB container
docker exec -it mongodb mongosh

# Inside MongoDB shell:
use entropy_stage2
db.honeypot_interactions.find().pretty()
db.attack_logs.count()
exit
```

#### Step H: Rebuild After Code Changes
**What this does:** Updates all honeypot services with your new code

```powershell
# Stop Stage 2
docker-compose stop honeypot-stage2

# Remove old container
docker-compose rm honeypot-stage2

# Rebuild with new code
docker build -f backend/Dockerfile-stage2 -t entropy-honeypot:latest .

# Start new container
docker-compose up -d honeypot-stage2

# Check if working
docker logs -f entropy-honeypot-stage2
```

---

## 📊 DOCKER NETWORKING - How Stage 2 Talks to Other Stages

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
│  │ Stage 2: Honeypot (port 8002)    │   │ ← You work here
│  │   Fake SSH: 9000                 │   │
│  │   Fake HTTP: 9001                │   │
│  │   Fake FTP: 9002                 │   │
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

### How Stage 2 Calls Other Services:
**Inside Docker, use container names:**

```python
# Stage 2 calling Stage 1 (Biometric)
import requests

# Inside Docker container
response = requests.get('http://biometric-stage1:8001/analyze')

# From your computer (outside Docker)
response = requests.get('http://localhost:8001/analyze')
```

---

## 🔧 COMMON DOCKER COMMANDS FOR STAGE 2

| Command | What It Does |
|---------|----------|
| `docker build -f backend/Dockerfile-stage2 -t entropy-honeypot:latest .` | Create image with all tools |
| `docker-compose up -d honeypot-stage2` | Start Stage 2 |
| `docker logs -f entropy-honeypot-stage2` | Watch what's happening |
| `docker exec -it entropy-honeypot-stage2 bash` | Go inside container |
| `docker ps -a` | See all containers |
| `docker-compose ps` | See all services status |
| `docker inspect entropy-honeypot-stage2` | See detailed info |
| `docker volume ls` | See all storage |
| `docker network ls` | See all networks |

---

## ⚠️ TROUBLESHOOTING DOCKER FOR STAGE 2

### Problem: Ports 9000-9002 Already in Use
```powershell
# See what's using the ports
netstat -ano | findstr :9000

# Change ports in docker-compose.yml:
# ports:
#   - "8002:8002"
#   - "9010:9000"   (use 9010 instead)
#   - "9011:9001"
#   - "9012:9002"
```

### Problem: Can't Capture Packets
```powershell
# Check if tcpdump is installed
docker exec entropy-honeypot-stage2 which tcpdump

# If missing, rebuild image
docker build -f backend/Dockerfile-stage2 --no-cache -t entropy-honeypot:latest .

# Make sure permissions are correct
docker exec entropy-honeypot-stage2 chmod 777 /app/captures
```

### Problem: Honeypot Interactions Not Being Logged
```powershell
# Check MongoDB is running
docker-compose ps | grep mongodb

# Connect to MongoDB and check database
docker exec -it mongodb mongosh
use entropy_stage2
db.honeypot_interactions.find().count()

# If count is 0, check logs
docker logs entropy-honeypot-stage2 | grep ERROR
```

---

## 📦 DOCKER BEST PRACTICES FOR STAGE 2

✅ **DO:**
- Keep honeypot logs for investigation
- Use tcpdump for packet capture
- Store attack patterns in MongoDB
- Test honeypots with real attacks
- Keep volumes for persistence
- Monitor honeypot health
- Share captured data with other stages

❌ **DON'T:**
- Delete honeypot-logs folder (you need them)
- Block the honeypot ports from your own testing
- Mix honeypot with production traffic
- Share real user data through honeypot
- Run honeypot without tcpdump installed

---

## ✅ DOCKER CHECKLIST - Before Starting Implementation

- [ ] Docker Desktop is installed and running
- [ ] docker-compose.yml updated with honeypot-stage2 service
- [ ] Dockerfile-stage2 created
- [ ] requirements-stage2.txt created
- [ ] Volume folders created (honeypot-logs, honeypot-captures, checkpoints)
- [ ] .env file has Stage 2 settings
- [ ] tcpdump and tshark in Dockerfile
- [ ] Multiple ports exposed (8002, 9000, 9001, 9002)
- [ ] Health check configured
- [ ] Test that you can SSH to port 9000 (honeypot)

---

### Key Docker Features for Stage 2:
- **Multiple Port Bindings:** Each fake service (SSH, HTTP, FTP) has its own port
- **Persistent Volumes:** Attack logs and packet captures saved forever
- **Network Isolation:** Honeypot can't accidentally access real services
- **Resource Limits:** Honeypot can't use all CPU/memory if attacked
- **Network Tools:** Tcpdump and Wireshark included for packet analysis

---

## 🤖 10 CLAUDE PROMPTS FOR VIVEK - STAGE 2 IMPLEMENTATION

### Prompt 1: Honeypot Service Emulation Engine
**File Location:** `backend/models/stage2_honeypot.py`
```
Create a sophisticated honeypot emulation system that:
1. Simulates multiple services:
   - SSH with fake credentials database
   - HTTP web application with fake admin panels
   - FTP with fake file structure
   - MySQL with honeypot database
   - Custom application services

2. Intelligent response generation:
   - Responses vary based on attacker input
   - Realistic error messages (not too obvious)
   - Service version information (can be fake)
   - Delayed responses to simulate processing
   - Connection state management

3. Features for each service:
   - SSH: Failed login tracking, command history, fake shell environment
   - HTTP: Session tracking, cookie handling, form submission logging
   - FTP: File listing, fake file transfers, directory traversal attempts
   - MySQL: Query parsing, table enumeration, authentication attempts

4. Data structures:
   {
     "service_type": "ssh|http|ftp|mysql|custom",
     "port": integer,
     "fake_credentials": {"username": "password"},
     "version_string": "OpenSSH_7.4",
     "interaction_log": [],
     "threat_indicators": [],
     "attacker_profile": {}
   }

5. Interaction logging:
   - Timestamp
   - Command executed
   - Attacker tool fingerprint (Metasploit, custom, etc.)
   - Response sent
   - Time to respond

Include PyTorch-based service classifier to identify attacker tools.
```

### Prompt 2: Network Packet Analysis & Anomaly Detection
**File Location:** `backend/models/stage2_honeypot.py` (packet_analyzer_module)
```
Build packet analysis system for Stage 2 honeypot:
1. Real-time packet capture and parsing:
   - Capture packets from honeypot services
   - Parse headers (IP, TCP, UDP, HTTP, SSH, FTP)
   - Extract application-layer data
   - Store raw packet data in pcap format

2. Anomaly detection using Deep Learning:
   - CNN model for pattern recognition in packet sequences
   - Features: packet sizes, inter-arrival times, flags, payloads
   - Detect known attack patterns
   - Detect novel attack patterns via autoencoder

3. Classification models:
   - Identify tool used (Nmap, Metasploit, custom, etc.)
   - Detect attack type (reconnaissance, exploitation, lateral movement)
   - Estimate attacker skill level (script kiddie vs APT)
   - Identify attack phase (scanning → exploitation → persistence)

4. Threat scoring:
   - Baseline normal traffic
   - Deviation scoring
   - Cumulative threat score
   - Output: 0-1 threat score with confidence

5. Feature engineering:
   - Packet size distribution
   - Inter-packet timing analysis
   - Protocol distribution
   - Payload entropy
   - Connection patterns

6. Output format:
   {
     "packet_id": "UUID",
     "timestamp": "ISO-8601",
     "threat_score": 0.75,
     "confidence": 0.92,
     "attack_type": "reconnaissance|exploitation|lateral_movement",
     "tool_fingerprint": "nmap|metasploit|custom",
     "protocol_anomalies": ["TCP_flag_unusual"],
     "payload_analysis": {"entropy": 7.2, "malware_detected": false},
     "recommended_action": "log|quarantine|block"
   }

Use PyTorch LSTM for temporal sequence modeling.
```

### Prompt 3: Attack Pattern Recognition & Threat Intelligence
**File Location:** `backend/services/honeypot_services.py` (threat_intel_module)
```
Create attack pattern recognition system:
1. Build attack signature database:
   - Store known attack patterns
   - MITRE ATT&CK framework mapping
   - CWE/CVE references
   - Tool signatures (Metasploit modules, custom exploits)
   - Attacker TTPs (Tactics, Techniques, Procedures)

2. Real-time pattern matching:
   - Compare honeypot interactions against known patterns
   - Fuzzy matching for variations
   - Temporal correlation (time between events)
   - Spatial correlation (source IPs, destinations)

3. Machine learning for unknown patterns:
   - Anomaly detection for novel attacks
   - Clustering similar interactions
   - Trend analysis over time
   - Predictive attack forecasting

4. Threat intelligence output:
   {
     "attack_id": "UUID",
     "pattern_confidence": 0.95,
     "matches": [
       {
         "signature_id": "sig_001",
         "attack_name": "Apache Struts RCE",
         "framework": "MITRE ATT&CK",
         "technique_id": "T1190",
         "severity": "critical",
         "description": "Remote code execution via vulnerable Struts",
         "indicators": ["GET request pattern", "payload signature"]
       }
     ],
     "attacker_profile": {
       "origin_country": "estimated",
       "skill_level": 0-10,
       "group_affiliation": "estimated",
       "known_targets": []
     },
     "related_attacks": []
   }

5. Integration with threat feeds:
   - Ingest external threat intelligence
   - Cross-reference with honeypot data
   - Identify known threat actors
   - Share indicators with other systems

Implement with Neo4j for relationship mapping.
```

### Prompt 4: Interactive Honeypot Response Simulation
**File Location:** `backend/services/honeypot_services.py` (interaction_module)
```
Create realistic interactive honeypot response system:
1. Context-aware responses:
   - Remember previous attacker actions
   - Maintain session state
   - Provide logical progression of fake system

2. Service-specific behaviors:
   - SSH: Respond to commands with realistic output
     * ls command returns fake files/directories
     * cat returns fake file contents
     * whoami returns honeypot user
     * Error messages match service version
   
   - HTTP: Simulate web application
     * Login form with rate limiting
     * Admin panel with fake data
     * Database error pages
     * Cookies and session tracking
   
   - FTP: Simulate file server
     * Directory traversal attempts logged
     * File upload acceptance
     * PASV mode simulated
     * Banner includes fake version

3. Deception tactics:
   - Insert false clues (old log files, config files)
   - Leave fake credentials in obvious places
   - Create honeypot users with suspicious activity
   - Stage incomplete exploits (makes attacker think system partially compromised)

4. Timing simulation:
   - Add realistic delays based on command complexity
   - Simulate I/O wait times
   - Vary response times to avoid obvious patterns

5. Intelligence gathering:
   Track for each attacker:
   - Commands executed
   - Reconnaissance techniques
   - Tool usage
   - Attack progression
   - Time spent in system
   - Failed/successful attempts

Output structure:
{
  "interaction_id": "UUID",
  "attacker_ip": "string",
  "session_id": "string",
  "service": "string",
  "timestamp": "ISO-8601",
  "command": "string",
  "response": "string",
  "response_time_ms": 100,
  "threat_indicators_in_response": [],
  "next_likely_commands": []
}
```

### Prompt 5: Polymorphic Honeypot Generation
**File Location:** `backend/services/honeypot_services.py` (polymorphic_module)
```
Build polymorphic honeypot system that changes appearance:
1. Dynamic configuration generation:
   - Generate different fake versions of services
   - Randomize directory structures
   - Vary response messages
   - Change fake credentials
   - Modify error messages

2. Trigger-based changes:
   - After detecting reconnaissance
   - If attacker attempts exploitation
   - On time-based schedule (daily rotation)
   - Per-attacker customization

3. Appearance variations:
   - Service version can be:
     * Old (likely to have known vulnerabilities)
     * Current (appears well-maintained)
     * Patched (false confidence)
   
   - Operating system fingerprints:
     * Linux variants
     * Windows versions
     * BSD variants
   
   - File system layouts:
     * Web root directories
     * Config file locations
     * Log directories

4. Adaptive polymorphism:
   - Learn from attacker behavior
   - If attacker targets specific CVEs, appear vulnerable to others
   - If attacker uses specific tools, prepare deceptive responses

5. Configuration persistence:
   - Store configurations in database
   - Allow manual override
   - Track which configuration caught which attacks

Configuration structure:
{
  "honeypot_instance_id": "UUID",
  "polymorphic_id": "UUID",
  "version": "1.2.3",
  "os_fingerprint": "Linux 4.15",
  "fake_credentials": {},
  "fake_files": [],
  "error_message_set": "set_001",
  "response_timing": "random",
  "created_at": "ISO-8601",
  "attacks_caught": []
}
```

### Prompt 6: Honeypot Orchestration & Deployment
**File Location:** `backend/pipeline/stage2_honeypot.py`
```
Create honeypot orchestration system:
1. Pipeline orchestration:
   - get_threat_from_stage1(biometric_data) -> threat_alert
   - deploy_honeypot(threat_alert) -> honeypot_config
   - monitor_honeypot() -> interactions
   - analyze_interactions(interactions) -> threat_analysis
   - update_models(threat_analysis) -> model_update
   - pass_to_stage3(threat_analysis) -> None

2. Dynamic honeypot deployment:
   - Deploy honeypot based on predicted attacker target
   - If Stage 1 detected: Data exfiltration risk → Deploy database honeypot
   - If Stage 1 detected: Privilege escalation risk → Deploy admin panel honeypot
   - If Stage 1 detected: Lateral movement risk → Deploy internal service honeypots

3. Resource management:
   - Spawn honeypot services on demand
   - Clean up after attack ends
   - Reuse honeypot instances when possible
   - Monitor resource utilization

4. Communication with other stages:
   - Input: User biometric profile from Stage 1
   - Output: Threat analysis for Stage 3
   - Feedback: Recovery actions from Stage 4

5. Response schema:
   {
     "stage": 2,
     "honeypot_ids": ["uuid1", "uuid2"],
     "threat_score": 0.75,
     "threat_type": "reconnaissance",
     "confidence": 0.92,
     "attack_timeline": [],
     "attacker_profile": {},
     "indicators_of_compromise": [],
     "suggested_defense": "string",
     "stage3_input": {...}
   }

Include state machine for honeypot lifecycle.
```

### Prompt 7: Attacker Profiling & Behavioral Analysis
**File Location:** `backend/services/honeypot_services.py` (profiling_module)
```
Build attacker profiling system:
1. Profile attributes:
   - Skill level: 0-10 (script kiddie to nation-state)
   - Tool usage patterns
   - Attack methodology
   - Time zone/geography indicators
   - Language clues (error messages, comments)
   - Target preferences
   - Persistence behaviors

2. Skill level indicators:
   - Automation vs manual interaction
   - Error handling sophistication
   - Tool customization
   - Multi-stage attack planning
   - Covering tracks techniques

3. Attribution clues:
   - IP geolocation
   - Infrastructure patterns (VPN, proxy usage)
   - Tool versions and modifications
   - Timing patterns (when attacks occur)
   - Language and cultural indicators
   - Known threat actor tool kits

4. Behavioral clustering:
   - Group attacks by similar characteristics
   - Identify repeat attackers
   - Link to known threat groups
   - Predict group membership

5. Output profile:
   {
     "attacker_id": "UUID or known_group_id",
     "skill_level": 7,
     "skill_confidence": 0.85,
     "likely_group": "apt28",
     "group_confidence": 0.72,
     "origin_country": "RU",
     "motivation": "financial|political|espionage",
     "targets": ["finance", "healthcare"],
     "known_tools": ["metasploit", "nmap"],
     "ttps": ["T1087", "T1592"],
     "last_seen": "ISO-8601",
     "attack_frequency": "daily",
     "sophistication": "advanced"
   }

Use MITRE ATT&CK framework for TTP mapping.
```

### Prompt 8: Deceptive Payload & Evidence Injection
**File Location:** `backend/services/honeypot_services.py` (deception_module)
```
Create deceptive evidence injection system:
1. False evidence generation:
   - Create fake config files with credentials
   - Generate fake database backups
   - Simulate incomplete exploitations
   - Leave suspicious log entries
   - Create honeypot user accounts with activity

2. Strategic placement:
   - Place clues in discoverable but not obvious locations
   - Vary placement based on attacker profile
   - Escalate clues (harder to find = more valuable)
   - Create breadcrumb trails

3. Payload types:
   - Fake source code files
   - Credential files (ssh keys, database passwords)
   - Config files with sensitive data
   - Log files showing compromise
   - Backup files with valuable data

4. Attacker engagement strategies:
   - For novice attackers: Obvious clues
   - For intermediate: Mix of real and fake
   - For advanced: Sophisticated deception
   - Create paths that lead to dead ends

5. False confidence building:
   - Stage 1: Show easy reconnaissance success
   - Stage 2: Appear vulnerable to known CVEs
   - Stage 3: Leave signs of previous breach
   - Stage 4: Suggest successful persistence

Example false evidence structure:
{
  "evidence_id": "UUID",
  "type": "credential_file|config_file|log_entry|backup",
  "content": "fake_data",
  "location": "/home/user/.ssh/id_rsa",
  "timestamp_created": "ISO-8601",
  "discoverable_by": "basic|intermediate|advanced",
  "value_to_attacker": "access_escalation",
  "expected_action": "private_key_usage",
  "trap_trigger": "if_key_used_trigger_alert"
}
```

### Prompt 9: Machine Learning Model Training for Stage 2
**File Location:** `backend/models/train_stage2_honeypot.py`
```
Create training pipeline for Stage 2 models:
1. Data preparation:
   - Source: Honeypot interaction logs
   - Features: Packet characteristics, command patterns, timing, payloads
   - Labels: Attack type, tool used, attacker skill, success/failure
   - Augmentation: Synthetic attack generation

2. Model 1: Attack Classification (CNN + LSTM)
   - Input: Sequence of packets/interactions
   - Output: Attack type (reconnaissance, exploitation, lateral movement)
   - Architecture: 1D CNN → LSTM → Dense layers
   - Loss: CrossEntropyLoss
   - Metrics: Accuracy, Precision, Recall per class

3. Model 2: Attacker Profiling (Multi-task Learning)
   - Input: Complete interaction sequence
   - Output: 
     * Skill level (regression 0-10)
     * Tool type (classification: metasploit/nmap/custom)
     * Likely group (classification: known_groups or unknown)
   - Share lower layers, split at classification

4. Model 3: Anomaly Detection (Autoencoder)
   - Input: Packet/command sequence
   - Output: Reconstruction error
   - Detect novel attack patterns
   - Threshold-based anomaly scoring

5. Model 4: Next Action Prediction (LSTM)
   - Input: Historical commands/packets
   - Output: Predicted next action
   - Used for preparation and deception

6. Training configuration:
   - Batch size: 64
   - Epochs: 150 with early stopping
   - Optimizer: Adam (lr=0.001)
   - Validation: 20% split
   - Test: 10% held out

7. Evaluation:
   - Per-attack-type metrics
   - Confusion matrices
   - ROC-AUC curves
   - Calibration curves

8. Dataset:
   - Source: Honeypot logs + public datasets (CICIDS2018, UNSW-NB15)
   - Normalization: StandardScaler
   - Imbalance handling: SMOTE

Save models to: checkpoints/honeypot_*.pt
```

### Prompt 10: Real-time Honeypot Monitoring Dashboard
**File Location:** `backend/services/honeypot_services.py` (monitoring_module) + `src/pages/HoneypotDashboard.jsx`
```
Create honeypot monitoring system:

Backend Endpoints:
1. GET /honeypot/status
   - All active honeypots and their status
   - Interaction count, threat level
   
2. GET /honeypot/interactions/{honeypot_id}
   - Paginated interaction log
   - Filtering by time, command, tool
   
3. GET /honeypot/attacks/timeline
   - Timeline of attacks across all honeypots
   - Attack types, duration, intensity
   
4. GET /honeypot/attackers
   - List of known attackers
   - Profiles, repeat attacks
   - Behavior patterns
   
5. WebSocket /honeypot/stream
   - Real-time interaction stream
   - Live command monitoring
   - Attack detection alerts

6. GET /honeypot/threat-intelligence
   - Aggregated threat insights
   - Attack trends, tool usage statistics
   - Attacker group activity

Frontend Components (src/pages/):
- HoneypotStatus: Real-time status of all honeypots
- InteractionLog: Detailed log with filtering
- AttackTimeline: Timeline visualization
- AttackerProfiles: Known attackers and their profiles
- ThreatIntelligence: Aggregated insights
- NetworkMap: Visual representation of honeypot network

Real-time updates:
- New interactions: Update within 100ms
- Attack detection: Alert immediately
- Metrics: Refresh every 5 seconds

Visualization ideas:
- Sankey diagram: Attack progression
- Heat map: Time of day patterns
- Geographic map: Attacker locations
- Tool usage chart: Most common attack tools
```

---

## 📁 FILE STRUCTURE TO CREATE/MODIFY

```
backend/
├── models/
│   ├── stage2_honeypot.py (MAIN MODEL - Prompts 1, 2)
│   └── train_stage2_honeypot.py (TRAINING - Prompt 9)
├── services/
│   └── honeypot_services.py (SERVICES - Prompts 3-5, 7-8, 10)
├── pipeline/
│   └── stage2_honeypot.py (ORCHESTRATION - Prompt 6)
├── tests/
│   └── test_stage2_honeypot.py (TESTING)
└── Dockerfile-stage2

src/pages/
└── HoneypotDashboard.jsx (Prompt 10)
```

---

## 🚀 IMPLEMENTATION STEPS

1. **Week 1:** Implement Prompts 1 & 2 (Honeypot emulation, packet analysis)
2. **Week 2:** Implement Prompts 3, 4, 6 (Pattern recognition, interaction, orchestration)
3. **Week 3:** Implement Prompts 5, 7, 8 (Polymorphism, profiling, deception)
4. **Week 4:** Implement Prompts 9, 10 (Training, monitoring)

---

## 📝 IMPORTANT NOTES

✅ **Work on branch:** `vivek-stage2-honeypot-advanced`
✅ **Merge strategy:** Create PR to main after testing
✅ **Documentation:** Add docstrings to all functions
✅ **Logging:** Use structured logging with JSON output
✅ **Error handling:** Comprehensive try-catch with detailed error messages

---

## 🔗 DEPENDENCIES & INTEGRATION

**Receives from Stage 1 (Biometric Profiling):**
- user_biometric_profile: dict
- anomaly_detection: bool
- risk_score: float

**Sends to Stage 3 (Governor):**
- threat_score: float (0-1)
- threat_type: string
- attacker_profile: dict
- attack_timeline: list
- indicators_of_compromise: list

**Uses:**
- MongoDB for attack logs
- Redis for session management
- Elasticsearch for log aggregation (optional)
- Neo4j for attack graph (optional)

---

**Branch to work on:** `vivek-stage2-honeypot-advanced`
**Merge responsibility:** Parikshith will handle merging to main after review
