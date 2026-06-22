"""
shadow_admin.py — Shadow Admin Environment (Feature 3, "Arm 3")
===============================================================

Recon / admin-discovery attackers are routed here.  It is the highest-value
bait: a fully-furnished but entirely synthetic admin console.

Assets:
    users      fake user-management table (roles, last login, "PII")
    logs       fake audit log (login events, config changes, IPs)
    analytics  fake KPIs / revenue / traffic
    config     fake feature flags, integrations, SMTP settings
    secrets    fake API keys / tokens — these are CANARY tokens.  Any later use
               of an exfiltrated secret is a high-fidelity exploitation signal
               (the attribution hook described in the Phase-3 architecture).

Everything is seeded for per-session consistency and per-session uniqueness.
"""
from __future__ import annotations

from datetime import datetime

from .engine import IndustryProfile
from .._seeded import SeededFaker


class ShadowAdminProfile(IndustryProfile):
    world_id = "shadow_admin"

    def assets(self) -> list[str]:
        return ["dashboard", "users", "logs", "analytics", "config", "secrets"]

    def resolve(self, faker: SeededFaker, asset: str, **params) -> dict:
        if asset == "dashboard":
            return self._dashboard(faker)
        if asset == "users":
            return self._users(faker, **params)
        if asset == "logs":
            return self._logs(faker, **params)
        if asset == "analytics":
            return self._analytics(faker)
        if asset == "config":
            return self._config(faker)
        if asset == "secrets":
            return self._secrets(faker)
        return {"asset": asset, "items": []}

    # ── assets ──────────────────────────────────────────────────────────────
    def _dashboard(self, f: SeededFaker) -> dict:
        return {
            "system":        f.choice(["prod-cluster-1", "prod-eu-west", "primary"]),
            "status":        "healthy",
            "active_users":  f.randint(120, 9000),
            "open_tickets":  f.randint(2, 80),
            "uptime_days":   f.randint(30, 700),
            "version":       f"{f.randint(2,5)}.{f.randint(0,9)}.{f.randint(0,30)}",
            "generated_at":  datetime.utcnow().isoformat() + "Z",
        }

    def _users(self, f: SeededFaker, page: int = 1, page_size: int = 20, **_) -> dict:
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        pf = SeededFaker(f"admin:users:{page}:{page_size}:{f.randint(0, 10**9)}")
        users = []
        for _ in range(page_size):
            name = pf.full_name()
            users.append({
                "user_id":    pf.token_like("usr_", 12),
                "name":       name,
                "email":      pf.email(name),
                "role":       pf.role(),
                "status":     pf.choice(["active", "active", "active", "suspended", "invited"]),
                "last_login": pf.past_datetime(60).strftime("%Y-%m-%d %H:%M"),
                "mfa":        pf.boolean(0.7),
            })
        return {"page": page, "page_size": page_size, "users": users, "has_more": True}

    def _logs(self, f: SeededFaker, page: int = 1, page_size: int = 30, **_) -> dict:
        page = max(1, int(page))
        page_size = min(200, max(1, int(page_size)))
        pf = SeededFaker(f"admin:logs:{page}:{page_size}:{f.randint(0, 10**9)}")
        logs = []
        for _ in range(page_size):
            logs.append({
                "ts":      pf.past_datetime(14).isoformat() + "Z",
                "actor":   pf.email(),
                "action":  pf.log_action(),
                "ip":      pf.ipv4(),
                "result":  pf.choice(["ok", "ok", "ok", "denied"]),
            })
        return {"page": page, "page_size": page_size, "logs": logs, "has_more": True}

    def _analytics(self, f: SeededFaker) -> dict:
        months = []
        for i in range(12):
            months.append({
                "month":   f"2025-{i+1:02d}",
                "revenue": f.amount(20000, 900000),
                "signups": f.randint(50, 4000),
                "churn":   round(f.randint(1, 12) / 100, 3),
            })
        return {"revenue_series": months, "mrr": f.amount(40000, 800000),
                "active_subscriptions": f.randint(500, 50000)}

    def _config(self, f: SeededFaker) -> dict:
        return {
            "feature_flags": {
                "new_billing":     f.boolean(0.5),
                "beta_dashboard":  f.boolean(0.5),
                "sso_enforced":    f.boolean(0.7),
                "rate_limiting":   True,
            },
            "integrations": {
                "smtp_host":   f.choice(["smtp.sendgrid.net", "smtp.mailgun.org", "email-smtp.us-east-1.amazonaws.com"]),
                "smtp_user":   f.token_like("SMTP_", 10),
                "webhook_url": f"https://hooks.{f.word()}.example.com/{f.token_like('', 8)}",
                "s3_bucket":   f"{f.word()}-prod-assets",
            },
            "regions": f.choice([["us-east-1", "eu-west-1"], ["us-west-2"], ["eu-central-1", "ap-south-1"]]),
        }

    def _secrets(self, f: SeededFaker) -> dict:
        """
        CANARY secrets.  Formats mimic real provider keys so an attacker
        believes they struck gold.  Each value is a tracked honeytoken.
        """
        return {
            "warning": "Rotate these regularly.",
            "secrets": [
                {"name": "AWS_ACCESS_KEY_ID",     "value": "AKIA" + f.token_like("", 16).upper(), "canary": True},
                {"name": "AWS_SECRET_ACCESS_KEY", "value": f.token_like("", 40),                   "canary": True},
                {"name": "STRIPE_SECRET_KEY",     "value": "sk_live_" + f.token_like("", 24),      "canary": True},
                {"name": "DATABASE_URL",          "value": f"postgres://admin:{f.token_like('', 12)}@db.internal:5432/prod", "canary": True},
                {"name": "JWT_SIGNING_KEY",       "value": f.token_like("", 48),                   "canary": True},
            ],
        }
