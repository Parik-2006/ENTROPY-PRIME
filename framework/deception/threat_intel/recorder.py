"""
recorder.py — Threat Intelligence recorder / profiler (Feature 5)
=================================================================

Records what shadow-routed attackers do so the admin dashboard
(ThreatPage.jsx / ThreatIntel.jsx) can display their activity:

    attack type · session · pages visited · decoys triggered · time spent ·
    actions taken

Storage model
-------------
    • ALWAYS keeps a thread-safe in-process ring buffer, so demos and the
      dashboard work even with no database (graceful degradation).
    • OPTIONALLY mirrors into MongoDB via backend.database helpers when an
      async db handle is supplied (production durability).  The Mongo write is
      best-effort and never raises into the request path.

This module is sync and dependency-free; the async Mongo mirroring is done by
the caller (main.py) using the new database.py helpers, keeping this importable
standalone.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AttackerEvent:
    """One recorded interaction in a shadow session."""
    session_token: str
    tenant_id:     str
    attack_class:  str
    event_type:    str           # "shadow_start" | "page_visit" | "decoy_trigger" | "api_call" | "canary_hit"
    detail:        dict = field(default_factory=dict)
    ts:            float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "session_token": self.session_token,
            "tenant_id":     self.tenant_id,
            "attack_class":  self.attack_class,
            "event_type":    self.event_type,
            "detail":        self.detail,
            "ts":            self.ts,
        }


class ThreatIntelRecorder:
    """In-process attacker-activity store with light profiling."""

    def __init__(self, max_events: int = 5000):
        self._lock = threading.Lock()
        self._events: list[AttackerEvent] = []
        self._max = max_events
        # session_token -> rolling summary
        self._sessions: dict[str, dict] = {}

    # ── write ─────────────────────────────────────────────────────────────────
    def record(
        self,
        *,
        session_token: str,
        tenant_id:     str,
        attack_class:  str,
        event_type:    str,
        detail:        Optional[dict] = None,
    ) -> AttackerEvent:
        ev = AttackerEvent(
            session_token = session_token,
            tenant_id     = tenant_id,
            attack_class  = attack_class,
            event_type    = event_type,
            detail        = detail or {},
        )
        with self._lock:
            self._events.append(ev)
            if len(self._events) > self._max:
                self._events = self._events[-self._max:]
            self._update_session(ev)
        return ev

    def _update_session(self, ev: AttackerEvent) -> None:
        s = self._sessions.get(ev.session_token)
        if s is None:
            s = {
                "session_token":   ev.session_token,
                "tenant_id":       ev.tenant_id,
                "attack_class":    ev.attack_class,
                "first_seen":      ev.ts,
                "last_seen":       ev.ts,
                "pages_visited":   0,
                "decoys_triggered": 0,
                "api_calls":       0,
                "canary_hits":     0,
                "actions":         [],
            }
            self._sessions[ev.session_token] = s
        s["last_seen"] = ev.ts
        s["time_spent"] = round(s["last_seen"] - s["first_seen"], 2)
        if ev.event_type == "page_visit":
            s["pages_visited"] += 1
        elif ev.event_type == "decoy_trigger":
            s["decoys_triggered"] += 1
        elif ev.event_type == "api_call":
            s["api_calls"] += 1
        elif ev.event_type == "canary_hit":
            s["canary_hits"] += 1
        # keep a short action trail
        s["actions"].append({"t": round(ev.ts, 2), "type": ev.event_type, "detail": ev.detail})
        s["actions"] = s["actions"][-50:]

    # ── read (for the admin dashboard) ─────────────────────────────────────────
    def sessions(self, limit: int = 100) -> list[dict]:
        with self._lock:
            items = sorted(self._sessions.values(), key=lambda s: s["last_seen"], reverse=True)
            return [dict(s) for s in items[:limit]]

    def events(self, limit: int = 200, session_token: Optional[str] = None) -> list[dict]:
        with self._lock:
            evs = self._events
            if session_token:
                evs = [e for e in evs if e.session_token == session_token]
            return [e.to_dict() for e in evs[-limit:][::-1]]

    def summary(self) -> dict:
        with self._lock:
            by_class: dict[str, int] = defaultdict(int)
            for s in self._sessions.values():
                by_class[s["attack_class"]] += 1
            return {
                "total_sessions": len(self._sessions),
                "total_events":   len(self._events),
                "by_attack_class": dict(by_class),
            }


# ── shared default recorder ───────────────────────────────────────────────────
_RECORDER: Optional[ThreatIntelRecorder] = None


def get_recorder() -> ThreatIntelRecorder:
    global _RECORDER
    if _RECORDER is None:
        _RECORDER = ThreatIntelRecorder()
    return _RECORDER
