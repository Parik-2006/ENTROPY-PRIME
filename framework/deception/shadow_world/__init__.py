"""
framework.deception.shadow_world — synthetic environments (Features 3 & 4)

Generic engine + pluggable IndustryProfile generators.  MVP ships:
    • BankingProfile      (Feature 4)  world id "banking"
    • ShadowAdminProfile  (Feature 3)  world id "shadow_admin"

Adding E-Commerce / Healthcare / SaaS later = add a new IndustryProfile and
register it.  No engine changes required.
"""
from .engine import ShadowWorldEngine, IndustryProfile, get_engine
from .banking import BankingProfile
from .shadow_admin import ShadowAdminProfile

__all__ = [
    "ShadowWorldEngine",
    "IndustryProfile",
    "BankingProfile",
    "ShadowAdminProfile",
    "get_engine",
]
