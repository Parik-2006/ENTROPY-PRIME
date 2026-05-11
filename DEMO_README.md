# Entropy Prime — Phase 2 Demo Guide

Short, simple, end-to-end explanation of what the project does, how it is deployed with Docker, and what each component/endpoints do. Includes diagrams and a demo checklist so you can present the prototype clearly.

---

## Abstract (one paragraph)

Entropy Prime is a prototype “zero-trust” authentication demo that augments normal email/password login with behavioral biometrics (keystroke/pointer signals). The frontend (SPA) collects biometric signals while the user types, then calls the backend API to authenticate and to submit biometric data to a 4-stage inference pipeline. The app runs as a Docker Compose stack: `nginx` serves the SPA and reverse-proxies API calls to the FastAPI backend, which stores users and sessions in MongoDB and uses Redis for caching/rate-limits. The backend references trained model checkpoints from the `checkpoints/` folder to run inference.

---

## High-level architecture

## High-level architecture

<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="620" viewBox="0 0 1100 620">
  <defs>
    <style>
      .title { font-family: "Segoe UI", Arial, sans-serif; font-size: 22px; font-weight: bold; fill: #0f172a; }
      .layer-label { font-family: "Segoe UI", Arial, sans-serif; font-size: 11px; font-weight: bold; fill: #666; text-transform: uppercase; letter-spacing: 1px; }
      .comp-title { font-family: "Segoe UI", Arial, sans-serif; font-size: 12px; font-weight: 700; fill: #111827; }
      .comp-detail { font-family: "Segoe UI", Arial, sans-serif; font-size: 10px; fill: #475569; }
      .box-client { fill: #dbeafe; stroke: #0284c7; stroke-width: 2px; rx: 8; }
      .box-proxy { fill: #fef3c7; stroke: #d97706; stroke-width: 2px; rx: 8; }
      .box-api { fill: #fecaca; stroke: #dc2626; stroke-width: 2px; rx: 8; }
      .box-data { fill: #dcfce7; stroke: #16a34a; stroke-width: 2px; rx: 8; }
      .box-ml { fill: #e9d5ff; stroke: #9333ea; stroke-width: 2px; rx: 8; }
      .arrow { stroke: #334155; stroke-width: 2px; fill: none; marker-end: url(#arrowhead); }
      .arrow-label { font-family: "Segoe UI", Arial, sans-serif; font-size: 9px; fill: #475569; background: white; }
      .divider { stroke: #e2e8f0; stroke-width: 1px; }
    </style>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#334155" />
    </marker>
  </defs>

  <!-- Title -->
  <text x="30" y="40" class="title">Entropy Prime — Layered Architecture</text>

  <!-- ======= CLIENT LAYER ======= -->
  <text x="30" y="90" class="layer-label">■ Client Layer</text>
  <rect x="30" y="105" width="240" height="130" class="box-client" />
  <text x="150" y="135" text-anchor="middle" class="comp-title">Web Browser</text>
  <text x="150" y="150" text-anchor="middle" class="comp-detail">HTML/CSS/JavaScript</text>
  <text x="150" y="163" text-anchor="middle" class="comp-detail">Keystroke & Pointer Capture</text>
  <text x="150" y="176" text-anchor="middle" class="comp-detail">Biometric Signal Processing</text>
  <text x="150" y="189" text-anchor="middle" class="comp-detail">Session Token Management</text>
  <text x="150" y="202" text-anchor="middle" class="comp-detail">User Credential Input</text>
  <text x="150" y="220" text-anchor="middle" class="comp-detail" style="font-style: italic;">(login, register, rate-limit UI)</text>

  <!-- ======= PROXY LAYER ======= -->
  <text x="330" y="90" class="layer-label">■ Proxy/Edge Layer</text>
  <rect x="330" y="105" width="240" height="130" class="box-proxy" />
  <text x="450" y="135" text-anchor="middle" class="comp-title">nginx Reverse Proxy</text>
  <text x="450" y="150" text-anchor="middle" class="comp-detail">Static Asset Serving</text>
  <text x="450" y="163" text-anchor="middle" class="comp-detail">API Request Routing</text>
  <text x="450" y="176" text-anchor="middle" class="comp-detail">Rate-Limiting (lua script)</text>
  <text x="450" y="189" text-anchor="middle" class="comp-detail">Response Caching</text>
  <text x="450" y="202" text-anchor="middle" class="comp-detail">HTTPS Termination</text>
  <text x="450" y="220" text-anchor="middle" class="comp-detail" style="font-style: italic;">(docker port 80→443)</text>

  <!-- ======= FRONTEND LAYER ======= -->
  <text x="630" y="90" class="layer-label">■ Frontend Layer</text>
  <rect x="630" y="105" width="240" height="130" class="box-client" />
  <text x="750" y="135" text-anchor="middle" class="comp-title">React SPA (Vite)</text>
  <text x="750" y="150" text-anchor="middle" class="comp-detail">Login/Register Pages</text>
  <text x="750" y="163" text-anchor="middle" class="comp-detail">Dashboard & Profile UI</text>
  <text x="750" y="176" text-anchor="middle" class="comp-detail">SDK Integration</text>
  <text x="750" y="189" text-anchor="middle" class="comp-detail">State Management (Context API)</text>
  <text x="750" y="202" text-anchor="middle" class="comp-detail">API Client (fetch wrapper)</text>
  <text x="750" y="220" text-anchor="middle" class="comp-detail" style="font-style: italic;">(src/ directory)</text>

  <!-- ======= API LAYER ======= -->
  <text x="30" y="290" class="layer-label">■ API / Business Logic Layer</text>
  <rect x="30" y="305" width="840" height="140" class="box-api" />
  <rect x="45" y="315" width="200" height="120" fill="none" stroke="#dc2626" stroke-width="1px" rx="6" stroke-dasharray="3,3" />
  <text x="145" y="335" text-anchor="middle" class="comp-title">Auth Module</text>
  <text x="145" y="350" text-anchor="middle" class="comp-detail">/auth/register</text>
  <text x="145" y="363" text-anchor="middle" class="comp-detail">/auth/login</text>
  <text x="145" y="376" text-anchor="middle" class="comp-detail">/auth/logout</text>
  <text x="145" y="389" text-anchor="middle" class="comp-detail">(Argon2 hashing)</text>
  <text x="145" y="403" text-anchor="middle" class="comp-detail">(session creation)</text>

  <rect x="265" y="315" width="200" height="120" fill="none" stroke="#dc2626" stroke-width="1px" rx="6" stroke-dasharray="3,3" />
  <text x="365" y="335" text-anchor="middle" class="comp-title">Session/Token Mgmt</text>
  <text x="365" y="350" text-anchor="middle" class="comp-detail">/session/verify</text>
  <text x="365" y="363" text-anchor="middle" class="comp-detail">/me (profile)</text>
  <text x="365" y="376" text-anchor="middle" class="comp-detail">Token validation</text>
  <text x="365" y="389" text-anchor="middle" class="comp-detail">Expiry checks</text>
  <text x="365" y="403" text-anchor="middle" class="comp-detail">(MongoDB lookup)</text>

  <rect x="485" y="315" width="200" height="120" fill="none" stroke="#dc2626" stroke-width="1px" rx="6" stroke-dasharray="3,3" />
  <text x="585" y="335" text-anchor="middle" class="comp-title">Biometric Pipeline</text>
  <text x="585" y="350" text-anchor="middle" class="comp-detail">/score endpoint</text>
  <text x="585" y="363" text-anchor="middle" class="comp-detail">Stage 1: Biometric</text>
  <text x="585" y="376" text-anchor="middle" class="comp-detail">Stage 2: Honeypot</text>
  <text x="585" y="389" text-anchor="middle" class="comp-detail">Stage 3: Governor</text>
  <text x="585" y="403" text-anchor="middle" class="comp-detail">Stage 4: Watchdog</text>

  <rect x="705" y="315" width="155" height="120" fill="none" stroke="#dc2626" stroke-width="1px" rx="6" stroke-dasharray="3,3" />
  <text x="782.5" y="335" text-anchor="middle" class="comp-title">Admin APIs</text>
  <text x="782.5" y="350" text-anchor="middle" class="comp-detail">/admin/models-status</text>
  <text x="782.5" y="363" text-anchor="middle" class="comp-detail">/admin/telemetry</text>
  <text x="782.5" y="376" text-anchor="middle" class="comp-detail">/admin/users</text>
  <text x="782.5" y="389" text-anchor="middle" class="comp-detail">Debug endpoints</text>

  <!-- ======= DATA LAYER ======= -->
  <text x="30" y="520" class="layer-label">■ Data / State Layer</text>
  
  <rect x="30" y="535" width="220" height="70" class="box-data" />
  <text x="140" y="560" text-anchor="middle" class="comp-title">MongoDB</text>
  <text x="140" y="575" text-anchor="middle" class="comp-detail">users, sessions, honeypot_logs</text>
  <text x="140" y="588" text-anchor="middle" class="comp-detail">admin_audit, pipeline_cache</text>

  <rect x="300" y="535" width="220" height="70" class="box-data" />
  <text x="410" y="560" text-anchor="middle" class="comp-title">Redis Cache</text>
  <text x="410" y="575" text-anchor="middle" class="comp-detail">Rate-limit counters, session cache</text>
  <text x="410" y="588" text-anchor="middle" class="comp-detail">Short-lived auth tokens</text>

  <rect x="570" y="535" width="220" height="70" class="box-ml" />
  <text x="680" y="560" text-anchor="middle" class="comp-title">Model Checkpoints</text>
  <text x="680" y="575" text-anchor="middle" class="comp-detail">CNN1D, DQN, PPO (checkpoints/)</text>
  <text x="680" y="588" text-anchor="middle" class="comp-detail">Loaded at backend startup</text>

  <rect x="840" y="535" width="220" height="70" class="box-data" />
  <text x="950" y="560" text-anchor="middle" class="comp-title">File System</text>
  <text x="950" y="575" text-anchor="middle" class="comp-detail">Static assets (nginx), logs</text>
  <text x="950" y="588" text-anchor="middle" class="comp-detail">Docker volumes for persistence</text>

  <!-- ======= ARROWS ======= -->
  <!-- Browser to nginx -->
  <path d="M 270 170 L 330 170" class="arrow" />
  <text x="290" y="165" class="arrow-label">HTTP(S) requests</text>

  <!-- nginx to Frontend -->
  <path d="M 570 140 L 630 140" class="arrow" />
  <text x="590" y="135" class="arrow-label">serve</text>

  <!-- nginx to API (proxy) -->
  <path d="M 420 280 L 420 305" class="arrow" />
  <text x="425" y="295" class="arrow-label">proxy /auth, /score, /api</text>

  <!-- Frontend to API -->
  <path d="M 720 235 L 540 305" class="arrow" />
  <text x="640" y="270" class="arrow-label">POST/GET calls</text>

  <!-- API to MongoDB -->
  <path d="M 280 445 L 220 535" class="arrow" />
  <text x="235" y="480" class="arrow-label">R/W users, sessions</text>

  <!-- API to Redis -->
  <path d="M 410 445 L 410 535" class="arrow" />
  <text x="415" y="485" class="arrow-label">cache, rate-limit</text>

  <!-- API to Checkpoints -->
  <path d="M 540 445 L 640 535" class="arrow" />
  <text x="570" y="480" class="arrow-label">inference load</text>

  <!-- API to File System -->
  <path d="M 750 445 L 900 535" class="arrow" />
  <text x="820" y="480" class="arrow-label">logs, assets</text>

</svg>

### Architecture Diagram Breakdown

The diagram is organized into **5 layers** from bottom to top:

1. **Data/State Layer (bottom):**
   - **MongoDB**: Persistent datastore for users, sessions, authentication logs, honeypot signals, and audit trails. Used by the backend for all CRUD operations.
   - **Redis Cache**: Fast in-memory store for rate-limiting counters, cached session tokens, and temporary authentication state.
   - **Model Checkpoints**: Pre-trained ML models (CNN1D, DQN, PPO) stored in the `checkpoints/` folder; loaded at backend startup for inference.
   - **File System**: Docker volumes for logs, static assets, and persistent data.

2. **API / Business Logic Layer (middle):**
   - **Auth Module** (`/auth/register`, `/auth/login`, `/auth/logout`): Handles user registration with Argon2 hashing and session token creation.
   - **Session/Token Management** (`/session/verify`, `/me`): Validates and manages active sessions; queries MongoDB for user details.
   - **Biometric Pipeline** (`/score` endpoint): Orchestrates the 4-stage inference pipeline (Biometric → Honeypot → Governor → Watchdog).
   - **Admin APIs** (`/admin/models-status`, `/admin/telemetry`): Debug and monitoring endpoints for developers.

3. **Frontend Layer (top-right):**
   - React SPA built with Vite; loaded once from nginx and runs entirely in the browser.
   - Captures user interactions (keystroke/pointer biometrics) via the SDK.
   - Manages local session tokens and routing between Login, Register, and Dashboard pages.
   - All API calls are made via the `api.js` fetch wrapper (relative URLs, no CORS issues).

4. **Proxy/Edge Layer (top-center):**
   - nginx acts as a reverse proxy: static files go to the browser directly, API calls are forwarded to the backend.
   - Rate-limiting and caching rules ensure API stability and reduce backend load.
   - HTTPS termination and request routing prevent the SPA catch-all from intercepting API responses.

5. **Client Layer (top-left):**
   - The user's web browser sends HTTP(S) requests to nginx.
   - Displays the login form, collects credentials, and submits biometric signals.

### Key Data Flows:
- **Register/Login**: Browser → nginx → backend → MongoDB (verify credentials) → session_token → frontend (store locally)
- **Biometric Score**: Frontend → nginx → backend → runs 4 stages in parallel or sequence → queries MongoDB/Redis as needed → returns JSON
- **Model Inference**: Backend loads .pt files on startup; during `/score`, each stage reads from loaded models in RAM.

---

## Login + Scoring sequence

## Login + Scoring sequence

<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">
  <defs>
    <style>
      .title { font-family: "Segoe UI", Arial, sans-serif; font-size: 20px; font-weight: bold; fill: #0f172a; }
      .actor-label { font-family: "Segoe UI", Arial, sans-serif; font-size: 12px; font-weight: 600; fill: #111827; }
      .actor-box { fill: #f0f9ff; stroke: #0284c7; stroke-width: 2px; rx: 6; }
      .lifeline { stroke: #cbd5e1; stroke-width: 1px; stroke-dasharray: 4,4; }
      .message { stroke: #334155; stroke-width: 2px; marker-end: url(#arrowhead); fill: none; }
      .return { stroke: #334155; stroke-width: 1.5px; marker-end: url(#arrowhead); fill: none; stroke-dasharray: 3,3; }
      .message-label { font-family: "Segoe UI", Arial, sans-serif; font-size: 10px; fill: #111827; font-weight: 500; }
      .description { font-family: "Segoe UI", Arial, sans-serif; font-size: 9px; fill: #64748b; }
      .note-box { fill: #fef3c7; stroke: #d97706; stroke-width: 1px; rx: 4; }
      .note-text { font-family: "Segoe UI", Arial, sans-serif; font-size: 9px; fill: #92400e; }
      .stage-box { fill: #f3e8ff; stroke: #9333ea; stroke-width: 1px; stroke-dasharray: 2,2; rx: 4; }
      .step { font-family: "Segoe UI", Arial, sans-serif; font-size: 11px; fill: #111827; font-weight: bold; }
    </style>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#334155" />
    </marker>
  </defs>

  <!-- Title -->
  <text x="30" y="40" class="title">Login + Scoring Authentication Flow</text>

  <!-- Actor boxes -->
  <rect x="20" y="70" width="140" height="50" class="actor-box" />
  <text x="90" y="95" text-anchor="middle" class="actor-label">User</text>
  <text x="90" y="110" text-anchor="middle" class="description">(Browser)</text>

  <rect x="210" y="70" width="140" height="50" class="actor-box" />
  <text x="280" y="95" text-anchor="middle" class="actor-label">Frontend SPA</text>
  <text x="280" y="110" text-anchor="middle" class="description">(React/Vite)</text>

  <rect x="400" y="70" width="140" height="50" class="actor-box" />
  <text x="470" y="95" text-anchor="middle" class="actor-label">nginx Proxy</text>
  <text x="470" y="110" text-anchor="middle" class="description">(reverse proxy)</text>

  <rect x="590" y="70" width="140" height="50" class="actor-box" />
  <text x="660" y="95" text-anchor="middle" class="actor-label">FastAPI Backend</text>
  <text x="660" y="110" text-anchor="middle" class="description">(Auth module)</text>

  <rect x="780" y="70" width="140" height="50" class="actor-box" />
  <text x="850" y="95" text-anchor="middle" class="actor-label">MongoDB</text>
  <text x="850" y="110" text-anchor="middle" class="description">(persistence)</text>

  <rect x="970" y="70" width="140" height="50" class="actor-box" />
  <text x="1040" y="95" text-anchor="middle" class="actor-label">Biometric Pipeline</text>
  <text x="1040" y="110" text-anchor="middle" class="description">(inference)</text>

  <!-- Lifelines -->
  <line x1="90" y1="120" x2="90" y2="780" class="lifeline" />
  <line x1="280" y1="120" x2="280" y2="780" class="lifeline" />
  <line x1="470" y1="120" x2="470" y2="780" class="lifeline" />
  <line x1="660" y1="120" x2="660" y2="780" class="lifeline" />
  <line x1="850" y1="120" x2="850" y2="780" class="lifeline" />
  <line x1="1040" y1="120" x2="1040" y2="780" class="lifeline" />

  <!-- STEP 1: Load Page -->
  <text x="30" y="160" class="step">1. Load Login Page</text>
  <path d="M 90 180 L 280 200" class="message" />
  <text x="140" y="195" class="message-label">GET /login</text>

  <path d="M 280 210 L 470 230" class="message" />
  <text x="330" y="225" class="message-label">proxy to SPA</text>

  <path d="M 470 240 L 280 260" class="return" />
  <text x="340" y="255" class="message-label">index.html + SDK</text>

  <path d="M 280 270 L 90 290" class="return" />
  <text x="140" y="285" class="message-label">200 OK</text>

  <!-- STEP 2: User Input -->
  <text x="30" y="330" class="step">2. User Enters Credentials</text>
  <rect x="45" y="340" width="450" height="50" class="note-box" />
  <text x="55" y="360" class="note-text">• Email & password typed into form</text>
  <text x="55" y="375" class="note-text">• SDK captures keystroke/pointer biometrics in background</text>

  <!-- STEP 3: Login Request -->
  <text x="30" y="430" class="step">3. Submit Login Credentials</text>
  <path d="M 90 450 L 280 470" class="message" />
  <text x="135" y="465" class="message-label">click submit</text>

  <path d="M 280 480 L 470 500" class="message" />
  <text x="330" y="495" class="message-label">POST /auth/login</text>
  <text x="330" y="508" class="description">{email, password}</text>

  <path d="M 470 520 L 660 540" class="message" />
  <text x="530" y="535" class="message-label">proxy → backend</text>

  <!-- Auth processing -->
  <rect x="680" y="550" width="140" height="40" class="actor-box" />
  <text x="750" y="575" text-anchor="middle" class="note-text">Verify Argon2 hash</text>

  <path d="M 660 600 L 850 620" class="message" />
  <text x="720" y="615" class="message-label">lookup user</text>

  <path d="M 850 630 L 660 650" class="return" />
  <text x="720" y="645" class="message-label">user document</text>

  <!-- Response path -->
  <path d="M 660 670 L 470 690" class="return" />
  <text x="530" y="685" class="message-label">200 {session_token}</text>

  <path d="M 470 700 L 280 720" class="return" />
  <text x="330" y="715" class="message-label">proxy response</text>

  <!-- STEP 4: Score submission (in alt box) -->
  <rect x="30" y="745" width="1050" height="45" class="stage-box" />
  <text x="45" y="765" class="step">4. Submit Biometric Score (POST /score)</text>
  <text x="45" y="780" class="description">→ Stage1 (biometric) → Stage2 (honeypot) → Stage3 (governor) → Stage4 (watchdog)</text>

  <!-- Legend -->
  <text x="30" y="820" class="description" style="font-weight: bold;">Key Points:</text>
  <text x="40" y="835" class="description">• nginx handles all routing and rate-limiting</text>
  <text x="40" y="848" class="description">• Backend verifies credentials against stored Argon2 hash</text>
  <text x="40" y="861" class="description">• Session token returned to frontend on successful login</text>
  <text x="40" y="874" class="description">• Biometric scoring happens after successful authentication (if desired)</text>

</svg>

### Sequence Diagram Explanation

This diagram shows the **step-by-step message flow** during a user login and biometric scoring session:

#### Step 1: Load Login Page
- User opens `http://localhost/login` (or navigates to it).
- Browser sends HTTP GET to nginx.
- nginx proxies to backend SPA handler, which returns `index.html`.
- Frontend JS loads, initializing the React app and biometric SDK.

#### Step 2: User Enters Credentials
- User types email and password into the login form.
- **Simultaneously**, the biometric SDK (in the browser) captures keystroke timings, pointer movements, and patterns.
- These signals are stored locally in the frontend and will be sent later to `/score`.

#### Step 3: Submit Login Credentials
- User clicks "Submit" or presses Enter.
- Frontend calls `POST /auth/login` with email and plain password.
- nginx intercepts and proxies to the backend (`POST /auth/login`).
- Backend:
  1. Looks up the user by email in MongoDB.
  2. Retrieves the stored Argon2 hash.
  3. Verifies the plain password against the hash using `PasswordHasher().verify()`.
  4. If match: creates a session in MongoDB and returns `200 { session_token, user_id, email }`.
  5. If no match: returns `401 { detail: "Invalid credentials" }`.
- nginx proxies the response back to the frontend.
- Frontend displays success/error message.

#### Step 4: Submit Biometric Score (if login succeeded)
- After successful login, the frontend calls `POST /score` with:
  - The collected biometric signals (keystroke timing, pointer data).
  - The latent vector computed by the SDK.
  - User agent, server load, and other metadata.
- nginx proxies to backend `/score` handler.
- Backend **orchestrator** runs the 4-stage pipeline **in sequence**:
  - **Stage 1 (Biometric)**: CNN1D extracts features (theta, h_exp) from keystroke/pointer signals.
  - **Stage 2 (Honeypot)**: MAB classifier decides if user should be shadowed or routed to a synthetic challenge.
  - **Stage 3 (Governor)**: DQN/PPO selects Argon2 parameters and behavioral actions.
  - **Stage 4 (Watchdog)**: Continuous monitoring for identity drift; recommends actions (ok, passive_reauth, etc.).
- Backend returns `PipelineOutput` containing:
  - `session_token`, `humanity_score`, `entropy_score`, `action_label`.
  - Per-stage results and confidence scores.
  - Recommended next actions for the UI.
- Frontend receives the response, stores the session token, and updates the UI (dashboard, threat alerts, etc.).

### Key Takeaways:
- **nginx acts as a transparent proxy**: the frontend doesn't know it's being routed; it just sends requests to relative URLs.
- **Authentication happens before biometric scoring**: the `/score` endpoint is only called after a successful login.
- **Biometric data is completely optional**: the login flow works without biometrics; the `/score` endpoint is a secondary enrichment.
- **All communication is JSON**: the backend speaks only JSON; HTML is only returned for static assets (via nginx).

---

## What Docker does here (each service)

- `nginx` (container): serves the built SPA (`index.html`, JS/CSS) and reverse-proxies API routes (`/auth/`, `/score`, `/api/`, `/password/`, `/session/`, etc.) to the backend. Also applies caching and rate-limiting. Config: `nginx/nginx.conf`.
- `backend` (container): runs the FastAPI application (handlers + 4-stage inference pipeline). Reads model checkpoints from `checkpoints/` and connects to MongoDB & Redis. Dockerfile builds a production image that bundles static assets into the backend image.
- `mongodb` (container): persistent store for users, sessions, honeypot logs, and admin data. Configured in `docker-compose.yml` and initialized using `mongo/init.js` if present.
- `redis` (container): lightweight cache and rate-limit store, used by nginx/backends for short-lived state.
- Composer: `docker-compose.yml` wires the services, environment variables, healthchecks and networks. Use `docker compose up -d --build` to run the whole stack.

---

## What `nginx` does (details)

- Serves static files from `/usr/share/nginx/html` (the Vite build), so the browser can load the SPA with the same origin as the API.
- Proxies API paths to the backend. This allows the frontend to use relative URLs (no CORS problems).
- Applies rate-limits and caching rules for static assets in `nginx/nginx.conf`.

Common nginx gotchas:
- If a proxied API path is not configured (missing `location` block), the SPA catch-all may return `index.html` for that API URL. That causes JSON parse errors and HTTP 405/HTML responses. Ensure API locations exist for `/score`, `/auth/`, `/password/`, `/session/`, etc.

---

## What MongoDB does (details)

- Stores `users` collection with fields like `email`, `password_hash`, `is_active`.
- Stores `sessions` collection: `session_token`, `user_id`, `latent_vector`, `expires_at`.
- Stores honeypot and audit logs used by the pipeline and admin dashboard.
- Connection is configured via `MONGODB_URL` / `MONGO_PASSWORD` environment variables in `docker-compose.yml` or your local `.env`/`all.env`.

---

## Important endpoints (what they do)

- `POST /auth/register` — Register a new user. Body: `{ email, plain_password }`. Creates user document and returns 201.
- `POST /auth/login` — Login. Body: `{ email, plain_password }`. Verifies argon2 hash; on success creates a session and returns `{ session_token, user_id, email }`.
- `POST /auth/logout` — Invalidate a session token.
- `POST /score` — Submit biometric payload to the 4-stage pipeline. Body: biometric features, latent vector, user agent, server_load. Returns `PipelineOutput` containing `session_token`, `humanity_score`, `entropy_score`, `action_label`, and per-stage metadata.
- `POST /password/hash` — Compute a hash using chosen Argon2 params (used by UI to show or test hashing results).
- `POST /password/verify` — Verify a plain password against a stored hash.
- `POST /session/verify` — Watchdog heartbeat for session verification.
- `POST /telemetry` — Collects events/telemetry (used for analytics).
- `GET /health` — Health check (used by docker-compose healthchecks).
- Admin endpoints: `/admin/*` and `/admin/models-status` — require admin keys; return model / pipeline debug info.

For code: main handlers live in `backend/main.py` and pipeline orchestration in `backend/models/orchestrator.py`.

---

## 4-stage pipeline (plain words)

1. Stage 1 — Biometric extraction: raw keystroke and pointer signals are normalized and converted into features (theta, h_exp, latent_vector).
2. Stage 2 — Honeypot: classifier decides whether to shadow the user or route them to a synthetic challenge (and selects a MAB arm when shadowing).
3. Stage 3 — Governor (DQN + PPO): determines Argon2 hashing parameters (memory/time/parallelism) and may select behavioral actions (e.g., stricter reauth flows).
4. Stage 4 — Watchdog: continuous checks for identity drift and recommends actions (ok, passive_reauth, disable_sensitive_apis, force_logout).

The orchestrator composes these results into the `PipelineOutput` returned by `/score`.

---

## Demo checklist (commands and steps)

1. Make sure local envs are set (copy `.env.example` → `.env` or populate `all.env`):

```powershell
# Example (PowerShell)
set -Machine EP_SESSION_SECRET=replace_with_secure_value
set -Machine MONGO_PASSWORD=your_mongo_pass
set -Machine REDIS_PASSWORD=your_redis_pass
```

2. Start Docker Compose (from repo root):

```bash
docker compose up -d --build
```

3. Verify containers and logs:

```bash
docker ps --filter "name=entropy_"
docker logs entropy_backend --tail 200
docker logs entropy_nginx --tail 200
```

4. Open the demo:

 - Visit `http://localhost/login` in a browser.
 - Register a test user and log in.
 - Observe backend logs showing `Registered` and `Login` messages and `/score` pipeline logs.

5. If you see JSON parse errors in the frontend, verify nginx returned JSON (not HTML). Check `nginx` logs to ensure requests are proxied rather than served by the SPA catch-all.

---

## Troubleshooting quick reference

- 405 / HTML returned: nginx is routing to SPA. Fix: add `location` block for the API route in `nginx/nginx.conf` and reload nginx (rebuild container).
- 500 with PPO/DQN matrix errors: model checkpoint mismatch or missing checkpoint — confirm files in `checkpoints/` and correct `EP_*_CHECKPOINT` env vars.
- Mongo auth failures: check `MONGO_PASSWORD` and the `MONGODB_URL` used by the container.

---

## Where to read code (quick pointers)

- `backend/main.py` — API handlers and app startup
- `backend/models/orchestrator.py` — pipeline orchestration (Stage 1→4 aggregation)
- `backend/models/*.py` — per-stage logic (see `stage1_biometric.py`, `stage2_honeypot.py`, `stage3_governor.py`, `stage4_watchdog.py`)
- `src/pages/LoginPage.jsx` — login UI flow and orchestration of login → score
- `src/services/api.js` — frontend HTTP client wrapper and endpoints
- `nginx/nginx.conf` — static serving + proxy rules
- `docker-compose.yml` — service definitions and env wiring

---

If you want I will:

- produce a single-slide markdown (or PDF) summary with these diagrams for your presentation, or
- create a short automated smoke-test script that performs register → login → score and prints the responses.

Tell me which one you prefer and I'll add it to the repo.
