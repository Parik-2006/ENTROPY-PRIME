"""
demo_mvp.py - Phase 3 Deception Engine MVP demonstration (stdlib only)
=====================================================================

Runs the five required scenarios end-to-end against the deception layer
WITHOUT needing the backend's third-party deps (pydantic / numpy / fastapi) or
a running server - everything here is stdlib + framework.deception.

    Scenario 1  Human user            -> real environment (not shadowed)
    Scenario 2  Credential-stuffing   -> Banking shadow world
    Scenario 3  Recon bot             -> Shadow Admin
    Scenario 4  Scraper               -> synthetic data feed
    Scenario 5  Threat dashboard records all attacker activity

Run from the repo root:

    python -m framework.deception.demo_mvp

The upstream bot-detection gate is reproduced inline (``_should_shadow``) so
the demo is self-contained; it mirrors backend.models.stage2_honeypot._should_shadow
exactly (BOT -> always; SUSPECT -> only HIGH/MEDIUM confidence).
"""
from __future__ import annotations

from framework.deception.classifier import classify, AttackSignals
from framework.deception.synthetic_success import SyntheticSuccessInjector, get_default_store
from framework.deception.shadow_world import get_engine
from framework.deception.threat_intel import get_recorder
from framework.deception.anti_fingerprint import generate_decoys, session_seed


# ── upstream gate (mirrors stage2_honeypot._should_shadow) ────────────────────
def _should_shadow(verdict: str, confidence: str) -> bool:
    if verdict == "bot":
        return True
    if verdict == "suspect" and confidence in ("high", "medium"):
        return True
    return False


def _hr(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def run_demo() -> None:
    injector = SyntheticSuccessInjector(secret="demo-secret")
    engine   = get_engine()
    recorder = get_recorder()
    store    = get_default_store()

    # ── Scenario 1: Human ─────────────────────────────────────────────────────
    _hr("SCENARIO 1 - Human user -> REAL environment")
    verdict, conf = "human", "high"
    print(f"verdict={verdict} confidence={conf}")
    if _should_shadow(verdict, conf):
        print("  [X] unexpectedly shadowed")
    else:
        print("  [OK] NOT shadowed - proceeds to the real application. No deception.")

    # ── Scenario 2: Credential stuffing ──────────────────────────────────────
    _hr("SCENARIO 2 - Credential-stuffing bot -> BANKING shadow world")
    sig = AttackSignals(distinct_usernames=18, failed_attempts=22, theta=0.04,
                        user_agent="python-requests/2.31")
    clf = classify(sig)
    print(f"classified: {clf.attack_class.value} ({clf.confidence.value}) -> world={clf.suggested_world}")
    print(f"  reasons: {clf.reasons}")
    resp, st = injector.mint_success(tenant_id="acme-bank", attack_class=clf.attack_class.value,
                                     world=clf.suggested_world, arm=clf.arm_hint, ip_address="9.9.9.9")
    print(f"  attacker receives: status={resp['status']!r} token={resp['token'][:24]}... redirect={resp['redirect']}")
    print(f"  token has NO 'bot_'/'ep_shadow_' prefix: {not resp['token'].startswith(('bot_', 'ep_shadow_'))}")
    recorder.record(session_token=st.session_token, tenant_id=st.tenant_id,
                    attack_class=st.attack_class, event_type="shadow_start", detail={"world": st.world})
    dash = engine.resolve(st.world, st.world_seed, "dashboard")
    accts = engine.resolve(st.world, st.world_seed, "accounts")
    print(f"  shadow dashboard: {dash['greeting']!r}, net_worth=${dash['net_worth']:,}")
    print(f"  shadow accounts : {len(accts['accounts'])} accounts, total=${accts['total_balance']:,}")
    recorder.record(session_token=st.session_token, tenant_id=st.tenant_id,
                    attack_class=st.attack_class, event_type="api_call", detail={"path": "/accounts"})

    # Determinism check: same seed -> same data
    accts2 = engine.resolve(st.world, st.world_seed, "accounts")
    print(f"  deterministic per session (same seed -> same data): {accts == accts2}")

    # ── Scenario 3: Recon ─────────────────────────────────────────────────────
    _hr("SCENARIO 3 - Recon bot -> SHADOW ADMIN")
    sig = AttackSignals(admin_path_hits=4, unique_paths=30, not_found_ratio=0.6,
                        theta=0.03, user_agent="curl/8.1")
    clf = classify(sig)
    print(f"classified: {clf.attack_class.value} ({clf.confidence.value}) -> world={clf.suggested_world}")
    resp, st = injector.mint_success(tenant_id="acme-bank", attack_class=clf.attack_class.value,
                                     world=clf.suggested_world, arm=clf.arm_hint, ip_address="6.6.6.6")
    recorder.record(session_token=st.session_token, tenant_id=st.tenant_id,
                    attack_class=st.attack_class, event_type="shadow_start", detail={"world": st.world})
    users = engine.resolve(st.world, st.world_seed, "users")
    secrets_pg = engine.resolve(st.world, st.world_seed, "secrets")
    print(f"  fake admin users page: {len(users['users'])} users, first={users['users'][0]['email']}")
    print(f"  CANARY secrets exposed: {[s['name'] for s in secrets_pg['secrets']]}")
    recorder.record(session_token=st.session_token, tenant_id=st.tenant_id,
                    attack_class=st.attack_class, event_type="canary_hit", detail={"path": "/admin/secrets"})
    print("  -> attacker 'exfiltrates' canary secrets; any later use is high-fidelity attribution.")

    # ── Scenario 4: Scraper ───────────────────────────────────────────────────
    _hr("SCENARIO 4 - Scraper -> SYNTHETIC DATA FEED")
    sig = AttackSignals(request_rate=25.0, unique_paths=40, theta=0.06,
                        user_agent="Scrapy/2.11")
    clf = classify(sig)
    print(f"classified: {clf.attack_class.value} ({clf.confidence.value}) -> world={clf.suggested_world}")
    resp, st = injector.mint_success(tenant_id="acme-bank", attack_class=clf.attack_class.value,
                                     world=clf.suggested_world, arm=clf.arm_hint, ip_address="7.7.7.7")
    recorder.record(session_token=st.session_token, tenant_id=st.tenant_id,
                    attack_class=st.attack_class, event_type="shadow_start", detail={"world": st.world})
    p1 = engine.resolve(st.world, st.world_seed, "transactions", page=1, page_size=5)
    p2 = engine.resolve(st.world, st.world_seed, "transactions", page=2, page_size=5)
    print(f"  page 1: {len(p1['transactions'])} txns, e.g. {p1['transactions'][0]['merchant']} {p1['transactions'][0]['amount']}")
    print(f"  page 2 differs from page 1 (deep pagination): {p1['transactions'] != p2['transactions']}")
    for _ in range(3):
        recorder.record(session_token=st.session_token, tenant_id=st.tenant_id,
                        attack_class=st.attack_class, event_type="api_call", detail={"path": "/transactions"})

    # ── Anti-fingerprinting demonstration (Feature 6) ─────────────────────────
    _hr("FEATURE 6 - Anti-fingerprinting: decoys vary per session")
    s1 = session_seed("token-AAA", tenant_id="acme-bank", arm=1)
    s2 = session_seed("token-BBB", tenant_id="acme-bank", arm=1)
    d1 = [d.name for d in generate_decoys(s1)]
    d2 = [d.name for d in generate_decoys(s2)]
    d1_again = [d.name for d in generate_decoys(s1)]
    print(f"  session A decoys: {d1}")
    print(f"  session B decoys: {d2}")
    print(f"  A != B (no shared signature): {d1 != d2}")
    print(f"  A == A (stable for verification): {d1 == d1_again}")

    # ── Scenario 5: Threat dashboard ──────────────────────────────────────────
    _hr("SCENARIO 5 - Threat dashboard records attacker activity")
    summary = recorder.summary()
    print(f"  summary: {summary}")
    print("  recent sessions:")
    for s in recorder.sessions(limit=10):
        print(f"    - {s['attack_class']:<20} pages={s['pages_visited']} "
              f"api={s['api_calls']} canary={s['canary_hits']} time={s['time_spent']}s "
              f"token={s['session_token'][:16]}...")
    print(f"  server-side shadow sessions tracked: {len(store.all())}")

    _hr("DEMO COMPLETE - all 5 scenarios + 6 features exercised")


if __name__ == "__main__":
    run_demo()
