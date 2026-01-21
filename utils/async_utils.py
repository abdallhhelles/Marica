"""
Async helpers for task tracking and safe background execution.
"""
from __future__ import annotations

import asyncio
import logging

from utils.telemetry import record_task_failure


def create_tracked_task(
    coro,
    *,
    name: str,
    logger: logging.Logger,
) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)

    def _done_callback(done: asyncio.Task) -> None:
        if done.cancelled():
            return
        try:
            exc = done.exception()
        except asyncio.CancelledError:
            return
        if exc:
            logger.exception("Background task failed: %s", name, exc_info=exc)
            record_task_failure(task_name=name, error=str(exc))

    task.add_done_callback(_done_callback)
    return task


__all__ = ["create_tracked_task"]
