# ENTROPY PRIME: SaaS Implementation Prompts

This file contains 10 sequential prompts to transform Entropy Prime into a multi-tenant SaaS.

---

### Prompt 1: Multi-Tenant Schema Evolution
**Files**: `backend/database.py`, `backend/models.py`, `backend/setup_mongodb.py`
**Task**: Implement the multi-tenant layer. Create `tenants` and `sites` collections. Update `users`, `sessions`, `biometric_profiles`, `drift_events`, and `honeypot` collections to include `tenant_id` and `site_id`. Ensure data isolation by filtering all queries by these IDs.

### Prompt 2: SaaS API Gateway & Tenant Auth
**Files**: `backend/main.py`, `backend/middleware/auth.py`, `backend/services/auth_service.py`
**Task**: Build authentication middleware. Validate `X-API-Key` from SDK requests against the `sites` collection. Resolve keys to `tenant_id`/`site_id` context. Separate Admin APIs (JWT) from Public APIs (API Key).

### Prompt 3: The Universal Biometric SDK (Core Capture)
**Files**: `public/sdk/entropy.js`, `src/sdk/collectors.js`, `vite.config.js`
**Task**: Create a lightweight JS SDK for silent biometric capture (keystrokes, mouse). Use `requestIdleCallback` for telemetry. Ensure zero interference with the host site's functionality.

### Prompt 4: Stage 1 - Biometric Autoencoder SaaS Adaptation
**Files**: `backend/models/stage1_biometric.py`, `backend/models/cnn1d.py`, `backend/services/biometric_service.py`
**Task**: Update Stage 1 to be context-aware. Load specific user profiles within the scope of the `site_id`. Handle learning phases for new users on third-party sites.

### Prompt 5: Stage 2 - Dynamic SaaS Honeypot Engine
**Files**: `backend/models/stage2_honeypot.py`, `public/sdk/entropy.js`, `backend/pipeline/orchestrator.py`
**Task**: Implement remote-triggered honeypots. Backend Stage 2 sends "Challenge" signals; SDK dynamically injects invisible decoys (fake fields/buttons) into the host DOM to catch bots.

### Prompt 6: Stage 3 - Governor: Multi-Tenant Policy Engine
**Files**: `backend/models/stage3_governor.py`, `backend/models/pydantic_models.py`, `backend/services/governor_service.py`
**Task**: Enable tenant-specific security policies. Implement a PPO RL agent that optimizes decisions (block, log, challenge) based on a tenant's risk tolerance settings.

### Prompt 7: Stage 4 - Global Watchdog & Threat Intelligence
**Files**: `backend/models/stage4_watchdog.py`, `backend/services/watchdog_service.py`, `backend/database.py`
**Task**: Create a cross-site threat intelligence system. Flag malicious fingerprints or IPs detected on one site across the entire SaaS platform.

### Prompt 8: Developer Dashboard - Onboarding & Analytics
**Files**: `src/pages/AdminDashboard.jsx`, `src/pages/SiteManagement.jsx`, `src/components/ThreatMap.jsx`
**Task**: Build the SaaS admin portal. Include real-time threat maps, security health scores, API key management, and policy configuration using premium aesthetics.

### Prompt 9: Integration API & Real-time Webhooks
**Files**: `backend/webhooks.py`, `backend/main.py`, `backend/services/notification_service.py`
**Task**: Implement outgoing webhooks for high-risk detections. Provide a verification API for customer backends to check session trust scores before transactions.

### Prompt 10: Production Readiness & SDK Bundling
**Files**: `Dockerfile`, `scripts/bundle-sdk.sh`, `docker-compose.prod.yml`, `README.md`
**Task**: Finalize production packaging. Create a minified `entropy.min.js` for CDN distribution. Update README with a 5-minute onboarding guide for new customers.
