"""/v1 honeypot router — MAB reward, decoy trigger, signatures."""
from .._clone import clone_matching

TAG = "v1:honeypot"


def matches(path: str) -> bool:
    # /admin/honeypot/* belongs to the admin group, not here.
    return path.startswith("/honeypot/")


def make_router(main_module):
    return clone_matching(main_module, matches, TAG)
