"""
FILE: cogs/utility.py
USE: General helper functions, information, and interactive dialogue.
FEATURES: Flag-based translation, Polls, Reminders, and Marcia Manuals.
"""
import asyncio
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from googletrans import Translator

from assets import MARICA_LORE, INTEL_DATABASE
from database import get_settings, guild_analytics_snapshot

# Expanded Language Library
FLAG_LANG = {
    "🇺🇸": "en", "🇬🇧": "en", "🇦🇺": "en", "🇨🇦": "en",
    "🇫🇷": "fr", "🇪🇸": "es", "🇩🇪": "de", "🇮🇹": "it", "🇵🇹": "pt", "🇳🇱": "nl", "🇷🇺": "ru",
    "🇯🇵": "ja", "🇰🇷": "ko", "🇨🇳": "zh-cn", "🇻🇳": "vi", "🇹🇭": "th",
    "🇦🇪": "ar", "🇹🇷": "tr", "🇮🇳": "hi", "🇧🇷": "pt"
}

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Use the public translate.googleapis.com endpoint for better uptime
        self.translator = Translator(service_urls=["translate.googleapis.com"])

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
                "/features",
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

    def _build_feature_pack(self, guild_name: Optional[str] = None) -> discord.Embed:
        """Return a consolidated feature showcase that mirrors the command list."""
        embed = discord.Embed(
            title="🛰️ Marcia OS | Feature Pack",
            color=0x9b59b6,
            description="What I handle for Dark War Survival alliances (UTC-2 clock).",
        )
        embed.add_field(
            name="Operations",
            value=(
                "Event scheduler with `/event`, `/events`, and `/event_remove`, auto reminders, and `/status` health checks"
                " for linked channels."
            ),
            inline=False,
        )
        embed.add_field(
            name="Trading Network",
            value="Fish-Link terminal with auto re-anchoring, `/setup_trade` wiring, donor matching, and server-isolated boards.",
            inline=False,
        )
        embed.add_field(
            name="Progression & Loot",
            value=(
                "Hourly `/scavenge` runs, XP tiers, prestige rewards, `/profile`, `/inventory`, `/leaderboard` tracking, and"
                " `/missions` for legacy checklists."
            ),
            inline=False,
        )
        embed.add_field(
            name="Intel & Utilities",
            value=(
                "Flag emoji translation, `/intel` quick lookups, `/poll`, `/remindme`, `/clear`, `/manual`, `/tips`, and"
                " `/support` to reach the handler."
            ),
            inline=False,
        )
        embed.add_field(
            name="Owner Ops",
            value="Private dashboards and broadcast tools accessible only to the handler.",
            inline=False,
        )
        scope = guild_name or "your sector"
        embed.set_footer(text=f"Built for Dark War Survival alliances | Sector: {scope} | Clock: UTC-2")
        return embed

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Translation Matrix: React with a flag to translate a message."""
        if str(payload.emoji) in FLAG_LANG:
            channel = self.bot.get_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)

            if not msg.content: return

            dest = FLAG_LANG[str(payload.emoji)]
            try:
                # Running in thread to prevent blocking the bot
                tr = await asyncio.to_thread(self.translator.translate, msg.content, dest=dest)
                await msg.reply(f"📡 **DECODED [{dest.upper()}]:**\n{tr.text}", mention_author=False)
            except Exception as e:
                print(f"Translation Error: {e}")
                await msg.reply(
                    "⚠️ Translation uplink failed. Try again in a moment or pick another flag.",
                    mention_author=False,
                )

    @commands.hybrid_command(name="commands", aliases=["help"], description="Show Marcia's command directory.")
    async def list_commands(self, ctx):
        """Displays all available commands categorized by module."""
        embed = self._build_command_directory(ctx.guild.name if ctx.guild else None)
        await ctx.send(embed=embed)

    @app_commands.command(name="commands", description="Show Marcia's command directory.")
    async def slash_commands(self, interaction: discord.Interaction):
        embed = self._build_command_directory(interaction.guild.name if interaction.guild else None)
        await interaction.response.send_message(embed=embed, ephemeral=True)

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

    @commands.hybrid_command(description="Showcase Marcia's capabilities for new crews.")
    async def features(self, ctx):
        """Showcase Marcia's capabilities for new crews."""
        embed = self._build_feature_pack(ctx.guild.name if ctx.guild else None)
        await ctx.send(embed=embed)

    @app_commands.command(name="features", description="Show Marcia's feature set.")
    async def slash_features(self, interaction: discord.Interaction):
        embed = self._build_feature_pack(interaction.guild.name if interaction.guild else None)
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

    @commands.hybrid_command(description="Create a poll. /poll 'Title' option1 option2 ...")
    async def poll(self, ctx, question: str, *options):
        """Create a poll. Usage: !poll \"Title\" Yes No Maybe"""
        if not options:
            msg = await ctx.send(embed=discord.Embed(title="🗳️ POLL", description=question, color=0x00ffcc))
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
        else:
            if len(options) > 10: return await ctx.send("Limit 10.")
            reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            desc = "\n".join([f"{reactions[i]} {opt}" for i, opt in enumerate(options)])
            msg = await ctx.send(embed=discord.Embed(title=f"🗳️ {question}", description=desc, color=0x00ffcc))
            for i in range(len(options)): await msg.add_reaction(reactions[i])

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