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
import httpx

from utils.assets import (
    MARCIA_CAPABILITIES,
    MARCIA_TRAITS,
)
from database import (
    get_settings,
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

# Single source of truth for the in-bot showcase. Keep this list aligned with docs/SHOWCASE.md
# so Discord users see the same capabilities advertised in documentation/screenshots.
SHOWCASE_SECTIONS = [
    {
        "name": "Lore Snapshot",
        "lines": [
            "Former underground hacker who now guards ops and data with her drone fleet (Sparky, Vulture-7, Ghost-Link).",
            "Protects refugees while keeping morale high with banter; rewards banshees with barbs if they break server safety.",
            "Keeps all survivor data isolated per server for security—no cross-pollination.",
            "Tracks scavenging streaks like war diaries; discipline earns the big hauls.",
        ],
    },
        {
            "name": "Core Systems",
            "lines": [
                "📡 Operations (UTC-2 clock): `/event`, `/setup`, `/status`, `/analytics`.",
                "🎣 Trading | Fish-Link: `/setup_trade` anchors the terminal; trade flows through buttons and profile/inventory views.",
                "🛰️ Progression & Scavenging: `/scavenge` with streak + overclock XP, `/leaderboard` exports, `/profile`, `/inventory`.",
                "🛰️ Profile Scan: `/scan_profile` intake configured via `/setup`; stats flow into `/profile` + `/leaderboard`.",
            ],
        },
    {
        "name": "Welcomes, Departures, & Automation",
        "lines": [
            "`/setup` links welcome/verify/rules and reminder channels; use `/setup` any time to review link status.",
            "Auto role: optional helper to assign a base role on join for visibility.",
            "Analytics dashboards summarize command usage so admins know what crews lean on most.",
        ],
    },
    {
            "name": "Command Directory (quick view)",
            "lines": [
                "Admin: `/setup`, `/setup_trade`, `/refresh_commands`, `/event`, `/analytics`, `/status`.",
                "Members: `/event` (upcoming ops), `/scavenge`, `/profile`, `/leaderboard`, `/inventory`, `/features`, `/commands`, `/heroes`.",
                "Profile scans: `/scan_profile`; `/leaderboard` export sends TSV to DM.",
                "Trading: Fish-Link buttons + trade access in `/profile` and `/inventory`.",
            ],
        },
    {
            "name": "How to Deploy",
            "lines": [
                "1) With Mod permissions, run `/setup` to link channels and auto-role in minutes.",
                "2) Launch `/setup_trade` in a trade channel to pin the Fish-Link terminal (seeded in SQLite for persistence).",
                "3) Run `/event` for mission planning; auto reminders are stored in SQLite with crash-safe WAL mode.",
                "4) Add event timers to `/scavenge` and trading to keep grind and swaps moving.",
            ],
        },
    {
        "name": "Data & Safety",
        "lines": [
            "Events, reminders, and trading data live in `marcia_os.db`; backups are WAL-friendly and seed data restores wiped hosts.",
            "Trade data is isolated per server; analytics and reminders never cross guild boundaries.",
        ],
    },
    {
        "name": "Tips for Server Admins",
        "lines": [
            "Use `/setup` before events to highlight missing channel links or permissions.",
            "Use `/status` for a fast signal check; `/analytics` shows per-server command usage and trading depth.",
            "Welcome, rules, and event channels can be kept minimal—Marcia formats reminders and guidance automatically.",
        ],
    },
]

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.http = httpx.AsyncClient(timeout=10.0)
        self.log = logging.getLogger("MarciaOS.Utility")
        self._app_owner = None
        self._feedback_owner = None
        self._share_link = "https://bit.ly/49z28IZ"

    async def cog_unload(self):
        await self.http.aclose()

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

        response = await self.http.get(
            "https://translate.googleapis.com/translate_a/single",
            params=params,
        )
        response.raise_for_status()

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
                "and mission intel on time."
            ),
            color=0x5865F2,
        )
        embed.add_field(
            name="Why I exist",
            value=(
                "I was created to give crews a reliable command center: clean scheduling, opt-in reminders, "
                "inventory tracking, and readable stats—without leaking data across servers."
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
                f"Invite link: {self._share_link}\n"
                "Support station (keeps the uptime running): https://www.buymeacoffee.com/akrot\n"
                "Official server: https://discord.gg/z9pdDMDgak"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Sector: {scope} | Data never leaves your guild")
        return embed

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
        return "\n".join(rendered) if rendered else "—"

    def _build_featureboard(self, guild_name: Optional[str] = None) -> discord.Embed:
        """Readable feature grid to pair with the showcase section."""
        scope = guild_name or "your sector"
        embed = discord.Embed(
            title="🗄️ Marcia OS | Featureboard",
            description="Pick a lane and I'll automate it. Everything stays siloed per guild.",
            color=0x9b59b6,
        )
        embed.add_field(
            name="Operations",
            value="\n".join([
                "• `/event` (with upcoming ops + removal) for UTC-2 planning",
                "• `/remind` with templates, schedule, and immediate blasts",
                "• `/status` & `/analytics` for uptime, wiring, and usage",
            ]),
            inline=False,
        )
        embed.add_field(
            name="Community & Safety",
            value="\n".join([
                "• Channel ignore keeps blacked-out rooms fully silent",
                "• `/commands`, `/features`, `/about` to onboard crews",
                "• `/feedback` to ping my handler without leaking server data",
            ]),
            inline=False,
        )
        embed.add_field(
            name="Economy & Progression",
            value="\n".join([
                "• Trading terminal with persistent Fish-Link inventory",
                "• `/scavenge`, `/inventory`, `/leaderboard` (10/25/50/100 rows + export)",
                "• Profile scans: `/scan_profile` (configure intake via `/setup`); caches uploads",
                "• Analytics per guild; nothing crosses sectors",
            ]),
            inline=False,
        )
        embed.set_footer(text=f"Sector: {scope} | Clock: UTC-2 | Personality: spicy")
        return embed

    def _build_command_directory(self, guild_name: Optional[str] = None) -> discord.Embed:
        """Return a consistent command directory embed for both text and slash calls."""
        categories = [
            (
                "Quick start",
                [
                    "`/scavenge` • deploy a drone",
                    "`/inventory` • check your stash",
                    "`/event` • see what's scheduled",
                    "`/profile` | `/leaderboard`",
                ],
            ),
            (
                "Events & ops",
                [
                    "`/event` • plan ops + upcoming list + removal",
                    "`/remind` • channel reminder",
                    "`/remindme` • DM timer",
                    "`/status` • quick signal | `/analytics`",
                ],
            ),
            (
                "Trading",
                [
                    "`/setup_trade` • deploy Fish-Link",
                    "Buttons: Spares / Find listings",
                    "Per-server inventory; no cross-bleed",
                ],
            ),
            (
                "Profile scans",
                [
                    "`/scan_profile` • scan a screenshot",
                    "`/leaderboard` • XP + CP/Kills with export",
                ],
            ),
            (
                "Utility & safety",
                [
                    "`/features` + `/about` + `/heroes`",
                    "`/feedback` • ping handler",
                    "`/clear` • purge",
                ],
            ),
            (
                "Admin (UTC-2 clock)",
                [
                    "`/setup` • channel links + setup help",
                    "`/refresh_commands` • resync slash",
                ],
            ),
        ]

        embed = discord.Embed(
            title="🛠️ Marcia OS | Command Directory",
            description="Pick a section, tap a command. Everything below is slash-friendly.",
            color=0x3498db,
        )
        for title, cmd_list in categories:
            embed.add_field(name=f"📌 {title}", value="\n".join(cmd_list), inline=False)

        scope = guild_name or "your sector"
        embed.set_footer(text=f"Marcia OS v3.0 | Sector: {scope}")
        return embed

    def _build_command_center_embed(self, section: str, guild_name: Optional[str] = None) -> discord.Embed:
        scope = guild_name or "your sector"
        section_key = section.lower()
        sections = {
            "home": {
                "title": "🧭 Marcia Command Center",
                "description": "Everything is here, categorized. Tap a menu button to jump around.",
                "fields": [
                    ("How to use this", "Pick a category button. Each panel lists commands with a short, clear purpose."),
                    ("Why it’s shorter now", "Fewer commands, same power. You only need to remember the menu."),
                ],
            },
            "daily ops": {
                "title": "⚡ Daily Ops",
                "description": "Your core loop: loot, stash, progress, compare.",
                "fields": [
                    ("Command list", "\n".join([
                        "`/scavenge` — run an hourly loot + XP mission",
                        "`/inventory` — view your stash",
                        "`/profile` — XP, stash, and scan summary",
                        "`/leaderboard` — XP + scan stats menu",
                    ])),
                ],
            },
            "events": {
                "title": "🛰️ Events & Reminders",
                "description": "Schedule ops, ping once, DM the rest.",
                "fields": [
                    ("Command list", "\n".join([
                        "`/event` — schedule, view, or remove upcoming ops",
                        "`/remind` — send/schedule reminders + manage templates",
                        "`/remindme` — personal DM timer",
                    ])),
                ],
            },
            "trading": {
                "title": "🎣 Trading",
                "description": "Fish-Link stays anchored in one channel.",
                "fields": [
                    ("Command list", "\n".join([
                        "`/setup_trade` — pin the Fish-Link terminal (admins)",
                        "Fish-Link buttons — Add Spare / Find Fish / Who Has My Wanted",
                        "Trade access — open from `/profile` or `/inventory`",
                    ])),
                ],
            },
            "profiles": {
                "title": "🛰️ Profiles & Scans",
                "description": "Capture scans and keep stats clean.",
                "fields": [
                    ("Command list", "\n".join([
                        "`/scan_profile` — upload a profile screenshot",
                        "`/profile_review` — admin review of scans",
                        "`/ocr_status` — OCR diagnostics (admins)",
                    ])),
                ],
            },
            "admin": {
                "title": "🛡️ Setup & Admin",
                "description": "Link channels, check health, and clean up chat.",
                "fields": [
                    ("Command list", "\n".join([
                        "`/setup` — select a feature and link its channel",
                        "`/status` — system diagnostics",
                        "`/analytics` — server stats for everyone",
                        "`/refresh_commands` — resync slash commands",
                        "`/clear` — purge messages (admins)",
                        "`/import_old_levels` — legacy XP migration (text command)",
                    ])),
                ],
            },
            "support": {
                "title": "📚 Support & Fun",
                "description": "Onboarding, feedback, and global signals.",
                "fields": [
                    ("Guides", "\n".join([
                        "`/commands` — this directory",
                        "`/features` — showcase",
                        "`/heroes` — hero codex",
                        "`/about` — why Marcia exists",
                    ])),
                    ("Extras", "\n".join([
                        "`/feedback` — report ideas or bugs",
                        "`/tips` — survival tips",
                        "`/poll` — quick polls",
                        "`/network` — global pulse",
                    ])),
                ],
            },
        }

        selected = sections.get(section_key, sections["home"])
        embed = discord.Embed(
            title=selected["title"],
            description=selected["description"],
            color=0x3498db,
        )
        for name, value in selected["fields"]:
            embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text=f"Marcia OS v3.0 | Sector: {scope} | Menu: {selected['title']}")
        return embed

    async def _submit_feedback(self, ctx, feedback_text: str, category: Optional[str]):
        """Persist feedback, notify the owner, and acknowledge the user."""
        category_label = (category or "general").strip() or "general"
        packaged = f"[{category_label}] {feedback_text}".strip()

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
            color=0x9b59b6,
            description="Freedom is expensive. Don't waste my time for free. — Marcia",
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

    @commands.hybrid_command(name="commands", aliases=["help"], description="Show Marcia's command directory.")
    async def list_commands(self, ctx):
        """Displays all available commands categorized by module."""
        embed = self._build_command_center_embed("home", ctx.guild.name if ctx.guild else None)
        view = CommandCenterView(self, ctx.guild.name if ctx.guild else None)
        await self._safe_send(ctx, embed=embed, view=view)

    @commands.hybrid_command(description="Marcia's lore, values, and operating scope.")
    async def about(self, ctx):
        """Share Marcia's lore and promise to the guild."""
        owner_label = "akrott"
        embed = self._build_about_embed(ctx.guild.name if ctx.guild else None, owner_label)
        await self._safe_send(ctx, embed=embed)


    @commands.hybrid_command(description="Send feedback, ideas, or bug reports to my handler.")
    @app_commands.describe(message="What do you want to report?", category="bug, idea, praise, or anything else")
    async def feedback(self, ctx, *, message: str, category: Optional[str] = None):
        await self._submit_feedback(ctx, message, category)

    @commands.hybrid_command(description="Random survival and bot tips from Marcia.")
    async def tips(self, ctx):
        """Random survival tips and bot tricks."""
        tips_list = [
            "You can use `/remindme 60 Prepare for War` and I will DM you in one hour.",
            "Mission timers use the Dark War Survival clock (UTC-2) across every server.",
            "The Trading Terminal is server-specific. You won't see fish from other servers here!",
            "Try `/heroes` for the hero codex and `/features` for the full showcase."
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
            await ctx.reply(f"❌ Sync failed: `{e}`", mention_author=False)
            return

        await ctx.reply(
            f"📡 Command uplink refreshed. Registered `{len(synced)}` slash commands.",
            mention_author=False,
        )

    @commands.hybrid_command(description="Showcase Marcia's capabilities for new crews.")
    async def features(self, ctx):
        """Showcase Marcia's capabilities for new crews."""
        embed = self._build_showcase_embed(ctx.guild.name if ctx.guild else None)
        featureboard = self._build_featureboard(ctx.guild.name if ctx.guild else None)
        await self._safe_send(ctx, embeds=[featureboard, embed])

    @commands.hybrid_command(description="System diagnostic and latency check.")
    async def status(self, ctx):
        """System diagnostic and latency check."""
        latency = round(self.bot.latency * 1000)
        settings = await get_settings(ctx.guild.id)

        embed = discord.Embed(title="📡 System Diagnostic", color=0x2ecc71)
        embed.add_field(name="Signal Latency", value=f"🟢 {latency}ms")
        embed.add_field(name="Databank", value="🔵 SQL Stable")
        embed.add_field(
            name="Sectors Linked",
            value=(
                "✅ Event" if settings and settings.get('event_channel_id') else "❌ Event missing"
            ) + " | " + (
                "✅ Chat" if settings and settings.get('chat_channel_id') else "❌ Chat missing"
            ),
            inline=False,
        )
        embed.add_field(
            name="⏱️ Server Clock",
            value="UTC-2 (Dark War Survival global time)",
            inline=False,
        )
        embed.set_footer(text="Need a deeper check? Open /setup to review linked channels.")
        await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(description="Per-server analytics and fun stats.")
    async def analytics(self, ctx):
        """Detailed per-server analytics for the current server."""
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Analytics are only available inside servers.",
                ephemeral=True,
            )
        snapshot = await guild_analytics_snapshot(ctx.guild.id)
        xp_rows = await top_xp_leaderboard(ctx.guild.id, limit=5)
        cp_rows = await top_profile_stat(ctx.guild.id, "cp", limit=5)
        kill_rows = await top_profile_stat(ctx.guild.id, "kills", limit=5)

        embed = discord.Embed(
            title="📊 Sector Analytics",
            description="Fun stats, live counts, and leaderboard slices for this server only.",
            color=0x9b59b6,
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
                member = ctx.guild.get_member(row["user_id"])
                name = member.display_name if member else f"User {row['user_id']}"
                lines.append(f"**{idx}. {name}** — L{row['level']} | {row['xp']:,} XP")
            embed.add_field(name="🏆 Top XP", value="\n".join(lines), inline=False)

        if cp_rows:
            lines = []
            for idx, row in enumerate(cp_rows, start=1):
                member = ctx.guild.get_member(row["user_id"])
                name = row["player_name"] or (member.display_name if member else f"User {row['user_id']}")
                lines.append(f"**{idx}. {name}** — {row['value']:,} CP")
            embed.add_field(name="⚔️ Top Combat Power", value="\n".join(lines), inline=False)

        if kill_rows:
            lines = []
            for idx, row in enumerate(kill_rows, start=1):
                member = ctx.guild.get_member(row["user_id"])
                name = row["player_name"] or (member.display_name if member else f"User {row['user_id']}")
                lines.append(f"**{idx}. {name}** — {row['value']:,} Kills")
            embed.add_field(name="☠️ Top Kills", value="\n".join(lines), inline=False)

        embed.set_footer(text="Clock: UTC-2 | Data never crosses sectors.")

        await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(description="Global network leaderboard and usage pulse.")
    async def network(self, ctx):
        """Shows global XP leaders, server usage, and top commands."""
        xp_rows = await top_global_xp(5)
        usage_rows = await top_guild_usage(5)
        command_rows = await top_commands(5)

        embed = discord.Embed(
            title="🌐 Network Pulse",
            description=(
                "Live signal from every connected sector. Share me with allies to climb these boards."
            ),
            color=0x5865F2,
        )

        if xp_rows:
            lines = []
            for idx, row in enumerate(xp_rows, start=1):
                guild = self.bot.get_guild(row["guild_id"])
                guild_name = guild.name if guild else f"Guild {row['guild_id']}"
                user = self.bot.get_user(row["user_id"])
                handle = user.mention if user else f"<@{row['user_id']}>"
                lines.append(
                    f"{idx}. {handle} — {row['xp']} XP (L{row['level']} | {guild_name})"
                )
            embed.add_field(name="Top Survivors", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Top Survivors", value="No XP data yet.", inline=False)

        if usage_rows:
            usage_lines = []
            for idx, row in enumerate(usage_rows, start=1):
                guild = self.bot.get_guild(row["guild_id"])
                guild_name = guild.name if guild else f"Guild {row['guild_id']}"
                usage_lines.append(f"{idx}. {guild_name} — {row['total']} commands")
            embed.add_field(name="Server Usage", value="\n".join(usage_lines), inline=False)
        else:
            embed.add_field(name="Server Usage", value="No command traffic yet.", inline=False)

        if command_rows:
            cmd_lines = [f"`{row['command_name']}` — {row['total']} runs" for row in command_rows]
            embed.add_field(name="Most Used Commands", value="\n".join(cmd_lines), inline=False)
        else:
            embed.add_field(name="Most Used Commands", value="No command telemetry yet.", inline=False)

        embed.set_footer(text=f"Invite link: {self._share_link} | Commanders don't remind. Systems do.")
        await self._safe_send(ctx, embed=embed)

    @commands.command(description="Create a poll. /poll 'Title' option1 option2 ...")
    async def poll(self, ctx, question: str, *options):
        """Message-based polls with up to 10 options."""
        if not options:
            msg = await ctx.send(embed=discord.Embed(title="🗳️ POLL", description=question, color=0x00ffcc))
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            return

        if len(options) > 10:
            return await ctx.send("Limit 10.")

        reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        desc = "\n".join([f"{reactions[i]} {opt}" for i, opt in enumerate(options)])
        msg = await ctx.send(embed=discord.Embed(title=f"🗳️ {question}", description=desc, color=0x00ffcc))
        for i in range(len(options)):
            await msg.add_reaction(reactions[i])

    @app_commands.command(name="poll", description="Create a poll with up to five options.")
    @app_commands.describe(
        question="Poll question",
        option1="First option",
        option2="Second option",
        option3="Third option (optional)",
        option4="Fourth option (optional)",
        option5="Fifth option (optional)",
    )
    async def slash_poll(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: Optional[str] = None,
        option4: Optional[str] = None,
        option5: Optional[str] = None,
    ):
        options = [option1, option2]
        for opt in (option3, option4, option5):
            if opt:
                options.append(opt)

        reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        desc = "\n".join([f"{reactions[i]} {opt}" for i, opt in enumerate(options)])
        embed = discord.Embed(title=f"🗳️ {question}", description=desc, color=0x00ffcc)
        await interaction.response.send_message(embed=embed)
        poll_message = await interaction.original_response()
        for i in range(len(options)):
            await poll_message.add_reaction(reactions[i])

    @commands.hybrid_command(description="DM reminder after X minutes. /remindme 10 Wake up")
    async def remindme(self, ctx, minutes: int, *, task: str):
        """Set a reminder. !remindme 10 Wake Up"""
        await self._safe_send(ctx, content=f"⏰ Affirmative. Reminder set for `{task}`.")
        await asyncio.sleep(minutes * 60)
        await ctx.author.send(f"🔔 **REMINDER:** {task}")

    @commands.hybrid_command(description="Purge chat history (admins).")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 5):
        """Purge chat history."""
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 {amount} signals cleared.", delete_after=3)


class CommandCenterView(discord.ui.View):
    def __init__(self, cog: Utility, guild_name: Optional[str]):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_name = guild_name

    async def _switch(self, interaction: discord.Interaction, section: str):
        embed = self.cog._build_command_center_embed(section, self.guild_name)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Home", style=discord.ButtonStyle.secondary, emoji="🧭")
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, "home")

    @discord.ui.button(label="Daily Ops", style=discord.ButtonStyle.primary, emoji="⚡")
    async def quick_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, "daily ops")

    @discord.ui.button(label="Events", style=discord.ButtonStyle.secondary, emoji="🛰️")
    async def events(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, "events")

    @discord.ui.button(label="Trading", style=discord.ButtonStyle.success, emoji="🎣")
    async def trading(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, "trading")

    @discord.ui.button(label="Profiles", style=discord.ButtonStyle.secondary, emoji="🧬")
    async def profiles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, "profiles")

    @discord.ui.button(label="Admin", style=discord.ButtonStyle.danger, emoji="🛡️")
    async def admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, "admin")

    @discord.ui.button(label="Support", style=discord.ButtonStyle.secondary, emoji="📚")
    async def support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, "support")

async def setup(bot):
    await bot.add_cog(Utility(bot))
