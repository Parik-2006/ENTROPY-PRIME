"""/v1 integration router — webhooks + notifications (the Integration API)."""
from .._clone import clone_matching

TAG = "v1:integration"


def matches(path: str) -> bool:
    return path.startswith("/webhooks") or path.startswith("/notifications")


def make_router(main_module):
    return clone_matching(main_module, matches, TAG)
