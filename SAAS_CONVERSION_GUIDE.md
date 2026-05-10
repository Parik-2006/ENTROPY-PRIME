# Entropy Prime SaaS Conversion Guide

## 1. Current Position

Entropy Prime is already moving in the right direction for a Security-as-a-Service product. The current project has:

- A FastAPI backend with security APIs.
- A React frontend with login, profile building, dashboard, and threat-intelligence views.
- Browser-side behavioral biometric capture.
- MongoDB persistence.
- Docker support.
- A four-stage security pipeline:
  - Biological Gateway
  - Honeypot / Deception
  - Resource Governor
  - Session Watchdog

However, the project currently behaves more like a single application with its own security system. To become SaaS, Entropy Prime should become a security layer that other organizations can plug into their own websites or apps.

The goal is to evolve from:

```text
Entropy Prime App
  owns login
  owns users
  owns dashboard
  owns security logic
```

to:

```text
Organization's Website
  uses Entropy Prime SDK/API
  keeps its own user experience
  receives security decisions

Entropy Prime SaaS
  scores risk
  verifies sessions
  detects bots
  provides dashboards, policies, logs, and alerts
```

You do not need to rebuild the whole project. You need to separate it into SaaS provider, SDK, and demo customer app.

---

## 2. Target SaaS Architecture

Recommended structure:

```text
ENTROPY-PRIME/
  backend/                 # Entropy Prime SaaS API
  src/                     # Entropy Prime admin dashboard
  sdk/                     # JavaScript SDK for customer websites
  demo-client/             # Dummy organization website
  docs/                    # Integration and demo documentation
```

### 2.1 Entropy Prime SaaS Platform

This is the actual product. It should provide:

- Organization accounts.
- API keys.
- Security policy configuration.
- Risk scoring APIs.
- Session verification APIs.
- Honeypot and threat-intelligence logs.
- Organization dashboard.
- Analytics and audit logs.

### 2.2 JavaScript SDK

The SDK is what customer websites use.

Example future usage:

```js
import { EntropyPrime } from "@entropy-prime/sdk"

const ep = new EntropyPrime({
  apiKey: "demo_org_api_key",
  endpoint: "http://localhost:8000"
})

await ep.start()

const result = await ep.scoreLogin({
  userId: "user_123",
  passwordStrengthSignal: 0.72
})

if (result.action === "allow") {
  // Continue login
}

if (result.action === "require_reauth") {
  // Ask for re-authentication
}

if (result.action === "shadow_route") {
  // Send attacker into fake success flow
}
```

### 2.3 Demo Client Website

This is a dummy customer website used to prove that Entropy Prime works as a SaaS.

Good demo ideas:

- Fake banking portal.
- Student ERP portal.
- Company HR dashboard.
- Healthcare records portal.

The demo website should not contain the full Entropy Prime dashboard. It should look like a normal organization website that uses Entropy Prime APIs for security decisions.

---

## 3. API Shape For SaaS

The current backend already has useful endpoints, but for SaaS the public API should be more integration-focused.

Recommended public API:

```http
POST /v1/risk/score
POST /v1/session/verify
POST /v1/honeypot/reward
GET  /v1/threats
GET  /v1/analytics
GET  /v1/policies
PUT  /v1/policies
```

### 3.1 Risk Score API

Customer website calls this during login.

```http
POST /v1/risk/score
X-EP-API-Key: ep_demo_key
Content-Type: application/json
```

```json
{
  "external_user_id": "customer_user_123",
  "theta": 0.87,
  "h_exp": 0.71,
  "server_load": 0.42,
  "latent_vector": [0.01, 0.02, 0.03],
  "context": {
    "ip_address": "127.0.0.1",
    "user_agent": "Mozilla/5.0",
    "app": "demo-bank"
  }
}
```

Response:

```json
{
  "request_id": "risk_abc123",
  "risk_score": 0.18,
  "humanity_score": 0.87,
  "entropy_score": 0.71,
  "action": "allow",
  "argon2_preset": "standard",
  "shadow_mode": false,
  "session_token": "ep_session_...",
  "confidence": "medium"
}
```

Possible actions:

```text
allow
harden
require_reauth
shadow_route
block
```

### 3.2 Session Verify API

Customer website calls this periodically during an active session.

```http
POST /v1/session/verify
X-EP-API-Key: ep_demo_key
Content-Type: application/json
```

```json
{
  "session_token": "ep_session_...",
  "external_user_id": "customer_user_123",
  "latent_vector": [0.01, 0.02, 0.03],
  "e_rec": 0.14,
  "trust_score": 0.86
}
```

Response:

```json
{
  "action": "ok",
  "trust_score": 0.84,
  "e_rec": 0.14,
  "reason": "within_thresholds"
}
```

### 3.3 Threat Intelligence API

Used by the SaaS dashboard and optionally customer admin panels.

```http
GET /v1/threats
X-EP-API-Key: ep_demo_key
```

Response:

```json
{
  "count": 12,
  "signatures": [
    {
      "timestamp": "2026-05-09T10:30:00Z",
      "theta": 0.04,
      "ip_address": "192.168.1.10",
      "user_agent": "bot-client",
      "action": "shadow_route"
    }
  ]
}
```

---

## 4. Required SaaS Features

### 4.1 Organization Accounts

Add an `organizations` collection/table.

Example:

```json
{
  "_id": "org_123",
  "name": "Acme Bank",
  "plan": "demo",
  "created_at": "2026-05-09T10:00:00Z",
  "is_active": true
}
```

### 4.2 API Keys

Each organization needs one or more API keys.

Example:

```json
{
  "_id": "key_123",
  "org_id": "org_123",
  "name": "Demo Bank Website",
  "key_hash": "...",
  "created_at": "2026-05-09T10:00:00Z",
  "last_used_at": null,
  "is_active": true
}
```

Important: store only a hash of the API key, not the raw key.

### 4.3 Tenant Isolation

Add `org_id` to SaaS-owned data:

- Users or external user mappings.
- Sessions.
- Biometric profiles.
- Honeypot logs.
- Drift events.
- Analytics.
- Policies.

Every query should filter by `org_id`.

### 4.4 Security Policies

Each organization should be able to configure thresholds.

Example policy:

```json
{
  "org_id": "org_123",
  "bot_theta_hard": 0.10,
  "bot_theta_soft": 0.30,
  "trust_warn": 0.50,
  "trust_critical": 0.25,
  "low_entropy_action": "harden",
  "bot_action": "shadow_route",
  "session_drift_action": "require_reauth"
}
```

### 4.5 Admin Dashboard

The SaaS dashboard should show:

- Total API calls.
- Allowed logins.
- Hardened logins.
- Re-auth events.
- Shadow-routed bots.
- Average humanity score.
- Average trust score.
- Recent threat signatures.
- Per-organization policy settings.

### 4.6 Audit Logs

Add logs for professor demo and real SaaS credibility.

Example:

```json
{
  "org_id": "org_123",
  "event_type": "risk_score",
  "external_user_id": "customer_user_123",
  "theta": 0.87,
  "h_exp": 0.71,
  "action": "allow",
  "created_at": "2026-05-09T10:30:00Z"
}
```

---

## 5. How To Demonstrate The SaaS

The best demonstration is to build a dummy organization website and show it consuming Entropy Prime APIs.

Use three tabs:

```text
Tab 1: Demo Client Website
Tab 2: Entropy Prime SaaS Dashboard
Tab 3: FastAPI Swagger / API logs
```

### 5.1 Demo Client Website

Build a simple website:

```text
Acme Bank
  Login page
  Dashboard after login
  Transfer money page
  Profile page
```

The dummy website should integrate the Entropy Prime SDK.

It should display only customer-facing behavior:

- Login success.
- Re-auth required.
- Session expired.
- Access denied.

It should not expose internal ML details to the normal user.

### 5.2 Entropy Prime Dashboard

This dashboard should show what the SaaS provider sees:

- Incoming API requests from Acme Bank.
- Humanity score.
- Entropy score.
- Session trust.
- Action chosen.
- Honeypot signatures.
- Drift alerts.

### 5.3 Swagger / API Logs

Use this to prove to professors that:

- The dummy website is really calling Entropy Prime APIs.
- Security decisions are coming from the SaaS backend.
- The SaaS is not hardcoded inside the dummy website.

---

## 6. Professor Demo Script

### Scenario 1: Normal Human Login

Steps:

1. Open the Acme Bank demo website.
2. Type email and password naturally.
3. Submit login.
4. Entropy Prime SDK sends behavioral signals to SaaS API.
5. SaaS returns `allow`.
6. User enters the dummy bank dashboard.

Explain:

```text
The organization does not implement behavioral biometric logic itself.
It simply integrates Entropy Prime's SDK and receives an authentication decision.
```

Dashboard should show:

```text
Action: allow
Humanity score: high
Entropy score: acceptable
Session trust: high
```

### Scenario 2: Weak Password Hardening

Steps:

1. Login with a weak password like `password123`.
2. Entropy score becomes low.
3. SaaS returns `harden`.
4. Backend chooses a stronger Argon2id preset.

Explain:

```text
Entropy Prime applies asymmetric hardening.
The real user can still log in, but attackers performing repeated guesses face a much higher computational cost.
```

Dashboard should show:

```text
Action: harden
Argon2 preset: hard or punisher
Reason: low entropy
```

### Scenario 3: Bot Attack / Credential Stuffing

Add a button in the demo website:

```text
Simulate Bot Attack
```

When clicked, send:

```json
{
  "theta": 0.05,
  "h_exp": 0.30
}
```

Expected SaaS response:

```text
Action: shadow_route
Shadow mode: true
Synthetic token generated
```

Explain:

```text
Instead of blocking the bot and revealing that detection happened,
Entropy Prime returns fake success and moves the attacker into a honeypot path.
```

Dashboard should show:

```text
New honeypot signature captured
Bot theta: 0.05
Synthetic success injected
```

### Scenario 4: Session Hijacking / Different User Typing

Steps:

1. Login normally.
2. Build a small behavioral profile.
3. Type abnormally or click a demo button:

```text
Simulate Different User
```

4. Send higher reconstruction error or drift.
5. SaaS returns `require_reauth` or `force_logout`.

Explain:

```text
Even after login, trust is not permanent.
Entropy Prime continuously verifies the user's behavioral signature.
If the behavior changes, the SaaS asks the customer app to re-authenticate or terminate the session.
```

Dashboard should show:

```text
Action: require_reauth
Trust score: reduced
Reason: behavioral drift
```

---

## 7. Minimum Implementation Plan

### Phase 1: Make The Demo Work

Goal: prove the SaaS idea without rebuilding everything.

Tasks:

- Create `demo-client/`.
- Build a fake organization login page.
- Reuse the existing biometric client logic.
- Call current backend `/score` and `/session/verify`.
- Show the Entropy Prime dashboard separately.
- Add simulation buttons for:
  - Normal human login.
  - Weak password.
  - Bot login.
  - Session hijack.

This is enough for a strong academic demonstration.

### Phase 2: Add SaaS Identity

Goal: make the backend multi-tenant.

Tasks:

- Add organizations.
- Add API keys.
- Add `org_id` to sessions, honeypot logs, biometric profiles, and audit logs.
- Require `X-EP-API-Key` for SaaS endpoints.
- Create organization-specific dashboard views.

### Phase 3: Build SDK

Goal: make integration clean.

Tasks:

- Create `sdk/entropy-prime.js`.
- Move reusable browser biometric code into SDK-friendly functions.
- Expose:

```js
start()
scoreLogin()
verifySession()
stop()
```

### Phase 4: SaaS Dashboard And Policies

Goal: make it feel like a product.

Tasks:

- Add organization dashboard.
- Add policy configuration.
- Add API usage logs.
- Add threat-intelligence view per organization.
- Add charts for allow/harden/reauth/shadow events.

### Phase 5: Production Readiness

Goal: prepare for real deployment later.

Tasks:

- API key hashing.
- Rate limiting.
- Request signing.
- HTTPS deployment.
- Model checkpoints.
- FAR/FRR testing.
- Privacy documentation.
- Terms for biometric processing.

---

## 8. What To Tell Professors

Use this positioning:

```text
Entropy Prime is a Security-as-a-Service platform for behavioral authentication.
Organizations integrate our JavaScript SDK and APIs into their existing login systems.
Our SaaS provides real-time risk scoring, adaptive password hardening,
honeypot deception, and continuous session verification.
```

Then explain the separation:

```text
The demo bank website represents a customer organization.
The Entropy Prime dashboard represents our SaaS provider console.
The API calls between them prove that the security logic is being provided as a service.
```

Key sentence:

```text
We are not building only a login page.
We are building a reusable security layer that other organizations can subscribe to.
```

---

## 9. Final Recommendation

Do not rewrite the entire project.

Recommended next move:

1. Keep the current backend as the Entropy Prime API.
2. Keep the current dashboard as the Entropy Prime admin console.
3. Add a `demo-client/` dummy organization website.
4. Add simple API-key based organization support.
5. Demonstrate the dummy website consuming Entropy Prime as an external service.

This will make the project clearly look like SaaS while preserving all the work already done.

