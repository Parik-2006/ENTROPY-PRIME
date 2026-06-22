# Entropy Prime — Project Abstract

## Problem Statement

Modern authentication systems verify identity **once**, at the point of login. A
correct password or a valid session token is treated as proof of identity for
the entire session. This single-point model collapses under three common
threats: (a) credential compromise, where an attacker logs in with stolen but
valid credentials; (b) session hijacking, where a session is taken over after a
legitimate login; and (c) automated abuse, where bots exploit valid endpoints at
machine speed. In each case the system has *no mechanism to notice that the
person now operating the account is not the person who logged in*. Furthermore,
when malicious activity is detected, conventional defences simply **block** the
request — which immediately informs the attacker that they were detected and
invites them to adapt, retry, or pivot.

## Existing System Limitations

1. **Binary, one-time authentication.** Identity is asserted at login and never
   re-checked, so a compromised session remains trusted indefinitely.
2. **No behavioural continuity.** Systems do not model *how* a legitimate user
   types or moves, so a different human operating the same account is invisible.
3. **Detection equals disclosure.** Blocking, CAPTCHAs and error pages reveal
   the defence to the attacker, enabling rapid evasion.
4. **No intelligence capture.** Once an attacker is blocked, the opportunity to
   observe their behaviour and harvest threat intelligence is lost.
5. **Coarse threat response.** Most systems apply the same response to every
   threat class rather than tailoring the response to attacker intent.

## Proposed Solution

**Entropy Prime** is a behavioural-security framework that adds *continuous*,
*deceptive* defence on top of existing authentication. It contributes two
cooperating capabilities:

1. **Continuous Behavioural Authentication.** A client-side biometric engine
   captures keystroke dynamics (dwell, flight, per-digraph latency) and pointer
   dynamics, and continuously compares the live signature against an **immutable
   enrolment template**. A progressive confidence score (0–100) is maintained
   and mapped to three zones — Trusted, Monitor, Re-authenticate — so that a
   *different human* operating the same account is detected mid-session and
   challenged for re-verification, without ever logging out a legitimate user.

2. **Generative Deception (Honeypot Engine).** When the upstream pipeline
   classifies a request as malicious, the system does **not** block it. Instead
   it performs *Synthetic Success Injection*: the attacker receives a normal
   "login succeeded" response and is transparently routed into an isolated
   **shadow environment** — a fully synthetic banking or admin application — that
   is believable, consistent, and entirely disconnected from real data. A
   rule-based classifier infers attacker intent (credential stuffing, brute
   force, reconnaissance, scraping, session abuse) and selects the appropriate
   deception strategy, while all interactions are recorded as threat
   intelligence.

## Key Features

- Keystroke- and pointer-based behavioural biometrics with a frozen enrolment
  template and a progressive, hysteresis-controlled identity score.
- Three-zone continuous authentication (Trusted 80–100, Monitor 60–79,
  Re-auth 0–59) with idle-freeze, corroboration override, and post-verify
  cooldown to eliminate false re-authentication prompts.
- Rule-based attack classification mapping intent to a deception strategy.
- Synthetic Success Injection and per-tenant, seeded shadow environments
  (Banking Shadow World, Shadow Admin World, synthetic datasets, tarpit).
- A demonstration lab that drives the *real* classifier, routing and shadow
  APIs and visualises the attack pipeline end-to-end.
- Defence-in-depth foundations: Argon2id password hashing, server-side session
  state, and MongoDB/Redis persistence.

## Expected Outcome

A working prototype that (i) keeps a legitimate user authenticated across a
session while reliably detecting and challenging a different human, and (ii)
silently diverts classified attackers into believable synthetic environments,
preserving the attacker's belief of success while isolating them from real
assets and capturing their behaviour for analysis.

## Conclusion

Entropy Prime reframes authentication as a *continuous behavioural* property
rather than a one-time credential check, and reframes threat response as
*deception* rather than blocking. Together these shift the asymmetry of web
security in favour of the defender: legitimate users experience frictionless
continuity, while attackers expend effort against a synthetic target and reveal
their methods. The framework is implemented as a modular system over a
React/FastAPI stack and is designed to augment, not replace, existing
authentication infrastructure.
