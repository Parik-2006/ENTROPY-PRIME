"""
examples._common — offline framework harness for the demos
==========================================================

Builds the 4-engine pipeline in-process (no API server, no MongoDB, no Redis)
so every demo runs with a single `python demo.py`. It exercises the *same*
framework engines the production server uses, via the public `framework.*`
surface.

Two entry points:
  * score_session(theta, h_exp, latent) -> dict   (Cadence + Honeypot + DMS)
  * continuous_check(latent, baseline, trust) -> dict  (Continuous Auth / drift)

To instead run a demo against a *live* server, use the Python SDK:
    from entropy_prime import EntropyPrime
    ep = EntropyPrime(api_url="http://localhost:8000")
"""
from __future__ import annotations

import os
import sys

# Make the repository root importable so `import framework` works when the demo
# is run from inside its own directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import numpy as np  # noqa: E402

from framework.orchestrator import PipelineOrchestrator, BiometricInput  # noqa: E402
from framework.dms_engine import DQNAgent, PPOPolicyAgent  # noqa: E402
from framework.honeypot_engine import MABAgent  # noqa: E402
from framework.continuous_auth_engine import PPOAgent  # noqa: E402
from framework import continuous_auth_engine as ca  # noqa: E402

_ORCH = None


def get_orchestrator() -> PipelineOrchestrator:
    """Construct the 4-engine pipeline once (preserves the PPO/PPOPolicy split)."""
    global _ORCH
    if _ORCH is None:
        _ORCH = PipelineOrchestrator(
            dqn_agent=DQNAgent(state_dim=3, action_dim=4),
            mab_agent=MABAgent(n_arms=3),
            gov_ppo_agent=PPOPolicyAgent(state_dim=5, action_dim=4),   # governor → int
            ppo_agent=PPOAgent(state_dim=10, action_dim=3),            # watchdog → tuple
            shadow_secret="demo-shadow-secret",
            session_secret="demo-session-secret",
        )
    return _ORCH


def score_session(theta: float, h_exp: float, latent) -> dict:
    """Run Cadence → Honeypot → DMS and return a flat result dict."""
    out = get_orchestrator().run(
        BiometricInput(
            theta=theta, h_exp=h_exp, server_load=0.4,
            user_agent="demo", latent_vector=list(np.asarray(latent, dtype=float)),
            ip_address="127.0.0.1",
        )
    )
    return {
        "theta": theta,
        "shadow_mode": out.shadow_mode,
        "action_label": out.action_label,
        "argon2_params": out.argon2_params,
        "verdict": out.biometric.verdict.value,
        "is_bot": out.biometric.is_bot,
        "mab_arm": out.honeypot.mab_arm_selected,
        "confidence": out.pipeline_confidence.value,
    }


def continuous_check(latent, baseline, trust: float = 1.0) -> dict:
    """Run the Continuous-Auth engine (drift) for a heartbeat-style check."""
    from examples._simulation import recon_error
    e_rec = recon_error(baseline, latent)
    wd = ca.run(
        latent_vector=list(np.asarray(latent, dtype=float)),
        e_rec=e_rec,
        trust_score=trust,
        ppo_agent=get_orchestrator()._ppo,
    )
    zone = "GREEN" if wd.action.value == "ok" else (
        "RED" if wd.action.value == "force_logout" else "YELLOW"
    )
    return {
        "e_rec": round(e_rec, 4),
        "action": wd.action.value,
        "trust_score": round(wd.trust_score, 3),
        "confidence": wd.confidence.value,
        "zone": zone,
        "reason": wd.reason,
    }
