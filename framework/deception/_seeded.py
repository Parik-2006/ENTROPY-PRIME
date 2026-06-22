"""
_seeded.py — deterministic synthetic-data primitives (stdlib only)
==================================================================

A tiny, dependency-free "faker".  Everything is driven by a per-session seed so
that:

    same seed  → identical synthetic world (consistency across requests)
    diff seed  → completely different world (no repeated fake data, #anti-corr)

We deliberately avoid the third-party `Faker` package to honour the MVP Docker
constraint (no new dependencies).  The curated word lists below are small but
combinatorially large enough that two sessions practically never collide.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

_FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen", "Aisha",
    "Wei", "Priya", "Diego", "Fatima", "Yuki", "Omar", "Sofia", "Liam", "Nadia",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Khan",
    "Chen", "Patel", "Nguyen", "Kim", "Okafor", "Rossi", "Haddad", "Novak",
]
_STREETS = [
    "Maple Ave", "Oak St", "Pine Rd", "Cedar Ln", "Elm St", "Park Blvd",
    "Sunset Dr", "Lakeview Ct", "Highland Way", "Riverside Dr", "Market St",
]
_CITIES = [
    "Springfield", "Riverton", "Fairview", "Lakewood", "Georgetown",
    "Bristol", "Clinton", "Franklin", "Greenville", "Madison", "Ashford",
]
_BANKS = [
    "First National", "Meridian Trust", "Coastal Federal", "Summit Bank",
    "Pioneer Credit Union", "Atlas Financial", "Cornerstone Bank",
]
_MERCHANTS = [
    "Amazon", "Whole Foods", "Shell", "Netflix", "Uber", "Starbucks",
    "Apple Store", "Target", "Spotify", "Delta Air Lines", "IKEA", "Costco",
    "Steam", "DoorDash", "Home Depot", "CVS Pharmacy", "Best Buy",
]
_TXN_TYPES = ["debit", "credit", "transfer", "payment", "withdrawal", "deposit"]
_ROLES = ["admin", "manager", "analyst", "support", "auditor", "viewer"]
_LOG_ACTIONS = [
    "login.success", "login.failed", "password.reset", "role.changed",
    "config.updated", "export.csv", "user.created", "user.suspended",
    "api_key.rotated", "session.revoked",
]
_WORDS = [
    "report", "summary", "invoice", "ledger", "audit", "policy", "contract",
    "statement", "forecast", "minutes", "proposal", "roadmap", "budget",
]


class SeededFaker:
    """Deterministic generator keyed by an arbitrary seed value."""

    def __init__(self, seed):
        # Hash the seed to a stable 64-bit int so strings/ints both work.
        h = hashlib.sha256(str(seed).encode()).hexdigest()
        self._rng = random.Random(int(h[:16], 16))

    # ── primitives ──────────────────────────────────────────────────────────
    def choice(self, seq):
        return self._rng.choice(seq)

    def randint(self, a, b):
        return self._rng.randint(a, b)

    def boolean(self, p_true: float = 0.5) -> bool:
        return self._rng.random() < p_true

    def amount(self, lo: float = 1.0, hi: float = 5000.0) -> float:
        """
        Log-uniform amount: realistic spread across the whole [lo, hi] range
        (most values small, a few large) without piling up at the bounds the
        way a clamped log-normal does.
        """
        import math
        lo = max(0.01, lo)
        u = self._rng.uniform(math.log(lo), math.log(hi))
        return round(math.exp(u), 2)

    # ── identity ──────────────────────────────────────────────────────────────
    def first_name(self) -> str:
        return self.choice(_FIRST_NAMES)

    def last_name(self) -> str:
        return self.choice(_LAST_NAMES)

    def full_name(self) -> str:
        return f"{self.first_name()} {self.last_name()}"

    def email(self, name: str | None = None) -> str:
        if name is None:
            name = self.full_name()
        user = name.lower().replace(" ", ".")
        domain = self.choice(["gmail.com", "outlook.com", "proton.me", "yahoo.com", "icloud.com"])
        return f"{user}{self.randint(1, 99)}@{domain}"

    def phone(self) -> str:
        return f"+1-{self.randint(200, 989)}-{self.randint(200, 999)}-{self.randint(1000, 9999)}"

    def address(self) -> str:
        return f"{self.randint(10, 9999)} {self.choice(_STREETS)}, {self.choice(_CITIES)}"

    def ssn_masked(self) -> str:
        return f"***-**-{self.randint(1000, 9999)}"

    # ── banking ───────────────────────────────────────────────────────────────
    def account_number(self) -> str:
        return "".join(str(self.randint(0, 9)) for _ in range(12))

    def iban(self) -> str:
        return f"GB{self.randint(10, 99)}{self.choice(['BARC','HBUK','NWBK','LOYD'])}{self.randint(10**13, 10**14 - 1)}"

    def bank(self) -> str:
        return self.choice(_BANKS)

    def merchant(self) -> str:
        return self.choice(_MERCHANTS)

    def txn_type(self) -> str:
        return self.choice(_TXN_TYPES)

    # ── admin ──────────────────────────────────────────────────────────────────
    def role(self) -> str:
        return self.choice(_ROLES)

    def log_action(self) -> str:
        return self.choice(_LOG_ACTIONS)

    def word(self) -> str:
        return self.choice(_WORDS)

    def ipv4(self) -> str:
        return ".".join(str(self.randint(1, 254)) for _ in range(4))

    # ── time ───────────────────────────────────────────────────────────────────
    def past_datetime(self, max_days: int = 365) -> datetime:
        delta = timedelta(
            days    = self.randint(0, max_days),
            hours   = self.randint(0, 23),
            minutes = self.randint(0, 59),
        )
        return datetime.utcnow() - delta

    def token_like(self, prefix: str, n: int = 32) -> str:
        body = "".join(self._rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") for _ in range(n))
        return f"{prefix}{body}"
