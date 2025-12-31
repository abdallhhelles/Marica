"""
Centralized bug/error logging utilities.
- Writes structured JSON lines to data/logs/bug_events.log
- Optionally mirrors critical errors to a Discord channel via BUG_LOG_CHANNEL_ID env var
"""
from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import discord

logger = logging.getLogger("MarciaOS.BugLog")

LOG_FILE = Path("data/logs/bug_events.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
BUG_LOG_CHANNEL_ID = int(os.getenv("BUG_LOG_CHANNEL_ID", "0") or 0)


def _serialize_error(error: Exception) -> dict[str, Any]:
    return {
        "type": type(error).__name__,
        "message": str(error),
        "trace": traceback.format_exception(error),
    }


def _write_local_log(payload: dict[str, Any]) -> None:
    try:
        with LOG_FILE.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed to persist bug log payload")


async def _mirror_to_discord(bot: discord.Client, payload: dict[str, Any]) -> None:
    if not BUG_LOG_CHANNEL_ID:
        return

    channel = bot.get_channel(BUG_LOG_CHANNEL_ID)
    if not channel or not isinstance(channel, discord.TextChannel):
        return

    description_lines = [
        f"**Source:** {payload.get('source')}",
        f"**Command:** {payload.get('command') or 'n/a'}",
        f"**User:** <@{payload.get('user_id')}>" if payload.get("user_id") else "User: n/a",
        f"**Guild:** {payload.get('guild_id') or 'DM'}",
    ]

    embed = discord.Embed(
        title="🚨 Bug Captured",
        description="\n".join(description_lines),
        timestamp=datetime.fromisoformat(payload["timestamp"]),
        color=discord.Color.red(),
    )
    embed.add_field(name="Error", value=payload["error"].get("message", "(no message)"), inline=False)

    trace = payload["error"].get("trace") or []
    if trace:
        condensed = "".join(trace[-2:])
        embed.add_field(name="Traceback", value=f"```py\n{condensed}\n```", inline=False)

    try:
        await channel.send(embed=embed)
    except Exception:
        logger.exception("Failed to mirror bug log to Discord")


async def log_command_exception(
    bot: discord.Client,
    error: Exception,
    *,
    ctx: Any | None = None,
    interaction: discord.Interaction | None = None,
    source: str = "command",
    note: str | None = None,
) -> None:
    """Record an exception with user, guild, and command context when available."""

    guild_id = None
    channel_id = None
    user_id = None
    command_name = None

    if ctx is not None:
        guild_id = getattr(getattr(ctx, "guild", None), "id", None)
        channel_id = getattr(getattr(ctx, "channel", None), "id", None)
        user_id = getattr(getattr(ctx, "author", None), "id", None)
        command_name = getattr(getattr(ctx, "command", None), "qualified_name", None)
        interaction = getattr(ctx, "interaction", interaction)
    elif interaction is not None:
        guild_id = getattr(getattr(interaction, "guild", None), "id", None)
        channel_id = getattr(getattr(interaction, "channel", None), "id", None)
        user_id = getattr(getattr(interaction, "user", None), "id", None)
        command_name = getattr(getattr(interaction, "command", None), "qualified_name", None)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "guild_id": guild_id,
        "channel_id": channel_id,
        "user_id": user_id,
        "command": command_name,
        "note": note,
        "error": _serialize_error(error),
    }

    _write_local_log(payload)
    await _mirror_to_discord(bot, payload)


__all__ = ["log_command_exception"]
