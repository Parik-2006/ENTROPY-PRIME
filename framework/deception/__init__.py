"""
framework.deception — PHASE 3 MVP: Deception & Synthetic Environment Engine
===========================================================================

Evolves the existing Stage 2 honeypot (backend.models.stage2_honeypot) into a
believable deception engine.  The attacker must NEVER know they entered a
honeypot — detection is silent, the login "succeeds", and the attacker is
transparently isolated inside a synthetic world.

This package is ADDITIVE.  It does not modify or replace any existing module;
it composes them.  Every sub-module is import-safe with stdlib only (no new
runtime dependencies, no microservices) so it runs inside the existing FastAPI
container and can also be exercised standalone (see demo_mvp.py).

Sub-modules
-----------
    classifier/         Rule-based attacker-intent classification (Feature 2)
    synthetic_success/  Believable login + server-side shadow state (Feature 1)
    shadow_world/       Seeded synthetic environments (Banking) + ShadowAdmin
                        (Features 3 & 4)
    threat_intel/       Attacker activity recording / profiling (Feature 5)
    anti_fingerprint/   Seeded per-session decoy generation (Feature 6)
    api.py              FastAPI router exposing the shadow world + threat intel
    demo_mvp.py         Standalone 5-scenario demonstration

Design philosophy (MVP)
-----------------------
    • Generic first: nothing is banking-specific except shadow_world/banking.py.
      New industries (E-Commerce, Healthcare, SaaS) plug in by adding an
      IndustryProfile subclass — no engine changes.
    • Deterministic seeding: the same shadow session always sees the same world;
      different sessions/tenants see different worlds (anti-correlation).
    • Graceful degradation: if the DB / Redis is unavailable, recording falls
      back to an in-process store so demos never crash.
"""
from __future__ import annotations

__all__ = [
    "classifier",
    "synthetic_success",
    "shadow_world",
    "threat_intel",
    "anti_fingerprint",
]

__version__ = "0.1.0-mvp"
