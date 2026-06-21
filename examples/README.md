# Entropy Prime — Examples

Demonstrations that *consume* Entropy Prime as a framework, plus the five
required demo scenarios. The demos run **offline** (no API server, MongoDB, or
Redis required) by driving the framework engines in-process via the public
`framework.*` API. The integration example talks to a live server through the
SDKs.

## Run the demos (offline, no server)

```bash
python examples/bot_detection_demo/demo.py        # DEMO 5
python examples/captcha_bypass_demo/demo.py        # DEMO 1
python examples/legit_user_demo/demo.py            # DEMO 2
python examples/different_human_demo/demo.py       # DEMO 3
python examples/human_variability_demo/demo.py     # DEMO 4
```

| Demo | Scenario | Engine(s) exercised | Expected outcome |
|---|---|---|---|
| `captcha_bypass_demo` | Bot passes CAPTCHA, still acts automated | Cadence + Honeypot | Traditional gate ALLOWs; Entropy Prime shadow-routes |
| `legit_user_demo` | Same user logs in over days | Continuous Auth | All GREEN, trust stays high |
| `different_human_demo` | Friend uses same account/laptop | Continuous Auth | Owner GREEN, friend RED → force_logout |
| `human_variability_demo` | Same user fast/slow/tired/stressed | Continuous Auth | Same user never RED; different human RED |
| `bot_detection_demo` | Scripted perfect-timing typing | Cadence + Honeypot | Bot → shadow-routed to honeypot |

Decisions are deterministic (seeded). The humanity score (θ) and latent vector
are synthesized by `examples/_simulation.py` as stand-ins for the browser
TensorFlow.js engine (`src/services/biometrics.js`); the *decision logic* is the
real framework.

## Live integration (needs a running server + SDK)

```bash
# Server side (Python SDK)
pip install -e framework/sdk/python
python examples/integration_minimal/app.py

# Browser side (JavaScript SDK)
#   serve examples/integration_minimal/index.html from any static server
```

## How the offline harness works
`examples/_common.py` builds the 4-engine `PipelineOrchestrator` once (preserving
the governor=`PPOPolicyAgent` / watchdog=`PPOAgent` split) and exposes:
- `score_session(theta, h_exp, latent)` → Cadence + Honeypot + DMS
- `continuous_check(latent, baseline, trust)` → Continuous-Auth drift + GREEN/YELLOW/RED zone

> Note: with no trained checkpoints present, the DQN/PPO agents use random
> weights and the framework relies on its deterministic hard-override and
> threshold-fallback rules — which is exactly what the demos exercise.
