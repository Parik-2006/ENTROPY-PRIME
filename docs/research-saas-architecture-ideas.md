# Research-Driven SaaS Architecture Ideas

## Goal

This note turns the project into a stronger SaaS by combining four research themes: behavioral biometrics, adaptive authentication, deception systems, and drift-aware continuous trust. The objective is not just to detect bots once, but to maintain a live security posture for every tenant, site, and user session.

The best architecture for this repo is a layered trust system:

1. Collect behavioral signals in the browser.
2. Convert them into stable user patterns.
3. Use a governor to decide how expensive and how strict authentication should be.
4. Use a watchdog to keep checking whether the session still matches the original user.
5. Use a honeypot layer to observe and isolate suspicious traffic without exposing the real system.

That gives the product a clear SaaS story: it is not a single bot detector, it is a trust orchestration platform.

## What Research Usually Supports

### 1. Behavioral biometrics and keystroke dynamics

Research in behavioral biometrics usually shows the same idea: humans have repeatable timing patterns, but those patterns are noisy and change over time. The useful lesson for this project is not that one model can perfectly classify a person. The useful lesson is that a profile should be learned gradually and treated as a probability distribution, not as a fixed fingerprint.

What to borrow:
- Rolling per-user baselines instead of one-shot classification.
- Feature vectors built from dwell time, flight time, rhythm, jitter, and pointer speed.
- Confidence thresholds that change with sample count.
- Separate handling for onboarding noise versus mature profile drift.

How this fits Entropy Prime:
- Browser collection becomes the source of stable profile features.
- MongoDB stores the evolving profile in `biometric_profiles`.
- The frontend shows a sample target, a stable state, and a drift state.

### 2. Continuous authentication and session trust

Continuous authentication papers usually argue that login is not enough. The identity check must continue during the session, because hijacking can happen after the first successful login. The important design idea is session trust decay and recovery.

What to borrow:
- A trust score that updates over time.
- Passive re-authentication when risk rises.
- Force logout when the trust score crosses a hard threshold.
- Session-specific decisions instead of global user blocking.

How this fits Entropy Prime:
- The watchdog becomes a continuous risk engine.
- The backend stores trust history and drift events.
- The user sees soft warnings before hard enforcement.

### 3. Deception and honeypot systems

Deception research usually shows that attackers reveal themselves when they interact with fake assets. In a SaaS security system, this is valuable because it lets you learn attacker behavior without exposing production resources.

What to borrow:
- Silent decoy fields and fake links.
- Shadow routing for suspicious sessions.
- At-least-once logging of suspicious interactions.
- Tenant-specific deception policies.

How this fits Entropy Prime:
- The honeypot stage should be treated as an observation layer, not just a block button.
- The system can collect attacker fingerprints, interaction style, and timing.
- The backend can feed that data back into the governor and watchdog policies.

### 4. Adaptive hardening and risk-based resource control

Research on adaptive authentication and defensive resource allocation tends to favor one principle: make attacks more expensive without punishing normal users too much. That is exactly where Argon2id, DQN, and policy control fit together.

What to borrow:
- Stronger hashing for risky sessions.
- More expensive verification only when risk is high.
- Resource-aware policies that consider load and threat level.
- A small number of carefully designed security presets.

How this fits Entropy Prime:
- The governor selects Argon2id cost presets.
- The backend can keep normal users fast while slowing down suspicious repeat attempts.
- The system can make security adaptive instead of static.

## Recommended Product Architecture

### Browser Layer

The browser should only do three things:
- capture typing and pointer signals,
- aggregate them into a local biometric profile,
- send summarized features and stability updates to the backend.

Do not keep raw keystrokes as the backend source of truth. The browser can observe them, but the server should only store compact behavioral summaries.

### API Layer

The backend should expose clean trust-oriented endpoints:
- profile build sync,
- session scoring,
- watchdog heartbeat,
- honeypot reward and telemetry,
- profile fetch and summary endpoints for UI.

The API should never trust client risk values blindly. It should always validate the active session and own the final trust decision.

### Policy Layer

The policy layer should combine four outputs:
- biometric confidence,
- drift score,
- session trust,
- deception outcome.

Then it should return one of four actions:
- allow,
- challenge,
- passive re-auth,
- force logout.

This is the simplest design that still feels enterprise-grade.

### Data Layer

MongoDB should store distinct documents for distinct jobs:
- `users` for identity and account state,
- `biometric_profiles` for the stable behavioral model,
- `sessions` for active trust and latent state,
- `drift_events` for forensics and audit,
- `honeypot` and `threat_intelligence` for deception outcomes.

The database should answer three questions quickly:
- Who is this user?
- What does their stable pattern look like?
- Is this session still behaving like the same person?

## SaaS Differentiators

The unique value of this project becomes much stronger if the product is framed as a trust platform rather than just a biometric classifier.

### Differentiator 1: Tenant-aware behavioral baselines

Each tenant can have its own policy profile:
- sample thresholds,
- drift sensitivity,
- action severity,
- allowed Argon2id hardening ceiling,
- honeypot aggressiveness.

This lets the product adapt to different businesses instead of forcing one security default.

### Differentiator 2: Proof of continuity, not just proof of login

The system should market itself as a continuity engine:
- it proves the same user is still present,
- it proves the session did not drift too far,
- it proves suspicious actions are being trapped or slowed.

That is stronger than a simple login gate.

### Differentiator 3: Privacy-preserving profile learning

The product should emphasize that raw keystrokes never need to leave the browser. The backend only needs compact behavioral summaries, profile statistics, and drift metrics.

This is useful for SaaS trust, compliance messaging, and user adoption.

### Differentiator 4: Deception-backed telemetry loop

Suspicious sessions should not disappear silently. They should produce telemetry:
- honeypot events,
- drift spikes,
- suspicious route counts,
- session invalidation reasons,
- re-auth triggers.

That telemetry makes the product feel operationally mature.

## A Better End-to-End Flow

### Phase A: Onboarding / Profile Build

User logs in and enters the profile-build page.

The browser:
- collects typing samples,
- computes local timing and pointer features,
- groups them into patterns,
- shows progress toward stability.

The backend:
- validates the session,
- stores aggregated profile updates,
- records summary stats in MongoDB,
- marks the profile as stable after enough samples.

### Phase B: Login and Re-Login

User submits password and biometric context.

The system:
- hashes the password with Argon2id,
- chooses a cost preset based on risk and load,
- issues a session only if the score is acceptable.

If risk is higher, the system does not need to invent a new algorithm. It just uses a harder preset, a tighter challenge, or a denial path.

### Phase C: Live Session Monitoring

While the user is active:
- the watchdog compares current behavior with the baseline,
- drift updates the trust score,
- soft anomalies trigger passive re-auth,
- severe anomalies trigger logout or sensitive-API blocking.

### Phase D: Deception and Threat Intelligence

If the user looks malicious:
- route them into the honeypot,
- keep their interactions isolated,
- log what they touched,
- feed the result into threat intelligence.

This gives the platform a defensive learning loop.

## Research-Inspired Feature Set

### Core features

- Browser-based biometric capture.
- Per-user stable profile learning.
- Session trust score and drift tracking.
- DQN-based Argon2id preset selection.
- PPO-based action selection for allow/challenge/logout.
- Honeypot decoy routing.
- Tenant-aware policies.

### Advanced features

- Progressive onboarding threshold instead of a fixed sample count.
- Profile confidence score that rises with consistency.
- Per-tenant drift sensitivity tuning.
- Suspicious-session replay analysis.
- Dashboard for drift trends and attack patterns.
- Rules to disable expensive actions for untrusted tenants.

### SaaS-grade features

- Multi-tenant isolation.
- Audit log export.
- Admin policy editor.
- Event webhooks.
- Risk tiering by site, tenant, and user.
- Role-based access control for security admins.

## What Makes This Unique

This project becomes unique when it is framed as a security operating system for behavioral trust, not just a keystroke model.

The strongest angle is:
- user behavior is learned over time,
- the system responds dynamically to risk,
- deception is used as an active sensor,
- and the final profile is a live behavioral model that can be queried per user in MongoDB.

That makes the SaaS easier to explain, easier to extend, and more credible for production use.

## Implementation Priorities

1. Make profile-build persistence reliable and auditable.
2. Make the watchdog the main continuous security loop.
3. Make the governor truly risk-aware and tenant-aware.
4. Make honeypot events feed threat intelligence.
5. Make the dashboard show one stable behavioral pattern per user.
6. Keep the browser as the raw-signal boundary.

## Final Target State

At the end of the day, the product should let you answer these questions from MongoDB and the UI:

- What does this user’s stable behavioral pattern look like?
- Is their current session drifting away from that pattern?
- Should their next re-auth be cheap, strict, or punitive?
- Did they interact with decoy assets?
- Which tenant policy produced the decision?

If those answers are easy to query, the SaaS is ready for a serious production story.