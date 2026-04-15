"""
FILE: cogs/marcia_server.py
USE: Special automation for the Marcia Server (ID-specific).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from database import (
    activity_metric_totals,
    command_usage_totals,
    get_settings,
    global_analytics_snapshot,
    top_commands,
    top_global_profile_stat,
    top_global_xp,
    top_guild_usage,
    update_setting,
)


MARCIA_SERVER_ID = 1454704176662843525
ANALYTICS_CHANNEL_NAME = "marcia-info"
REQUIRED_CHANNEL_SPECS = {
    "about": {
        "setting_key": None,
        "topic": "Welcome brief and orientation for new survivors.",
        "seed_message": (
            "## 👋 Welcome to the Marcia Server\n"
            "Marcia keeps this server focused: clear rules, clear events, clear operations.\n\n"
            "Start here, read **#rules**, then watch **#events** for scheduled ops and reminders."
        ),
    },
    "rules": {
        "setting_key": "rules_channel_id",
        "topic": "Server rules and conduct expectations.",
        "seed_message": (
            "## 📜 Marcia Server Rules\n"
            "1. Respect everyone in comms.\n"
            "2. Keep operations and coordination clear.\n"
            "3. No spam, harassment, or disruptive behavior.\n"
            "4. Follow Discord Terms of Service and Community Guidelines.\n\n"
            "Violation handling is at moderator discretion."
        ),
    },
    "events": {
        "setting_key": "event_channel_id",
        "topic": "Scheduled operations, reminders, and start pings.",
        "seed_message": (
            "## 📡 Event Operations Channel\n"
            "Marcia posts mission schedules here.\n\n"
            "Reminder policy for this server:\n"
            "• T-60 message in this channel with @everyone\n"
            "• Follow-up reminders are DM-only for members who react with 🤝"
        ),
    },
}


class MarciaServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger("MarciaOS.MarciaServer")
        self._ready_once = False
        self._analytics_message_id: int | None = None
        self._channel_lock = asyncio.Lock()
        self.analytics_loop.start()

    def cog_unload(self):
        self.analytics_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if self._ready_once:
            return
        self._ready_once = True
        guild = self.bot.get_guild(MARCIA_SERVER_ID)
        if not guild:
            return
        await self._ensure_marcia_channels(guild)
        await self._post_or_update_analytics(guild)

    async def _ensure_marcia_channels(self, guild: discord.Guild) -> None:
        async with self._channel_lock:
            settings = await get_settings(guild.id)
            settings = settings or {}
            for channel_name, spec in REQUIRED_CHANNEL_SPECS.items():
                linked_channel = None
                setting_key = spec["setting_key"]
                if setting_key:
                    linked_id = settings.get(setting_key)
                    if linked_id:
                        linked_channel = guild.get_channel(linked_id)

                if linked_channel and linked_channel.name != channel_name:
                    try:
                        await linked_channel.edit(
                            name=channel_name,
                            reason=f"Marcia Server align {channel_name} channel name",
                        )
                    except Exception:
                        self.log.warning("Unable to rename %s channel %s", channel_name, linked_channel.id)

                channels_named = [channel for channel in guild.text_channels if channel.name == channel_name]
                if linked_channel is None and channels_named:
                    linked_channel = min(channels_named, key=lambda channel: channel.id)

                if linked_channel is None:
                    linked_channel = await self._ensure_channel(
                        guild,
                        channel_name,
                        topic=spec["topic"],
                        read_only=True,
                    )
                else:
                    await self._apply_read_only_permissions(linked_channel)
                    if linked_channel.topic != spec["topic"]:
                        try:
                            await linked_channel.edit(
                                topic=spec["topic"],
                                reason=f"Marcia Server align {channel_name} channel topic",
                            )
                        except Exception:
                            self.log.warning("Unable to update %s channel topic %s", channel_name, linked_channel.id)

                if channels_named:
                    for channel in channels_named:
                        if channel.id != linked_channel.id:
                            try:
                                await channel.delete(reason=f"Marcia Server dedupe {channel_name}")
                            except Exception:
                                self.log.warning("Unable to delete duplicate %s channel %s", channel_name, channel.id)

                await self._seed_channel_message(linked_channel, spec["seed_message"])
                if setting_key:
                    await update_setting(guild.id, setting_key, linked_channel.id, guild.name)

            analytics_channel = None
            channel_id = settings.get("analytics_channel_id")
            if channel_id:
                analytics_channel = guild.get_channel(channel_id)

            if analytics_channel and analytics_channel.name != ANALYTICS_CHANNEL_NAME:
                try:
                    await analytics_channel.edit(
                        name=ANALYTICS_CHANNEL_NAME,
                        reason="Marcia Server align analytics channel name",
                    )
                except Exception:
                    self.log.warning("Unable to rename analytics channel %s", analytics_channel.id)

            channels_named = [
                channel
                for channel in guild.text_channels
                if channel.name == ANALYTICS_CHANNEL_NAME
            ]
            if analytics_channel is None and channels_named:
                analytics_channel = min(channels_named, key=lambda channel: channel.id)

            if analytics_channel is None:
                analytics_channel = await self._ensure_channel(
                    guild,
                    ANALYTICS_CHANNEL_NAME,
                    topic="Marcia network pulse, stats, and updates.",
                    read_only=True,
                )
            else:
                await self._apply_read_only_permissions(analytics_channel)
                if analytics_channel.topic != "Marcia network pulse, stats, and updates.":
                    try:
                        await analytics_channel.edit(
                            topic="Marcia network pulse, stats, and updates.",
                            reason="Marcia Server align analytics channel topic",
                        )
                    except Exception:
                        self.log.warning("Unable to update analytics channel topic %s", analytics_channel.id)

            if channels_named and analytics_channel:
                for channel in channels_named:
                    if channel.id != analytics_channel.id:
                        try:
                            await channel.delete(reason="Marcia Server dedupe marcia-info")
                        except Exception:
                            self.log.warning("Unable to delete duplicate marcia-info channel %s", channel.id)

            await update_setting(guild.id, "analytics_channel_id", analytics_channel.id, guild.name)

    async def _seed_channel_message(self, channel: discord.TextChannel, seed_message: str) -> None:
        """Ensure baseline info posts exist without spamming duplicate messages."""
        try:
            async for msg in channel.history(limit=25):
                if msg.author.id == self.bot.user.id:
                    return
        except Exception:
            self.log.warning("Unable to inspect history for %s (%s)", channel.guild.name, channel.id)
            return

        try:
            await channel.send(seed_message)
        except Exception:
            self.log.warning("Unable to seed baseline message in %s (%s)", channel.guild.name, channel.id)

    async def _ensure_channel(
        self,
        guild: discord.Guild,
        name: str,
        *,
        topic: str,
        read_only: bool,
    ) -> discord.TextChannel:
        channel = discord.utils.get(guild.text_channels, name=name)
        if channel:
            if read_only:
                await self._apply_read_only_permissions(channel)
            return channel

        overwrites = self._read_only_overwrites(guild) if read_only else {}

        channel = await guild.create_text_channel(
            name=name,
            topic=topic,
            overwrites=overwrites,
            reason="Marcia Server auto-setup",
        )
        if read_only:
            await self._apply_read_only_permissions(channel)
        return channel

    def _read_only_overwrites(self, guild: discord.Guild) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=False),
        }
        bot_member = guild.me or guild.get_member(self.bot.user.id)
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                send_messages=True,
                manage_messages=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True,
            )
        return overwrites

    async def _apply_read_only_permissions(self, channel: discord.TextChannel) -> None:
        overwrites = self._read_only_overwrites(channel.guild)
        await channel.edit(overwrites=overwrites, reason="Marcia Server read-only channel policy")


    def _build_analytics_embed(
        self,
        guild: discord.Guild,
        snapshot: dict,
        xp_rows,
        cp_rows,
        kill_rows,
        activity_totals: dict[str, int],
        command_total: int,
        top_command: str | None,
        top_command_uses: int,
        top_commands_rows,
        top_guild_rows,
    ) -> discord.Embed:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        total_guilds = len(self.bot.guilds)
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        embed = discord.Embed(
            title="🌐 Global Analytics Pulse",
            description="Hourly update: galaxy-wide stats from Marcia's command deck.",
            color=0x5865F2,
        )
        embed.add_field(name="⏱️ Last update", value=now, inline=False)
        embed.add_field(
            name="📡 Network Pulse",
            value="\n".join(
                [
                    f"Servers online: **{total_guilds}**",
                    f"Survivors in comms: **{total_members:,}**",
                    f"Tracked profiles: **{snapshot['survivors_tracked']:,}**",
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name="🛰️ Field Intel",
            value="\n".join(
                [
                    f"Fish-Link listings: **{snapshot['trade_listings']:,}**",
                    f"Active traders: **{snapshot['traders']:,}**",
                    f"Missions live: **{snapshot['missions_active']:,}**",
                    f"Templates locked: **{snapshot['templates']:,}**",
                    f"Items logged: **{snapshot['items']:,}**",
                ]
            ),
            inline=False,
        )
        top_command_line = (
            f"`{top_command}` ({top_command_uses:,} runs)"
            if top_command
            else "No command telemetry yet."
        )
        embed.add_field(
            name="🎮 Command Cadence",
            value="\n".join(
                [
                    f"Total commands fired: **{command_total:,}**",
                    f"Most-used command: {top_command_line}",
                ]
            ),
            inline=False,
        )
        if activity_totals:
            embed.add_field(
                name="🧪 Ops Highlights",
                value="\n".join(
                    [
                        f"Scavenge runs: **{activity_totals.get('scavenge_runs', 0):,}**",
                        f"Translations decrypted: **{activity_totals.get('translations', 0):,}**",
                        f"Events scheduled: **{activity_totals.get('events_scheduled', 0):,}**",
                        f"Profile scans: **{activity_totals.get('profile_views', 0):,}**",
                    ]
                ),
                inline=False,
            )

        if top_guild_rows:
            lines = []
            for idx, row in enumerate(top_guild_rows, start=1):
                guild_obj = self.bot.get_guild(row["guild_id"])
                guild_name = guild_obj.name if guild_obj else f"Guild {row['guild_id']}"
                lines.append(f"{idx}. {guild_name} - {row['total']:,} commands")
            embed.add_field(name="🏙️ Top Command Hubs", value="\n".join(lines), inline=False)

        if top_commands_rows:
            lines = [f"`{row['command_name']}` — {row['total']:,} runs" for row in top_commands_rows]
            embed.add_field(name="🧭 Most Used Commands", value="\n".join(lines), inline=False)

        if xp_rows:
            top_xp = []
            for idx, row in enumerate(xp_rows, start=1):
                member = self.bot.get_user(row["user_id"])
                name = member.mention if member else f"User {row['user_id']}"
                top_xp.append(f"{idx}. {name} - L{row['level']} | {row['xp']:,} XP")
            embed.add_field(name="🏆 Network XP Legends", value="\n".join(top_xp), inline=False)

        if cp_rows:
            top_cp = []
            for idx, row in enumerate(cp_rows, start=1):
                member = self.bot.get_user(row["user_id"])
                name = row["player_name"] or (member.mention if member else f"User {row['user_id']}")
                top_cp.append(f"{idx}. {name} - {row['value']:,} CP")
            embed.add_field(name="⚔️ Combat Power Titans", value="\n".join(top_cp), inline=False)

        if kill_rows:
            top_kills = []
            for idx, row in enumerate(kill_rows, start=1):
                member = self.bot.get_user(row["user_id"])
                name = row["player_name"] or (member.mention if member else f"User {row['user_id']}")
                top_kills.append(f"{idx}. {name} - {row['value']:,} Kills")
            embed.add_field(name="☠️ Killboard Stars", value="\n".join(top_kills), inline=False)

        embed.add_field(
            name="🛠️ What Marcia is doing",
            value="\n".join([
                "• Tracking event reminders and RSVP opt-ins.",
                "• Matching Fish-Link trades and notifying survivors.",
                "• Logging profile scans and leaderboard data.",
            ]),
            inline=False,
        )
        embed.set_footer(text="Marcia Server | Clock: UTC-2 | Fun stats, serious ops.")
        return embed

    async def _post_or_update_analytics(self, guild: discord.Guild) -> None:
        settings = await get_settings(guild.id)
        if not settings:
            return
        channel_id = settings.get("analytics_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if not channel:
            channel = discord.utils.get(guild.text_channels, name=ANALYTICS_CHANNEL_NAME)
        if not channel:
            return

        snapshot = await global_analytics_snapshot()
        xp_rows = await top_global_xp(limit=5)
        cp_rows = await top_global_profile_stat("cp", limit=5)
        kill_rows = await top_global_profile_stat("kills", limit=5)
        activity_totals = await activity_metric_totals(
            ["scavenge_runs", "translations", "events_scheduled", "profile_views"]
        )
        command_total, top_command, top_command_uses = await command_usage_totals()
        top_commands_rows = await top_commands(3)
        top_guild_rows = await top_guild_usage(3)

        embed = self._build_analytics_embed(
            guild,
            snapshot,
            xp_rows,
            cp_rows,
            kill_rows,
            activity_totals,
            command_total,
            top_command,
            top_command_uses,
            top_commands_rows,
            top_guild_rows,
        )

        message = None
        if self._analytics_message_id:
            try:
                message = await channel.fetch_message(self._analytics_message_id)
            except Exception:
                message = None

        if not message:
            async for msg in channel.history(limit=5):
                if msg.author.id == self.bot.user.id:
                    message = msg
                    break

        if message:
            await message.edit(embed=embed)
            self._analytics_message_id = message.id
        else:
            sent = await channel.send(embed=embed)
            self._analytics_message_id = sent.id

    @tasks.loop(hours=1)
    async def analytics_loop(self):
        guild = self.bot.get_guild(MARCIA_SERVER_ID)
        if not guild:
            return
        await self._ensure_marcia_channels(guild)
        await self._post_or_update_analytics(guild)

    @analytics_loop.before_loop
    async def before_analytics_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(MarciaServer(bot))
