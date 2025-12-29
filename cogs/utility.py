"""
FILE: cogs/utility.py
USE: General helper functions, information, and interactive dialogue.
FEATURES: Flag-based translation, Polls, Reminders, and Marcia Manuals.
"""
import asyncio
import logging
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
import httpx

from assets import MARICA_LORE, INTEL_DATABASE
from database import get_settings, guild_analytics_snapshot

# Expanded Language Library
FLAG_LANG = {
    "🇺🇸": "en", "🇬🇧": "en", "🇦🇺": "en", "🇨🇦": "en",
    "🇫🇷": "fr", "🇪🇸": "es", "🇩🇪": "de", "🇮🇹": "it", "🇵🇹": "pt", "🇳🇱": "nl", "🇷🇺": "ru",
    "🇯🇵": "ja", "🇰🇷": "ko", "🇨🇳": "zh-cn", "🇻🇳": "vi", "🇹🇭": "th",
    "🇦🇪": "ar", "🇹🇷": "tr", "🇮🇳": "hi", "🇧🇷": "pt"
}

# Single source of truth for the in-bot showcase. Keep this list aligned with SHOWCASE.md
# so Discord users see the same capabilities advertised in documentation/screenshots.
SHOWCASE_SECTIONS = [
    {
        "name": "Lore Snapshot",
        "lines": [
            "Former underground hacker who now guards ops and data with her drone fleet (Sparky, Vulture-7, Ghost-Link).",
            "Protects refugees while keeping morale high with banter; rewards banshees with barbs if they break server safety.",
            "Keeps all survivor data isolated per server for security—no cross-pollination.",
        ],
    },
    {
        "name": "Core Systems",
        "lines": [
            "📡 Operations (UTC-2 clock): `/event`, `/events`, `/event_remove`, `/setup`, `/audit`, `/status`, `/analytics`.",
            "🎣 Trading | Fish-Link: `/setup_trade`, `/trade_item`, `/trade`, `/find`, `/my listings`, `/who has my wanted`.",
            "🛰️ Progression & Scavenging: hourly `/scavenge`, `/leaderboard`, `/profile`, and `/inventory` with set bonuses.",
        ],
    },
    {
        "name": "Welcomes, Departures, & Automation",
        "lines": [
            "`/setup` auto-wires welcome/verify/rules and reminder channels; `/setup audit` reviews links in-line.",
            "Auto role: optional helper to assign a base role on join for visibility.",
            "Analytics dashboards summarize command usage so admins know what crews lean on most.",
        ],
    },
    {
        "name": "Command Directory (quick view)",
        "lines": [
            "Admin: `/setup`, `/audit`, `/setup_trade`, `/refresh_commands`, `/event`, `/events`, `/analytics`, `/status`.",
            "Members: `/events`, `/scavenge`, `/profile`, `/inventory`, flag-reaction translation, `/trade_item`, `/features`, `/commands`.",
            "Trading: Fish-Link buttons + `/trade_item`.",
        ],
    },
    {
        "name": "How to Deploy",
        "lines": [
            "1) With Mod permissions, run `/setup` to link channels and optional auto-role. Add `/setup audit` to verify wiring.",
            "2) Launch `/setup_trade` in a trade channel to pin the Fish-Link terminal (seeded in SQLite for persistence).",
            "3) Run `/event` for mission planning; auto reminders are stored in SQLite with crash-safe WAL mode.",
            "4) Add event timers to `/scavenge`, `/trade`, and `/trade_item` to keep grind and trades moving.",
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
            "Use `/setup audit` before events to highlight missing channel links or permissions.",
            "Use `/status` for a fast signal check; `/analytics` shows per-server command usage and trading depth.",
            "Welcome, rules, and event channels can be kept minimal—Marcia formats reminders and intel automatically.",
        ],
    },
]

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.http = httpx.AsyncClient(timeout=10.0)
        self.log = logging.getLogger("MarciaOS.Utility")

    async def cog_unload(self):
        await self.http.aclose()

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
    def _build_command_directory(self, guild_name: Optional[str] = None) -> discord.Embed:
        """Return a consistent command directory embed for both text and slash calls."""
        categories = {
            "Admin (UTC-2 Clock)": [
                "/setup",
                "/event",
                "/event_remove <codename>",
                "/setup_trade",
                "/analytics",
                "/status",
                "/refresh_commands",
                "/setup audit",
                "/missions (legacy list)",
            ],
            "Members": [
                "/events",
                "/profile / /inventory / /trade_item",
                "/scavenge (loot + XP)",
                "/leaderboard",
                "/missions (legacy list)",
                "/manual",
                "/features / /showcase",
                "/commands",
            ],
            "Utility": [
                "/intel <topic>",
                "/poll 'Question' opt1 opt2",
                "/remindme <minutes> <task>",
                "/clear <amount>",
                "/tips",
                "/support",
            ],
            "Trading": [
                "Interact with Fish-Link buttons",
                "/setup_trade (admins)",
                "Fish spares/wanted are per-server",
            ],
        }

        embed = discord.Embed(
            title="🛠️ Marcia OS | Command Directory",
            description="I split intel by crew role. All times are UTC-2.",
            color=0x3498db,
        )
        for title, cmd_list in categories.items():
            embed.add_field(name=f"📦 {title}", value="\n".join(cmd_list), inline=False)

        scope = guild_name or "your sector"
        embed.set_footer(text=f"Marcia OS v3.0 | Sector: {scope}")
        return embed

    def _build_showcase_embed(self, guild_name: Optional[str] = None) -> discord.Embed:
        """
        Return a consolidated showcase of Marcia's systems.

        The copy mirrors SHOWCASE.md to keep Discord help embeds aligned with the
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
        except Exception as e:
            self.log.warning("Translation Error: %s", e)
            await msg.reply(
                "⚠️ Translation uplink failed. Try again in a moment or pick another flag.",
                mention_author=False,
            )

    @commands.hybrid_command(name="commands", aliases=["help"], description="Show Marcia's command directory.")
    async def list_commands(self, ctx):
        """Displays all available commands categorized by module."""
        embed = self._build_command_directory(ctx.guild.name if ctx.guild else None)
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Marcia's quick-start operations manual.")
    async def manual(self, ctx):
        """A quick-start guide for new users and admins."""
        embed = discord.Embed(title="📖 Marcia OS | Operations Manual", color=0xf1c40f)
        embed.add_field(
            name="🛰️ For Admins",
            value="1. Use `/setup` to link channels.\n2. Use `/event` to schedule missions.\n3. Use `/setup_trade` to open the market.",
            inline=False
        )
        embed.add_field(
            name="🎣 For Traders", 
            value="Interact with the buttons in the Trading Terminal to add fish you have (Spares) or fish you need (Find).", 
            inline=False
        )
        embed.add_field(
            name="🌍 For Everyone", 
            value="React to any message with a 🇺🇸 or 🇪🇸 (and more) flag to translate it instantly!", 
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Random survival and bot tips from Marcia.")
    async def tips(self, ctx):
        """Random survival tips and bot tricks."""
        tips_list = [
            "You can use `/remindme 60 Prepare for War` and I will DM you in one hour.",
            "Mission timers use the Dark War Survival clock (UTC-2) across every server.",
            "The Trading Terminal is server-specific. You won't see fish from other servers here!",
            "Use `/intel [topic]` to search the survival database for game-specific info."
        ]
        await ctx.reply(f"💡 **TIP:** {random.choice(tips_list)}")

    @commands.hybrid_command(description="How to report issues or contact Marcia's handler.")
    async def support(self, ctx):
        """Share feedback, report bugs, or support development."""
        embed = discord.Embed(
            title="🛰️ Marcia OS | Support Channel",
            description=(
                "Report issues or drop feedback and I'll relay it to my handler.\n\n"
                "Creator: **akrott**\n"
                "Support the uptime: https://www.buymeacoffee.com/akrott"
            ),
            color=0x5865f2,
        )
        embed.add_field(
            name="How to report",
            value=(
                "Describe the command you ran, the server, and any error text."
                " I stay in UTC-2, so include times in that clock."
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

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

    @commands.hybrid_command(description="Showcase Marcia's capabilities for new crews.", aliases=["showcase"])
    async def features(self, ctx):
        """Showcase Marcia's capabilities for new crews."""
        embed = self._build_showcase_embed(ctx.guild.name if ctx.guild else None)
        await ctx.send(embed=embed)

    @app_commands.command(name="showcase", description="Showcase Marcia's capabilities for new crews.")
    async def slash_showcase(self, interaction: discord.Interaction):
        embed = self._build_showcase_embed(interaction.guild.name if interaction.guild else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        embed.set_footer(text="Need a deeper check? Use /setup audit for a full report.")
        await ctx.reply(embed=embed)

    @commands.hybrid_command(description="Per-server analytics (admins).")
    @commands.has_permissions(manage_guild=True)
    async def analytics(self, ctx):
        """Detailed per-server analytics for admins."""
        snapshot = await guild_analytics_snapshot(ctx.guild.id)

        embed = discord.Embed(
            title="📊 Sector Analytics",
            description="Live stats are scoped to this server only. Other sectors stay isolated.",
            color=0x9b59b6,
        )
        embed.add_field(name="🎣 Trading Listings", value=str(snapshot["trade_listings"]), inline=True)
        embed.add_field(name="👥 Active Traders", value=str(snapshot["traders"]), inline=True)
        embed.add_field(name="🛰️ Missions Running", value=str(snapshot["missions_active"]), inline=True)
        embed.add_field(name="📂 Templates Saved", value=str(snapshot["templates"]), inline=True)
        embed.add_field(name="🧭 Survivors Tracked", value=str(snapshot["survivors_tracked"]), inline=True)
        embed.add_field(name="🎒 Items Logged", value=str(snapshot["items"]), inline=True)
        embed.set_footer(text="Clock: UTC-2 | Data never crosses sectors.")

        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Query survival intel topics (e.g., /intel trucks).")
    async def intel(self, ctx, topic: str = None):
        """Query survival topics (e.g., !intel trucks)."""
        if not topic: 
            return await ctx.reply(f"Available Intel Topics: `{', '.join(INTEL_DATABASE.keys())}`")
        
        info = INTEL_DATABASE.get(topic.lower())
        if info: 
            embed = discord.Embed(title=f"📥 INTEL: {topic.upper()}", description=info, color=0x3498db)
            await ctx.send(embed=embed)
        else:
            await ctx.reply("❌ Topic not found in the archives.")

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
        await ctx.reply(f"⏰ Affirmative. Reminder set for `{task}`.")
        await asyncio.sleep(minutes * 60)
        await ctx.author.send(f"🔔 **REMINDER:** {task}")

    @commands.hybrid_command(description="Purge chat history (admins).")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 5):
        """Purge chat history."""
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 {amount} signals cleared.", delete_after=3)

async def setup(bot):
    await bot.add_cog(Utility(bot))