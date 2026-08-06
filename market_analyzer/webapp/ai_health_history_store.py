"""
Phase 10.4 Goal 3 — AI Health History Store.

Purely additive, new file. Does NOT modify validation_history_store.py,
learning_engine.py, or ai_health_engine.py — it mirrors
validation_history_store.py's exact I/O pattern (one JSON file,
read-whole/write-whole, atomic on write, corrupted-JSON recovery, bounded
most-recent-first list) applied to a new, independent concern: a rolling
log of past compute_ai_health() snapshots, so the dashboard can show how
system health has changed over time instead of only "right now".

This module has no import of ai_health_engine.py and never computes a
health snapshot itself — it only ever stores/returns whatever dict its
caller (webapp/app.py) already built via compute_ai_health(). Same
decoupling convention validation_history_store.py's own docstring
establishes for its relationship with ValidationEngine.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA_VERSION = "1.0"

# Bounds the stored log so this file can't grow unbounded — same intent as
# validation_history_store.MAX_RUN_LOG_ENTRIES / learning_engine.
# MAX_RECOMMENDATION_LOG_ENTRIES, sized larger here since health snapshots
# are expected to accumulate at a steady polling cadence (see
# webapp/app.py's throttle) rather than once per manual validation run.
MAX_SNAPSHOT_ENTRIES = 2000


def _now() -> float:
    return time.time()


def _iso(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else _now()))


def _default_history() -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "snapshots": []}


def _deep_merge_missing(data: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Same forward-compatibility technique validation_history_store.py /
    learning_engine.py use (reimplemented independently here, not
    imported — this module operates on its own, different schema)."""
    merged = dict(data)
    for key, default_value in defaults.items():
        if key not in merged:
            merged[key] = default_value
        elif isinstance(default_value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_missing(merged[key], default_value)
    return merged


class AIHealthHistoryStore:
    """
    One JSON file, read-whole/write-whole, atomic on write — same pattern
    as validation_history_store.ValidationHistoryStore /
    learning_engine.LearningHistoryStore. No locking (same single-run
    assumption the rest of this codebase's stores already make).
    """

    def __init__(self, path: str):
        self.path = Path(path)
        if not self.path.exists():
            self._write(_default_history())

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = _default_history()
            self._write(data)
            return data
        defaults = _default_history()
        merged = _deep_merge_missing(data, defaults)
        if not isinstance(merged.get("snapshots"), list):
            merged["snapshots"] = []
        if merged != data:
            self._write(merged)
        return merged

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(self.path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)  # atomic on POSIX — avoids a torn write

    # ── Public API ───────────────────────────────────────────────────────────
    def get_history(self) -> Dict[str, Any]:
        """Full stored snapshot log (most recent first)."""
        return self._read()

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """The single most recently recorded snapshot, or None if the log is empty."""
        snapshots = self._read().get("snapshots") or []
        return snapshots[0] if snapshots else None

    def record_snapshot(self, health_snapshot: Dict[str, Any],
                         timestamp: Optional[str] = None) -> Dict[str, Any]:
        """
        Records ONE compute_ai_health() output dict as-is (this store
        never recomputes or reinterprets it — pure accumulation, same
        convention validation_history_store.record_run() and
        learning_engine.LearningHistoryStore.record_recommendation()
        already follow). Appends to the bounded, most-recent-first log.
        Returns the updated full history (same shape as get_history()).
        """
        data = self._read()
        ts = timestamp or _iso()
        data["snapshots"].insert(0, {"timestamp": ts, "health": health_snapshot})
        data["snapshots"] = data["snapshots"][:MAX_SNAPSHOT_ENTRIES]
        self._write(data)
        return data

    def reset(self) -> Dict[str, Any]:
        """Explicit, user-initiated only (never called automatically) —
        wipes the snapshot log back to empty. Does NOT touch
        validation_history_store.py's or learning_engine.py's data — this
        only ever resets this module's own snapshot log."""
        defaults = _default_history()
        self._write(defaults)
        return defaults
