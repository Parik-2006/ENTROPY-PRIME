"""
Tests for the Phase 3 Deception Engine MVP (framework.deception).

These tests are intentionally dependency-light: the deception layer is
stdlib-only, so they run without numpy / pydantic / fastapi and without a
server.  They cover the five required scenarios and the six features.
"""
import sys
from pathlib import Path

# Repo root on path so `framework` is importable regardless of pytest rootdir.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pytest

from framework.deception.classifier import classify, AttackSignals, AttackClass
from framework.deception.synthetic_success import SyntheticSuccessInjector, ShadowStateStore
from framework.deception.shadow_world import get_engine, ShadowWorldEngine, BankingProfile
from framework.deception.threat_intel import ThreatIntelRecorder
from framework.deception.anti_fingerprint import generate_decoys, session_seed


# ── Feature 2: Attack classification ──────────────────────────────────────────
class TestClassifier:
    def test_credential_stuffing(self):
        c = classify(AttackSignals(distinct_usernames=20))
        assert c.attack_class == AttackClass.CREDENTIAL_STUFFING
        assert c.suggested_world == "banking"

    def test_brute_force(self):
        c = classify(AttackSignals(password_attempts=12))
        assert c.attack_class == AttackClass.BRUTE_FORCE

    def test_recon_admin_probe(self):
        c = classify(AttackSignals(admin_path_hits=3))
        assert c.attack_class == AttackClass.RECON
        assert c.suggested_world == "shadow_admin"
        assert c.arm_hint == 3

    def test_scraper_high_rate(self):
        c = classify(AttackSignals(request_rate=20.0))
        assert c.attack_class == AttackClass.SCRAPER

    def test_scraper_crawler_ua(self):
        c = classify(AttackSignals(user_agent="Scrapy/2.11", theta=0.05))
        assert c.attack_class == AttackClass.SCRAPER

    def test_unknown_default(self):
        c = classify(AttackSignals())
        assert c.attack_class == AttackClass.UNKNOWN

    def test_never_raises_on_empty(self):
        # Robustness: classifier must not raise on default/empty signals.
        assert classify(AttackSignals()) is not None


# ── Feature 1: Synthetic success injection ────────────────────────────────────
class TestSyntheticSuccess:
    def test_response_looks_like_login(self):
        inj = SyntheticSuccessInjector(secret="s", store=ShadowStateStore())
        resp, state = inj.mint_success(tenant_id="t", attack_class="recon", world="shadow_admin")
        assert resp["status"] == "success"
        assert "token" in resp and resp["user"]["verified"] is True
        assert resp["token"] == state.session_token

    def test_token_has_no_shadow_markers(self):
        inj = SyntheticSuccessInjector(secret="s", store=ShadowStateStore())
        resp, _ = inj.mint_success(tenant_id="t", attack_class="scraper", world="banking")
        assert not resp["token"].startswith("bot_")
        assert not resp["token"].startswith("ep_shadow_")
        assert resp["token"].startswith("ep_")  # same shape as a real token

    def test_shadow_state_is_server_side(self):
        store = ShadowStateStore()
        inj = SyntheticSuccessInjector(secret="s", store=store)
        resp, _ = inj.mint_success(tenant_id="t", attack_class="recon", world="shadow_admin")
        # The token alone reveals nothing; only the server-side store knows.
        assert store.is_shadow(resp["token"]) is True
        assert store.is_shadow("ep_some_other_token") is False

    def test_register_existing_token(self):
        store = ShadowStateStore()
        inj = SyntheticSuccessInjector(secret="s", store=store)
        st = inj.register(session_token="ep_abc_123", tenant_id="t",
                          attack_class="brute_force", world="banking", arm=0)
        assert store.get("ep_abc_123").world == "banking"
        assert st.world_seed  # deterministic seed assigned


# ── Features 3 & 4: Shadow worlds ─────────────────────────────────────────────
class TestShadowWorlds:
    def test_banking_assets_present(self):
        eng = get_engine()
        assert eng.has_world("banking")
        for asset in ("dashboard", "accounts", "transactions", "beneficiaries",
                      "statements", "profile"):
            data = eng.resolve("banking", "seedX", asset)
            assert isinstance(data, dict) and data

    def test_shadow_admin_assets_present(self):
        eng = get_engine()
        assert eng.has_world("shadow_admin")
        for asset in ("users", "logs", "analytics", "config", "secrets"):
            data = eng.resolve("shadow_admin", "seedX", asset)
            assert isinstance(data, dict) and data

    def test_secrets_are_canary(self):
        eng = get_engine()
        secrets_pg = eng.resolve("shadow_admin", "seedX", "secrets")
        assert all(s.get("canary") for s in secrets_pg["secrets"])

    def test_determinism_same_seed(self):
        eng = get_engine()
        a = eng.resolve("banking", "seed-1", "accounts")
        b = eng.resolve("banking", "seed-1", "accounts")
        assert a == b

    def test_uniqueness_different_seed(self):
        eng = get_engine()
        a = eng.resolve("banking", "seed-1", "accounts")
        b = eng.resolve("banking", "seed-2", "accounts")
        assert a != b

    def test_deep_pagination_differs(self):
        eng = get_engine()
        p1 = eng.resolve("banking", "seed-1", "transactions", page=1, page_size=5)
        p2 = eng.resolve("banking", "seed-1", "transactions", page=2, page_size=5)
        assert p1["transactions"] != p2["transactions"]

    def test_unknown_world_raises(self):
        eng = get_engine()
        with pytest.raises(KeyError):
            eng.resolve("nonexistent", "seed", "asset")

    def test_new_industry_pluggable(self):
        # Adding an industry requires no engine change — just register().
        eng = ShadowWorldEngine()
        eng.register(BankingProfile())
        assert eng.worlds() == ["banking"]


# ── Feature 5: Threat intelligence ────────────────────────────────────────────
class TestThreatIntel:
    def test_records_and_summarizes(self):
        rec = ThreatIntelRecorder()
        rec.record(session_token="s1", tenant_id="t", attack_class="recon",
                   event_type="shadow_start", detail={})
        rec.record(session_token="s1", tenant_id="t", attack_class="recon",
                   event_type="canary_hit", detail={})
        summary = rec.summary()
        assert summary["total_sessions"] == 1
        assert summary["total_events"] == 2
        sess = rec.sessions()[0]
        assert sess["canary_hits"] == 1

    def test_event_filtering(self):
        rec = ThreatIntelRecorder()
        rec.record(session_token="a", tenant_id="t", attack_class="scraper",
                   event_type="api_call", detail={})
        rec.record(session_token="b", tenant_id="t", attack_class="scraper",
                   event_type="api_call", detail={})
        assert len(rec.events(session_token="a")) == 1


# ── Feature 6: Anti-fingerprinting ────────────────────────────────────────────
class TestAntiFingerprint:
    def test_per_session_variation(self):
        a = [d.name for d in generate_decoys(session_seed("tokA", "t", 1))]
        b = [d.name for d in generate_decoys(session_seed("tokB", "t", 1))]
        assert a != b

    def test_stable_for_same_seed(self):
        seed = session_seed("tokA", "t", 1)
        assert [d.name for d in generate_decoys(seed)] == [d.name for d in generate_decoys(seed)]

    def test_no_static_legacy_names(self):
        # The legacy static literals must not appear deterministically.
        seen = set()
        for i in range(20):
            for d in generate_decoys(session_seed(f"tok{i}", "t", 1)):
                seen.add(d.name)
        assert "usernmae" not in seen
        assert "passwrd" not in seen
        assert "ep_canary_field" not in seen


# ── Scenario routing (end-to-end intent → world) ──────────────────────────────
@pytest.mark.parametrize("signals,expected_world", [
    (AttackSignals(distinct_usernames=20),  "banking"),       # credential stuffing
    (AttackSignals(admin_path_hits=3),       "shadow_admin"),  # recon
    (AttackSignals(request_rate=20.0),       "banking"),       # scraper
])
def test_scenario_routing(signals, expected_world):
    assert classify(signals).suggested_world == expected_world
