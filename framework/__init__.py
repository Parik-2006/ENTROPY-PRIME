"""
Entropy Prime — Behavioral Security Framework
=============================================

This package is the *public, product-facing surface* of Entropy Prime. It
organizes the existing implementation (currently living under ``backend/``)
into the framework's conceptual engines so that applications, SDKs, and the
API gateway can depend on stable, intention-revealing import paths instead of
the internal ``backend.pipeline.stageN_*`` layout.

Engines
-------
    framework.cadence_engine          Phase 1 — Cognitive Cadence (human vs bot)
    framework.dms_engine              Phase 2 — Dynamic Memory Security (Argon2id)
    framework.honeypot_engine         Phase 3 — Generative Honeypot (deception)
    framework.continuous_auth_engine  Phase 4 — Continuous Authentication (drift)
    framework.intelligence_engine     Cross-cutting — threat intel, notifications, webhooks
    framework.orchestrator            Runs the 4 engines in sequence
    framework.storage                 MongoDB + Redis data access
    framework.shared                  Contracts, enums, thresholds (the spine)

Migration note (v0.1 — facade stage)
-------------------------------------
At this stage every engine module *re-exports* the canonical implementation
from ``backend/`` without copying or modifying it. This guarantees ZERO
behavior change: the running application and its imports are untouched. A
later, test-gated migration phase will physically relocate the source into
these packages and leave compatibility shims at the old ``backend.*`` paths.

See ``MIGRATION_LOG.md`` at the repository root for the full mapping and the
classification of every file (ACTIVE / LEGACY / DUPLICATE / EXPERIMENTAL).

Import safety
-------------
``import framework`` is intentionally lightweight and pulls in no heavy
dependencies (torch, motor, fastapi). Import the specific engine you need;
each engine guards its optional heavy imports and exposes an ``*_AVAILABLE``
flag so a consumer that only wants, e.g., the contracts never has to install
PyTorch.
"""

__version__ = "0.1.0-facade"

__all__ = ["__version__"]
