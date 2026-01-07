"""
FILE: cogs/devhub.py
PURPOSE: Maintain the Marcia Devs server with stats and patch-note broadcasts.
"""
from __future__ import annotations

import logging
import subprocess
import textwrap
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from database import command_usage_totals
from patch_notes import PatchNotesStore

DEV_GUILD_ID = 1455313963507257486
TEST_GUILD_ID = 1454704176662843525
INFO_CHANNEL_NAME = "marcia-info"
PATCH_NOTES_CHANNEL_NAME = "marcia-patch-notes"
EXTRA_CHANNELS = [
    ("ops-requests", "Routing for tasks Marcia should handle next."),
    ("ideas-lab", "Brainstorming and design discussions for new Marcia features."),
    ("bug-reports", "Log regressions or issues found during testing."),
]
TEST_LAYOUT = [
    (
        "Control Tower",
        [
            (
                "readme",
                "Rules, verification, and fast onboarding.",
                {
                    "marker": "seed:readme:v2-min",
                    "content": textwrap.dedent(
                        """
                        **Welcome:** Keep it concise. `/setup` to map events/welcome/verify/rules + auto-role. Re-run `/setup audit` after permission tweaks.

                        **Core Flows:**
                        - `/event` for ops (UTC-2). Reminders at 60/30/15/3/0.
                        - `/scavenge` hourly, chat for XP (60s), `/trade_item` to barter.
                        - `/commands` + `/manual` for quick discovery.

                        **QA Etiquette:** One issue per thread, include command, timestamp, expected vs actual, and a log or screenshot.
                        """
                    ),
                    "pin": True,
                },
            ),
            (
                "updates",
                "Deploy notes and important pings only.",
                {
                    "marker": "seed:updates:v1-min",
                    "content": "Changelogs + maintenance windows land here. Keep reactions lightweight; discussions move to `#bug-reports` or `#ideas-lab`.",
                },
            ),
            (
                "marcia-stats",
                "Live Marcia stats and quick tips.",
                {
                    "marker": "seed:stats:v1-min",
                    "content": textwrap.dedent(
                        """
                        Snapshots to watch:
                        - Command volume (top 5) across guilds.
                        - Error count last 24h (auto-fed from bug logger).
                        - XP/level milestones posted to `#level-up`.

                        Use `/manual` for feature overviews and `/intel <topic>` for deep dives.
                        """
                    ),
                },
            ),
        ],
    ),
    (
        "Operations",
        [
            (
                "events",
                "Read-only reminders for ops; `/event` posts here.",
                {
                    "marker": "seed:events:v2-min",
                    "content": "Lock this channel. `/event` announcements only. Pin the current schedule and keep chatter in `#lounge`.",
                },
            ),
            (
                "level-up",
                "Rank milestones and lightweight XP tips.",
                {
                    "marker": "seed:level-up:v1-min",
                    "content": "Marcia posts rank-ups here. Keep it noise-free; drop congratulations with emojis only.",
                },
            ),
        ],
    ),
    (
        "QA",
        [
            (
                "bug-reports",
                "Repro steps, screenshots, expected vs actual.",
                {
                    "marker": "seed:bug-reports:v2-min",
                    "content": "Template: what happened • expected behavior • exact command • timestamp (UTC-2) • screenshot/log. Link to messages if translation/reaction related.",
                    "pin": True,
                },
            ),
            (
                "load-tests",
                "Stress test commands, cooldowns, and concurrency.",
                {
                    "marker": "seed:load-tests:v2-min",
                    "content": "Queue stress runs: rapid `/scavenge`, concurrent `/event` creation, button mashing on Fish-Link. Post rate-limit results + traces.",
                },
            ),
            (
                "ideas-lab",
                "Short-form requests and polish notes.",
                {
                    "marker": "seed:ideas:v1-min",
                    "content": "Pitch the upgrade in 5 lines max. Include target users, channel touchpoints, and success criteria.",
                },
            ),
        ],
    ),
    (
        "Lounge",
        [
            ("lounge", "Low-noise chat for testers and devs.", None),
            ("showcase", "Clips and screenshots of Marcia in action.", None),
        ],
    ),
]


logger = logging.getLogger("MarciaOS.DevHub")


class DevServerManager(commands.Cog):
    """Orchestrate housekeeping for the Marcia Devs hub."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.patch_notes = PatchNotesStore()
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

            if guild_id == TEST_GUILD_ID:
                await self._ensure_test_hub_layout(guild)

        if not self.info_updater.is_running():
            self.info_updater.start()

    async def _ensure_channels(self, guild: discord.Guild) -> None:
        """Create required channels if they do not already exist."""
        await self._get_or_create_channel(
            guild,
            INFO_CHANNEL_NAME,
            topic="Live Marcia stats across all servers.",
        )
        await self._get_or_create_channel(
            guild,
            PATCH_NOTES_CHANNEL_NAME,
            topic="Autopublished Marcia patch notes.",
        )

        for name, topic in EXTRA_CHANNELS:
            await self._get_or_create_channel(guild, name, topic=topic)

    async def _ensure_test_hub_layout(self, guild: discord.Guild) -> None:
        """Align the testing guild with the published playbook."""

        for category_name, channels in TEST_LAYOUT:
            category = await self._get_or_create_category(guild, category_name)
            for name, topic, seed in channels:
                channel = await self._get_or_create_channel(
                    guild, name, topic=topic, category=category
                )
                if channel and seed:
                    await self._seed_channel(channel, seed)

    async def _get_or_create_channel(
        self,
        guild: discord.Guild,
        name: str,
        *,
        topic: str | None = None,
        category: discord.CategoryChannel | None = None,
    ) -> discord.TextChannel | None:
        existing = discord.utils.get(guild.text_channels, name=name, category=category) or discord.utils.get(
            guild.text_channels, name=name
        )
        if existing:
            if topic and existing.topic != topic:
                try:
                    await existing.edit(topic=topic, reason="Align Marcia Devs channel topic")
                except discord.Forbidden:
                    logger.warning("Missing permissions to edit topic for %s", name)
            if category and existing.category != category:
                try:
                    await existing.edit(category=category, reason="Align Marcia Devs channel category")
                except discord.Forbidden:
                    logger.warning("Missing permissions to move channel %s", name)
            return existing

        try:
            channel = await guild.create_text_channel(name, topic=topic, category=category)
            await channel.send(f"📡 Channel online: `{name}`.")
            return channel
        except discord.Forbidden:
            logger.warning("Missing permissions to create channel %s", name)
        except Exception:
            logger.exception("Failed to create channel %s", name)
        return None

    async def _get_or_create_category(
        self, guild: discord.Guild, name: str
    ) -> discord.CategoryChannel | None:
        existing = discord.utils.get(guild.categories, name=name)
        if existing:
            return existing

        try:
            return await guild.create_category(name)
        except discord.Forbidden:
            logger.warning("Missing permissions to create category %s", name)
        except Exception:
            logger.exception("Failed to create category %s", name)
        return None

    async def _seed_channel(self, channel: discord.TextChannel, seed: dict) -> None:
        marker = seed.get("marker")
        content = seed.get("content")
        if not marker or not content:
            return

        desired_body = f"{content}\n\n`{marker}`"
        existing_message: discord.Message | None = None

        async for message in channel.history(limit=50):
            if message.author == self.bot.user and marker in (message.content or ""):
                existing_message = message
                break

        if existing_message:
            if existing_message.content != desired_body:
                try:
                    await existing_message.edit(content=desired_body)
                except discord.Forbidden:
                    logger.warning("Missing permissions to update seeded message in %s", channel.name)
                except Exception:
                    logger.exception("Failed editing seeded message in %s", channel.name)
            if seed.get("pin") and not existing_message.pinned:
                try:
                    await existing_message.pin(reason="Pin seeded onboarding copy")
                except discord.Forbidden:
                    logger.warning("Missing permissions to pin message in %s", channel.name)
                except Exception:
                    logger.exception("Failed to pin seeded message in %s", channel.name)
            return

        body = desired_body
        try:
            sent = await channel.send(body)
            if seed.get("pin"):
                try:
                    await sent.pin(reason="Pin seeded onboarding copy")
                except discord.Forbidden:
                    logger.warning("Missing permissions to pin message in %s", channel.name)
        except discord.Forbidden:
            logger.warning("Missing permissions to seed channel %s", channel.name)
        except Exception:
            logger.exception("Failed to seed channel %s", channel.name)

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
            guild, INFO_CHANNEL_NAME, topic="Live Marcia stats across all servers."
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
            title="📊 Marcia Ops Board",
            description=(
                "Live pulse of Marcia across every connected server. This panel refreshes automatically."
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
        embed.set_footer(text="Marcia Devs | Auto-maintained")
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
            guild, PATCH_NOTES_CHANNEL_NAME, topic="Autopublished Marcia patch notes."
        )
        if not channel:
            return

        tag = self._current_patch_tag()
        notes = self.patch_notes.format_bullets()
        if not notes:
            return

        body = "\n".join(f"• {line}" for line in notes)
        desired_content = f"Patch `{tag}`\n{body}"

        async for message in channel.history(limit=200):
            if message.author != self.bot.user:
                continue

            content = message.content or ""
            if tag in content:
                if content != desired_content:
                    try:
                        await message.edit(content=desired_content)
                    except discord.Forbidden:
                        logger.warning("Missing permissions to edit patch notes")
                    except Exception:
                        logger.exception("Failed to edit patch notes message")
                self.patch_notes.clear()
                return

            if content.strip() == desired_content.strip():
                # Avoid reposting identical bodies to preserve concise history.
                self.patch_notes.clear()
                return

        try:
            await channel.send(desired_content)
            self.patch_notes.clear()
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
