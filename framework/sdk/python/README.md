# Entropy Prime — Python SDK

Dependency-free REST client for the Entropy Prime behavioral security
framework. Use it from any server-side Python app to enroll users, submit
behavioral scores, run continuous-auth heartbeats, and gate transactions.

## Install (editable, from the repo)
```bash
pip install -e framework/sdk/python
```

## Usage
```python
from entropy_prime import EntropyPrime

ep = EntropyPrime(api_url="http://localhost:8000")   # talks to /v1 by default

# 1. Enroll / authenticate
ep.register("parik@example.com", "correct horse battery staple")

# 2. Score behavioral signals through the 4-engine pipeline
res = ep.score(theta=0.92, h_exp=0.8, latent_vector=[0.1] * 32)
print(res["action_label"], "shadow:", res["shadow_mode"])

# 3. Continuous-auth heartbeat (identity drift)
hb = ep.verify(user_id="usr_123", latent_vector=[0.1] * 32, e_rec=0.04)
print(hb["action"], hb["trust_score"])

# 4. Gate a sensitive transaction
gate = ep.trust(user_id="usr_123", transaction_risk=0.8)
print(gate["action"])     # allow | challenge | deny
```

## Method ↔ endpoint map

| SDK method | Endpoint (default prefix `/v1`) |
|---|---|
| `health()` | `GET /v1/health` |
| `register()` / `enroll()` | `POST /v1/auth/register` |
| `login()` | `POST /v1/auth/login` |
| `logout()` | `POST /v1/auth/logout` |
| `me()` | `GET /v1/me` |
| `score()` | `POST /v1/score` |
| `sync_profile()` | `POST /v1/biometric/profile` |
| `profile_status()` | `GET /v1/biometric/profile/{id}/status` |
| `reset_profile()` | `POST /v1/biometric/profile/reset` |
| `verify()` | `POST /v1/session/verify` |
| `trust()` | `POST /v1/session/trust` |
| `honeypot_reward()` | `POST /v1/honeypot/reward` |

Pass `prefix=""` to target the legacy un-prefixed routes.
