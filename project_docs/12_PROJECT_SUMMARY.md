# Entropy Prime — Executive Summary

**Entropy Prime** is a behavioural-security framework that augments conventional
authentication with two cooperating capabilities: **continuous behavioural
authentication** and **generative deception**.

## The problem
Authentication today is a one-time check: a valid password or session token is
trusted for the whole session, so stolen credentials and hijacked sessions go
unnoticed. When threats *are* detected, systems block them — which discloses the
defence and discards intelligence.

## What we built
1. **Continuous behavioural authentication.** A browser-based engine captures
   keystroke dynamics (dwell, flight, per-digraph latency) and pointer dynamics,
   and continuously scores the live signature against an *immutable enrolment
   template*. A progressive confidence score maps to three zones — **Trusted
   (80–100)**, **Monitor (60–79)** and **Re-authenticate (0–59)**. A different
   human operating the same account is detected mid-session and challenged,
   while idle periods, transient noise and context-dependent speed never trigger
   false prompts (idle-freeze, corroboration override, suspicion accumulator,
   post-verify cooldown).

2. **Generative deception (honeypot engine).** Classified attackers are not
   blocked. Via **Synthetic Success Injection** they receive a normal "login
   succeeded" response and are transparently routed into isolated, believable
   **shadow environments** — a synthetic banking application, a shadow admin
   console with canary secrets, a synthetic dataset, a tarpit, or a restricted
   sandbox — chosen by a rule-based **attack classifier** (credential stuffing,
   brute force, reconnaissance, scraping, session abuse). All activity is
   recorded as threat intelligence.

## Technology
React · Vite · JavaScript · TensorFlow.js (frontend); FastAPI · Python (backend);
MongoDB · Redis (data); Argon2id (password hashing); Docker (infrastructure).

## Status
Working: behavioural biometrics, continuous authentication, attack
classification, honeypot routing, shadow banking/admin environments, the
Deception Demo Lab, frontend and backend. Partial (by design): durable
persistence depends on a running MongoDB — otherwise an in-memory fallback keeps
the system functional for demonstrations.

## Why it matters
Entropy Prime shifts the asymmetry of web security toward the defender:
legitimate users get frictionless, continuous protection, while attackers expend
effort against a synthetic target and reveal their methods — all without ever
learning they were detected. It is designed to *augment*, not replace, existing
authentication.

*Suitable for review by faculty, judges and evaluators. For a guided walkthrough
see `11_DEMO_SCRIPT.md`; for component status see `FINAL_AUDIT.md`.*
