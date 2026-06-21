"""/v1 scoring router — full pipeline, telemetry, password hardening, embed."""
from .._clone import clone_matching

TAG = "v1:score"
# Note: /biometric/extract is owned by the `biometric` group (it matches the
# /biometric/ prefix there); excluded here to avoid a duplicate /v1 mirror.
_PATHS = {"/score", "/telemetry", "/password/hash", "/password/verify"}


def matches(path: str) -> bool:
    return path in _PATHS


def make_router(main_module):
    return clone_matching(main_module, matches, TAG)
