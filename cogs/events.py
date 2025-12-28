"""
FILE: cogs/events.py
USE: Automations, Duel Reminders, and Mission Control (SQL Version).
FEATURES: Server-time synced resets, persistent mission recovery, and broadcast logic.
"""
import discord
from discord.ext import commands, tasks
import asyncio
import random
import logging
from datetime import datetime, timezone, timedelta
from assets import TIMED_REMINDERS, DRONE_NAMES, MARICA_STATUSES, MARICA_QUOTES
from database import (
    get_settings, get_templates, add_template, delete_template,
    get_all_active_missions, add_mission, delete_mission,
    can_run_daily_task, mark_task_complete
)

logger = logging.getLogger('MarciaOS.Events')

DUEL_DATA = {
    0: "**MONDAY – Day 1: Research / Building / Gathering**\n\n✅ **DO:**\n• Send gatherers before reset.\n• Duel points count on Return.\n• Use gathering heroes: Musashimaru, Bob, Joe.\n📊 **SP SLOTS:** Shelter → Hero → Unit → Science → Arms.",
    1: "**TUESDAY – Day 2: Radar / Recruitment / Heroes**\n\n✅ **DO:**\n• Claim radar missions. Use Prime tickets.\n• Spend hero fragments.\n📊 **SP SLOTS:** Hero → Unit → Science → Arms → Shelter → Hero.",
    2: "**WEDNESDAY – Day 3: Trucks / Orange / Training**\n\n✅ **DO:**\n• Run 4 S-Trucks & 8-9 Orange missions.\n• Use Power Cores. Train units passively.\n📊 **SP SLOTS:** Unit → Science → Arms → Shelter → Hero → Unit.",
    3: "**THURSDAY – Day 4: Radar / Vehicles / Monsters**\n\n✅ **DO:**\n• Burn stamina on Lv20+ mummies.\n• Use vehicle gears and blueprints.\n📊 **SP SLOTS:** Science → Arms → Shelter → Hero → Unit → Science.",
    4: "**FRIDAY – Day 5: Vehicles / Fragments / Wisdom**\n\n✅ **DO:**\n• Collect Zombie Siege rewards.\n• Use Wisdom Medals.\n📊 **SP SLOTS:** Arms → Shelter → Hero → Unit → Science → Arms.",
    5: "**SATURDAY – Day 6: Enemy Buster**\n\n✅ **DO:**\n• KE and RSS hunting. Focus on easy 40K slots.\n📊 **SP SLOTS:** Shelter → Hero → Unit → Science → Arms → Shelter.",
    6: "**SUNDAY – Day 7: Preparation**\n\nDirectives: Prepare gatherers for Monday reset. Restock speedups."
}

# --- UI COMPONENTS ---

class TemplateSelect(discord.ui.Select):
    def __init__(self, templates, callback_func, placeholder="Select a template...", mode="use"):
        options = [discord.SelectOption(label=t['template_name'], emoji="📋" if mode=="use" else "🗑️") for t in templates[:24]]
        options.append(discord.SelectOption(label="Cancel", emoji="❌"))
        super().__init__(placeholder=placeholder, options=options)
        self.callback_func = callback_func

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "Cancel":
            return await interaction.response.edit_message(content="📡 Directive cancelled.", view=None, embed=None)
        await self.callback_func(interaction, self.values[0])

class EventMenuView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=60)
        self.cog, self.ctx = cog, ctx

    @discord.ui.button(label="Custom Event", style=discord.ButtonStyle.primary, emoji="✍️")
    async def custom_event(self, it, btn):
        await it.response.send_message("📡 Setup signal sent to DMs.", ephemeral=True)
        await self.cog.create_mission_flow(self.ctx)

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.success, emoji="📋")
    async def template_event(self, it, btn):
        tps = await get_templates(it.guild.id)
        if not tps: return await it.response.send_message("❌ Archive is empty.", ephemeral=True)
        view = discord.ui.View(); view.add_item(TemplateSelect(tps, self.cog.use_template_callback))
        await it.response.edit_message(content="**Select a mission preset:**", view=view, embed=None)

    @discord.ui.button(label="Archive Template", style=discord.ButtonStyle.secondary, emoji="💾")
    async def create_template_btn(self, it, btn):
        await it.response.send_message("💾 Archiving Module Active. Check DMs.", ephemeral=True)
        await self.cog.create_template_flow(self.ctx)

# --- COG MAIN ---

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.running_tasks = {}
        self.cycle_status.start()
        self.check_duel_reset.start()
        self.bot.loop.create_task(self.recover_missions())

    def cog_unload(self):
        self.cycle_status.cancel()
        self.check_duel_reset.cancel()
        for task in self.running_tasks.values(): task.cancel()

    async def recover_missions(self):
        """Reloads active missions from SQL on startup."""
        await self.bot.wait_until_ready()
        all_missions = await get_all_active_missions()
        for m in all_missions:
            try:
                utc_dt = datetime.fromisoformat(m['target_utc']).replace(tzinfo=timezone.utc)
                if utc_dt > datetime.now(timezone.utc):
                    task_key = f"{m['guild_id']}_{m['codename']}"
                    self.running_tasks[task_key] = self.bot.loop.create_task(
                        self.manage_reminders(m['codename'], m['description'], utc_dt, m['guild_id'])
                    )
                else:
                    await delete_mission(m['guild_id'], m['codename'])
            except: pass

    @tasks.loop(minutes=5)
    async def check_duel_reset(self):
        """Sends daily Duel info at Midnight Server Time."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            settings = await get_settings(guild.id)
            if not settings or not settings['event_channel_id']: continue

            # Sync to server clock
            offset = timedelta(hours=settings['server_offset_hours'])
            now_server = datetime.now(timezone.utc) + offset
            
            if now_server.hour == 0:
                date_key = now_server.strftime("%Y-%m-%d")
                task_id = f"duel_{guild.id}"
                
                if await can_run_daily_task(task_id, date_str=date_key):
                    chan = guild.get_channel(settings['event_channel_id'])
                    if chan:
                        info = DUEL_DATA.get(now_server.weekday(), "No data.")
                        await chan.send(f"@everyone\n📡 **MARCIA OS | DUEL DIRECTIVE**\n\n{info}")
                        await mark_task_complete(task_id, date_str=date_key)

    @tasks.loop(minutes=30)
    async def cycle_status(self):
        try: await self.bot.change_presence(activity=discord.Game(name=random.choice(MARICA_STATUSES)))
        except: pass

    @commands.command(name="event")
    @commands.has_permissions(manage_guild=True)
    async def event_cmd(self, ctx):
        """Opens the Mission Control menu."""
        embed = discord.Embed(title="📡 Mission Control", description="Select a directive to deploy.", color=0x2b2d31)
        await ctx.send(embed=embed, view=EventMenuView(self, ctx))

    async def create_template_flow(self, ctx):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send("💾 **Template Title?**")
            title = (await self.bot.wait_for('message', check=check, timeout=120)).content
            await ctx.author.send("📝 **Directives?**")
            desc = (await self.bot.wait_for('message', check=check, timeout=300)).content
            await add_template(ctx.guild.id, title, desc)
            await ctx.author.send(f"✅ Protocol `{title}` archived.")
        except: await ctx.author.send("❌ Timeout.")

    async def create_mission_flow(self, ctx):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        settings = await get_settings(ctx.guild.id)
        offset = settings['server_offset_hours'] if settings else 0
        try:
            await ctx.author.send("📡 **Mission Codename?**")
            name = (await self.bot.wait_for('message', check=check, timeout=120)).content
            await ctx.author.send("📝 **Instructions?**")
            desc = (await self.bot.wait_for('message', check=check, timeout=300)).content
            await ctx.author.send(f"⏰ **Target Time?** `YYYY-MM-DD HH:MM` (UTC{offset:+}h)")
            t_str = (await self.bot.wait_for('message', check=check, timeout=120)).content
            await self.finalize_mission(ctx.author, name, desc, t_str, ctx.guild.id)
        except: await ctx.author.send("❌ Timed out.")

    async def finalize_mission(self, user, name, desc, t_str, guild_id):
        settings = await get_settings(guild_id)
        offset = timedelta(hours=settings['server_offset_hours'] if settings else 0)
        try:
            target_dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
            utc_dt = target_dt.replace(tzinfo=timezone.utc) - offset
            if utc_dt < datetime.now(timezone.utc): return await user.send("❌ Past time.")
            
            await add_mission(guild_id, name, desc, t_str, utc_dt.isoformat())
            self.running_tasks[f"{guild_id}_{name}"] = self.bot.loop.create_task(self.manage_reminders(name, desc, utc_dt, guild_id))
            await user.send(f"✅ Mission `{name}` locked.")
        except: await user.send("❌ Use: `YYYY-MM-DD HH:MM`.")

    async def manage_reminders(self, name, desc, utc_dt, guild_id):
        for mins in [60, 30, 15, 3, 0]:
            wait = (utc_dt - timedelta(minutes=mins) - datetime.now(timezone.utc)).total_seconds()
            if wait > 0:
                await asyncio.sleep(wait)
                # Final check if mission still exists in DB
                missions = await get_all_active_missions()
                if not any(m['guild_id'] == guild_id and m['codename'] == name for m in missions): return
                
                settings = await get_settings(guild_id)
                if settings and settings['event_channel_id']:
                    chan = self.bot.get_channel(settings['event_channel_id'])
                    if chan:
                        drone = random.choice(DRONE_NAMES)
                        msg = f"@everyone\n📡 **INCOMING TRANSMISSION | {name}**\n\n{desc}\n\n*Drone: {drone}*"
                        await chan.send(msg)
        
        await delete_mission(guild_id, name)

async def setup(bot):
    await bot.add_cog(Events(bot))