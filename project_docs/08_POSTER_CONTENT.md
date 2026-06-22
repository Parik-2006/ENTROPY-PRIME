# Entropy Prime — Poster Content (A1 ready)

## Title
**ENTROPY PRIME**
Continuous Behavioural Authentication & Generative Deception for Web Security

*Sub-title:* "Keep the right user in. Keep attackers busy in a world that isn't
real."

## Abstract
Conventional systems verify identity once at login and respond to threats by
blocking — which leaks the defence and forfeits intelligence. Entropy Prime adds
two cooperating layers: (1) **continuous behavioural authentication** that scores
keystroke and pointer dynamics against an immutable enrolment template and
re-verifies only on a sustained mismatch, and (2) **generative deception** that
silently routes classified attackers into believable synthetic environments via
Synthetic Success Injection. The result is frictionless continuity for
legitimate users and isolated, observable engagement for attackers.

## Architecture (poster diagram)
```
User → Behavioral Engine → Identity Verification → [Trusted | Re-auth]
                                     │
        malicious request → Attack Classification → Deception Engine
                                     → Shadow Environment → Monitoring
```
*(Use the Mermaid flow from 03_SYSTEM_ARCHITECTURE.md rendered as a clean
left-to-right band across the poster.)*

## Modules
- **Behavioural Biometrics** — 8-D keystroke/pointer features + per-digraph
  latency + frozen template.
- **Continuous Authentication** — progressive score, zones (80/60), idle-freeze,
  corroboration, cooldown.
- **Attack Classification** — rule-based intent: stuffing, brute force, recon,
  scraper, unknown.
- **Honeypot Routing & Synthetic Success** — believable "success" + isolation.
- **Shadow Environments** — Banking world, Admin world (canary secrets),
  synthetic dataset, tarpit, restricted sandbox.
- **Monitoring** — threat-intelligence recording of attacker activity.

## Results
- A different human on the same account is detected and challenged
  (identity score drops from ~95 to <60 on sustained mismatch).
- Five attack vectors are classified and routed to five distinct environments,
  end-to-end, through the real backend.
- Detection never discloses the defence — attackers believe they succeeded.

## Future Scope
- ML / contextual-bandit attack classification and honeypot selection.
- Canary-token attribution across environments.
- Multi-tenant, production-hardened deployment.

## Footer
Stack: React · Vite · FastAPI · Python · MongoDB · Redis · Argon2id · Docker ·
TensorFlow.js  |  Team & Guide credits.
