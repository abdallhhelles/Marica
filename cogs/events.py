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
from utils.assets import TIMED_REMINDERS, DRONE_NAMES, MARCIA_STATUSES, MARCIA_SYSTEM_LINES
from utils.time_utils import now_game, game_to_utc, format_game, utc_to_game
from database import (
    add_mission,
    add_template,
    can_run_daily_task,
    delete_mission,
    get_all_active_missions,
    get_rsvp_counts,
    get_rsvp_members,
    get_settings,
    get_templates,
    get_upcoming_missions,
    increment_activity_metric,
    is_channel_ignored,
    lookup_rsvp_prompt,
    mark_task_complete,
    remove_rsvp_status,
    set_rsvp_status,
    upsert_rsvp_prompt,
)

logger = logging.getLogger('MarciaOS.Events')
JOIN_EVENT_EMOJI = "🤝"
RSVP_EMOJIS = {
    JOIN_EVENT_EMOJI: "going",
}

DUEL_DATA = {
    0: (
        "**MONDAY — Day 1: Shelter Expansion**\n\n"
        "**Event Focus:** Construction, Research, and Wisdom Medals.\n"
        "**Primary Score Sources:** Building upgrades, Research completions, Wisdom Medal spending.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 🏗️ **Construction:** Start long upgrades early so they finish before reset.\n"
        "• 🔬 **Research:** Queue big tech nodes; stack Wisdom Medals for better ROI.\n"
        "• 📜 **Wisdom Medals:** Spend on Research Center, Duel, and Battle Strategy trees.\n"
        "• ⚙️ **Speedups:** Use only construction/research boosts today.\n"
        "• 💰 **Gathering:** Keep fleets running for wood/iron/electricity + mint bonus.\n\n"
        "**💾 Save For Later:**\n"
        "• Radar missions, gears, titanium alloy, power cores\n"
        "• Hero equipment chests, Prime Recruit tickets\n"
        "• Truck/Shadow refresh tickets, hero fragments\n\n"
        "**💡 Marcia’s Call:** Front-load long builds now. Finishing after reset still scores today."
    ),
    1: (
        "**TUESDAY — Day 2: Hero Initiative**\n\n"
        "**Event Focus:** Hero upgrades, Prime Recruit, Radar missions.\n"
        "**Primary Score Sources:** Tickets, hero fragments, exclusive equipment upgrades.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 🎖️ **Prime Recruit:** Spend gold tickets today—no hoarding.\n"
        "• 🧩 **Hero Fragments:** Star-rise orange/purple heroes first.\n"
        "• 🎯 **Exclusive Gear:** Upgrade core gear on your main squad.\n"
        "• 📡 **Radar Missions:** Clear every radar you can for steady points.\n\n"
        "**💾 Save For Later:**\n"
        "• Gears, power cores, wisdom medals, equipment chests\n\n"
        "**💡 Marcia’s Call:** Queue troop training late tonight so it finishes after reset for Day 3 points."
    ),
    2: (
        "**WEDNESDAY — Day 3: Logistics Surge**\n\n"
        "**Event Focus:** Cargo/Shadow missions and troop training.\n"
        "**Primary Score Sources:** S-tier trucks, orange shadow calls, troop training speedups.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 🚚 **Escort/Cargo:** Run S-tier only. Prioritize refreshes for orange trucks.\n"
        "• 🕶️ **Shadow Calls:** Orange missions deliver the best point-per-stamina.\n"
        "• 🪖 **Troop Training:** Train steadily all day; use training speedups only.\n"
        "• 🔋 **Power Cores:** Push orange equipment upgrades now.\n\n"
        "**💾 Save For Later:**\n"
        "• Construction/research speedups, wisdom medals, excess energy\n\n"
        "**💡 Marcia’s Call:** Keep queues full. Empty barracks means empty scoreboard."
    ),
    3: (
        "**THURSDAY — Day 4: Arms Expert**\n\n"
        "**Event Focus:** APC upgrades and radar events.\n"
        "**Primary Score Sources:** APC parts, vehicle upgrades, roamer hunts.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 🚙 **APC Upgrades:** Spend gears/titanium/blueprints on your main vehicle.\n"
        "• 📡 **Radar Events:** Clear all available radar missions.\n"
        "• 🧟 **Roamers/Boomers:** Follow alliance scale callouts for efficient kills.\n\n"
        "**💾 Save For Later:**\n"
        "• Hero fragments, wisdom medals, general speedups\n\n"
        "**💡 Marcia’s Call:** Hunt in coordinated waves. Efficiency beats chaos."
    ),
    4: (
        "**FRIDAY — Day 5: Holistic Growth**\n\n"
        "**Event Focus:** Catch-up growth across systems.\n"
        "**Primary Score Sources:** Hero fragments, wisdom medals, APC upgrades, speedups.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• ⏫ **Hero Fragments:** Star-rise high-rarity heroes first.\n"
        "• 🏅 **Wisdom Medals:** Spend on the most impactful research tiers.\n"
        "• 🚙 **APC Upgrades:** Finish any vehicle upgrades queued earlier in the week.\n"
        "• ⏩ **Speedups:** Use targeted boosts where you lag behind.\n\n"
        "**💾 Save For Later:**\n"
        "• Dark Syndicate/Shadow refreshes if you plan for Saturday.\n\n"
        "**💡 Marcia’s Call:** Fix weak links today so Saturday doesn’t expose them."
    ),
    5: (
        "**SATURDAY — Day 6: Enemy Buster (Kill Event)**\n\n"
        "**Event Focus:** PvP eliminations and high-risk scoring.\n"
        "**Primary Score Sources:** Rival unit defeats, gold trucks, gold shadow calls.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 💀 **Combat:** Choose targets wisely; avoid wasteful fights.\n"
        "• 🚚 **Gold Trucks:** Use refreshes to secure gold-tier escorts.\n"
        "• 🎫 **Gold Shadow Calls:** Run in intervals to avoid stamina burnout.\n"
        "• ⏩ **Speedups:** Spend only if it converts to direct points.\n\n"
        "**🛡️ DEFENSE (If Not Participating):**\n"
        "• Keep **24h shields** active for the full event.\n"
        "• Set alarms for shorter shields—missed refreshes get you zeroed.\n"
        "• Shelter troops before shields drop.\n\n"
        "**💡 Marcia’s Call:** This day is high-risk. Win smart or sit safe."
    ),
    6: (
        "**SUNDAY — Day 7: Preparation & Planning**\n\n"
        "**Event Focus:** Reset prep and alliance alignment.\n"
        "**Primary Score Sources:** Minimal—this day is for setup.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 🧭 **Gathering Prep:** Queue gatherers before reset.\n"
        "• 📦 **Inventory Audit:** Stock speedups, stamina, and medals.\n"
        "• 📣 **Alliance Brief:** Review the week and align on Monday priorities.\n"
        "• 🗺️ **Resource Plan:** Assign farming targets for the next cycle.\n\n"
        "**✅ Checklist:**\n"
        "• Speedups restocked\n"
        "• Stamina items ready\n"
        "• Hero fragments staged\n"
        "• Gathering fleet prepared\n"
        "• Alliance comms confirmed\n\n"
        "**💡 Marcia’s Call:** Monday rewards preparation. Set the pace before the week starts."
    )
}

KILL_EVENT_SHIELD_REMINDERS = {
    0: "🛰️ Midnight sweep. The kill event just lit up, so drop that **24h shield** if you can.",
    2: "🌙 Early hours check. Two hours into the kill event. Make sure that shield is solid and refresh if needed.",
    4: "🌃 Pre-dawn watch. Four hours in—if you're running short on shield time, top it off now.",
    6: "☀️ Dawn check-in. If your shield is shorter, set alarms to refresh it before it fizzles.",
    12: "🧭 Midday scan. Keep shields up and remind your squad—no free hits on my watch.",
    18: "🌆 Dusk patrol. If you're on timers, renew now before the evening rush.",
    20: "🌆 Evening sweep. Four hours left—make sure protection is maxed and rally your allies.",
    22: "🌙 Late op window. Last stretch—top off protection and keep loved ones safe.",
}

# Reminders for the day BEFORE kill event (Friday)
KILL_EVENT_PRE_SHIELD_REMINDERS = {
    20: "⚠️ Kill event starts in 4 hours. Prep your **24h shield** stock and coordinate with your squad.",
    21: "🛡️ Kill event starts in 3 hours. Confirm shield timers and notify anyone still unprotected.",
    22: "🛡️ Kill event starts in 2 hours. Last call to drop shields and lock in protection.",
}


def _marcia_quip():
    return random.choice(MARCIA_SYSTEM_LINES)

# --- UI COMPONENTS ---

def _template_summary(template) -> str:
    summary = template["description"] if "description" in template.keys() else ""
    if not summary:
        return "No briefing saved."
    return summary[:90] + ("…" if len(summary) > 90 else "")


def _build_template_preview_embed(template_name: str, template_desc: str) -> discord.Embed:
    embed = discord.Embed(
        title="📋 Mission Template Preview",
        color=0x5865f2,
    )
    embed.add_field(name="Codename", value=template_name, inline=False)
    embed.add_field(name="Briefing", value=template_desc or "No briefing saved.", inline=False)
    embed.set_footer(text="Confirm or edit before scheduling this operation.")
    return embed


class TemplateSelect(discord.ui.Select):
    def __init__(self, templates, preview_callback, placeholder="Select a template..."):
        options = [
            discord.SelectOption(
                label=t["template_name"],
                description=_template_summary(t),
                emoji="📋",
            )
            for t in templates[:24]
        ]
        options.append(discord.SelectOption(label="Cancel", emoji="❌"))
        super().__init__(placeholder=placeholder, options=options)
        self.preview_callback = preview_callback

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "Cancel":
            return await interaction.response.edit_message(
                content="📡 Directive cancelled.",
                view=None,
                embed=None,
            )
        await self.preview_callback(interaction, self.values[0])


class TemplateEditModal(discord.ui.Modal, title="Edit Template Before Sending"):
    def __init__(self, template_name: str, template_desc: str, on_submit_callback):
        super().__init__()
        self.template_name = discord.ui.TextInput(
            label="Template Codename",
            default=template_name,
            max_length=100,
        )
        self.template_desc = discord.ui.TextInput(
            label="Briefing",
            style=discord.TextStyle.paragraph,
            default=template_desc,
            max_length=1500,
        )
        self.add_item(self.template_name)
        self.add_item(self.template_desc)
        self.on_submit_callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(
            interaction,
            self.template_name.value.strip(),
            self.template_desc.value.strip(),
        )


class TemplatePreviewView(discord.ui.View):
    def __init__(
        self,
        cog,
        ctx,
        template_name: str,
        template_desc: str,
        message_id: int | None = None,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.template_name = template_name
        self.template_desc = template_desc
        self.message_id = message_id

    async def _refresh_preview(self, interaction: discord.Interaction):
        embed = _build_template_preview_embed(self.template_name, self.template_desc)
        await interaction.response.edit_message(
            content="Review the template below before scheduling.",
            embed=embed,
            view=self,
        )

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.success, emoji="✅")
    async def use_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.use_template_callback(
            interaction,
            self.template_name,
            self.ctx,
            template_desc_override=self.template_desc,
        )

    @discord.ui.button(label="Edit Before Sending", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TemplateEditModal(
            self.template_name,
            self.template_desc,
            self._handle_edit_submit,
        )
        await interaction.response.send_modal(modal)

    async def _handle_edit_submit(
        self,
        interaction: discord.Interaction,
        template_name: str,
        template_desc: str,
    ):
        self.template_name = template_name or self.template_name
        self.template_desc = template_desc
        await interaction.response.defer()
        embed = _build_template_preview_embed(self.template_name, self.template_desc)
        if self.message_id is not None:
            await interaction.followup.edit_message(
                message_id=self.message_id,
                content="Review the template below before scheduling.",
                embed=embed,
                view=self,
            )
        else:
            await interaction.followup.send(
                content="Review the template below before scheduling.",
                embed=embed,
                view=self,
                ephemeral=True,
            )

    @discord.ui.button(label="Back to Templates", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        templates = await get_templates(interaction.guild.id)
        if not templates:
            return await interaction.response.edit_message(
                content="❌ Archive is empty.",
                view=None,
                embed=None,
            )
        view = TemplateMenuView(self.cog, self.ctx, templates)
        await interaction.response.edit_message(
            content="**Select a mission preset to preview:**",
            embed=None,
            view=view,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="🛑")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="📡 Directive cancelled.",
            view=None,
            embed=None,
        )


class TemplateMenuView(discord.ui.View):
    def __init__(self, cog, ctx, templates: list[dict]):
        super().__init__(timeout=90)
        self.cog = cog
        self.ctx = ctx
        self.templates = templates
        self.add_item(TemplateSelect(templates, self._preview_template))

    async def _preview_template(self, interaction: discord.Interaction, template_name: str):
        selected = next(
            (template for template in self.templates if template["template_name"] == template_name),
            None,
        )
        if not selected:
            return await interaction.response.edit_message(
                content="❌ Template not found. Try again from `/event`.",
                view=None,
                embed=None,
            )
        preview = _build_template_preview_embed(
            selected["template_name"],
            selected["description"],
        )
        await interaction.response.edit_message(
            content="Review the template below before scheduling.",
            embed=preview,
            view=TemplatePreviewView(
                self.cog,
                self.ctx,
                selected["template_name"],
                selected["description"],
                message_id=interaction.message.id if interaction.message else None,
            ),
        )

class EventMenuView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=60)
        self.cog, self.ctx = cog, ctx

    def _can_manage_events(self, interaction: discord.Interaction) -> bool:
        return bool(
            interaction.guild
            and interaction.user
            and interaction.user.guild_permissions.manage_guild
        )

    async def _require_manage_events(self, interaction: discord.Interaction) -> bool:
        if self._can_manage_events(interaction):
            return True
        await interaction.response.send_message(
            "🔒 You need Manage Server permissions to schedule or archive events.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Custom Event", style=discord.ButtonStyle.primary, emoji="✍️")
    async def custom_event(self, it, btn):
        if not await self._require_manage_events(it):
            return
        await it.response.send_message("📡 Setup signal sent to DMs.", ephemeral=True)
        await self.cog.create_mission_flow(self.ctx)

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.success, emoji="📋")
    async def template_event(self, it, btn):
        if not await self._require_manage_events(it):
            return
        tps = await get_templates(it.guild.id)
        if not tps: return await it.response.send_message("❌ Archive is empty.", ephemeral=True)
        view = TemplateMenuView(self.cog, self.ctx, tps)
        await it.response.edit_message(
            content="**Select a mission preset to preview:**",
            view=view,
            embed=None,
        )

    @discord.ui.button(label="Archive Template", style=discord.ButtonStyle.secondary, emoji="💾")
    async def create_template_btn(self, it, btn):
        if not await self._require_manage_events(it):
            return
        await it.response.send_message("💾 Archiving Module Active. Check DMs.", ephemeral=True)
        await self.cog.create_template_flow(self.ctx)

    @discord.ui.button(label="Upcoming Events", style=discord.ButtonStyle.secondary, emoji="📆")
    async def upcoming_events(self, it, btn):
        missions = await get_upcoming_missions(it.guild.id, limit=10)
        if not missions:
            return await it.response.send_message(
                "📡 *No upcoming events logged for this sector.*",
                ephemeral=True,
            )
        embed = self.cog._build_upcoming_events_embed(it.guild, missions)
        await it.response.send_message(embed=embed, ephemeral=True)

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

    async def _safe_send(self, ctx, *, ephemeral: bool = False, **kwargs):
        interaction = getattr(ctx, "interaction", None)
        if interaction:
            return await self.bot._safe_interaction_reply(
                interaction, ephemeral=ephemeral, **kwargs
            )
        kwargs.pop("ephemeral", None)
        return await ctx.send(**kwargs)

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
                    if chan and not await is_channel_ignored(guild.id, chan.id):
                        info = DUEL_DATA.get(now_server.weekday(), "No data.")
                        day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][now_server.weekday()]
                        await chan.send(
                            f"Good morning @everyone,\n\n"
                            f"📡 **MARCIA OS | DUEL DIRECTIVE – {day_name.upper()}**\n\n"
                            f"{info}\n\n"
                            f"Stay sharp and keep those points climbing. I'm tracking your progress.",
                            allowed_mentions=discord.AllowedMentions(everyone=True),
                        )
                        await mark_task_complete(task_id, date_str=date_key)
            # Saturday (weekday 5) - Kill Event Shield Reminders
            if now_server.weekday() == 5 and now_server.hour in KILL_EVENT_SHIELD_REMINDERS:
                date_key = now_server.strftime("%Y-%m-%d")
                task_id = f"duel_shield_{guild.id}_{now_server.hour}"
                if await can_run_daily_task(task_id, date_str=date_key):
                    chan = guild.get_channel(settings['event_channel_id'])
                    if chan and not await is_channel_ignored(guild.id, chan.id):
                        hours_left = max(0, 24 - now_server.hour)
                        reminder_line = KILL_EVENT_SHIELD_REMINDERS[now_server.hour]
                        await chan.send(
                            "Dear @everyone,\n\n"
                            "🛡️ **KILL EVENT SHIELD CHECK**\n\n"
                            f"{reminder_line}\n"
                            f"⏳ **{hours_left}h** remaining in the kill event.\n"
                            "If you can't maintain 24h shields, set alarms to refresh before they expire.\n"
                            "Marcia's monitoring the grid—keep your squad protected. 💙",
                            allowed_mentions=discord.AllowedMentions(everyone=True),
                        )
                        await mark_task_complete(task_id, date_str=date_key)
            
            # Friday (weekday 4) - Pre-Kill Event Shield Reminders
            if now_server.weekday() == 4 and now_server.hour in KILL_EVENT_PRE_SHIELD_REMINDERS:
                date_key = now_server.strftime("%Y-%m-%d")
                task_id = f"duel_pre_shield_{guild.id}_{now_server.hour}"
                if await can_run_daily_task(task_id, date_str=date_key):
                    chan = guild.get_channel(settings['event_channel_id'])
                    if chan and not await is_channel_ignored(guild.id, chan.id):
                        hours_until = 24 - now_server.hour
                        reminder_line = KILL_EVENT_PRE_SHIELD_REMINDERS[now_server.hour]
                        await chan.send(
                            "Attention @everyone,\n\n"
                            "🛡️ **PRE-KILL EVENT PREPARATION**\n\n"
                            f"{reminder_line}\n"
                            f"⏰ Kill event begins at midnight (in **{hours_until}h**).\n"
                            "Stack your shields, coordinate with your alliance, and be ready.\n"
                            "Marcia's got your back—but only if you prep smart. 💙",
                            allowed_mentions=discord.AllowedMentions(everyone=True),
                        )
                        await mark_task_complete(task_id, date_str=date_key)

    @tasks.loop(minutes=30)
    async def cycle_status(self):
        try: await self.bot.change_presence(activity=discord.Game(name=random.choice(MARCIA_STATUSES)))
        except: pass

    @commands.hybrid_command(name="event", description="Open Marcia's mission control console.")
    async def event_cmd(self, ctx):
        """Opens the Mission Control menu."""
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Events can only be managed inside servers.",
                ephemeral=True,
            )
        embed = discord.Embed(
            title="📡 Mission Control // Marcia",
            description=(
                "Pick how you want me to broadcast your operation.\n"
                "`Custom Event` opens a DM interview, `Use Template` pulls from your archive.\n"
                "`Upcoming Events` previews the next ops list for this sector.\n"
                "I track everything in UTC-2 (Dark War Survival)."
            ),
            color=0x2b2d31
        )
        embed.set_footer(text="Marcia drones on standby. Keep it sharp.")
        await self._safe_send(ctx, embed=embed, view=EventMenuView(self, ctx))

    @commands.hybrid_command(name="event_remove", description="Delete a scheduled operation.")
    @commands.has_permissions(manage_guild=True)
    async def event_remove(self, ctx, *, codename: str):
        """Remove a scheduled event."""
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Events can only be removed inside servers.",
                ephemeral=True,
            )
        await delete_mission(ctx.guild.id, codename)
        await self._safe_send(ctx, content=f"🗑️ Event **{codename}** scrubbed from the docket.")

    async def create_template_flow(self, ctx):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send("💾 **Template Title?** (what do we call this op?)")
            title = (await self.bot.wait_for('message', check=check, timeout=120)).content
            await ctx.author.send("📝 **Directives?** Drop the briefing text.")
            desc = (await self.bot.wait_for('message', check=check, timeout=300)).content
            await add_template(ctx.guild.id, title, desc)
            await ctx.author.send(f"✅ Protocol `{title}` archived. {_marcia_quip()}")
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
            ping_target = await self._resolve_ping(ctx, ping_msg.content)

            await ctx.author.send(
                f"⏰ **Target Time?** `YYYY-MM-DD HH:MM` using the game clock (UTC-2)."
            )
            t_msg = await self.bot.wait_for('message', check=check, timeout=180)
            await self.finalize_mission(ctx, name, desc, t_msg.content, location, ping_target)
        except asyncio.TimeoutError:
            await ctx.author.send("⌛ Timed out. Ping me again with `/event` when you're ready.")

    async def create_template_mission_flow(self, ctx, template_name, template_desc):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send(
                f"📋 **Template Loaded:** `{template_name}`\n{template_desc}\n\n"
                "Reply with a new codename or type `skip` to keep this name."
            )
            name_msg = await self.bot.wait_for('message', check=check, timeout=120)
            name = template_name if name_msg.content.lower().strip() == "skip" else name_msg.content

            await ctx.author.send("📍 **Location or voice channel?** Reply with coords/link or type `skip`.")
            location_msg = await self.bot.wait_for('message', check=check, timeout=180)
            location = None if location_msg.content.lower().strip() == "skip" else location_msg.content

            await ctx.author.send(
                "👥 **Ping who?** Mention a role, type `everyone`, or `none` to stay quiet."
            )
            ping_msg = await self.bot.wait_for('message', check=check, timeout=120)
            ping_target = await self._resolve_ping(ctx, ping_msg.content)

            await ctx.author.send(
                "⏰ **Target Time?** `YYYY-MM-DD HH:MM` using the game clock (UTC-2)."
            )
            t_msg = await self.bot.wait_for('message', check=check, timeout=180)
            await self.finalize_mission(ctx, name, template_desc, t_msg.content, location, ping_target)
        except asyncio.TimeoutError:
            await ctx.author.send("⌛ Timed out. Ping me again with `/event` when you're ready.")

    async def use_template_callback(
        self,
        interaction,
        template_name,
        ctx,
        template_desc_override: str | None = None,
    ):
        templates = await get_templates(ctx.guild.id)
        selected = next(
            (template for template in templates if template["template_name"] == template_name),
            None,
        )
        if not selected:
            return await self.bot._safe_interaction_reply(
                interaction,
                content="❌ Template not found. Try again from `/event`.",
                ephemeral=True,
            )

        await self.bot._safe_interaction_reply(
            interaction,
            content="📡 Template loaded. Check your DMs to schedule the time.",
            ephemeral=True,
        )
        await self.create_template_mission_flow(
            ctx,
            selected["template_name"],
            template_desc_override if template_desc_override is not None else selected["description"],
        )

    def _build_upcoming_events_embed(self, guild, missions):
        embed = discord.Embed(
            title="🛰️ Upcoming Operations (UTC-2)",
            color=0x3498db,
            description="I'll ping this channel when it's go-time.",
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
        embed.set_footer(text=f"Sector: {guild.name} | Clock: UTC-2")
        return embed

    async def finalize_mission(self, ctx, name, desc, t_str, location, ping_target):
        try:
            target_dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
            utc_dt = game_to_utc(target_dt)
            if utc_dt < datetime.now(timezone.utc):
                return await ctx.author.send("❌ Past time.")

            ping_role_id = ping_target.id if isinstance(ping_target, discord.Role) else ping_target
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
            await increment_activity_metric(ctx.guild.id, "events_scheduled")
            self.running_tasks[f"{ctx.guild.id}_{name}"] = self.bot.loop.create_task(
                self.manage_reminders(name, desc, utc_dt, ctx.guild.id, location, ping_role_id)
            )

            preview = self._build_event_embed(ctx.guild, name, desc, utc_dt, location, ping_role_id)
            await ctx.author.send(f"✅ Mission `{name}` locked. {_marcia_quip()}", embed=preview)

            settings = await get_settings(ctx.guild.id)
            if settings and settings['event_channel_id']:
                chan = ctx.guild.get_channel(settings['event_channel_id'])
                if chan and not await is_channel_ignored(ctx.guild.id, chan.id):
                    await chan.send("🛰️ **Operation Scheduled**", embed=preview)
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
            if not chan or await is_channel_ignored(guild_id, chan.id):
                continue

            drone = random.choice(DRONE_NAMES)
            guild = chan.guild
            role = guild.get_role(ping_role_id) if isinstance(ping_role_id, int) and ping_role_id >= 0 else None
            mention = ""
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=False)
            if mins == 60:
                mention = "@everyone"
                allowed_mentions = discord.AllowedMentions(everyone=True, roles=False)
            elif ping_role_id == -1:
                mention = "@everyone"
                allowed_mentions = discord.AllowedMentions(everyone=True, roles=False)
            elif role:
                mention = role.mention
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=True)
            
            # Add natural greeting variations for mentions
            greetings = ["Dear", "Hello", "Attention", "Listen up,", "Heads up,"]
            natural_mention = f"{random.choice(greetings)} {mention}" if mention else ""
            
            location_line = f"\n📍 {location}" if location else ""
            title, body = random.choice(TIMED_REMINDERS.get(mins, [("", "`{name}` is coming up.")]))
            body = body.format(name=name, drone=drone)
            quote = random.choice(MARCIA_SYSTEM_LINES)
            counts = await get_rsvp_counts(guild_id, name)
            participant_count = counts.get("going", 0)
            rsvp_line = f"Join Event {JOIN_EVENT_EMOJI}: {participant_count} joined"

            if mins == 60:
                # Build the message with natural mention integration
                if natural_mention:
                    msg = (
                        f"{natural_mention},\n\n"
                        f"{quote}\n\n"
                        f"{body}\n\n"
                        f"{desc}{location_line}\n\n"
                        f"{rsvp_line}\n\n"
                        f"React with {JOIN_EVENT_EMOJI} to join this event and receive DM reminders."
                        f"\n\n*Drone: {drone}*"
                    )
                else:
                    msg = (
                        f"{quote}\n\n"
                        f"{body}\n\n"
                        f"{desc}{location_line}\n\n"
                        f"{rsvp_line}\n\n"
                        f"React with {JOIN_EVENT_EMOJI} to join this event and receive DM reminders."
                        f"\n\n*Drone: {drone}*"
                    )
                sent = await chan.send(
                    msg,
                    allowed_mentions=allowed_mentions,
                )

                try:
                    await sent.add_reaction(JOIN_EVENT_EMOJI)
                except Exception:
                    logger.warning("Could not add join reaction for %s", name)
                await upsert_rsvp_prompt(guild_id, name, sent.id)
            else:
                # Build the message with natural mention integration
                if natural_mention:
                    msg = (
                        f"{natural_mention},\n\n"
                        f"{quote}\n\n"
                        f"{body}\n\n"
                        f"{desc}{location_line}\n\n"
                        f"{rsvp_line}\n\n"
                        f"*Drone: {drone}*"
                    )
                else:
                    msg = (
                        f"{quote}\n\n"
                        f"{body}\n\n"
                        f"{desc}{location_line}\n\n"
                        f"{rsvp_line}\n\n"
                        f"*Drone: {drone}*"
                    )
                await chan.send(
                    msg,
                    allowed_mentions=allowed_mentions,
                )
                await self._notify_dm_participants(guild_id, name, mins, desc, location)

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
        if ping_role_id is not None:
            if ping_role_id == -1:
                ping_display = "@everyone"
            else:
                role = guild.get_role(ping_role_id)
                ping_display = role.mention if role else "🔇 None"
            embed.add_field(name="👥 Ping", value=ping_display, inline=True)
        embed.set_footer(text=f"Sector: {guild.name} | Clock: UTC-2")
        return embed

    async def _notify_dm_participants(self, guild_id: int, codename: str, mins: int, desc: str, location: str | None) -> None:
        subscribers = await get_rsvp_members(guild_id, codename, status="going")
        if not subscribers:
            return

        guild = self.bot.get_guild(guild_id)
        location_line = f"\n📍 {location}" if location else ""
        countdown = "now" if mins == 0 else f"in {mins} minutes"

        for uid in subscribers:
            member = guild.get_member(uid) if guild else None
            user = member or self.bot.get_user(uid)
            if not user or getattr(user, "bot", False):
                continue

            try:
                await user.send(
                    f"📡 `{codename}` hits {countdown}.\n{desc}{location_line}\n\n"
                    "You joined this operation. Keep your gear ready and your squad accountable."
                )
            except Exception:
                logger.debug("Failed to DM participant %s for %s", uid, codename)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) in RSVP_EMOJIS:
            await self._handle_rsvp_reaction(payload, RSVP_EMOJIS[str(payload.emoji)])
            return

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) not in RSVP_EMOJIS:
            return
        await self._handle_rsvp_reaction(payload, RSVP_EMOJIS[str(payload.emoji)], removing=True)

    async def _handle_rsvp_reaction(
        self,
        payload: discord.RawReactionActionEvent,
        status: str,
        removing: bool = False,
    ) -> None:
        if payload.user_id == getattr(self.bot.user, "id", None):
            return

        prompt = await lookup_rsvp_prompt(payload.message_id)
        if not prompt:
            return

        guild_id, codename = prompt
        if payload.guild_id and payload.guild_id != guild_id:
            return

        if removing:
            await remove_rsvp_status(guild_id, codename, payload.user_id)
        else:
            await set_rsvp_status(guild_id, codename, payload.user_id, status)

    async def _resolve_ping(self, ctx, msg_content):
        text = msg_content.strip().lower()
        if text == "none":
            return None
        if text == "everyone":
            return -1
        # Try mention syntax
        if msg_content.startswith("<@&") and msg_content.endswith(">"):
            role_id = int(msg_content[3:-1])
            return ctx.guild.get_role(role_id)

        return discord.utils.get(ctx.guild.roles, name=msg_content)

async def setup(bot):
    await bot.add_cog(Events(bot))
