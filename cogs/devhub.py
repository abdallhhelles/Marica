"""
FILE: cogs/devhub.py
PURPOSE: Maintain the Marica Devs server with stats and patch-note broadcasts.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from database import command_usage_totals

DEV_GUILD_ID = 1455313963507257486
TEST_GUILD_ID = 1454704176662843525
INFO_CHANNEL_NAME = "marica-info"
PATCH_NOTES_CHANNEL_NAME = "marica-patch-notes"
EXTRA_CHANNELS = [
    ("ops-requests", "Routing for tasks Marica should handle next."),
    ("ideas-lab", "Brainstorming and design discussions for new Marica features."),
    ("bug-reports", "Log regressions or issues found during testing."),
]

logger = logging.getLogger("MarciaOS.DevHub")


class DevServerManager(commands.Cog):
    """Orchestrate housekeeping for the Marica Devs hub."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._bootstrap_task = self.bot.loop.create_task(self._bootstrap())

    def cog_unload(self):
        if self._bootstrap_task:
            self._bootstrap_task.cancel()
        if self.info_updater.is_running():
            self.info_updater.cancel()

    async def _bootstrap(self):
        await self.bot.wait_until_ready()

        for guild_id in (DEV_GUILD_ID, TEST_GUILD_ID):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.warning("Managed guild not found (ID: %s)", guild_id)
                continue

            await self._ensure_channels(guild)
            await self._publish_info_panel(guild)
            await self._post_patch_notes(guild)

        if not self.info_updater.is_running():
            self.info_updater.start()

    async def _ensure_channels(self, guild: discord.Guild) -> None:
        """Create required channels if they do not already exist."""
        await self._get_or_create_channel(
            guild,
            INFO_CHANNEL_NAME,
            topic="Live Marica stats across all servers.",
        )
        await self._get_or_create_channel(
            guild,
            PATCH_NOTES_CHANNEL_NAME,
            topic="Autopublished Marica patch notes.",
        )

        for name, topic in EXTRA_CHANNELS:
            await self._get_or_create_channel(guild, name, topic=topic)

    async def _get_or_create_channel(
        self, guild: discord.Guild, name: str, *, topic: str | None = None
    ) -> discord.TextChannel | None:
        existing = discord.utils.get(guild.text_channels, name=name)
        if existing:
            if topic and existing.topic != topic:
                try:
                    await existing.edit(topic=topic, reason="Align Marica Devs channel topic")
                except discord.Forbidden:
                    logger.warning("Missing permissions to edit topic for %s", name)
            return existing

        try:
            channel = await guild.create_text_channel(name, topic=topic)
            await channel.send(f"📡 Channel online: `{name}`.")
            return channel
        except discord.Forbidden:
            logger.warning("Missing permissions to create channel %s", name)
        except Exception:
            logger.exception("Failed to create channel %s", name)
        return None

    def _current_patch_tag(self) -> str:
        try:
            return (
                subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True)
                .strip()
            )
        except Exception:
            return datetime.now(timezone.utc).strftime("patch-%Y%m%d%H%M")

    async def _publish_info_panel(self, guild: discord.Guild) -> None:
        channel = await self._get_or_create_channel(
            guild, INFO_CHANNEL_NAME, topic="Live Marica stats across all servers."
        )
        if not channel:
            return

        embed = await self._build_stats_embed()
        await self._upsert_bot_embed(channel, embed)

    async def _build_stats_embed(self) -> discord.Embed:
        now = datetime.now(timezone.utc)
        servers = len(self.bot.guilds)
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        visible_channels = sum(len(g.text_channels) + len(g.voice_channels) for g in self.bot.guilds)
        command_total, top_command, top_uses = await command_usage_totals()

        embed = discord.Embed(
            title="📊 Marica Ops Board",
            description=(
                "Live pulse of Marica across every connected server. This panel refreshes automatically."
            ),
            color=0x5865F2,
            timestamp=now,
        )
        embed.add_field(name="Servers", value=str(servers))
        embed.add_field(name="Total Members", value=str(total_members))
        embed.add_field(name="Active Channels", value=str(visible_channels))

        if top_command:
            embed.add_field(
                name="Top Command",
                value=f"`{top_command}` ({top_uses} uses)",
                inline=False,
            )
        embed.add_field(name="Commands Logged", value=str(command_total), inline=False)
        embed.set_footer(text="Marica Devs | Auto-maintained")
        return embed

    async def _upsert_bot_embed(self, channel: discord.TextChannel, embed: discord.Embed) -> None:
        async for message in channel.history(limit=15):
            if message.author == self.bot.user and message.embeds:
                try:
                    await message.edit(embed=embed)
                except discord.Forbidden:
                    logger.warning("Missing permissions to edit info panel message")
                return

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning("Missing permissions to post info panel message")

    async def _post_patch_notes(self, guild: discord.Guild) -> None:
        channel = await self._get_or_create_channel(
            guild, PATCH_NOTES_CHANNEL_NAME, topic="Autopublished Marica patch notes."
        )
        if not channel:
            return

        tag = self._current_patch_tag()
        async for message in channel.history(limit=15):
            if message.author == self.bot.user and tag in message.content:
                return

        # ✍️ Update this list whenever new work ships so the bot announces the latest changes
        # on the next restart/deploy. Keep bullets concise, user-facing, and specific to the
        # build you're deploying.
        notes = [
            "Dev automation now manages Marica Devs and the test guild (1454704176662843525).",
            "Stats board refreshes every 30 minutes with live server/member/channel counts and command usage.",
            "Patch notes broadcast with each deployment—refresh this list before shipping new work.",
            "Ops, ideas, and bug triage channels are auto-created for faster collaboration.",
        ]
        body = "\n".join(f"• {line}" for line in notes)
        try:
            await channel.send(f"Patch `{tag}`\n{body}")
        except discord.Forbidden:
            logger.warning("Missing permissions to post patch notes")

    @tasks.loop(minutes=30)
    async def info_updater(self):
        for guild_id in (DEV_GUILD_ID, TEST_GUILD_ID):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            await self._publish_info_panel(guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(DevServerManager(bot))
