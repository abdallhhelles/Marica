"""
FILE: cogs/devhub.py
PURPOSE: Maintain the Marica Devs server with stats and patch-note broadcasts.
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
INFO_CHANNEL_NAME = "marica-info"
PATCH_NOTES_CHANNEL_NAME = "marica-patch-notes"
EXTRA_CHANNELS = [
    ("ops-requests", "Routing for tasks Marica should handle next."),
    ("ideas-lab", "Brainstorming and design discussions for new Marica features."),
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
                    "marker": "seed:readme:v1",
                    "content": textwrap.dedent(
                        """
                        **Marica:** "Welcome to the test grid. I don’t babysit — I calibrate."

                        **Setup:** Run `/setup` to link `events`, `welcome`, `verify`, `rules`, and auto-role. Use `/setup audit` after permissions change.
                        **Clock:** Ops run on UTC-2. `/event` schedules raids/sieges/briefings. Reminders fire at 60/30/15/3/0.
                        **Trading:** In `#fish-link`, hit **Add Spare**, **Find Fish**, **My Listings**, **Who Has My Wanted?**. Donors get DM'd automatically.
                        **Progression:** Chat for XP (60s cooldown). `/scavenge` hourly for Common → Mythic loot. `/trade_item` to barter. Finish the catalog to earn **Vaultwalker**.
                        **Tools:** `/commands`, `/features`, `/manual`, `/intel <topic>`, `/poll`, flag reactions for translations.
                        **Conduct:** No spam in events/level-up channels. Keep repro steps clear in QA threads.
                        """
                    ),
                    "pin": True,
                },
            ),
            (
                "changelog",
                "Ship notes for every deploy; Marica/staff posts only.",
                {
                    "marker": "seed:changelog:v1",
                    "content": textwrap.dedent(
                        """
                        **Changelog Template**
                        - Ops: e.g., "Improved UTC-2 reminder formatting; 60-minute post now includes location."
                        - Trading: e.g., "Fish-Link anchor recovery after restarts."
                        - Progression: e.g., "Adjusted XP curve; new rank color band."
                        - QA: e.g., "Telemetry now shows command counts per guild."
                        """
                    ),
                },
            ),
            (
                "announcements",
                "Major milestones, maintenance notices, and beta calls.",
                {
                    "marker": "seed:announcements:v1",
                    "content": "**Marica:** \"Broadcasting to all sectors. New firmware pushed — check `/features` then go break it.\"",
                },
            ),
            (
                "mod-log",
                "Private moderation log and transcript archive target.",
                None,
            ),
            (
                "about",
                "Overview of Marica OS and testing expectations.",
                {
                    "marker": "seed:about:v1",
                    "content": textwrap.dedent(
                        """
                        **Marica:** "I’m the ops spine for your raids, trades, and ranks."

                        **What I do:**
                        - Automate ops reminders on UTC-2 with `/event`.
                        - Anchor Fish-Link trading with `/setup_trade` and smart donor matching.
                        - Track XP/ranks and grant roles per guild without cross-contamination.
                        - Answer intel quickly: `/intel <topic>`, `/manual`, `/features`.

                        **How to help:**
                        - Keep channel links current (`/setup audit`).
                        - Report broken flows in `#bug-reports` with repro steps.
                        - Stress the buttons in `#load-tests` before major pushes.
                        """
                    ),
                },
            ),
        ],
    ),
    (
        "Operations (UTC-2)",
        [
            (
                "events",
                "Read-only reminders for ops; `/event` posts here.",
                {
                    "marker": "seed:events:v1",
                    "content": "Keep this channel read-only for everyone except Marica. All `/event` reminders land here with drone call-signs. Pin the current week’s schedule.",
                },
            ),
            ("ops-planning", "Chatter for raid/defense prep.", None),
            ("voice-pings", "Role mention targets when ops go live.", None),
        ],
    ),
    (
        "Trading",
        [
            (
                "fish-link",
                "Fish-Link terminal and donor matching live here.",
                {
                    "marker": "seed:fish-link:v1",
                    "content": "Run `/setup_trade` once. Pin the terminal. Remind traders: Add Spare, Find Fish, My Listings, Who Has My Wanted?. Matches DM donors automatically.",
                },
            ),
            (
                "loot-market",
                "Barter scavenged items; pair with `/trade_item` runs.",
                None,
            ),
        ],
    ),
    (
        "Progression",
        [
            (
                "level-up",
                "Auto messages for rank milestones; keep low-noise.",
                None,
            ),
            (
                "vaultwalker-wall",
                "Hall of fame for catalog completions.",
                None,
            ),
        ],
    ),
    (
        "Labs & QA",
        [
            (
                "bug-reports",
                "Repro steps, screenshots, expected vs actual.",
                {
                    "marker": "seed:bug-reports:v1",
                    "content": "Format: what happened, expected behavior, exact command, screenshot/log, timestamp (UTC-2). Include message link if translation or reaction related.",
                },
            ),
            (
                "feature-requests",
                "Suggestions for the next sprint.",
                {
                    "marker": "seed:feature-requests:v1",
                    "content": "Marica: \"Pitch the upgrade. If it saves time or ammo, I’ll consider it.\" Use bullets, not essays. Include intended user flow and channel targets.",
                },
            ),
            (
                "load-tests",
                "Stress test commands, cooldowns, and concurrency.",
                {
                    "marker": "seed:load-tests:v1",
                    "content": "Queue stress runs: high-frequency `/scavenge`, rapid Fish-Link button presses, and concurrent `/event` creation. Log results and rate limits.",
                },
            ),
            (
                "localization",
                "Collect translation edge cases and flag reaction tests.",
                {
                    "marker": "seed:localization:v1",
                    "content": "Collect emoji flags that fail to trigger translations, edge-case languages, or layout issues. Include source message links.",
                },
            ),
        ],
    ),
    (
        "General",
        [
            (
                "welcome",
                "Auto welcomes + verification reminders.",
                None,
            ),
            ("lounge", "Free chat for testers.", None),
            ("showcase", "Screenshots and clips of Marica in action.", None),
            (
                "intel",
                "/intel answers, FAQs, guides live here.",
                {
                    "marker": "seed:intel:v1",
                    "content": "Seed with `/intel rules`, `/intel events`, `/intel trading`, and `/intel ranks` to keep testers aligned.",
                },
            ),
            (
                "usage-guide",
                "Step-by-step setup and usage flow for new testers.",
                {
                    "marker": "seed:usage-guide:v1",
                    "content": textwrap.dedent(
                        """
                        **Goal:** Get Marica online in under 5 minutes.

                        1) **Permissions:** Invite with message content + Manage Roles. Place Marica’s role above auto-roles.
                        2) **Core setup:** Run `/setup` and map: `events`, `welcome`, `verify`, `rules`, auto-role. Confirm in `/setup audit`.
                        3) **Trading:** In `#fish-link`, run `/setup_trade`. Pin the terminal. Use Add Spare, Find Fish, My Listings, Who Has My Wanted?.
                        4) **Events:** Schedule with `/event` (UTC-2). Reminders: 60/30/15/3/0. Keep channel read-only.
                        5) **Progression:** Encourage chat for XP. Use `/scavenge` hourly. Track prestige and assign **Vaultwalker** for catalog completions.
                        6) **Intel & support:** Use `/commands`, `/features`, `/manual`, `/intel <topic>`. If something breaks, post in `#bug-reports` with timestamp + screenshot.
                        """
                    ),
                    "pin": True,
                },
            ),
        ],
    ),
]

logger = logging.getLogger("MarciaOS.DevHub")


class DevServerManager(commands.Cog):
    """Orchestrate housekeeping for the Marica Devs hub."""

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
            topic="Live Marica stats across all servers.",
        )
        await self._get_or_create_channel(
            guild,
            PATCH_NOTES_CHANNEL_NAME,
            topic="Autopublished Marica patch notes.",
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
                    await existing.edit(topic=topic, reason="Align Marica Devs channel topic")
                except discord.Forbidden:
                    logger.warning("Missing permissions to edit topic for %s", name)
            if category and existing.category != category:
                try:
                    await existing.edit(category=category, reason="Align Marica Devs channel category")
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

        async for message in channel.history(limit=25):
            if message.author == self.bot.user and marker in message.content:
                return

        body = f"{content}\n\n`{marker}`"
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

        notes = self.patch_notes.format_bullets()
        if not notes:
            return

        body = "\n".join(f"• {line}" for line in notes)
        try:
            await channel.send(f"Patch `{tag}`\n{body}")
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
