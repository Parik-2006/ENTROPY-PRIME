"""
Minimal integration — server side (Python SDK)
==============================================
A ~20-line example of protecting a login flow with Entropy Prime. Requires a
running framework server (see repo README) and the Python SDK on the path:

    pip install -e framework/sdk/python
    python examples/integration_minimal/app.py
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "framework", "sdk", "python",
))

from entropy_prime import EntropyPrime, EntropyPrimeError


def protected_login(email: str, password: str, theta: float, latent: list[float]) -> str:
    ep = EntropyPrime(api_url="http://localhost:8000")   # talks to /v1
    ep.login(email, password)                            # raises on bad creds

    result = ep.score(theta=theta, h_exp=0.7, latent_vector=latent)
    if result["shadow_mode"]:
        return "DENIED — bot behavior detected (shadow-routed)."

    gate = ep.trust(user_id=ep.session_token, transaction_risk=0.3)
    return f"ALLOWED — action={gate['action']}, preset={result['action_label']}"


if __name__ == "__main__":
    try:
        print(protected_login("parik@example.com", "hunter2", theta=0.9, latent=[0.1] * 32))
    except EntropyPrimeError as exc:
        print("Login blocked:", exc)
