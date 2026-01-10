"""
Shared time helpers to keep Marcia aligned with Dark War Survival's global clock.

The game runs on UTC-2 for every server; local/system time is ignored.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

GAME_TZ = timezone(timedelta(hours=-2))


def now_game() -> datetime:
    """Return the current game time (UTC-2) as an aware datetime."""
    return datetime.now(timezone.utc).astimezone(GAME_TZ)


def utc_to_game(dt: datetime) -> datetime:
    """Convert a UTC datetime to game time (UTC-2). Accepts naive-as-UTC inputs."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.astimezone(GAME_TZ)


def game_to_utc(dt: datetime) -> datetime:
    """Convert a game-time datetime to UTC. Accepts naive-as-game inputs."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=GAME_TZ)
    else:
        dt = dt.astimezone(GAME_TZ)
    return dt.astimezone(timezone.utc)


def format_game(dt: datetime) -> str:
    """Human-friendly display for game time."""
    return utc_to_game(dt).strftime("%Y-%m-%d %H:%M UTC-2")

