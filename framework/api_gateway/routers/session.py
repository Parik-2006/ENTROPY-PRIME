"""/v1 session router — continuous-auth heartbeat + trust gate."""
from .._clone import clone_matching

TAG = "v1:session"


def matches(path: str) -> bool:
    return path.startswith("/session/")


def make_router(main_module):
    return clone_matching(main_module, matches, TAG)
