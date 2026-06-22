"""
banking.py — Banking Shadow World (Feature 4)
=============================================

Generates a complete, self-consistent synthetic banking environment for a
shadow session:

    accounts · transactions · beneficiaries · statements · customer profile

Everything is seeded, so:
    same session  → same accounts / transactions / beneficiaries
    diff session  → an entirely different (but equally plausible) bank

Nothing is hardcoded; amounts follow a log-normal-ish curve and timestamps
follow recent history so the data passes a casual sniff test.
"""
from __future__ import annotations

from datetime import datetime

from .engine import IndustryProfile
from .._seeded import SeededFaker


class BankingProfile(IndustryProfile):
    world_id = "banking"

    def assets(self) -> list[str]:
        return ["dashboard", "accounts", "transactions", "beneficiaries",
                "statements", "profile"]

    def resolve(self, faker: SeededFaker, asset: str, **params) -> dict:
        if asset == "dashboard":
            return self._dashboard(faker)
        if asset == "accounts":
            return self._accounts(faker)
        if asset == "transactions":
            return self._transactions(faker, **params)
        if asset == "beneficiaries":
            return self._beneficiaries(faker)
        if asset == "statements":
            return self._statements(faker)
        if asset == "profile":
            return self._profile(faker)
        # Unknown asset inside a known world → empty-but-valid shape, never an
        # error that would reveal the boundary.
        return {"asset": asset, "items": []}

    # ── assets ──────────────────────────────────────────────────────────────
    def _profile(self, f: SeededFaker) -> dict:
        name = f.full_name()
        return {
            "customer": {
                "name":     name,
                "email":    f.email(name),
                "phone":    f.phone(),
                "address":  f.address(),
                "ssn":      f.ssn_masked(),
                "customer_since": f.past_datetime(2000).strftime("%Y-%m-%d"),
                "tier":     f.choice(["Standard", "Gold", "Platinum", "Private"]),
            }
        }

    def _accounts(self, f: SeededFaker) -> dict:
        n = f.randint(2, 4)
        kinds = ["Checking", "Savings", "Credit Card", "Money Market", "Brokerage"]
        accounts = []
        for i in range(n):
            accounts.append({
                "account_id":   f.account_number(),
                "type":         kinds[i % len(kinds)],
                "bank":         f.bank(),
                "balance":      f.amount(50, 250000),
                "currency":     "USD",
                "iban":         f.iban(),
                "status":       "active",
            })
        return {"accounts": accounts, "total_balance": round(sum(a["balance"] for a in accounts), 2)}

    def _transactions(self, f: SeededFaker, page: int = 1, page_size: int = 20, **_) -> dict:
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        # Re-seed per page so pagination is stable & deep (no boundary wall).
        pf = SeededFaker(f"{id(self)}:txn:{page}:{page_size}:{f.randint(0, 10**9)}")
        items = []
        for _ in range(page_size):
            amt = pf.amount(1, 8000)
            ttype = pf.txn_type()
            items.append({
                "txn_id":      pf.token_like("txn_", 16),
                "date":        pf.past_datetime(180).strftime("%Y-%m-%d %H:%M"),
                "merchant":    pf.merchant(),
                "type":        ttype,
                "amount":      amt if ttype in ("credit", "deposit") else -amt,
                "status":      pf.choice(["posted", "posted", "posted", "pending"]),
                "category":    pf.choice(["Groceries", "Travel", "Dining", "Utilities",
                                          "Entertainment", "Transfer", "Income"]),
            })
        return {"page": page, "page_size": page_size, "transactions": items, "has_more": True}

    def _beneficiaries(self, f: SeededFaker) -> dict:
        n = f.randint(2, 6)
        beneficiaries = []
        for _ in range(n):
            name = f.full_name()
            beneficiaries.append({
                "beneficiary_id": f.token_like("ben_", 12),
                "name":           name,
                "bank":           f.bank(),
                "account_number": f.account_number(),
                "nickname":       f.choice(["Mom", "Rent", "Landlord", "Savings", "Business", name.split()[0]]),
                "last_transfer":  f.past_datetime(90).strftime("%Y-%m-%d"),
            })
        return {"beneficiaries": beneficiaries}

    def _statements(self, f: SeededFaker) -> dict:
        n = f.randint(6, 12)
        statements = []
        for _ in range(n):
            dt = f.past_datetime(365)
            statements.append({
                "statement_id": f.token_like("stmt_", 12),
                "period":       dt.strftime("%Y-%m"),
                "opening":      f.amount(100, 50000),
                "closing":      f.amount(100, 50000),
                "document":     f"{dt.strftime('%Y-%m')}-statement.pdf",
            })
        return {"statements": statements}

    def _dashboard(self, f: SeededFaker) -> dict:
        name = f.full_name()
        return {
            "greeting":      f"Welcome back, {name.split()[0]}",
            "net_worth":     f.amount(1000, 500000),
            "accounts_count": f.randint(2, 4),
            "pending_count":  f.randint(0, 5),
            "alerts": [
                {"type": "info", "text": "Your monthly statement is ready."},
                {"type": "info", "text": f"Payment to {f.merchant()} scheduled."},
            ],
            "generated_at":  datetime.utcnow().isoformat() + "Z",
        }
