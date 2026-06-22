# Entropy Prime — Project Overview

## Introduction

Entropy Prime is a behavioural-security framework that adds two capabilities on
top of conventional authentication: **continuous behavioural authentication**
and **generative deception**. The system is built as a single-page React
application (the protected "Entropy Bank" product surface plus a Deception Demo
Lab) backed by a FastAPI service, with MongoDB and Redis for persistence and
TensorFlow.js for in-browser behavioural modelling. The project demonstrates
that identity can be treated as a *continuous* signal and that malicious traffic
can be *deceived* rather than blocked.

## Motivation

Account takeover via stolen-but-valid credentials and session hijacking defeats
password-only and even MFA-at-login systems, because nothing re-verifies the
operator after the initial check. Simultaneously, the standard response to bots
and intrusions — blocking — leaks the defence and forfeits intelligence. We were
motivated to build a system that (a) continuously asks "is this still the same
person?" using behaviour rather than secrets, and (b) answers detected threats
with believable deception that wastes the attacker's effort and exposes their
techniques.

## Objectives

1. Capture and model per-user keystroke and pointer dynamics in the browser.
2. Maintain a continuous identity-confidence score and re-authenticate only on a
   *sustained* behavioural mismatch, never on transient noise or idle periods.
3. Classify malicious requests by attacker intent using transparent rules.
4. Route classified attackers into isolated, believable synthetic environments
   via Synthetic Success Injection instead of blocking them.
5. Record attacker interactions as threat intelligence.
6. Provide a presentation-grade demonstration lab that exercises the real
   backend pipeline end-to-end.

## Scope

**In scope:** client-side behavioural biometrics; a three-zone continuous-auth
state machine; a rule-based attack classifier; honeypot routing and seeded
shadow environments (banking and admin); a deception demonstration lab; Argon2id
authentication; session management with MongoDB/Redis; and supporting
documentation.

**Out of scope (future work):** production-grade ML attack classification,
contextual-bandit honeypot selection, multi-tenant deployment hardening,
cross-environment canary-token attribution at scale, and formal security
certification. These are documented as roadmap items, not delivered features.

## Innovation

- **Synthetic Success Injection** — the attacker is told "login succeeded" and
  routed into a synthetic world, so detection never equals disclosure.
- **Frozen-template progressive identity scoring** — an immutable enrolment
  baseline plus a suspicion accumulator with corroboration and hysteresis,
  which discriminates *different humans* (not just bots) while avoiding false
  re-auth prompts.
- **Intent-aware deception** — attacker class selects the deception strategy
  (banking world, admin world, synthetic dataset, tarpit, restricted sandbox).

## Benefits

- **For legitimate users:** frictionless, continuous protection; re-verification
  is requested only on genuine, sustained anomalies.
- **For defenders:** attackers are isolated from real data, kept engaged, and
  observed; threat behaviour is captured rather than discarded.
- **For the organisation:** the framework augments existing login systems
  without replacing them, and degrades gracefully (in-memory fallbacks) for
  demonstrations and development.
