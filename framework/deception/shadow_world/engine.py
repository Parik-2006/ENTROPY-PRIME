"""
engine.py — Shadow World Engine
===============================

A generic, industry-agnostic resolver.  Given a world id (e.g. "banking"), a
per-session ``world_seed`` and an asset name (e.g. "transactions"), it returns
realistic synthetic JSON.

Determinism contract
---------------------
    resolve(world, seed, asset, **params) is a PURE function of its arguments.
    The same (world, seed, asset, params) always yields the same data, so an
    attacker exploring the world sees a consistent, self-referential place — no
    flicker that would reveal generation.

Extensibility
-------------
    Register any number of ``IndustryProfile`` instances.  The MVP wires
    Banking + ShadowAdmin in ``get_engine()``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .._seeded import SeededFaker


class IndustryProfile(ABC):
    """Base class for a synthetic-environment generator."""

    #: world id used in routing (must be unique across registered profiles)
    world_id: str = "generic"

    @abstractmethod
    def assets(self) -> list[str]:
        """List of asset names this profile can serve (for menus/dashboards)."""

    @abstractmethod
    def resolve(self, faker: SeededFaker, asset: str, **params) -> dict:
        """Return synthetic JSON for ``asset`` using the seeded ``faker``."""

    # Helper: stable per-(seed, asset) faker so different assets in the same
    # world don't all reuse the identical RNG stream, while staying
    # deterministic.
    def _faker_for(self, world_seed: str, asset: str) -> SeededFaker:
        return SeededFaker(f"{self.world_id}:{world_seed}:{asset}")


class ShadowWorldEngine:
    """Registry + dispatcher over IndustryProfiles."""

    def __init__(self):
        self._profiles: dict[str, IndustryProfile] = {}

    def register(self, profile: IndustryProfile) -> None:
        self._profiles[profile.world_id] = profile

    def worlds(self) -> list[str]:
        return list(self._profiles.keys())

    def has_world(self, world: str) -> bool:
        return world in self._profiles

    def assets(self, world: str) -> list[str]:
        profile = self._profiles.get(world)
        return profile.assets() if profile else []

    def resolve(self, world: str, world_seed: str, asset: str, **params) -> dict:
        """
        Resolve one asset.  Raises KeyError for an unknown world so the caller
        (API layer) can translate it into a believable 404 *inside* the world
        rather than leaking that the world doesn't exist.
        """
        profile = self._profiles.get(world)
        if profile is None:
            raise KeyError(f"unknown world: {world}")
        faker = profile._faker_for(world_seed, asset)
        return profile.resolve(faker, asset, **params)


# ── shared default engine ─────────────────────────────────────────────────────
_ENGINE: Optional[ShadowWorldEngine] = None


def get_engine() -> ShadowWorldEngine:
    """Lazily build the MVP engine with Banking + ShadowAdmin registered."""
    global _ENGINE
    if _ENGINE is None:
        from .banking import BankingProfile
        from .shadow_admin import ShadowAdminProfile
        eng = ShadowWorldEngine()
        eng.register(BankingProfile())
        eng.register(ShadowAdminProfile())
        _ENGINE = eng
    return _ENGINE
