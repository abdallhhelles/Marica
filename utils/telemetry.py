"""
Structured telemetry helpers for Marcia.
Records command latency, external call timing, task failures, and reconnect events.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field


logger = logging.getLogger("MarciaOS.Telemetry")


def _log_event(event: str, **fields) -> None:
    payload = {"event": event, "timestamp": time.time(), **fields}
    try:
        logger.info(json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        logger.exception("Failed to log telemetry event: %s", event)


@dataclass
class TimingStats:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def observe(self, duration_ms: float) -> None:
        self.count += 1
        self.total_ms += duration_ms
        self.max_ms = max(self.max_ms, duration_ms)

    def snapshot(self) -> dict[str, float]:
        avg = self.total_ms / self.count if self.count else 0.0
        return {"count": self.count, "avg_ms": avg, "max_ms": self.max_ms}


@dataclass
class MetricsStore:
    counters: dict[str, int] = field(default_factory=dict)
    timings: dict[str, TimingStats] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self.counters[key] = self.counters.get(key, 0) + amount

    def observe(self, key: str, duration_ms: float) -> None:
        with self._lock:
            stats = self.timings.get(key)
            if stats is None:
                stats = TimingStats()
                self.timings[key] = stats
            stats.observe(duration_ms)

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {
                "counters": dict(self.counters),
                "timings": {k: v.snapshot() for k, v in self.timings.items()},
            }


METRICS = MetricsStore()
_LAST_SNAPSHOT: dict[str, dict] | None = None


def record_command_latency(
    *,
    command: str,
    duration_ms: float,
    success: bool,
    guild_id: int | None,
    user_id: int | None,
    source: str,
    invocation_id: str | None = None,
    log_event: bool = True,
) -> None:
    METRICS.observe("command_latency_ms", duration_ms)
    METRICS.inc("command_success" if success else "command_error")
    if log_event:
        _log_event(
            "command_latency",
            command=command,
            duration_ms=round(duration_ms, 2),
            success=success,
            guild_id=guild_id,
            user_id=user_id,
            source=source,
            invocation_id=invocation_id,
        )


def record_external_call(
    *,
    service: str,
    duration_ms: float,
    success: bool,
    status_code: int | None = None,
    retries: int = 0,
    error: str | None = None,
) -> None:
    METRICS.observe("external_call_ms", duration_ms)
    METRICS.inc("external_call_success" if success else "external_call_error")
    _log_event(
        "external_call",
        service=service,
        duration_ms=round(duration_ms, 2),
        success=success,
        status_code=status_code,
        retries=retries,
        error=error,
    )


def record_rate_limit(*, service: str, retry_after: float | None = None) -> None:
    METRICS.inc("rate_limit_events")
    _log_event("rate_limit", service=service, retry_after=retry_after)


def record_task_failure(*, task_name: str, error: str) -> None:
    METRICS.inc("task_failures")
    _log_event("task_failure", task_name=task_name, error=error)


def record_reconnect(*, shard_id: int | None = None, reason: str) -> None:
    METRICS.inc("reconnect_events")
    _log_event("reconnect", shard_id=shard_id, reason=reason)


def log_metrics_snapshot() -> None:
    global _LAST_SNAPSHOT
    snapshot = METRICS.snapshot()
    if snapshot == _LAST_SNAPSHOT:
        return
    _LAST_SNAPSHOT = snapshot
    _log_event("metrics_snapshot", **snapshot)


__all__ = [
    "METRICS",
    "record_command_latency",
    "record_external_call",
    "record_rate_limit",
    "record_task_failure",
    "record_reconnect",
    "log_metrics_snapshot",
]
