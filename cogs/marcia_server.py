"""
FILE: cogs/marcia_server.py
USE: Special automation for the Marcia Server (ID-specific).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from database import (
    guild_analytics_snapshot,
    top_profile_stat,
    top_xp_leaderboard,
    update_setting,
    get_settings,
)


MARCIA_SERVER_ID = 1454704176662843525
ABOUT_CHANNEL_NAME = "about"
RULES_CHANNEL_NAME = "rules"
GENERAL_CHANNEL_NAME = "general"
ANALYTICS_CHANNEL_NAME = "analytics"
EVENTS_CHANNEL_NAME = "events"


class MarciaServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger("MarciaOS.MarciaServer")
        self._ready_once = False
        self._analytics_message_id: int | None = None
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
        about_channel = await self._ensure_channel(
            guild,
            ABOUT_CHANNEL_NAME,
            topic="What Marcia OS is and why this server exists.",
            read_only=True,
        )
        rules_channel = await self._ensure_channel(
            guild,
            RULES_CHANNEL_NAME,
            topic="Server rules and expectations (Marcia-managed).",
            read_only=True,
        )
        general_channel = await self._ensure_channel(
            guild,
            GENERAL_CHANNEL_NAME,
            topic="Welcome + general chat.",
            read_only=False,
        )
        analytics_channel = await self._ensure_channel(
            guild,
            ANALYTICS_CHANNEL_NAME,
            topic="Hourly Marcia OS network pulse and fun stats.",
            read_only=True,
        )
        events_channel = await self._ensure_channel(
            guild,
            EVENTS_CHANNEL_NAME,
            topic="Event announcements (Marcia-managed).",
            read_only=True,
        )

        await update_setting(guild.id, "rules_channel_id", rules_channel.id, guild.name)
        await update_setting(guild.id, "event_channel_id", events_channel.id, guild.name)
        await update_setting(guild.id, "chat_channel_id", general_channel.id, guild.name)
        await update_setting(guild.id, "welcome_channel_id", general_channel.id, guild.name)
        await update_setting(guild.id, "feedback_channel_id", general_channel.id, guild.name)
        await update_setting(guild.id, "analytics_channel_id", analytics_channel.id, guild.name)

        await self._seed_about(about_channel)
        await self._seed_rules(rules_channel)
        await self._seed_general(general_channel)
        await self._seed_events(events_channel)

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

    async def _seed_about(self, channel: discord.TextChannel) -> None:
        try:
            history = [msg async for msg in channel.history(limit=1)]
        except Exception:
            history = []
        if history:
            return
        info_lines = [
            "🛰️ **Marcia Server - About**",
            "This server exists to help survivors learn Marcia OS, follow updates, and give dev feedback.",
            "",
            "**Start here**",
            "• Read **#rules** to stay aligned.",
            "• Use `/commands` for the full command list and quick-starts.",
            "• Ask questions in **#general** or ping `/feedback` with issues.",
            "",
            "**Feedback lane**",
            "• Use `/feedback` for bugs and feature ideas (auto-routed to the handler).",
        ]
        await channel.send("\n".join(info_lines))

    async def _seed_rules(self, channel: discord.TextChannel) -> None:
        try:
            history = [msg async for msg in channel.history(limit=1)]
        except Exception:
            history = []
        if history:
            return
        rules_lines = [
            "📜 **Marcia Server Rules**",
            "1) Respect the squad. No harassment, hate speech, or personal attacks.",
            "2) Keep chat readable. No spam, scams, or walls of text.",
            "3) Use `/feedback` for bugs and feature requests.",
            "4) Keep feedback actionable (steps, screenshots, expected vs actual).",
            "5) English preferred so everyone can coordinate.",
        ]
        await channel.send("\n".join(rules_lines))

    async def _seed_general(self, channel: discord.TextChannel) -> None:
        try:
            history = [msg async for msg in channel.history(limit=1)]
        except Exception:
            history = []
        if history:
            return
        await channel.send(
            "👋 **Welcome to Marcia OS.** Ask questions, share screenshots, and coordinate here."
        )

    async def _seed_events(self, channel: discord.TextChannel) -> None:
        try:
            history = [msg async for msg in channel.history(limit=1)]
        except Exception:
            history = []
        if history:
            return
        await channel.send("📣 **Events channel** - Marcia posts mission reminders here.")

    def _build_analytics_embed(self, guild: discord.Guild, snapshot: dict, xp_rows, cp_rows, kill_rows) -> discord.Embed:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        embed = discord.Embed(
            title="🌐 Global Analytics Pulse",
            description="Hourly update: fun stats + what Marcia is doing.",
            color=0x5865F2,
        )
        embed.add_field(name="⏱️ Last update", value=now, inline=False)
        embed.add_field(name="🎣 Trade Listings", value=str(snapshot["trade_listings"]), inline=True)
        embed.add_field(name="👥 Active Traders", value=str(snapshot["traders"]), inline=True)
        embed.add_field(name="🛰️ Missions Running", value=str(snapshot["missions_active"]), inline=True)
        embed.add_field(name="📂 Templates Saved", value=str(snapshot["templates"]), inline=True)
        embed.add_field(name="🧭 Survivors Tracked", value=str(snapshot["survivors_tracked"]), inline=True)
        embed.add_field(name="🎒 Items Logged", value=str(snapshot["items"]), inline=True)

        if xp_rows:
            top_xp = []
            for idx, row in enumerate(xp_rows, start=1):
                member = guild.get_member(row["user_id"])
                name = member.display_name if member else f"User {row['user_id']}"
                top_xp.append(f"{idx}. {name} - L{row['level']} | {row['xp']:,} XP")
            embed.add_field(name="🏆 Top XP", value="\n".join(top_xp), inline=False)

        if cp_rows:
            top_cp = []
            for idx, row in enumerate(cp_rows, start=1):
                member = guild.get_member(row["user_id"])
                name = row["player_name"] or (member.display_name if member else f"User {row['user_id']}")
                top_cp.append(f"{idx}. {name} - {row['value']:,} CP")
            embed.add_field(name="⚔️ Top Combat Power", value="\n".join(top_cp), inline=False)

        if kill_rows:
            top_kills = []
            for idx, row in enumerate(kill_rows, start=1):
                member = guild.get_member(row["user_id"])
                name = row["player_name"] or (member.display_name if member else f"User {row['user_id']}")
                top_kills.append(f"{idx}. {name} - {row['value']:,} Kills")
            embed.add_field(name="☠️ Top Kills", value="\n".join(top_kills), inline=False)

        embed.add_field(
            name="🛠️ What Marcia is doing",
            value="\n".join([
                "• Tracking event reminders and RSVP opt-ins.",
                "• Matching Fish-Link trades and notifying survivors.",
                "• Logging profile scans and leaderboard data.",
            ]),
            inline=False,
        )
        embed.set_footer(text="Marcia Server | Clock: UTC-2")
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

        snapshot = await guild_analytics_snapshot(guild.id)
        xp_rows = await top_xp_leaderboard(guild.id, limit=5)
        cp_rows = await top_profile_stat(guild.id, "cp", limit=5)
        kill_rows = await top_profile_stat(guild.id, "kills", limit=5)

        embed = self._build_analytics_embed(guild, snapshot, xp_rows, cp_rows, kill_rows)

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
