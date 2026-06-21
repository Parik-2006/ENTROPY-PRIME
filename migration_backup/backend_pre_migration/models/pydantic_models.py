"""
models/pydantic_models.py  —  Pydantic API-Boundary Models

These models live at the HTTP edge.  They own:
  • Input validation and type coercion for incoming JSON.
  • Response serialisation shape (camelCase aliases where needed).
  • Field-level documentation that surfaces in the OpenAPI schema.

They deliberately do NOT inherit from the internal dataclasses in contracts.py.
The two layers are decoupled so the API contract can evolve independently of
the internal pipeline contracts, and vice-versa.

Conversion helpers (to_dataclass / from_dataclass) bridge the two worlds at
the service boundary.

Requires pydantic >= 2.0.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator, EmailStr


# ────────────────────────────────────────────────────────────────────────────
# Authentication models (added to satisfy imports in backend/main.py)
# ────────────────────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    email: EmailStr
    plain_password: str

    class Config:
        json_schema_extra = {
            "example": {"email": "user@example.com", "plain_password": "securepassword123"}
        }


class UserLogin(BaseModel):
    email: EmailStr
    plain_password: str



# ── Enums (re-declared as plain strings for Pydantic — avoids circular imports)

_VALID_GOVERNOR_ACTIONS = {"allow", "log", "challenge", "block"}
_VALID_SECURITY_PRESETS = {"economy", "standard", "hard", "punisher"}


# ── Tenant Policy ─────────────────────────────────────────────────────────────

class TenantPolicyCreate(BaseModel):
    """
    Request body for POST /tenants/{site_id}/policy

    All fields except site_id are optional; omitted fields keep their current
    stored value (PATCH semantics when used with the update endpoint).
    """
    risk_tolerance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Risk tolerance in [0, 1].  "
            "0 = paranoid (block / challenge everything borderline).  "
            "1 = permissive (only act on definite bots).  "
            "Controls both PPO reward shaping and the hard action floor/ceiling."
        ),
    )
    min_action: str = Field(
        default="allow",
        description=(
            "Minimum behavioral action the PPO may choose for this tenant.  "
            "One of: allow | log | challenge | block.  "
            "Setting 'log' guarantees every evaluation is audited."
        ),
    )
    max_preset: str = Field(
        default="punisher",
        description=(
            "Maximum Argon2id preset allowed for this tenant (resource cap).  "
            "One of: economy | standard | hard | punisher."
        ),
    )
    challenge_on_suspect: bool = Field(
        default=True,
        description=(
            "If true, SUSPECT biometric verdicts always produce at least a "
            "CHALLENGE action, regardless of risk_tolerance."
        ),
    )
    block_bots_hard: bool = Field(
        default=True,
        description=(
            "If true, BOT verdicts always produce BLOCK, regardless of "
            "risk_tolerance.  Set false only for honeypot / observation tenants."
        ),
    )

    @field_validator("min_action")
    @classmethod
    def validate_min_action(cls, v: str) -> str:
        v = v.lower()
        if v not in _VALID_GOVERNOR_ACTIONS:
            raise ValueError(f"min_action must be one of {_VALID_GOVERNOR_ACTIONS}")
        return v

    @field_validator("max_preset")
    @classmethod
    def validate_max_preset(cls, v: str) -> str:
        v = v.lower()
        if v not in _VALID_SECURITY_PRESETS:
            raise ValueError(f"max_preset must be one of {_VALID_SECURITY_PRESETS}")
        return v

    def to_dataclass(self, site_id: str):
        """Convert to the internal TenantPolicy dataclass."""
        from .contracts import GovernorAction, SecurityPreset, TenantPolicy
        return TenantPolicy(
            site_id              = site_id,
            risk_tolerance       = self.risk_tolerance,
            min_action           = GovernorAction(self.min_action),
            max_preset           = SecurityPreset(self.max_preset),
            challenge_on_suspect = self.challenge_on_suspect,
            block_bots_hard      = self.block_bots_hard,
        )


class TenantPolicyUpdate(TenantPolicyCreate):
    """
    Request body for PATCH /tenants/{site_id}/policy

    All fields are optional; only supplied fields are updated.
    """
    risk_tolerance:       Optional[float] = None   # type: ignore[assignment]
    min_action:           Optional[str]   = None   # type: ignore[assignment]
    max_preset:           Optional[str]   = None   # type: ignore[assignment]
    challenge_on_suspect: Optional[bool]  = None   # type: ignore[assignment]
    block_bots_hard:      Optional[bool]  = None   # type: ignore[assignment]

    @field_validator("min_action", mode="before")
    @classmethod
    def validate_min_action_optional(cls, v):
        if v is None:
            return v
        v = v.lower()
        if v not in _VALID_GOVERNOR_ACTIONS:
            raise ValueError(f"min_action must be one of {_VALID_GOVERNOR_ACTIONS}")
        return v

    @field_validator("max_preset", mode="before")
    @classmethod
    def validate_max_preset_optional(cls, v):
        if v is None:
            return v
        v = v.lower()
        if v not in _VALID_SECURITY_PRESETS:
            raise ValueError(f"max_preset must be one of {_VALID_SECURITY_PRESETS}")
        return v

    def apply_to_dataclass(self, existing):
        """
        Merge non-None fields from this update onto an existing TenantPolicy
        dataclass.  Returns a new dataclass instance (dataclasses are mutable
        but this makes the intent explicit).
        """
        from .contracts import GovernorAction, SecurityPreset, TenantPolicy
        return TenantPolicy(
            site_id = existing.site_id,
            risk_tolerance = (
                self.risk_tolerance
                if self.risk_tolerance is not None
                else existing.risk_tolerance
            ),
            min_action = (
                GovernorAction(self.min_action)
                if self.min_action is not None
                else existing.min_action
            ),
            max_preset = (
                SecurityPreset(self.max_preset)
                if self.max_preset is not None
                else existing.max_preset
            ),
            challenge_on_suspect = (
                self.challenge_on_suspect
                if self.challenge_on_suspect is not None
                else existing.challenge_on_suspect
            ),
            block_bots_hard = (
                self.block_bots_hard
                if self.block_bots_hard is not None
                else existing.block_bots_hard
            ),
        )


class TenantPolicyResponse(BaseModel):
    """Response body for GET/POST/PATCH /tenants/{site_id}/policy"""
    site_id:              str
    risk_tolerance:       float
    min_action:           str
    max_preset:           str
    challenge_on_suspect: bool
    block_bots_hard:      bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_dataclass(cls, policy) -> "TenantPolicyResponse":
        """Convert from the internal TenantPolicy dataclass."""
        return cls(
            site_id              = policy.site_id,
            risk_tolerance       = policy.risk_tolerance,
            min_action           = policy.min_action.value,
            max_preset           = policy.max_preset.value,
            challenge_on_suspect = policy.challenge_on_suspect,
            block_bots_hard      = policy.block_bots_hard,
        )


# ── Governor Evaluate Request ─────────────────────────────────────────────────

class GovernorEvaluateRequest(BaseModel):
    """
    Request body for POST /governor/evaluate

    The site_id is used to load the tenant's TenantPolicy before running
    Stage 3.  All other fields mirror the BiometricResult fields that Stage 3
    consumes.
    """
    site_id:     str   = Field(..., description="Tenant identifier")
    user_id:     str   = Field(..., description="End-user identifier (opaque)")
    theta:       float = Field(..., ge=0.0, le=1.0, description="Humanity score")
    h_exp:       float = Field(..., ge=0.0, le=1.0, description="Entropy signal")
    server_load: float = Field(default=0.0, ge=0.0, le=1.0)
    verdict:     str   = Field(..., description="HoneypotVerdict from Stage 1")
    confidence:  str   = Field(..., description="Confidence from Stage 1")
    is_bot:      bool  = False
    is_suspect:  bool  = False

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, v: str) -> str:
        valid = {"bot", "suspect", "human", "learning"}
        if v.lower() not in valid:
            raise ValueError(f"verdict must be one of {valid}")
        return v.lower()

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: str) -> str:
        valid = {"high", "medium", "low"}
        if v.lower() not in valid:
            raise ValueError(f"confidence must be one of {valid}")
        return v.lower()

    @model_validator(mode="after")
    def validate_verdict_flags_consistency(self) -> "GovernorEvaluateRequest":
        if self.is_bot and self.verdict != "bot":
            raise ValueError("is_bot=True requires verdict='bot'")
        if self.is_suspect and self.verdict != "suspect":
            raise ValueError("is_suspect=True requires verdict='suspect'")
        return self


class GovernorEvaluateResponse(BaseModel):
    """Response body for POST /governor/evaluate"""
    # Argon2id params
    action:      int
    preset:      str
    memory_kb:   int
    time_cost:   int
    parallelism: int

    # PPO behavioral decision
    governor_action: str
    confidence:      str
    fallback:        bool
    policy_applied:  Optional[str]

    @classmethod
    def from_result(cls, result) -> "GovernorEvaluateResponse":
        """Convert from GovernorResult dataclass."""
        return cls(
            action          = result.action,
            preset          = result.preset.value,
            memory_kb       = result.memory_kb,
            time_cost       = result.time_cost,
            parallelism     = result.parallelism,
            governor_action = result.governor_action.value if result.governor_action else "allow",
            confidence      = result.confidence.value,
            fallback        = result.fallback,
            policy_applied  = result.policy_applied,
        )