"""
entropy_prime.client — REST client for the Entropy Prime framework.

Stdlib only (urllib) so it runs anywhere with zero install footprint.
Every method maps 1:1 onto a framework API endpoint; the client manages the
session token returned by register/login automatically.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class EntropyPrimeError(Exception):
    """Raised on any non-2xx response. Carries status code + server detail."""

    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"Entropy Prime API error {status}: {detail}")


class EntropyPrime:
    """
    Thin REST client.

    Parameters
    ----------
    api_url        Base URL of the framework (e.g. http://localhost:8000).
    api_key        Optional site API key (sent as X-API-Key) for SDK routes.
    session_token  Optional pre-existing user session token.
    prefix         API version prefix; "/v1" (default) or "" for legacy routes.
    timeout        Per-request timeout in seconds.
    """

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        session_token: Optional[str] = None,
        prefix: str = "/v1",
        timeout: float = 10.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.session_token = session_token
        self.prefix = prefix.rstrip("/")
        self.timeout = timeout

    # ── transport ────────────────────────────────────────────────────────────

    def _p(self, path: str) -> str:
        return f"{self.prefix}{path}" if self.prefix else path

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        auth: bool = True,
        query: Optional[dict] = None,
    ) -> Any:
        url = self.api_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if auth and self.session_token:
            headers["X-Session-Token"] = self.session_token

        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode() or "{}"
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode()).get("detail")
            except Exception:
                detail = exc.reason
            raise EntropyPrimeError(exc.code, detail) from None
        except urllib.error.URLError as exc:
            raise EntropyPrimeError(0, f"connection failed: {exc.reason}") from None

    # ── health ───────────────────────────────────────────────────────────────

    def health(self) -> dict:
        return self._request("GET", self._p("/health"), auth=False)

    # ── auth / enrollment ────────────────────────────────────────────────────

    def register(self, email: str, password: str) -> dict:
        """Enroll a new user; seeds an empty behavioral profile (`collecting`)."""
        r = self._request(
            "POST", self._p("/auth/register"),
            {"email": email, "plain_password": password}, auth=False,
        )
        self.session_token = r.get("session_token", self.session_token)
        return r

    # Framework-friendly alias.
    enroll = register

    def login(self, email: str, password: str) -> dict:
        r = self._request(
            "POST", self._p("/auth/login"),
            {"email": email, "plain_password": password}, auth=False,
        )
        self.session_token = r.get("session_token", self.session_token)
        return r

    def logout(self) -> dict:
        token = self.session_token
        r = self._request("POST", self._p("/auth/logout"), {"session_token": token})
        self.session_token = None
        return r

    def me(self) -> dict:
        return self._request("GET", self._p("/me"))

    # ── pipeline ─────────────────────────────────────────────────────────────

    def score(
        self,
        theta: float,
        h_exp: float,
        latent_vector: Optional[list[float]] = None,
        user_agent: str = "",
        server_load: float = 0.5,
        fingerprint: str = "",
    ) -> dict:
        """Run the full 4-engine pipeline. Returns routing + Argon2id params."""
        return self._request(
            "POST", self._p("/score"),
            {
                "theta": theta, "h_exp": h_exp, "server_load": server_load,
                "user_agent": user_agent,
                "latent_vector": latent_vector or [],
                "fingerprint": fingerprint,
            },
            auth=False,
        )

    def sync_profile(self, **kwargs: Any) -> dict:
        """Persist aggregated typing stats during profile-build (`/biometric/profile`)."""
        return self._request("POST", self._p("/biometric/profile"), kwargs)

    def profile_status(self, user_id: str) -> dict:
        return self._request("GET", self._p(f"/biometric/profile/{user_id}/status"))

    def reset_profile(self, reason: str = "user_request") -> dict:
        return self._request("POST", self._p("/biometric/profile/reset"), {"reason": reason})

    # ── continuous authentication ────────────────────────────────────────────

    def verify(
        self,
        user_id: str,
        latent_vector: list[float],
        e_rec: float,
        onboarding_state: str = "collecting",
        **extra: Any,
    ) -> dict:
        """Continuous-auth heartbeat (`/session/verify`). Returns drift action."""
        body = {
            "session_token": self.session_token or "",
            "user_id": user_id,
            "latent_vector": latent_vector,
            "e_rec": e_rec,
            "onboarding_state": onboarding_state,
        }
        body.update(extra)
        return self._request("POST", self._p("/session/verify"), body, auth=False)

    def trust(self, user_id: str, transaction_risk: float = 0.5, **extra: Any) -> dict:
        """Gate a sensitive transaction (`/session/trust`). Returns allow/challenge/deny."""
        body = {
            "session_token": self.session_token or "",
            "user_id": user_id,
            "transaction_risk": transaction_risk,
        }
        body.update(extra)
        return self._request("POST", self._p("/session/trust"), body, auth=False)

    # ── honeypot feedback ────────────────────────────────────────────────────

    def honeypot_reward(self, arm: int, reward: float) -> dict:
        return self._request("POST", self._p("/honeypot/reward"), {"arm": arm, "reward": reward}, auth=False)
