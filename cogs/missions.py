"""
FILE: cogs/missions.py
USE: Manages live countdowns and mission presets.
FEATURES: Persistent missions, guild-isolated templates, auto-cleanup, and help tips.
"""
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import logging
from database import (
    add_mission, delete_mission, get_all_active_missions, 
    add_template, get_templates, delete_template
)

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
        now = datetime.utcnow()

        for m in missions:
            try:
                target_utc = datetime.fromisoformat(m['target_utc'])
                if now >= target_utc:
                    await delete_mission(m['guild_id'], m['codename'])
                    logger.info(f"🗑️ Mission {m['codename']} expired in guild {m['guild_id']}")
            except Exception as e:
                logger.error(f"Error checking mission {m['codename']}: {e}")

    @commands.command()
    async def mission_help(self, ctx):
        """Information and tips on using the Mission System."""
        embed = discord.Embed(
            title="🛰️ Marcia OS | Mission Intelligence",
            description=(
                "The Mission system allows you to track real-time objectives across the server. "
                "All data is saved to the SQL databank, so timers continue even if the bot restarts."
            ),
            color=0x3498db
        )
        embed.add_field(
            name="💡 Pro-Tip: Templates", 
            value="Use `!template_add` for recurring missions like 'Weekly Scavenge'. You can then copy-paste the text when adding a live mission.",
            inline=False
        )
        embed.add_field(
            name="🕒 Time Logic", 
            value="Missions use **Hours** as the input. If you want a mission to end in 2 days, use `48`.",
            inline=False
        )
        embed.add_field(
            name="📋 Command Summary",
            value=(
                "`!mission_add [name] [hours] [text]` - Start a timer\n"
                "`!missions` - View active objectives\n"
                "`!template_add [name] [text]` - Save a preset"
            )
        )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def mission_add(self, ctx, codename: str, hours: int, *, description: str = "No details provided."):
        """Adds a new mission countdown."""
        target_utc = datetime.utcnow() + timedelta(hours=hours)
        target_display = target_utc.strftime("%Y-%m-%d %H:%M UTC")

        await add_mission(
            ctx.guild.id, 
            codename.upper(), 
            description, 
            target_display, 
            target_utc.isoformat()
        )

        embed = discord.Embed(
            title=f"🚀 MISSION DEPLOYED: {codename.upper()}",
            description=description,
            color=0x3498db
        )
        embed.add_field(name="Ends At", value=f"`{target_display}`")
        embed.set_footer(text=f"Deployment Sector: {ctx.guild.name}")
        await ctx.send(embed=embed)

    @commands.command()
    async def missions(self, ctx):
        """Lists active missions for this server."""
        all_m = await get_all_active_missions()
        local_m = [m for m in all_m if m['guild_id'] == ctx.guild.id]

        if not local_m:
            return await ctx.send("📡 *No active missions detected in this sector.*")

        embed = discord.Embed(title="🛰️ Active Tactical Missions", color=0x2ecc71)
        for m in local_m:
            embed.add_field(
                name=f"🔹 {m['codename']}", 
                value=f"**Info:** {m['description']}\n**Target:** `{m['target_time']}`", 
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def mission_delete(self, ctx, codename: str):
        """Removes a mission manually."""
        await delete_mission(ctx.guild.id, codename.upper())
        await ctx.send(f"✅ Mission **{codename.upper()}** has been scrubbed from the logs.")

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