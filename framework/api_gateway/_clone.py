"""
framework.api_gateway._clone — faithful route mirroring
=======================================================

Builds a ``/v1``-prefixed APIRouter that mirrors a subset of the existing
application's routes WITHOUT re-declaring any handler, dependency, response
model, or status code. Each mirrored route points at the *same* endpoint
callable the original route uses, so behavior is identical by construction.

This is the mechanism that lets us "create routers" (organized, resource-
grouped, framework-style) while keeping ``backend/main.py`` as the single
source of truth for the handlers (compatibility layer). Old routes are never
touched; only new ``/v1`` aliases are added.
"""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter
from fastapi.routing import APIRoute

V1_PREFIX = "/v1"

_SKIP_METHODS = {"HEAD", "OPTIONS"}


def _safe_name(path: str, methods: list[str]) -> str:
    base = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"v1_{'_'.join(sorted(methods)).lower()}_{base or 'root'}"


def clone_matching(main_module, predicate: Callable[[str], bool], tag: str) -> APIRouter:
    """
    Return an APIRouter (prefix=/v1) mirroring every ``APIRoute`` on
    ``main_module.app`` whose path satisfies ``predicate``.

    The original handler object is reused verbatim, so FastAPI re-derives the
    exact same dependency graph (session guard, API-key, Pydantic bodies) for
    the alias. Response model / status code are copied from the source route.
    """
    app = main_module.app
    router = APIRouter(prefix=V1_PREFIX, tags=[tag])

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path.startswith(V1_PREFIX):
            continue  # never mirror an alias of an alias
        if not predicate(route.path):
            continue

        methods = [m for m in (route.methods or set()) if m not in _SKIP_METHODS]
        if not methods:
            continue

        router.add_api_route(
            path=route.path,                                  # -> /v1 + path
            endpoint=route.endpoint,                          # same callable
            methods=methods,
            response_model=getattr(route, "response_model", None),
            status_code=route.status_code,
            summary=getattr(route, "summary", None),
            name=_safe_name(route.path, methods),
            include_in_schema=True,
        )

    return router
