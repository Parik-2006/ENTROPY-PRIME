"""/v1 auth router — register, login, logout, current user."""
from .._clone import clone_matching

TAG = "v1:auth"
_PATHS = {"/auth/register", "/auth/login", "/auth/logout", "/me"}


def matches(path: str) -> bool:
    return path in _PATHS


def make_router(main_module):
    return clone_matching(main_module, matches, TAG)
