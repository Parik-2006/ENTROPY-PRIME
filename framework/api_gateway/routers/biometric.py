"""/v1 biometric router — profile-build state machine + Stage 1 analytics."""
from .._clone import clone_matching

TAG = "v1:biometric"


def matches(path: str) -> bool:
    return (
        path.startswith("/biometric/")
        or path.startswith("/stage1/")
        or path == "/analyze"
    )


def make_router(main_module):
    return clone_matching(main_module, matches, TAG)
