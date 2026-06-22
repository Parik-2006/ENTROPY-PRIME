"""
decoy_factory.py — anti-fingerprinting decoy generation (Feature 6)
===================================================================

The legacy Stage 2 emits STATIC decoy field names (`usernmae`, `passwrd`,
`ep_canary_field`) — trivially signature-matched by any bot author who has seen
Entropy Prime once.  This factory replaces them with values that vary:

    • per session   (seeded by session token)
    • per tenant    (tenant id folded into the seed)
    • per attack    (arm / attack-class folded into the seed)

Same seed → same decoys (so the backend can still verify a trigger against the
challenge); different seed → different decoys (so no two sessions share a
signature).

This module is intentionally decoupled from backend.models.stage2_honeypot: it
returns plain dicts, and the Stage-2 builder adapts them into its own
``DecoySpec`` dataclass.  That keeps the existing Stage-2 contract untouched.
"""
from __future__ import annotations

from dataclasses import dataclass

from .._seeded import SeededFaker

# Pools of realistic-but-varied field names.  We mutate/recombine these so the
# concrete `name=` attribute is never a fixed literal across sessions.
_FIELD_STEMS = [
    "email", "mail", "login", "user", "account", "phone", "mobile", "secret",
    "token", "code", "pin", "pass", "credential", "verify", "confirm", "otp",
    "session", "ref", "id", "key",
]
_FIELD_SUFFIXES = ["", "_field", "_input", "_val", "_chk", "_x", "_q", "_ctx", "2", "_id"]
_LABELS = [
    "Email", "Username", "Phone", "Security Code", "Verification", "Account ID",
    "Reference", "One-time Code", "Confirm", "Backup Email", "Recovery Phone",
]
_KINDS = ["input", "input", "input", "button", "checkbox", "link"]  # weighted toward input
_AUTOCOMPLETE = ["email", "username", "current-password", "tel", "one-time-code", "off"]


@dataclass(frozen=True)
class DecoyFieldSpec:
    """Transport-neutral decoy descriptor (adapted by Stage 2 into DecoySpec)."""
    decoy_id:     str
    kind:         str
    name:         str
    label:        str
    autocomplete: str = ""
    tab_index:    int = -1

    def to_dict(self) -> dict:
        return {
            "decoy_id":     self.decoy_id,
            "kind":         self.kind,
            "name":         self.name,
            "label":        self.label,
            "autocomplete": self.autocomplete,
            "tab_index":    self.tab_index,
        }


def session_seed(session_token: str, tenant_id: str = "default", arm: int = -1) -> str:
    """
    Deterministic seed string combining session + tenant + attack arm.

    Folding all three in means the *same* attacker session reproduces the same
    decoys (needed for trigger verification) while differing across sessions,
    tenants, and arms (anti-fingerprint).
    """
    return f"{tenant_id}:{arm}:{session_token}"


def generate_decoys(
    seed: str,
    count: int = 4,
) -> list[DecoyFieldSpec]:
    """
    Generate `count` randomized-but-deterministic decoy field specs from `seed`.

    The number, names, labels, kinds and ordering all vary with the seed, so a
    bot cannot fingerprint Entropy Prime by the decoy structure.
    """
    f = SeededFaker(seed)
    # Even the count wobbles a little so structure isn't fixed.
    n = max(2, count + f.randint(-1, 1))

    specs: list[DecoyFieldSpec] = []
    used_names: set[str] = set()
    for _ in range(n):
        # Build a unique, realistic-looking field name.
        for _attempt in range(8):
            name = f"{f.choice(_FIELD_STEMS)}{f.choice(_FIELD_SUFFIXES)}"
            if name not in used_names:
                used_names.add(name)
                break
        kind = f.choice(_KINDS)
        specs.append(
            DecoyFieldSpec(
                decoy_id     = f.token_like("", 10),     # opaque, no fixed prefix
                kind         = kind,
                name         = name,
                label        = f.choice(_LABELS),
                autocomplete = f.choice(_AUTOCOMPLETE) if kind == "input" else "",
                tab_index    = -1,
            )
        )
    return specs
