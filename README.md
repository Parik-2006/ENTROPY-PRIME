# ⚡ ENTROPY PRIME — Zero-Trust Behavioral Biometrics Engine

A next-generation, production-ready authentication system that moves beyond reputation-based security (cookies, browser fingerprints) to **biological-physics security**. It analyzes neuromuscular jitter and temporal DNA via ML models running entirely in the browser.

---

## 📖 Project Objective

Modern authentication systems are vulnerable to bots and advanced attacks. ENTROPY PRIME leverages real-time behavioral biometrics and adaptive resource control to:

- Detect bots using live keyboard/mouse signals and ML.
- Dynamically adjust password hashing cost for each login.
- Trap bots in a honeypot for threat intelligence.
- Continuously monitor user identity with deep learning.

---

## ⚙️ Core Algorithmic Phases

1. **Biological Gateway (Frontend)**
   - Captures dwell/flight times and neuromuscular jitter.
   - 1D-CNN model outputs a humanity score ($\theta$).
   - Password entropy ($H_{exp}$) is computed.

2. **Resource Governor (Backend)**
   - DQN agent selects Argon2id hashing strength based on $\theta$, $H_{exp}$, and server load.
   - Bots get punished with hard settings, humans get fast logins.

3. **Offensive Deception (Backend)**
   - Bots ($\theta < 0.1$) get synthetic session tokens and are tracked in a honeypot.

4. **Session Watchdog (Frontend + Backend)**
   - Deep autoencoder anchors a baseline; trust score decays if user behavior changes.

---

## 🌍 Real-World Scenarios

| Industry         | The Problem                                   | The ENTROPY PRIME Solution                |
|------------------|-----------------------------------------------|-------------------------------------------|
| Banking/Finance  | Credential stuffing attacks                   | Biometric signals + adaptive hashing      |
| SaaS Platforms   | Bot signups, fake accounts                    | Honeypot deception + session monitoring   |
| Healthcare       | Insider threats, session hijacking            | Continuous trust scoring, passive reauth  |
| Cloud Services   | Resource exhaustion, brute-force attacks      | RL-based resource governor                |

---

## 🛠️ Tech Stack

- **Frontend:** React, Vite, TensorFlow.js, Recharts
- **Backend:** Python (FastAPI), PyTorch, Argon2-cffi
- **ML:** 1D-CNN (biometrics), DQN (resource governor), Autoencoder (session trust)
- **Visualization:** Recharts (live trust/entropy graphs)

---

## 🚀 How to Run Locally

### Quick Start

```bash
git clone https://github.com/your-username/entropy-prime.git
cd entropy-prime
chmod +x start.sh
./start.sh
```
- Open [http://localhost:3000](http://localhost:3000)
- The script auto-creates a Python venv, installs all dependencies, generates session secrets, and starts both the FastAPI backend (port 8000) and React frontend (port 3000).

### Manual Setup

#### Backend

```bash
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
# (Optional) Pre-train RL governor
python train.py --episodes 100000 --out ../checkpoints/governor.pt
export EP_RL_CHECKPOINT=../checkpoints/governor.pt
uvicorn main:app --reload --port 8000
```

#### Frontend

```bash
npm install
npm run dev        # → http://localhost:3000
```

---

## 📄 License

This project is for educational research purposes.

---

## 🤝 Contributing & Issues

- **Found a bug?** Please open a new issue and describe the problem.
- **Want to fix it?** Fork the repo and submit a Pull Request (PR) for review.

---

## Privacy Model
```
Browser (client)                  Server (backend)
───────────────────────────       ───────────────
Raw keystrokes      ─╮
Raw mouse coords    ─┤  never leave   Only transmitted:
Dwell/flight times  ─┤  the browser   • θ  (1 float)
Velocity/jitter     ─╯               • H_exp (1 float)
                                                • latent vector (32 floats)
```
- Raw biometric signals are processed entirely in the browser.
- The server only receives derived features (never raw signals).
- Impossible to reconstruct keystroke timings or mouse paths from server data.

---

## Extending the System
- **Add a real user DB:** Replace the `uid = "usr_" + secrets.token_hex(6)` line in `/score` with a lookup against your user store, and add a `/login` endpoint that verifies the password hash before issuing the session token.
- **Pre-train the RL policy:** Run `python backend/train.py --episodes 200000` for best results.
- **Add HTTPS:** Use Nginx in front of uvicorn for production. Set `VITE_API_URL` in production to point directly at your API domain.

---

## Contributing
Pull requests and suggestions are welcome! Please open an issue to discuss your ideas or improvements.

## License
This project is licensed under the MIT License.
