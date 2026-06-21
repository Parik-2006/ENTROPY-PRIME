"""
Entropy Prime — Python SDK
==========================

A dependency-free (stdlib-only) REST client for the Entropy Prime behavioral
security framework. Lets server-side applications enroll users, submit
behavioral scores, run continuous-auth heartbeats, and gate sensitive
transactions on the live trust posture.

Quick start
-----------
    from entropy_prime import EntropyPrime

    ep = EntropyPrime(api_url="http://localhost:8000")   # uses /v1 by default
    ep.register("parik@example.com", "correct horse battery staple")
    result = ep.score(theta=0.92, h_exp=0.8, latent_vector=[0.1] * 32)
    print(result["action_label"], result["shadow_mode"])

The client targets the versioned ``/v1`` API mounted by the framework gateway;
set ``prefix=""`` to talk to the legacy un-prefixed routes instead.
"""
from .client import EntropyPrime, EntropyPrimeError

__version__ = "0.1.0"
__all__ = ["EntropyPrime", "EntropyPrimeError", "__version__"]
