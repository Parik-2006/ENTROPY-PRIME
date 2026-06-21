"""/v1 health router — liveness."""
from .._clone import clone_matching

TAG = "v1:health"


def matches(path: str) -> bool:
    return path == "/health"


def make_router(main_module):
    return clone_matching(main_module, matches, TAG)
