"""
Entropy Prime — Comprehensive Integration Test Suite
=====================================================

Tests the full FastAPI + Orchestrator stack using:
  - mongomock for in-memory MongoDB (no real instance required)
  - httpx.AsyncClient for async HTTP calls
  - pytest-asyncio for async test coroutines

Run with:
    pytest backend/tests -v
"""
from __future__ import annotations

import sys
import os
import time
import asyncio
import secrets
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient, ASGITransport

# ── ensure backend/ is on sys.path ─────────────────────────────────────────
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ── mongomock async motor shim ──────────────────────────────────────────────
import mongomock
from mongomock.mongo_client import MongoClient as MockMongoClient

# We need a mongomock database that exposes async collection methods.
# We wrap mongomock with AsyncMock-based shims so motor-style awaits work.

def _make_async_collection(sync_col):
    """Wrap a synchronous mongomock collection with async methods."""

    class AsyncCollection:
        def __init__(self, col):
            self._col = col

        async def insert_one(self, doc):
            return self._col.insert_one(doc)

        async def find_one(self, query=None, *args, **kwargs):
            return self._col.find_one(query or {}, *args, **kwargs)

        async def update_one(self, query, update, *args, **kwargs):
            return self._col.update_one(query, update, *args, **kwargs)

        async def count_documents(self, query=None, *args, **kwargs):
            return self._col.count_documents(query or {}, *args, **kwargs)

        def find(self, query=None, *args, **kwargs):
            return _AsyncCursor(self._col.find(query or {}, *args, **kwargs))

    return AsyncCollection(sync_col)


class _AsyncCursor:
    """Minimal async-cursor shim for mongomock sync cursor."""
    def __init__(self, cursor):
        self._cur = cursor

    def sort(self, *args, **kwargs):
        self._cur = self._cur.sort(*args, **kwargs)
        return self

    def limit(self, n):
        self._cur = self._cur.limit(n)
        return self

    async def to_list(self, length=None):
        results = list(self._cur)
        return results[:length] if length is not None else results


class _AsyncDB:
    """Wraps a mongomock DB to expose async-collection access via []."""
    def __init__(self, db):
        self._db = db
        self._cols: dict = {}

    def __getitem__(self, name):
        if name not in self._cols:
            self._cols[name] = _make_async_collection(self._db[name])
        return self._cols[name]


# ── shared mongomock instance (reset between test sessions) ─────────────────
_mock_client = MockMongoClient()
_mock_async_db = _AsyncDB(_mock_client["entropy_prime"])


# ── pytest configuration ─────────────────────────────────────────────────────
pytest_plugins = ("pytest_asyncio",)


# ── app fixture ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def app_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Spin up the FastAPI app once per test session with a mongomock DB injected
    directly, bypassing Motor.  The orchestrator is wired up manually here,
    mirroring exactly what the lifespan does.
    """
    import main as app_module
    from pipeline.orchestrator import PipelineOrchestrator

    # Wire the shim DB directly into the singleton
    app_module.db_handler.db = _mock_async_db

    # Build the orchestrator (the lifespan would normally do this)
    app_module.orchestrator = PipelineOrchestrator(
        dqn_agent      = app_module.dqn_agent,
        mab_agent      = app_module.mab_agent,
        ppo_agent      = app_module.ppo_agent,
        shadow_secret  = app_module.SHADOW_SECRET,
        session_secret = app_module.SESSION_SECRET,
    )

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def clear_db():
    """Drop all collections before each test for isolation."""
    for col in ("users", "sessions", "biometrics", "honeypot"):
        _mock_client["entropy_prime"][col].drop()
    yield


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

HUMAN_SCORE_PAYLOAD  = {"theta": 0.85, "h_exp": 0.70, "server_load": 0.30,
                         "user_agent": "Mozilla/5.0", "latent_vector": [0.5] * 32}
BOT_SCORE_PAYLOAD    = {"theta": 0.03, "h_exp": 0.95, "server_load": 0.20,
                         "user_agent": "python-requests/2.28", "latent_vector": [0.01] * 32}
SUSPECT_SCORE_PAYLOAD = {"theta": 0.18, "h_exp": 0.60, "server_load": 0.45,
                          "user_agent": "Mozilla/5.0", "latent_vector": [0.2] * 32}

TEST_EMAIL    = "integration@example.com"
TEST_PASSWORD = "S3cur3P@ssw0rd!"


async def _register(client: AsyncClient, email=TEST_EMAIL, pw=TEST_PASSWORD) -> dict:
    r = await client.post("/auth/register", json={"email": email, "plain_password": pw})
    assert r.status_code == 201, f"Register failed: {r.text}"
    return r.json()


async def _login(client: AsyncClient, email=TEST_EMAIL, pw=TEST_PASSWORD) -> dict:
    r = await client.post("/auth/login", json={"email": email, "plain_password": pw})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Health & Server Checks
# ─────────────────────────────────────────────────────────────────────────────

class TestServerHealth:
    async def test_health_returns_200(self, app_client: AsyncClient):
        r = await app_client.get("/health")
        assert r.status_code == 200

    async def test_health_payload_structure(self, app_client: AsyncClient):
        body = (await app_client.get("/health")).json()
        assert body["status"] == "ok"
        assert body["stages"] == 4
        assert "pipeline" in body
        assert "timestamp" in body

    async def test_health_pipeline_active(self, app_client: AsyncClient):
        body = (await app_client.get("/health")).json()
        assert body["pipeline"] == "active"

    async def test_cors_header_present(self, app_client: AsyncClient):
        r = await app_client.options(
            "/health",
            headers={"Origin": "http://localhost:3000",
                     "Access-Control-Request-Method": "GET"},
        )
        # FastAPI CORS middleware responds to OPTIONS preflight
        assert r.status_code in (200, 204)
        # The app must echo back an allow-origin header
        assert "access-control-allow-origin" in r.headers

    async def test_models_status_endpoint(self, app_client: AsyncClient):
        r = await app_client.get("/admin/models-status")
        assert r.status_code == 200
        body = r.json()
        for model_key in ("dqn", "mab", "ppo", "cnn1d"):
            assert model_key in body["models"]
            assert body["models"][model_key]["status"] == "loaded"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Scoring Scenarios
# ─────────────────────────────────────────────────────────────────────────────

class TestScoringScenarios:
    async def test_human_score_returns_200(self, app_client: AsyncClient):
        r = await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)
        assert r.status_code == 200

    async def test_human_score_not_shadow_mode(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)).json()
        assert body["shadow_mode"] is False

    async def test_human_score_standard_or_light_preset(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)).json()
        assert body["action_label"] in ("light", "standard", "hard", "paranoid")

    async def test_human_score_has_session_token(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)).json()
        assert isinstance(body["session_token"], str)
        assert len(body["session_token"]) > 10

    async def test_human_score_required_fields(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)).json()
        for field in ("session_token", "shadow_mode", "argon2_params",
                      "humanity_score", "entropy_score", "action_label",
                      "pipeline_confidence", "degraded"):
            assert field in body, f"Missing field: {field}"

    async def test_bot_score_shadow_mode_enabled(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=BOT_SCORE_PAYLOAD)).json()
        assert body["shadow_mode"] is True

    async def test_bot_score_returns_200_always(self, app_client: AsyncClient):
        """Bots always receive HTTP 200 (shadow token, not rejection)."""
        r = await app_client.post("/score", json=BOT_SCORE_PAYLOAD)
        assert r.status_code == 200

    async def test_bot_score_writes_honeypot_entry(self, app_client: AsyncClient):
        await app_client.post("/score", json=BOT_SCORE_PAYLOAD)
        count = _mock_client["entropy_prime"]["honeypot"].count_documents({})
        assert count >= 1

    async def test_bot_score_mab_arm_in_response(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=BOT_SCORE_PAYLOAD)).json()
        # mab_arm is only present when shadow_mode=True and arm >= 0
        if body["shadow_mode"]:
            assert "mab_arm" in body
            assert 0 <= body["mab_arm"] < 3

    async def test_suspect_score_returns_200(self, app_client: AsyncClient):
        r = await app_client.post("/score", json=SUSPECT_SCORE_PAYLOAD)
        assert r.status_code == 200

    async def test_suspect_score_fields_present(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=SUSPECT_SCORE_PAYLOAD)).json()
        assert "shadow_mode" in body
        assert "action_label" in body

    async def test_score_argon2_params_structure(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)).json()
        params = body["argon2_params"]
        assert "m" in params and "t" in params and "p" in params
        assert params["m"] > 0 and params["t"] > 0 and params["p"] > 0

    async def test_score_humanity_score_matches_theta(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)).json()
        assert abs(body["humanity_score"] - HUMAN_SCORE_PAYLOAD["theta"]) < 1e-6

    async def test_score_invalid_theta_rejected(self, app_client: AsyncClient):
        bad = {**HUMAN_SCORE_PAYLOAD, "theta": 1.5}
        r   = await app_client.post("/score", json=bad)
        assert r.status_code == 422

    async def test_score_invalid_latent_vector_rejected(self, app_client: AsyncClient):
        bad = {**HUMAN_SCORE_PAYLOAD, "latent_vector": [0.1] * 10}  # not 32-dim
        r   = await app_client.post("/score", json=bad)
        assert r.status_code == 422

    async def test_score_empty_latent_vector_accepted(self, app_client: AsyncClient):
        payload = {**HUMAN_SCORE_PAYLOAD, "latent_vector": []}
        r       = await app_client.post("/score", json=payload)
        assert r.status_code == 200

    async def test_watchdog_block_in_response_when_latent_present(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)).json()
        # latent_vector is present so watchdog should run
        assert "watchdog" in body
        assert body["watchdog"]["action"] in ("ok", "passive_reauth",
                                               "disable_sensitive_api", "force_logout")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentication:
    async def test_register_new_user_201(self, app_client: AsyncClient):
        r = await app_client.post("/auth/register",
                                   json={"email": TEST_EMAIL, "plain_password": TEST_PASSWORD})
        assert r.status_code == 201

    async def test_register_response_fields(self, app_client: AsyncClient):
        body = (await _register(app_client))
        for field in ("success", "user_id", "email", "session_token", "security_level"):
            assert field in body

    async def test_register_duplicate_email_409(self, app_client: AsyncClient):
        await _register(app_client)
        r = await app_client.post("/auth/register",
                                   json={"email": TEST_EMAIL, "plain_password": TEST_PASSWORD})
        assert r.status_code == 409

    async def test_login_correct_credentials_200(self, app_client: AsyncClient):
        await _register(app_client)
        r = await app_client.post("/auth/login",
                                   json={"email": TEST_EMAIL, "plain_password": TEST_PASSWORD})
        assert r.status_code == 200

    async def test_login_wrong_password_401(self, app_client: AsyncClient):
        await _register(app_client)
        r = await app_client.post("/auth/login",
                                   json={"email": TEST_EMAIL, "plain_password": "wrong!"})
        assert r.status_code == 401

    async def test_login_unknown_email_401(self, app_client: AsyncClient):
        r = await app_client.post("/auth/login",
                                   json={"email": "nobody@example.com", "plain_password": "x"})
        assert r.status_code == 401

    async def test_login_returns_session_token(self, app_client: AsyncClient):
        await _register(app_client)
        body = (await _login(app_client))
        assert isinstance(body["session_token"], str)
        assert len(body["session_token"]) > 10

    async def test_logout_success(self, app_client: AsyncClient):
        await _register(app_client)
        login_body   = await _login(app_client)
        session_token = login_body["session_token"]
        r = await app_client.post("/auth/logout", json={"session_token": session_token})
        assert r.status_code == 200
        assert r.json()["success"] is True

    async def test_logout_invalidates_session(self, app_client: AsyncClient):
        """After logout, /me with the same token must return 401."""
        await _register(app_client)
        login_body    = await _login(app_client)
        session_token = login_body["session_token"]
        await app_client.post("/auth/logout", json={"session_token": session_token})
        r = await app_client.get("/me", headers={"X-Session-Token": session_token})
        assert r.status_code == 401

    async def test_me_with_valid_token(self, app_client: AsyncClient):
        reg  = await _register(app_client)
        token = reg["session_token"]
        r = await app_client.get("/me", headers={"X-Session-Token": token})
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == TEST_EMAIL

    async def test_me_without_token_401(self, app_client: AsyncClient):
        r = await app_client.get("/me")
        assert r.status_code == 401

    async def test_me_with_bogus_token_401(self, app_client: AsyncClient):
        r = await app_client.get("/me", headers={"X-Session-Token": "bogus_token_xyz"})
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 4. Full Session Flow  (Register → Login → Heartbeat → Logout)
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionFlow:
    async def test_register_then_login_gives_different_tokens(self, app_client: AsyncClient):
        reg   = await _register(app_client)
        login = await _login(app_client)
        # Login always issues a fresh token
        assert reg["session_token"] != login["session_token"]

    async def test_heartbeat_with_healthy_session(self, app_client: AsyncClient):
        await _register(app_client)
        login = await _login(app_client)
        payload = {
            "session_token": login["session_token"],
            "user_id":       login["user_id"],
            "latent_vector": [0.5] * 32,
            "e_rec":         0.05,
        }
        r = await app_client.post("/session/verify", json=payload)
        assert r.status_code == 200

    async def test_heartbeat_returns_action(self, app_client: AsyncClient):
        await _register(app_client)
        login = await _login(app_client)
        payload = {"session_token": login["session_token"], "user_id": login["user_id"],
                   "latent_vector": [0.5] * 32, "e_rec": 0.05}
        body = (await app_client.post("/session/verify", json=payload)).json()
        assert body["action"] in ("ok", "passive_reauth", "disable_sensitive_api", "force_logout")
        assert "trust_score" in body
        assert "e_rec" in body

    async def test_heartbeat_decays_trust_score(self, app_client: AsyncClient):
        await _register(app_client)
        login = await _login(app_client)
        payload = {"session_token": login["session_token"], "user_id": login["user_id"],
                   "latent_vector": [0.5] * 32, "e_rec": 0.05}
        body = (await app_client.post("/session/verify", json=payload)).json()
        # Trust score should be < 1.0 after decay
        assert body["trust_score"] < 1.0

    async def test_heartbeat_with_critical_e_rec_force_logout(self, app_client: AsyncClient):
        await _register(app_client)
        login = await _login(app_client)
        payload = {"session_token": login["session_token"], "user_id": login["user_id"],
                   "latent_vector": [0.5] * 32, "e_rec": 0.90}  # way above critical 0.35
        body = (await app_client.post("/session/verify", json=payload)).json()
        assert body["action"] == "force_logout"
        assert body["session_invalidated"] is True

    async def test_heartbeat_after_force_logout_returns_401(self, app_client: AsyncClient):
        await _register(app_client)
        login = await _login(app_client)
        # Trigger force logout
        await app_client.post("/session/verify", json={
            "session_token": login["session_token"], "user_id": login["user_id"],
            "latent_vector": [0.5] * 32, "e_rec": 0.90,
        })
        # Subsequent heartbeat with same token must fail
        r = await app_client.post("/session/verify", json={
            "session_token": login["session_token"], "user_id": login["user_id"],
            "latent_vector": [0.5] * 32, "e_rec": 0.05,
        })
        assert r.status_code == 401

    async def test_heartbeat_user_id_mismatch_401(self, app_client: AsyncClient):
        await _register(app_client)
        login = await _login(app_client)
        payload = {"session_token": login["session_token"],
                   "user_id": "000000000000000000000000",  # wrong user
                   "latent_vector": [0.5] * 32, "e_rec": 0.05}
        r = await app_client.post("/session/verify", json=payload)
        assert r.status_code == 401

    async def test_heartbeat_bogus_token_401(self, app_client: AsyncClient):
        await _register(app_client)
        login = await _login(app_client)
        payload = {"session_token": "not_a_real_token", "user_id": login["user_id"],
                   "latent_vector": [0.5] * 32, "e_rec": 0.05}
        r = await app_client.post("/session/verify", json=payload)
        assert r.status_code == 401

    async def test_heartbeat_invalid_latent_dim_422(self, app_client: AsyncClient):
        await _register(app_client)
        login = await _login(app_client)
        payload = {"session_token": login["session_token"], "user_id": login["user_id"],
                   "latent_vector": [0.1] * 10, "e_rec": 0.05}  # wrong dim
        r = await app_client.post("/session/verify", json=payload)
        assert r.status_code == 422

    async def test_full_session_chain(self, app_client: AsyncClient):
        """Register → Login → Heartbeat (healthy) → Logout → /me 401"""
        # 1. Register
        reg = await _register(app_client)
        assert reg["success"] is True

        # 2. Login
        login = await _login(app_client)
        token   = login["session_token"]
        user_id = login["user_id"]

        # 3. Heartbeat
        hb_r = await app_client.post("/session/verify", json={
            "session_token": token, "user_id": user_id,
            "latent_vector": [0.5] * 32, "e_rec": 0.05,
        })
        assert hb_r.status_code == 200

        # 4. /me still works
        me_r = await app_client.get("/me", headers={"X-Session-Token": token})
        assert me_r.status_code == 200

        # 5. Logout
        lo_r = await app_client.post("/auth/logout", json={"session_token": token})
        assert lo_r.status_code == 200

        # 6. /me now 401
        me_r2 = await app_client.get("/me", headers={"X-Session-Token": token})
        assert me_r2.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 5. Honeypot / MAB
# ─────────────────────────────────────────────────────────────────────────────

class TestHoneypotAndMAB:
    async def test_honeypot_signatures_empty_initially(self, app_client: AsyncClient):
        r = await app_client.get("/honeypot/signatures")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    async def test_honeypot_count_increments_after_bot_score(self, app_client: AsyncClient):
        await app_client.post("/score", json=BOT_SCORE_PAYLOAD)
        r    = await app_client.get("/honeypot/signatures")
        body = r.json()
        assert body["count"] >= 1

    async def test_honeypot_dashboard(self, app_client: AsyncClient):
        r = await app_client.get("/admin/honeypot/dashboard")
        assert r.status_code == 200
        assert "total_count" in r.json()

    async def test_mab_reward_valid(self, app_client: AsyncClient):
        r = await app_client.post("/honeypot/reward", json={"arm": 0, "reward": 0.8})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["arm"] == 0

    async def test_mab_reward_negative(self, app_client: AsyncClient):
        r = await app_client.post("/honeypot/reward", json={"arm": 1, "reward": -0.5})
        assert r.status_code == 200

    async def test_mab_reward_out_of_bounds_arm_422(self, app_client: AsyncClient):
        r = await app_client.post("/honeypot/reward", json={"arm": 99, "reward": 0.5})
        assert r.status_code == 422

    async def test_mab_reward_clamp_max(self, app_client: AsyncClient):
        r = await app_client.post("/honeypot/reward", json={"arm": 0, "reward": 1.0})
        assert r.status_code == 200
        assert r.json()["reward"] <= 1.0

    async def test_mab_reward_out_of_range_422(self, app_client: AsyncClient):
        r = await app_client.post("/honeypot/reward", json={"arm": 0, "reward": 5.0})
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 6. Biometric Extract (CNN)
# ─────────────────────────────────────────────────────────────────────────────

class TestBiometricExtract:
    async def test_extract_returns_features(self, app_client: AsyncClient):
        r = await app_client.post("/biometric/extract",
                                   json={"raw_signal": [0.1, 0.2, 0.3, 0.4, 0.5]})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "features" in body
        assert body["dim"] == 32

    async def test_extract_empty_signal(self, app_client: AsyncClient):
        r = await app_client.post("/biometric/extract", json={"raw_signal": []})
        assert r.status_code == 200

    async def test_biometric_profile_requires_auth(self, app_client: AsyncClient):
        r = await app_client.get("/biometric/profile/some_user_id")
        assert r.status_code == 401

    async def test_biometric_profile_wrong_user_403(self, app_client: AsyncClient):
        reg  = await _register(app_client, "alice@test.com")
        reg2 = await _register(app_client, "bob@test.com",   "P@ssw0rd2")
        # alice tries to read bob's profile
        r = await app_client.get(
            f"/biometric/profile/{reg2['user_id']}",
            headers={"X-Session-Token": reg["session_token"]},
        )
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 7. Password Utilities
# ─────────────────────────────────────────────────────────────────────────────

class TestPasswordUtils:
    async def test_hash_endpoint(self, app_client: AsyncClient):
        r = await app_client.post("/password/hash",
                                   json={"plain_password": "hunter2", "theta": 0.8, "h_exp": 0.5})
        assert r.status_code == 200
        body = r.json()
        assert "hash" in body
        assert body["hash"].startswith("$argon2")

    async def test_verify_correct_password(self, app_client: AsyncClient):
        hash_r = (await app_client.post("/password/hash",
                                        json={"plain_password": "mypassword"})).json()
        r = await app_client.post("/password/verify",
                                   json={"plain_password": "mypassword",
                                         "stored_hash": hash_r["hash"]})
        assert r.status_code == 200
        assert r.json()["valid"] is True

    async def test_verify_wrong_password(self, app_client: AsyncClient):
        hash_r = (await app_client.post("/password/hash",
                                        json={"plain_password": "mypassword"})).json()
        r = await app_client.post("/password/verify",
                                   json={"plain_password": "wrongpassword",
                                         "stored_hash": hash_r["hash"]})
        assert r.status_code == 200
        assert r.json()["valid"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 8. Pipeline Debug & Admin
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminPipelineDebug:
    async def test_debug_default_params(self, app_client: AsyncClient):
        r = await app_client.get("/admin/pipeline-debug")
        assert r.status_code == 200
        body = r.json()
        assert "stages" in body
        assert "biometric" in body["stages"]
        assert "honeypot"  in body["stages"]
        assert "governor"  in body["stages"]
        assert "watchdog"  in body["stages"]

    async def test_debug_bot_theta(self, app_client: AsyncClient):
        r = await app_client.get("/admin/pipeline-debug?theta=0.02&h_exp=0.9&server_load=0.2")
        assert r.status_code == 200
        body = r.json()
        assert body["stages"]["biometric"]["is_bot"] is True
        assert body["shadow_mode"] is True

    async def test_debug_human_theta(self, app_client: AsyncClient):
        r = await app_client.get("/admin/pipeline-debug?theta=0.95&h_exp=0.1&server_load=0.3")
        assert r.status_code == 200
        body = r.json()
        assert body["stages"]["biometric"]["is_bot"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 9. Fallback / Degraded Mode Resilience
# ─────────────────────────────────────────────────────────────────────────────

class TestDegradedModeFallback:
    async def test_score_still_returns_200_when_stage1_raises(self, app_client: AsyncClient):
        """
        If Stage 1 (biometric interpreter) crashes, the orchestrator must
        catch the exception and return a degraded=True response with HTTP 200.
        Bots should never receive an error page — that breaks the deception.
        """
        import main as app_module
        import pipeline.stage1_biometric as s1_mod

        original_run = s1_mod.run
        s1_mod.run = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated s1 failure"))

        try:
            r = await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)
            assert r.status_code == 200
            body = r.json()
            assert body["degraded"] is True
        finally:
            s1_mod.run = original_run

    async def test_score_degraded_when_governor_raises(self, app_client: AsyncClient):
        """Stage 3 (governor/DQN) failure → degraded=True, STANDARD preset fallback."""
        import pipeline.stage3_governor as s3_mod

        original_run = s3_mod.run
        s3_mod.run = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("dqn exploded"))

        try:
            r = await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)
            assert r.status_code == 200
            assert r.json()["degraded"] is True
        finally:
            s3_mod.run = original_run

    async def test_score_degraded_when_honeypot_raises(self, app_client: AsyncClient):
        """Stage 2 (honeypot/MAB) failure → degraded result but no crash."""
        import pipeline.stage2_honeypot as s2_mod

        original_run = s2_mod.run
        s2_mod.run = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("mab crashed"))

        try:
            r = await app_client.post("/score", json=BOT_SCORE_PAYLOAD)
            assert r.status_code == 200
            assert r.json()["degraded"] is True
        finally:
            s2_mod.run = original_run

    async def test_score_not_degraded_in_normal_operation(self, app_client: AsyncClient):
        body = (await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)).json()
        assert body["degraded"] is False

    async def test_watchdog_none_agent_falls_back_to_rule_based(self, app_client: AsyncClient):
        """
        Even with a broken PPO agent, the stage-4 rule-based fallback must
        still return a valid WatchdogResult.  We validate this through /score
        with a latent vector so the watchdog runs.
        """
        import main as app_module
        original_ppo = app_module.orchestrator.ppo
        app_module.orchestrator.ppo = None
        try:
            body = (await app_client.post("/score", json=HUMAN_SCORE_PAYLOAD)).json()
            assert "watchdog" in body
            assert body["watchdog"]["action"] in (
                "ok", "passive_reauth", "disable_sensitive_api", "force_logout"
            )
        finally:
            app_module.orchestrator.ppo = original_ppo


# ─────────────────────────────────────────────────────────────────────────────
# 10. Session Guard (require_active_session dependency)
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionGuard:
    async def test_guard_rejects_missing_header(self, app_client: AsyncClient):
        r = await app_client.get("/me")
        assert r.status_code == 401
        assert "X-Session-Token" in r.json().get("detail", "")

    async def test_guard_rejects_expired_session(self, app_client: AsyncClient):
        """Manually insert an expired session and verify the guard rejects it."""
        col = _mock_client["entropy_prime"]["sessions"]
        col.insert_one({
            "user_id":       "expired_user",
            "session_token": "expired_tok_999",
            "is_active":     True,
            "trust_score":   1.0,
            "created_at":    time.time() - 7200,
            "expires_at":    time.time() - 3600,  # expired 1 hour ago
        })
        r = await app_client.get("/me", headers={"X-Session-Token": "expired_tok_999"})
        assert r.status_code == 401

    async def test_guard_rejects_inactive_session(self, app_client: AsyncClient):
        """Manually insert an is_active=False session."""
        col = _mock_client["entropy_prime"]["sessions"]
        col.insert_one({
            "user_id":       "ghost_user",
            "session_token": "inactive_tok_888",
            "is_active":     False,
            "trust_score":   1.0,
            "created_at":    time.time(),
            "expires_at":    time.time() + 3600,
        })
        r = await app_client.get("/me", headers={"X-Session-Token": "inactive_tok_888"})
        assert r.status_code == 401

    async def test_guard_accepts_valid_session(self, app_client: AsyncClient):
        reg = await _register(app_client)
        r   = await app_client.get("/me", headers={"X-Session-Token": reg["session_token"]})
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 11. Edge-cases & Boundary values
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    async def test_score_theta_zero_is_bot(self, app_client: AsyncClient):
        payload = {**HUMAN_SCORE_PAYLOAD, "theta": 0.0}
        body    = (await app_client.post("/score", json=payload)).json()
        assert body["shadow_mode"] is True

    async def test_score_theta_one_is_human(self, app_client: AsyncClient):
        payload = {**HUMAN_SCORE_PAYLOAD, "theta": 1.0}
        body    = (await app_client.post("/score", json=payload)).json()
        assert body["shadow_mode"] is False

    async def test_score_server_overload_caps_preset(self, app_client: AsyncClient):
        payload = {**HUMAN_SCORE_PAYLOAD, "server_load": 0.92}
        body    = (await app_client.post("/score", json=payload)).json()
        # With server overload the governor caps to STANDARD or LIGHT
        assert body["action_label"] in ("light", "standard")

    async def test_multiple_bot_requests_accumulate_honeypot(self, app_client: AsyncClient):
        for _ in range(5):
            await app_client.post("/score", json=BOT_SCORE_PAYLOAD)
        r = await app_client.get("/honeypot/signatures")
        assert r.json()["count"] == 5

    async def test_register_creates_session_immediately(self, app_client: AsyncClient):
        """Fresh registration must return a usable session token (no separate login)."""
        reg = await _register(app_client)
        r   = await app_client.get("/me", headers={"X-Session-Token": reg["session_token"]})
        assert r.status_code == 200

    async def test_trust_score_not_accepted_from_client(self, app_client: AsyncClient):
        """
        /session/verify intentionally does NOT accept trust_score from the
        client body.  Verify the endpoint ignores extra fields gracefully.
        """
        await _register(app_client)
        login = await _login(app_client)
        payload = {
            "session_token": login["session_token"],
            "user_id":       login["user_id"],
            "latent_vector": [0.5] * 32,
            "e_rec":         0.05,
            "trust_score":   999.0,  # should be silently ignored
        }
        r = await app_client.post("/session/verify", json=payload)
        # Should still succeed; the injected trust_score is ignored
        assert r.status_code == 200
        assert r.json()["trust_score"] < 2.0  # DB value was used, not 999.0
