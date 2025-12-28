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
from time_utils import now_game, game_to_utc, format_game, utc_to_game
from database import (
    get_settings, get_templates, add_template, delete_template,
    get_all_active_missions, get_upcoming_missions, add_mission, delete_mission,
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


def _marica_quip():
    return random.choice(MARICA_QUOTES)

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
                utc_dt = datetime.fromisoformat(m['target_utc']).astimezone(timezone.utc)
                if utc_dt > datetime.now(timezone.utc):
                    task_key = f"{m['guild_id']}_{m['codename']}"
                    self.running_tasks[task_key] = self.bot.loop.create_task(
                        self.manage_reminders(
                            m['codename'],
                            m['description'],
                            utc_dt,
                            m['guild_id'],
                            location=m.get('location'),
                            ping_role_id=m.get('ping_role_id'),
                        )
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

            now_server = now_game()

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
        embed = discord.Embed(
            title="📡 Mission Control // Marcia",
            description=(
                "Pick how you want me to broadcast your operation.\n"
                "`Custom Event` opens a DM interview, `Use Template` pulls from your archive.\n"
                "I track everything in UTC-2 (Dark War Survival)."
            ),
            color=0x2b2d31
        )
        embed.set_footer(text="Marcia drones on standby. Keep it sharp.")
        await ctx.send(embed=embed, view=EventMenuView(self, ctx))

    @commands.command(name="events")
    async def list_events(self, ctx):
        """Members can view upcoming events in UTC-2."""
        missions = await get_upcoming_missions(ctx.guild.id, limit=10)
        if not missions:
            return await ctx.send("📡 *No upcoming events logged for this sector.*")

        embed = discord.Embed(
            title="🛰️ Upcoming Operations (UTC-2)",
            color=0x3498db,
            description="I'll ping this channel when it's go-time."
        )
        for m in missions:
            start_game = format_game(datetime.fromisoformat(m['target_utc']).astimezone(timezone.utc))
            details = [f"📝 {m['description']}"]
            if m['location']:
                details.append(f"📍 {m['location']}")
            embed.add_field(
                name=f"🔹 {m['codename']}",
                value="\n".join(details + [f"⏰ `{start_game}`"]),
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="event_remove")
    @commands.has_permissions(manage_guild=True)
    async def event_remove(self, ctx, *, codename: str):
        """Remove a scheduled event."""
        await delete_mission(ctx.guild.id, codename)
        await ctx.send(f"🗑️ Event **{codename}** scrubbed from the docket.")

    async def create_template_flow(self, ctx):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send("💾 **Template Title?** (what do we call this op?)")
            title = (await self.bot.wait_for('message', check=check, timeout=120)).content
            await ctx.author.send("📝 **Directives?** Drop the briefing text.")
            desc = (await self.bot.wait_for('message', check=check, timeout=300)).content
            await add_template(ctx.guild.id, title, desc)
            await ctx.author.send(f"✅ Protocol `{title}` archived. {_marica_quip()}")
        except: await ctx.author.send("❌ Timeout.")

    async def create_mission_flow(self, ctx):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send(
                "📡 **Mission Codename?** (keep it short; I'll broadcast it)"
            )
            name_msg = await self.bot.wait_for('message', check=check, timeout=120)
            name = name_msg.content

            await ctx.author.send("📝 **Instructions?** Tell the squad what to do.")
            desc_msg = await self.bot.wait_for('message', check=check, timeout=300)
            desc = desc_msg.content

            await ctx.author.send("📍 **Location or voice channel?** Reply with coords/link or type `skip`.")
            location_msg = await self.bot.wait_for('message', check=check, timeout=180)
            location = None if location_msg.content.lower().strip() == "skip" else location_msg.content

            await ctx.author.send(
                "👥 **Ping who?** Mention a role, type `everyone`, or `none` to stay quiet."
            )
            ping_msg = await self.bot.wait_for('message', check=check, timeout=120)
            ping_role = await self._resolve_ping(ctx, ping_msg.content)

            await ctx.author.send(
                f"⏰ **Target Time?** `YYYY-MM-DD HH:MM` using the game clock (UTC-2)."
            )
            t_msg = await self.bot.wait_for('message', check=check, timeout=180)
            await self.finalize_mission(ctx, name, desc, t_msg.content, location, ping_role)
        except asyncio.TimeoutError:
            await ctx.author.send("⌛ Timed out. Ping me again with `!event` when you're ready.")

    async def finalize_mission(self, ctx, name, desc, t_str, location, ping_role):
        try:
            target_dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
            utc_dt = game_to_utc(target_dt)
            if utc_dt < datetime.now(timezone.utc):
                return await ctx.author.send("❌ Past time.")

            ping_role_id = ping_role.id if ping_role else None
            await add_mission(
                ctx.guild.id,
                name,
                desc,
                t_str,
                utc_dt.isoformat(),
                location=location,
                ping_role_id=ping_role_id,
                tag=None,
                notes=None,
            )
            self.running_tasks[f"{ctx.guild.id}_{name}"] = self.bot.loop.create_task(
                self.manage_reminders(name, desc, utc_dt, ctx.guild.id, location, ping_role_id)
            )

            preview = self._build_event_embed(ctx.guild, name, desc, utc_dt, location, ping_role_id)
            await ctx.author.send(f"✅ Mission `{name}` locked. {_marica_quip()}", embed=preview)

            settings = await get_settings(ctx.guild.id)
            if settings and settings['event_channel_id']:
                chan = ctx.guild.get_channel(settings['event_channel_id'])
                if chan:
                    await chan.send("🛰️ **New Operation Logged**", embed=preview)
        except Exception:
            await ctx.author.send("❌ Use: `YYYY-MM-DD HH:MM`.")

    async def manage_reminders(self, name, desc, utc_dt, guild_id, location=None, ping_role_id=None):
        for mins in [60, 30, 15, 3, 0]:
            wait = (utc_dt - timedelta(minutes=mins) - datetime.now(timezone.utc)).total_seconds()
            if wait > 0:
                await asyncio.sleep(wait)

            # Final check if mission still exists in DB
            missions = await get_all_active_missions()
            if not any(m['guild_id'] == guild_id and m['codename'] == name for m in missions):
                return

            settings = await get_settings(guild_id)
            if not (settings and settings['event_channel_id']):
                continue

            chan = self.bot.get_channel(settings['event_channel_id'])
            if not chan:
                continue

            drone = random.choice(DRONE_NAMES)
            guild = chan.guild
            role = guild.get_role(ping_role_id) if ping_role_id else None
            mention = role.mention if role else "@everyone"
            location_line = f"\n📍 {location}" if location else ""
            title, body = random.choice(TIMED_REMINDERS.get(mins, [("📡 **ALERT:**", "`{name}` is coming up.")]))
            body = body.format(name=name, drone=drone)
            quote = random.choice(MARICA_QUOTES)

            if mins == 60:
                msg = (
                    f"{mention}\n{title} {quote}\n"
                    f"{body}\n\n"
                    f"{desc}{location_line}\n\n*Drone: {drone}*"
                )
            else:
                msg = f"{mention}\n{title} {quote}\n{body}\n\n*Drone: {drone}*"
            await chan.send(msg)

        await delete_mission(guild_id, name)

    def _build_event_embed(self, guild, name, desc, utc_dt, location=None, ping_role_id=None):
        embed = discord.Embed(
            title=f"📡 {name}",
            description=desc,
            color=0x5865f2,
        )
        embed.add_field(name="⏰ Game Time", value=format_game(utc_dt), inline=False)
        if location:
            embed.add_field(name="📍 Location", value=location, inline=True)
        if ping_role_id:
            role = guild.get_role(ping_role_id)
            embed.add_field(name="👥 Ping", value=role.mention if role else "@everyone", inline=True)
        embed.set_footer(text=f"Sector: {guild.name} | Clock: UTC-2")
        return embed

    async def _resolve_ping(self, ctx, msg_content):
        text = msg_content.strip().lower()
        if text == "none":
            return None
        if text == "everyone":
            return ctx.guild.default_role
        # Try mention syntax
        if msg_content.startswith("<@&") and msg_content.endswith(">"):
            role_id = int(msg_content[3:-1])
            return ctx.guild.get_role(role_id)

        return discord.utils.get(ctx.guild.roles, name=msg_content)

async def setup(bot):
    await bot.add_cog(Events(bot))