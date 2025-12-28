"""
FILE: cogs/missions.py
USE: Manages live countdowns and mission presets.
FEATURES: Persistent missions, guild-isolated templates, auto-cleanup, and help tips.
"""
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import logging
from database import (
    add_mission, delete_mission, get_all_active_missions,
    add_template, get_templates, delete_template, get_upcoming_missions
)
from time_utils import now_game, game_to_utc, format_game

logger = logging.getLogger('MarciaOS.Missions')

class Missions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mission_updater.start()

    def cog_unload(self):
        self.mission_updater.cancel()

    @tasks.loop(seconds=60)
    async def mission_updater(self):
        """Background task to check for expired missions."""
        missions = await get_all_active_missions()
        now = datetime.now(timezone.utc)

        for m in missions:
            try:
                target_utc = datetime.fromisoformat(m['target_utc']).astimezone(timezone.utc)
                if now >= target_utc:
                    await delete_mission(m['guild_id'], m['codename'])
                    logger.info(f"🗑️ Mission {m['codename']} expired in guild {m['guild_id']}")
            except Exception as e:
                logger.error(f"Error checking mission {m['codename']}: {e}")

    @commands.command()
    async def mission_help(self, ctx):
        """Information and tips on using the Mission System."""
        await ctx.send(
            "📡 Mission system has been folded into `!event`. Use `!event` to create ops or `!events` to list them."
        )

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def mission_add(self, ctx, codename: str, hours: int, *, description: str = "No details provided."):
        """Legacy alias for creating an event."""
        await ctx.send("Use `!event` for the guided event creator (UTC-2 clock).")

    @commands.command()
    async def missions(self, ctx):
        """Lists active missions for this server."""
        upcoming = await get_upcoming_missions(ctx.guild.id, limit=10)
        if not upcoming:
            return await ctx.send("📡 *No active missions detected in this sector.*")

        embed = discord.Embed(title="🛰️ Active Tactical Missions", color=0x2ecc71)
        for m in upcoming:
            target_utc = datetime.fromisoformat(m['target_utc']).astimezone(timezone.utc)
            display_time = format_game(target_utc)
            tag_line = f" | {m['tag']}" if m.get('tag') else ""
            embed.add_field(
                name=f"🔹 {m['codename']}{tag_line}",
                value=f"**Info:** {m['description']}\n**Target:** `{display_time}`",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def mission_delete(self, ctx, codename: str):
        """Removes a mission manually."""
        await delete_mission(ctx.guild.id, codename.upper())
        await ctx.send(f"✅ Mission **{codename.upper()}** has been scrubbed from the logs. (Use `!event_remove` next time.)")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def template_add(self, ctx, name: str, *, description: str):
        """Saves a mission description as a template."""
        await add_template(ctx.guild.id, name.upper(), description)
        await ctx.send(f"💾 Template **{name.upper()}** saved to local databank.")

    @commands.command()
    async def templates(self, ctx):
        """Lists all saved mission templates."""
        rows = await get_templates(ctx.guild.id)
        if not rows:
            return await ctx.send("📂 *Local databank is empty.*")

        list_str = "\n".join([f"• **{r['template_name']}**: {r['description']}" for r in rows])
        await ctx.send(f"📂 **Stored Mission Templates:**\n{list_str}")

async def setup(bot):
    await bot.add_cog(Missions(bot))