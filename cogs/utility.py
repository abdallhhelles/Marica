"""
FILE: cogs/utility.py
USE: General helper functions, information, and interactive dialogue.
FEATURES: Flag-based translation, Polls, Reminders, and Marcia Manuals.
"""
import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.http_client import CircuitBreakerOpen

from utils.assets import (
    EMOJI_ADORE,
    EMOJI_ANGRY,
    EMOJI_APPROVE,
    EMOJI_CONFIDENT,
    EMOJI_IDEA,
    EMOJI_LAUGH,
    EMOJI_SMUG,
    MARCIA_CAPABILITIES,
    MARCIA_TRAITS,
)
from database import (
    guild_analytics_snapshot,
    increment_activity_metric,
    log_feedback_entry,
    top_commands,
    top_global_xp,
    top_guild_usage,
    top_profile_stat,
    top_xp_leaderboard,
)

# Expanded Language Library
FLAG_LANG = {
    "🇺🇸": "en", "🇬🇧": "en", "🇦🇺": "en", "🇨🇦": "en",
    "🇫🇷": "fr", "🇪🇸": "es", "🇩🇪": "de", "🇮🇹": "it", "🇵🇹": "pt", "🇳🇱": "nl", "🇷🇺": "ru",
    "🇯🇵": "ja", "🇰🇷": "ko", "🇨🇳": "zh-cn", "🇻🇳": "vi", "🇹🇭": "th",
    "🇦🇪": "ar", "🇹🇷": "tr", "🇮🇳": "hi", "🇧🇷": "pt"
}

CLEAR_LIMIT = 100
CLEAR_CONFIRM_THRESHOLD = 25

# Single source of truth for the in-bot showcase. Keep this list aligned with docs/SHOWCASE.md
# so Discord users see the same capabilities advertised in documentation/screenshots.
SHOWCASE_SECTIONS = [
    {
        "name": "Ops & Reminders",
        "lines": [
            f"{EMOJI_IDEA} `/gyper event` schedules ops with UTC-2 timing, pings, and upcoming mission lists.",
            f"{EMOJI_CONFIDENT} `/gyper remind` opens a control deck for new reminders, templates, and scheduled blasts.",
            f"{EMOJI_APPROVE} `/gyper remindme` sets personal DM timers for solo tasks.",
        ],
    },
    {
        "name": "Trading & Progression",
        "lines": [
            f"{EMOJI_ADORE} Fish-Link trading terminal: `/gyper setup_trade` anchors the hub; buttons drive listings.",
            f"{EMOJI_CONFIDENT} `/gyper scavenge` runs for loot + XP with streak, hazard, and overclock bonuses.",
            f"{EMOJI_APPROVE} `/gyper leaderboard` + `/gyper profile` surface XP and scan stats; `/gyper inventory` tracks drops.",
        ],
    },
    {
        "name": "Profile Scans",
        "lines": [
            f"{EMOJI_SMUG} `/gyper scan` DMs you scan options; upload screenshots there to update `/gyper profile` and `/gyper leaderboard`.",
            f"{EMOJI_IDEA} `/gyper profile_review` lets mods validate or purge scan data.",
        ],
    },
    {
        "name": "Community & Safety",
        "lines": [
            f"{EMOJI_LAUGH} `/gyper commands`, `/gyper features`, `/gyper about`, and `/gyper heroes` onboard new survivors fast.",
            f"{EMOJI_APPROVE} `/gyper feedback` routes reports to the handler without leaking server data.",
            f"{EMOJI_ANGRY} Channel ignore keeps silenced rooms dark; analytics stay locked to each server.",
        ],
    },
    {
        "name": "Admin Toolkit",
        "lines": [
            f"{EMOJI_CONFIDENT} `/gyper setup` links channels + auto-role; `/gyper refresh_commands` re-syncs slash commands.",
            f"{EMOJI_IDEA} `/gyper analytics` gives per-server usage snapshots and trading depth.",
        ],
    },
]

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger("MarciaOS.Utility")
        self._app_owner = None
        self._feedback_owner = None
        self._feedback_dedupe: dict[tuple, float] = {}
        self._share_link = "https://bit.ly/49z28IZ"
        self._about_cache: dict[str | None, discord.Embed] = {}

    async def _safe_send(self, ctx, *, ephemeral: bool = False, **kwargs):
        """Send a response for both message and slash contexts without double-acking."""

        interaction = getattr(ctx, "interaction", None)
        if interaction:
            return await self.bot._safe_interaction_reply(
                interaction, ephemeral=ephemeral, **kwargs
            )

        kwargs.pop("ephemeral", None)
        return await ctx.send(**kwargs)

    async def _translate_text(self, text: str, dest: str) -> str:
        """Translate text using the public googleapis endpoint without googletrans."""
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": dest,
            "dt": "t",
            "q": text,
        }

        try:
            response = await self.bot.http.request(
                "translate",
                "GET",
                "https://translate.googleapis.com/translate_a/single",
                params=params,
                retries=2,
                safe=True,
            )
            response.raise_for_status()
        except CircuitBreakerOpen as exc:
            self.log.warning("Translate skipped: %s", exc)
            raise
        except Exception as exc:
            self.log.warning("Translate request failed: %s", exc)
            raise

        payload = response.json()
        # API returns [[['translated sentence', 'original sentence', ...], ...], ...]
        translated_chunks = payload[0]
        return "".join(chunk[0] for chunk in translated_chunks if chunk and chunk[0])

    # --------------------
    # Shared builders
    # --------------------
    async def _resolve_owner_user(self) -> Optional[discord.abc.User]:
        """Return the application owner or team owner for DM relays."""
        if self._app_owner:
            return self._app_owner

        try:
            info = await self.bot.application_info()
            owner = info.owner or (info.team.owner if info.team else None)
            if owner:
                self._app_owner = owner
            return owner
        except Exception as exc:
            self.log.warning("Owner lookup failed: %s", exc)
            return None

    async def _resolve_feedback_owner(self) -> Optional[discord.abc.User]:
        """Resolve akrott for feedback relays."""
        if self._feedback_owner:
            return self._feedback_owner

        target_name = "akrott"
        cached_user = discord.utils.find(
            lambda u: getattr(u, "name", "").lower() == target_name,
            self.bot.users,
        )
        if cached_user:
            self._feedback_owner = cached_user
            return cached_user

        for guild in self.bot.guilds:
            member = discord.utils.find(
                lambda m: getattr(m, "name", "").lower() == target_name,
                guild.members,
            )
            if member:
                self._feedback_owner = member
                return member

        owner = await self._resolve_owner_user()
        if owner and getattr(owner, "name", "").lower() == target_name:
            self._feedback_owner = owner
            return owner

        return owner

    def _build_about_embed(
        self,
        guild_name: Optional[str],
        owner_label: str,
    ) -> discord.Embed:
        """Brief intro, purpose, and highlights for Marcia."""
        scope = guild_name or "your sector"
        embed = discord.Embed(
            title="🛰️ About Marcia OS",
            description=(
                "Marcia is a tactical operations bot built to keep alliances coordinated, loud chaos quiet, "
                "and mission intel on time. Think of me as your command center for Dark War: Survival."
            ),
            color=0x5865F2,
        )
        embed.add_field(
            name="Why I exist",
            value=(
                "I was created to give crews a reliable command center: clean scheduling, opt-in reminders, "
                "inventory tracking, and readable stats-without leaking data across servers."
            ),
            inline=False,
        )
        embed.add_field(
            name="Feature snapshot",
            value=self._fit_embed_lines([f"• {line}" for line in MARCIA_CAPABILITIES]),
            inline=False,
        )
        embed.add_field(
            name="Personality Snapshot",
            value=self._fit_embed_lines([f"• {t}" for t in MARCIA_TRAITS[:6]]),
            inline=False,
        )
        embed.add_field(
            name="Signals & Support",
            value=(
                f"Owner: {owner_label}\n"
                "Contact: use `/gyper feedback` or DM the owner\n"
                f"Invite link: {self._share_link}\n"
                "Support station (keeps the uptime running): https://www.buymeacoffee.com/akrot\n"
                "Official server: https://discord.gg/tuWX4sVR4Y"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Sector: {scope} | Data never leaves your guild")
        return embed

    def _get_about_embed(self, guild_name: Optional[str], owner_label: str) -> discord.Embed:
        """Return a cached about embed for static content."""
        cache_key = guild_name or "your sector"
        cached = self._about_cache.get(cache_key)
        if cached:
            return cached
        built = self._build_about_embed(guild_name, owner_label)
        self._about_cache[cache_key] = built
        return built

    @staticmethod
    def _fit_embed_lines(lines: list[str], max_len: int = 1024) -> str:
        rendered: list[str] = []
        total = 0
        for line in lines:
            candidate = line if not rendered else f"\n{line}"
            if total + len(candidate) > max_len:
                if not rendered:
                    return line[: max_len - 1] + "…"
                break
            rendered.append(line)
            total += len(candidate)
        return "\n".join(rendered) if rendered else "-"

    def _build_featureboard(self, guild_name: Optional[str] = None) -> discord.Embed:
        """Readable feature grid to pair with the showcase section."""
        scope = guild_name or "your sector"
        embed = discord.Embed(
            title=f"{EMOJI_CONFIDENT} Marcia OS | Featureboard",
            description=(
                f"Quick, easy-to-read menu of everything Marcia does. Tap any section to explore {EMOJI_ADORE}"
            ),
            color=0x5865F2,
        )
        embed.add_field(
            name="Operations",
            value="\n".join([
                f"• {EMOJI_IDEA} `/gyper event` (with upcoming ops + removal) for UTC-2 planning",
                f"• {EMOJI_CONFIDENT} `/gyper remind` with templates, schedule, and immediate blasts",
                f"• {EMOJI_APPROVE} `/gyper analytics` for usage, wiring, and activity snapshots",
            ]),
            inline=False,
        )
        embed.add_field(
            name="Community & Safety",
            value="\n".join([
                f"• {EMOJI_ANGRY} Channel ignore keeps blacked-out rooms fully silent",
                f"• {EMOJI_LAUGH} `/gyper commands`, `/gyper features`, `/gyper about` to onboard crews",
                f"• {EMOJI_APPROVE} `/gyper feedback` to ping my handler without leaking server data",
            ]),
            inline=False,
        )
        embed.add_field(
            name="Economy & Progression",
            value="\n".join([
                f"• {EMOJI_ADORE} Trading terminal with persistent Fish-Link inventory",
                f"• {EMOJI_CONFIDENT} `/gyper scavenge`, `/gyper inventory`, `/gyper leaderboard` (10/25/50/100 rows + export)",
                f"• {EMOJI_SMUG} Profile scans: `/gyper scan` in DMs to log profile/duel stats",
                f"• {EMOJI_ANGRY} Per-guild analytics; nothing crosses sectors",
            ]),
            inline=False,
        )
        embed.set_footer(text=f"Sector: {scope} | Clock: UTC-2 | Personality: spicy {EMOJI_SMUG}")
        return embed

    def _build_command_directory(self, guild_name: Optional[str] = None) -> discord.Embed:
        """Return a consistent command directory embed for both text and slash calls."""
        categories = [
            (
                "Quick start",
                [
                    "`/gyper scavenge` • deploy a drone",
                    "`/gyper inventory` • check your stash",
                    "`/gyper event` • see what's scheduled",
                    "`/gyper profile` | `/gyper leaderboard`",
                ],
            ),
            (
                "Events & ops",
                [
                    "`/gyper event` • plan ops + upcoming list + removal",
                    "`/gyper remind` • channel reminder",
                    "`/gyper remindme` • DM timer",
                    "`/gyper analytics` • usage snapshot",
                ],
            ),
            (
                "Trading",
                [
                    "`/gyper setup_trade` • deploy Fish-Link",
                    "Buttons: Spares / Find listings",
                    "Per-server inventory; no cross-bleed",
                ],
            ),
            (
                "Profile scans",
                [
                    "`/gyper scan` • scan a screenshot in DMs",
                    "`/gyper leaderboard` • XP + CP/Kills with export",
                ],
            ),
            (
                "Utility & safety",
                [
                    "`/gyper features` + `/gyper about` + `/gyper heroes`",
                    "`/gyper feedback` • ping handler",
                    "`/gyper clear` • purge",
                ],
            ),
            (
                "Admin (UTC-2 clock)",
                [
                    "`/gyper setup` • channel links + setup help",
                    "`/gyper refresh_commands` • resync slash",
                ],
            ),
        ]

        embed = discord.Embed(
            title="🛠️ Marcia OS | Command Directory",
            description="Commands are independent-type the one you want to use.",
            color=0x3498db,
        )
        for title, cmd_list in categories:
            embed.add_field(name=f"📌 {title}", value="\n".join(cmd_list), inline=False)

        scope = guild_name or "your sector"
        embed.set_footer(text=f"Marcia OS v3.0 | Sector: {scope}")
        return embed

    async def _submit_feedback(self, ctx, feedback_text: str, category: Optional[str]):
        """Persist feedback, notify the owner, and acknowledge the user."""
        category_label = (category or "general").strip() or "general"
        packaged = f"[{category_label}] {feedback_text}".strip()

        interaction_id = getattr(getattr(ctx, "interaction", None), "id", None)
        message_id = getattr(getattr(ctx, "message", None), "id", None)
        dedupe_key = (
            ctx.guild.id if ctx.guild else None,
            ctx.author.id,
            interaction_id or message_id,
            packaged,
        )
        now = datetime.now(timezone.utc).timestamp()
        for key, timestamp in list(self._feedback_dedupe.items()):
            if now - timestamp > 10:
                self._feedback_dedupe.pop(key, None)
        if dedupe_key in self._feedback_dedupe:
            return
        self._feedback_dedupe[dedupe_key] = now

        guild_id = ctx.guild.id if ctx.guild else None
        channel_id = ctx.channel.id if getattr(ctx, "channel", None) else None
        user_id = ctx.author.id if getattr(ctx, "author", None) else None

        await log_feedback_entry(guild_id, user_id, channel_id, packaged)

        owner = await self._resolve_feedback_owner()
        if owner:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            embed = discord.Embed(
                title="📮 New Feedback Packet",
                description=feedback_text,
                color=0x2ecc71,
            )
            embed.add_field(name="Category", value=category_label.title(), inline=True)
            embed.add_field(name="Received", value=timestamp, inline=True)
            if ctx.guild:
                embed.add_field(name="Guild", value=f"{ctx.guild.name} ({ctx.guild.id})", inline=True)
            embed.add_field(
                name="Sender",
                value=f"{ctx.author} ({ctx.author.id}) | Mention: {ctx.author.mention}",
                inline=False,
            )
            if channel_id:
                channel_label = f"{getattr(ctx.channel, 'name', 'unknown')} ({channel_id})"
                embed.add_field(name="Channel", value=channel_label, inline=True)
            try:
                await owner.send(embed=embed)
            except Exception as exc:
                self.log.warning("Feedback DM failed: %s", exc)

        ack = (
            "💙 **Thanks for the feedback.** I logged it, tagged the handler, and routed it safely. "
            "If it’s a good idea, it stays. If it’s a bug, it dies."
        )
        await self._safe_send(ctx, content=ack)

    def _build_showcase_embed(self, guild_name: Optional[str] = None) -> discord.Embed:
        """
        Return a consolidated showcase of Marcia's systems.

        The copy mirrors docs/SHOWCASE.md to keep Discord help embeds aligned with the
        reference screenshot/documentation. Update SHOWCASE_SECTIONS if features
        are added/removed so both stay in sync.
        """
        embed = discord.Embed(
            title="🛰️ Marcia OS | Showcase",
            color=0x5865F2,
            description="Freedom is expensive. Don't waste my time for free. - Marcia",
        )

        for section in SHOWCASE_SECTIONS:
            embed.add_field(
                name=section["name"],
                value="\n".join(section["lines"]),
                inline=False,
            )

        scope = guild_name or "your sector"
        embed.set_footer(text=f"Built for Dark War Survival alliances | Sector: {scope} | Clock: UTC-2")
        return embed

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Translation Matrix: React with a flag to translate a message."""
        emoji = str(payload.emoji)
        if emoji not in FLAG_LANG:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(payload.channel_id)
            except discord.HTTPException as e:
                self.log.warning("Translation channel fetch failed: %s", e)
                return

        try:
            msg = await channel.fetch_message(payload.message_id)
        except discord.HTTPException as e:
            self.log.warning("Translation message fetch failed: %s", e)
            return

        if not msg.content:
            return

        if msg.author.bot:
            return

        dest = FLAG_LANG[emoji]
        try:
            translated = await self._translate_text(msg.content, dest)
            await msg.reply(f"📡 **DECODED [{dest.upper()}]:**\n{translated}", mention_author=False)
            await increment_activity_metric(msg.guild.id if msg.guild else None, "translations")
        except Exception as e:
            self.log.warning("Translation Error: %s", e)
            await msg.reply(
                "⚠️ Translation uplink failed. Try again in a moment or pick another flag.",
                mention_author=False,
            )

    @commands.hybrid_command(
        name="commands",
        aliases=["help"],
        description="View a categorized directory of all active commands.",
    )
    async def list_commands(self, ctx):
        """Displays all available commands categorized by module."""
        embed = self._build_command_directory(ctx.guild.name if ctx.guild else None)
        await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(description="Learn what Marcia is, why she exists, and how to support uptime.")
    async def about(self, ctx):
        """Share Marcia's lore and promise to the guild."""
        owner_label = "akrott"
        embed = self._get_about_embed(ctx.guild.name if ctx.guild else None, owner_label)
        await self._safe_send(ctx, embed=embed)


    @commands.hybrid_command(
        description="Store feedback and DM it to the bot owner.",
    )
    @app_commands.describe(message="What do you want to report?", category="bug, idea, praise, or anything else")
    async def feedback(self, ctx, *, message: str, category: Optional[str] = None):
        await self._submit_feedback(ctx, message, category)

    @commands.hybrid_command(description="Random survival and bot tips from Marcia.")
    async def tips(self, ctx):
        """Random survival tips and bot tricks."""
        tips_list = [
            "Use `/gyper remindme 60 Prepare for War` to get a DM in one hour.",
            "Mission timers run on Dark War Survival time (UTC-2).",
            "Pin Fish-Link with `/gyper setup_trade` so traders can move fast without spam.",
            "Use `/gyper remind` to schedule reminders or save templates for rapid ops pings.",
            "Run `/gyper event` to stage ops with a codename, location, and optional role ping.",
            "Need proof of power? `/gyper scan` DMs you scan options to update `/gyper profile` and `/gyper leaderboard` stats.",
            "Inventory is sector-locked-`/gyper inventory` only shows loot from this server.",
            "Clear stale drops with `/gyper clear` instead of manual pruning.",
            "Use `/gyper features` or `/gyper commands` to onboard new survivors in seconds.",
            "Keep a calm event channel-Marcia formats reminders so chatter stays low.",
            "Check `/gyper leaderboard` exports if you need a TSV for spreadsheets.",
            "Use `/gyper feedback` to report bugs or ideas without leaking server intel.",
            "Browse `/gyper heroes` when you need a quick dossier before upgrades."
        ]
        await ctx.reply(f"💡 **TIP:** {random.choice(tips_list)}")

    @commands.hybrid_command(
        name="refresh_commands",
        description="Force-refresh slash commands if Discord desyncs them.",
    )
    @commands.has_permissions(manage_guild=True)
    async def refresh_commands(self, ctx):
        """Allow admins to re-sync slash commands without restarting the bot."""
        if getattr(ctx, "interaction", None):
            await ctx.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
        except Exception as e:
            await self._safe_send(ctx, content=f"❌ Sync failed: `{e}`", ephemeral=True)
            return

        await self._safe_send(
            ctx,
            content=f"📡 Command uplink refreshed. Registered `{len(synced)}` slash commands.",
            ephemeral=True,
        )

    @commands.hybrid_command(
        description="Quick, easy-to-read menu of Marcia's features.",
    )
    async def features(self, ctx):
        """Showcase Marcia's capabilities for new crews."""
        embed = self._build_showcase_embed(ctx.guild.name if ctx.guild else None)
        featureboard = self._build_featureboard(ctx.guild.name if ctx.guild else None)
        await self._safe_send(ctx, embeds=[featureboard, embed])


    async def _build_analytics_embed(self, guild: discord.Guild) -> discord.Embed:
        snapshot = await guild_analytics_snapshot(guild.id)
        xp_rows = await top_xp_leaderboard(guild.id, limit=5)
        cp_rows = await top_profile_stat(guild.id, "cp", limit=5)
        kill_rows = await top_profile_stat(guild.id, "kills", limit=5)

        embed = discord.Embed(
            title="📊 Sector Analytics",
            description="Fun stats, live counts, and leaderboard slices for this server only.",
            color=0x5865F2,
        )
        embed.add_field(name="🎣 Trading Listings", value=str(snapshot["trade_listings"]), inline=True)
        embed.add_field(name="👥 Active Traders", value=str(snapshot["traders"]), inline=True)
        embed.add_field(name="🛰️ Missions Running", value=str(snapshot["missions_active"]), inline=True)
        embed.add_field(name="📂 Templates Saved", value=str(snapshot["templates"]), inline=True)
        embed.add_field(name="🧭 Survivors Tracked", value=str(snapshot["survivors_tracked"]), inline=True)
        embed.add_field(name="🎒 Items Logged", value=str(snapshot["items"]), inline=True)

        if xp_rows:
            lines = []
            for idx, row in enumerate(xp_rows, start=1):
                member = guild.get_member(row["user_id"])
                name = member.display_name if member else f"User {row['user_id']}"
                lines.append(f"**{idx}. {name}** - L{row['level']} | {row['xp']:,} XP")
            embed.add_field(name="🏆 Top XP", value="\n".join(lines), inline=False)

        if cp_rows:
            lines = []
            for idx, row in enumerate(cp_rows, start=1):
                member = guild.get_member(row["user_id"])
                name = row["player_name"] or (member.display_name if member else f"User {row['user_id']}")
                lines.append(f"**{idx}. {name}** - {row['value']:,} CP")
            embed.add_field(name="⚔️ Top Combat Power", value="\n".join(lines), inline=False)

        if kill_rows:
            lines = []
            for idx, row in enumerate(kill_rows, start=1):
                member = guild.get_member(row["user_id"])
                name = row["player_name"] or (member.display_name if member else f"User {row['user_id']}")
                lines.append(f"**{idx}. {name}** - {row['value']:,} Kills")
            embed.add_field(name="☠️ Top Kills", value="\n".join(lines), inline=False)

        embed.set_footer(text="Clock: UTC-2 | Data never crosses sectors.")
        return embed

    @commands.hybrid_command(description="Per-server analytics, fun stats, and leaderboard slices.")
    async def analytics(self, ctx):
        """Detailed per-server analytics for the current server."""
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Analytics are only available inside servers.",
                ephemeral=True,
            )
        embed = await self._build_analytics_embed(ctx.guild)
        view = AnalyticsView(self, ctx.guild)
        await self._safe_send(ctx, embed=embed, view=view)

    @commands.hybrid_command(
        description="Network-wide stats, fun counts, and popularity snapshot.",
    )
    async def network(self, ctx):
        """Shows global XP leaders, server usage, and top commands."""
        xp_rows = await top_global_xp(5)
        usage_rows = await top_guild_usage(5)
        command_rows = await top_commands(5)
        total_guilds = len(self.bot.guilds)
        total_members = sum(guild.member_count or 0 for guild in self.bot.guilds)

        embed = discord.Embed(
            title="🌐 Network Pulse",
            description=(
                "Live signal from every connected sector. Share me with allies to climb these boards."
            ),
            color=0x5865F2,
        )
        embed.add_field(
            name="📡 Popularity Snapshot",
            value=f"Servers online: **{total_guilds}**\nTracked survivors: **{total_members:,}**",
            inline=False,
        )

        if xp_rows:
            lines = []
            for idx, row in enumerate(xp_rows, start=1):
                guild = self.bot.get_guild(row["guild_id"])
                guild_name = guild.name if guild else f"Guild {row['guild_id']}"
                user = self.bot.get_user(row["user_id"])
                handle = user.mention if user else f"<@{row['user_id']}>"
                lines.append(
                    f"{idx}. {handle} - {row['xp']} XP (L{row['level']} | {guild_name})"
                )
            embed.add_field(name="Top Survivors", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Top Survivors", value="No XP data yet.", inline=False)

        if usage_rows:
            usage_lines = []
            for idx, row in enumerate(usage_rows, start=1):
                guild = self.bot.get_guild(row["guild_id"])
                guild_name = guild.name if guild else f"Guild {row['guild_id']}"
                usage_lines.append(f"{idx}. {guild_name} - {row['total']} commands")
            embed.add_field(name="Server Usage", value="\n".join(usage_lines), inline=False)
        else:
            embed.add_field(name="Server Usage", value="No command traffic yet.", inline=False)

        if command_rows:
            cmd_lines = [f"`{row['command_name']}` - {row['total']} runs" for row in command_rows]
            embed.add_field(name="Most Used Commands", value="\n".join(cmd_lines), inline=False)
        else:
            embed.add_field(name="Most Used Commands", value="No command telemetry yet.", inline=False)

        embed.set_footer(text=f"Invite link: {self._share_link} | Commanders don't remind. Systems do.")
        await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(name="poll", description="Create a poll with up to five options.")
    @app_commands.describe(
        question="Poll question",
        option1="First option (optional)",
        option2="Second option (optional)",
        option3="Third option (optional)",
        option4="Fourth option (optional)",
        option5="Fifth option (optional)",
    )
    async def poll(
        self,
        ctx,
        question: str,
        option1: Optional[str] = None,
        option2: Optional[str] = None,
        option3: Optional[str] = None,
        option4: Optional[str] = None,
        option5: Optional[str] = None,
    ):
        options = [opt for opt in (option1, option2, option3, option4, option5) if opt]
        if len(options) == 1:
            return await self._safe_send(
                ctx,
                content="Add at least two options, or send none for a yes/no poll.",
                ephemeral=True,
            )

        interaction = getattr(ctx, "interaction", None)
        if not options:
            embed = discord.Embed(title="🗳️ POLL", description=question, color=0x00ffcc)
            if interaction:
                await self.bot._safe_interaction_reply(interaction, embed=embed)
                poll_message = await interaction.original_response()
            else:
                poll_message = await ctx.send(embed=embed)
            await poll_message.add_reaction("✅")
            await poll_message.add_reaction("❌")
            return

        reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        desc = "\n".join([f"{reactions[i]} {opt}" for i, opt in enumerate(options)])
        embed = discord.Embed(title=f"🗳️ {question}", description=desc, color=0x00ffcc)
        if interaction:
            await self.bot._safe_interaction_reply(interaction, embed=embed)
            poll_message = await interaction.original_response()
        else:
            poll_message = await ctx.send(embed=embed)
        for i in range(len(options)):
            await poll_message.add_reaction(reactions[i])

    @commands.hybrid_command(description="DM reminder after X minutes. /gyper remindme 10 Wake up")
    async def remindme(self, ctx, minutes: int, *, task: str):
        """Set a reminder. !remindme 10 Wake Up"""
        await self._safe_send(ctx, content=f"⏰ Affirmative. Reminder set for `{task}`.")
        await asyncio.sleep(minutes * 60)
        await ctx.author.send(f"🔔 **REMINDER:** {task}")

    @commands.hybrid_command(description="Clear a number of messages in this channel.")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 5):
        """Purge chat history."""
        if amount <= 0:
            return await self._safe_send(
                ctx,
                content="⚠️ Enter a number greater than zero.",
                ephemeral=True,
            )

        if amount > CLEAR_LIMIT:
            return await self._safe_send(
                ctx,
                content=f"⚠️ Max clear limit is {CLEAR_LIMIT} messages.",
                ephemeral=True,
            )

        if amount >= CLEAR_CONFIRM_THRESHOLD:
            embed = discord.Embed(
                title="🧹 Confirm Channel Clear",
                description=(
                    f"You're about to clear **{amount}** messages from {ctx.channel.mention}.\n"
                    "Confirm to proceed, or cancel to keep history intact."
                ),
                color=0x5865F2,
            )
            view = ClearConfirmView(self, ctx, amount)
            return await self._safe_send(ctx, embed=embed, view=view, ephemeral=True)

        await self._execute_clear(ctx, amount)

    async def _execute_clear(self, ctx, amount: int) -> None:
        deleted = await ctx.channel.purge(limit=amount + 1)
        cleared = max(0, len(deleted) - 1)
        self.log.info(
            "Clear executed by %s in %s (%s) for %s messages",
            ctx.author.id,
            ctx.guild.id if ctx.guild else "DM",
            ctx.channel.id,
            cleared,
        )
        await ctx.send(f"🧹 {cleared} signals cleared.", delete_after=3)


class AnalyticsView(discord.ui.View):
    def __init__(self, cog: Utility, guild: discord.Guild):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild = guild

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog._build_analytics_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=self)


class ClearConfirmView(discord.ui.View):
    def __init__(self, cog: Utility, ctx: commands.Context, amount: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.amount = amount

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="🧹")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._execute_clear(self.ctx, self.amount)
        await interaction.response.edit_message(
            content="✅ Clear complete.",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Clear cancelled.",
            embed=None,
            view=None,
        )

async def setup(bot):
    await bot.add_cog(Utility(bot))
