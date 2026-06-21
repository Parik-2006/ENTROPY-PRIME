"""/v1 admin router — model status, onboarding summary, pipeline debug, dashboards."""
from .._clone import clone_matching

TAG = "v1:admin"


def matches(path: str) -> bool:
    return path.startswith("/admin/")


def make_router(main_module):
    return clone_matching(main_module, matches, TAG)
