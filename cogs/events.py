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
from utils.time_utils import now_game, game_to_utc, format_game
from database import (
    add_mission,
    add_template,
    can_run_daily_task,
    delete_mission,
    get_all_active_missions,
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
from utils.async_utils import create_tracked_task

logger = logging.getLogger('MarciaOS.Events')
JOIN_EVENT_EMOJI = "🤝"
RSVP_EMOJIS = {
    JOIN_EVENT_EMOJI: "going",
}

DUEL_DATA = {
    0: (
        "**MONDAY - Day 1: Shelter Expansion**\n\n"
        "**Event Focus:** Building + Research CP growth, Wisdom Medals, and Gathering.\n"
        "**Primary Score Sources:** **Building CP increase**, **Research CP increase**, Wisdom Medal spending, Gathering returns.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 🏗️ **Construction:** Finish **high-CP** upgrades today. Start long timers early.\n"
        "• 🔬 **Research:** Finish **high-CP** tech nodes. Stack Wisdom Medals for better points.\n"
        "• 📜 **Wisdom Medals:** Spend on Research Center **Duel** + **Battle Strategy** (and core progression).\n"
        "• ⚙️ **Speedups:** **Construction + Research ONLY** today.\n"
        "• 💰 **Gathering:** Run marches all day. Points count when troops **return** (time returns after reset if possible). Mint/coin is bonus.\n"
        "• 🧱 **Precision Parts:** Use them.\n\n"
        "**🚫 Don’t Do Today:**\n"
        "• ❌ Claim **Radar** missions (save for Day 2).\n\n"
        "**💾 Save For Later:**\n"
        "• Radar missions\n"
        "• Gears, titanium alloy, power cores\n"
        "• Hero equipment lucky chests, Prime Recruit tickets\n"
        "• Truck/Shadow refresh tickets, **ALL hero fragments**\n\n"
        "**💡 Marcia’s Call:** If CP didn’t move, you didn’t score. Build smart, research smarter, gather nonstop."
    ),
    1: (
        "**TUESDAY - Day 2: Hero Initiative**\n\n"
        "**Event Focus:** Radar, Prime Recruit, Hero Fragments, Exclusive Equipment.\n"
        "**Primary Score Sources:** Radar missions, Recruit tickets, Hero fragments spent, Exclusive equipment star-ups.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 📡 **Radar Missions:** Clear as many as possible.\n"
        "• 🎖️ **Prime Recruit:** Spend gold tickets today.\n"
        "• 🧩 **Hero Fragments:** Star-rise **orange first**, then purple.\n"
        "• 🎯 **Exclusive Equipment:** Upgrade your main squad only (don’t burn resources on side pieces).\n\n"
        "**💾 Save For Later:**\n"
        "• Gears, power cores, wisdom medals, hero equipment lucky chests\n\n"
        "**💡 Marcia’s Call:** Start troop training before reset so it **finishes after reset** for Day 3 points."
    ),
    2: (
        "**WEDNESDAY - Day 3: Keep Progressing**\n\n"
        "**Event Focus:** Trucks, Shadow Calls, Troop Training, Equipment progression.\n"
        "**Primary Score Sources:** S-tier trucks, orange Shadow Calls, troop training/promotion + training speedups, power cores, hero equipment lucky chests (and red equipment stars if applicable).\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 🚚 **Escort/Cargo:** Run **S-tier** only. Use refreshes to chase S-tier.\n"
        "• 🕶️ **Shadow Calls:** Prioritize **orange** missions.\n"
        "• 🪖 **Troop Training:** Train all day; use **training** speedups only.\n"
        "• 🔋 **Power Cores:** Upgrade orange hero equipment.\n"
        "• 🎁 **Hero Equipment Lucky Chests:** Open/use saved chests for points + power.\n"
        "• ⭐ **Red Equipment (late game):** If your version scores it, push stars only if planned.\n\n"
        "**🚫 Don’t Do Today:**\n"
        "• ❌ Claim **Radar** missions (save for Day 4).\n\n"
        "**💾 Save For Later:**\n"
        "• Construction/research speedups, wisdom medals, energy (if your alliance rallies hard Day 4)\n\n"
        "**💡 Marcia’s Call:** Keep queues full. Empty barracks means empty scoreboard."
    ),
    3: (
        "**THURSDAY - Day 4: Arms Expert**\n\n"
        "**Event Focus:** Radar, APC upgrades, Roamers/Boomers.\n"
        "**Primary Score Sources:** Radar missions, gears/titanium/blueprints spent on APC, roamer kills, boomer rally kills.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 📡 **Radar Events:** Clear all available radar missions.\n"
        "• 🚙 **APC Upgrades:** Spend gears/titanium/blueprints on your **main** vehicle.\n"
        "• 🧟 **Roamers:** Farm efficiently (routes > randomness).\n"
        "• 💥 **Boomers:** Rally with alliance scale for best efficiency.\n\n"
        "**💾 Save For Later:**\n"
        "• Hero fragments, wisdom medals, speedups (unless you’re behind)\n\n"
        "**💡 Marcia’s Call:** Spend materials with a plan. Efficiency beats chaos."
    ),
    4: (
        "**FRIDAY - Day 5: Holistic Growth**\n\n"
        "**Event Focus:** Flexible catch-up across systems.\n"
        "**Primary Score Sources:** APC upgrades, hero fragments, wisdom medals, accelerations (construction/research/training/promotion), plus other growth items your version includes.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 🚙 **APC Upgrades:** Finish what you started earlier in the week.\n"
        "• ⏫ **Hero Fragments:** Star-rise high-rarity heroes first.\n"
        "• 🏅 **Wisdom Medals:** Spend on the most impactful research tiers.\n"
        "• ⏩ **Speedups:** Use what you need (construction/research/training/promotion).\n\n"
        "**💾 Save For Later:**\n"
        "• Dark Syndicate/Shadow refreshes + accelerations if you’re going hard on Saturday.\n\n"
        "**💡 Marcia’s Call:** Fix weak links today so Saturday doesn’t expose them."
    ),
    5: (
        "**SATURDAY - Day 6: Enemy Buster (Kill Event)**\n\n"
        "**Event Focus:** PvP eliminations and high-risk scoring.\n"
        "**Primary Score Sources:** Defeating enemy units (and sometimes losses score too), plus **trucks/shadows/speedups** if your in-game task list shows them today.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 💀 **Combat:** Choose targets wisely. Scout first, finish fast.\n"
        "• 🚚 **Trucks:** Chase **S-tier/Gold** escorts *only if your tasks score them today*.\n"
        "• 🕶️ **Shadow Calls:** Run **orange/gold** in intervals to avoid stamina burnout.\n"
        "• ⏩ **Speedups:** Use only if it converts to direct points (or healing if your version counts it).\n\n"
        "**🛡️ DEFENSE (If Not Participating):**\n"
        "• Keep **24h shields** active for the full event.\n"
        "• Set alarms for shorter shields-missed refreshes get you zeroed.\n"
        "• Shelter troops before shields drop.\n\n"
        "**💡 Marcia’s Call:** High risk day. Win smart, or sit safe."
    ),
    6: (
        "**SUNDAY - Day 7: Preparation & Planning**\n\n"
        "**Event Focus:** Rest day. Prep for next cycle + Survival Preparedness only.\n"
        "**Primary Score Sources:** Minimal-use it to stage resources and line up Monday.\n\n"
        "**📋 Action Plan (Today):**\n"
        "• 🧭 **Gathering Prep:** Send gatherers so returns land after reset.\n"
        "• 📦 **Inventory Audit:** Stage speedups, stamina/energy, medals, tickets, fragments.\n"
        "• 🧠 **Monday Targets:** Pick next big build + next big research now.\n"
        "• 📣 **Alliance Brief:** Remind members what to save for Day 1.\n\n"
        "**✅ Checklist:**\n"
        "• Builds + research queued/planned\n"
        "• Stamina items ready\n"
        "• Hero fragments staged\n"
        "• Gathering fleet prepared\n"
        "• Alliance comms confirmed\n\n"
        "**💡 Marcia’s Call:** Sunday decides Monday. Set the pace before the week starts."
    )
}


KILL_EVENT_SHIELD_REMINDERS = {
    0: "🛰️ Midnight sweep. The kill event just lit up, so drop that **24h shield** if you can.",
    6: "☀️ Dawn check-in. If your shield is shorter, set alarms to refresh it before it fizzles.",
    12: "🧭 Midday scan. Keep shields up and remind your squad-no free hits on my watch.",
    18: "🌆 Dusk patrol. If you're on timers, renew now before the evening rush.",
    22: "🌙 Late op window. Last stretch-top off protection and keep loved ones safe.",
}

# Reminders for the day BEFORE kill event (Friday)
KILL_EVENT_PRE_SHIELD_REMINDERS = {
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
        settings: dict,
        templates: list[dict],
        message_id: int | None = None,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.template_name = template_name
        self.template_desc = template_desc
        self.settings = settings
        self.templates = templates
        self.message_id = message_id

    async def _refresh_preview(self, interaction: discord.Interaction):
        embed = _build_template_preview_embed(self.template_name, self.template_desc)
        await interaction.response.edit_message(
            content="Review the template below before scheduling.",
            embed=embed,
            view=self,
        )

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.success, emoji="✅", row=0)
    async def use_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.use_template_callback(
            interaction,
            self.template_name,
            self.ctx,
            template_desc_override=self.template_desc,
        )

    @discord.ui.button(label="Edit Before Sending", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
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

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message_id is not None and self.ctx.interaction:
            try:
                await self.ctx.interaction.followup.edit_message(message_id=self.message_id, view=self)
            except discord.HTTPException:
                pass


class TemplateMenuView(discord.ui.View):
    def __init__(self, cog, ctx, templates: list[dict], settings: dict):
        super().__init__(timeout=90)
        self.cog = cog
        self.ctx = ctx
        self.templates = templates
        self.settings = settings
        self.add_item(TemplateSelect(templates, self._preview_template))

    async def _preview_template(self, interaction: discord.Interaction, template_name: str):
        selected = next(
            (template for template in self.templates if template["template_name"] == template_name),
            None,
        )
        if not selected:
            return await interaction.response.edit_message(
                content="❌ Template not found. Try again from `/gyper event`.",
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
                self.settings,
                self.templates,
                message_id=interaction.message.id if interaction.message else None,
            ),
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.ctx.interaction and self.ctx.interaction.message:
            try:
                await self.ctx.interaction.message.edit(view=self)
            except discord.HTTPException:
                pass

class EventMenuView(discord.ui.View):
    def __init__(self, cog, ctx, settings: dict):
        super().__init__(timeout=120)
        self.cog, self.ctx = cog, ctx
        self.settings = settings or {}
        self.event_channel_id = self.settings.get("event_channel_id")

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

    @discord.ui.button(label="New Event", style=discord.ButtonStyle.primary, emoji="✍️", row=0)
    async def custom_event(self, it, btn):
        if not await self._require_manage_events(it):
            return
        await it.response.send_message("📡 Setup signal sent to DMs.", ephemeral=True)
        await self.cog.create_mission_flow(self.ctx)

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.success, emoji="📋", row=0)
    async def template_event(self, it, btn):
        if not await self._require_manage_events(it):
            return
        tps = await get_templates(it.guild.id)
        if not tps: return await it.response.send_message("❌ Archive is empty.", ephemeral=True)
        view = TemplateMenuView(self.cog, self.ctx, tps, self.settings)
        await it.response.edit_message(
            content="**Select a mission preset to preview:**",
            view=view,
            embed=None,
        )

    @discord.ui.button(label="Archive Template", style=discord.ButtonStyle.secondary, emoji="💾", row=0)
    async def create_template_btn(self, it, btn):
        if not await self._require_manage_events(it):
            return
        await it.response.send_message("💾 Archiving Module Active. Check DMs.", ephemeral=True)
        await self.cog.create_template_flow(self.ctx)

    @discord.ui.button(label="Upcoming Events", style=discord.ButtonStyle.secondary, emoji="📆", row=1)
    async def upcoming_events(self, it, btn):
        missions = await get_upcoming_missions(it.guild.id, limit=10)
        if not missions:
            return await it.response.send_message(
                "📡 *No upcoming events logged for this sector.*",
                ephemeral=True,
            )
        embed = self.cog._build_upcoming_events_embed(it.guild, missions)
        await it.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Remove Event", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def remove_event(self, it, btn):
        if not await self._require_manage_events(it):
            return
        missions = await get_upcoming_missions(it.guild.id, limit=25)
        if not missions:
            return await it.response.send_message(
                "📡 *No upcoming events to remove in this sector.*",
                ephemeral=True,
            )
        view = EventRemovalView(self.cog, self.ctx, missions, self.settings)
        await it.response.send_message(
            content="Select the event you want to remove.",
            view=view,
            ephemeral=True,
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.ctx.interaction and self.ctx.interaction.message:
            try:
                await self.ctx.interaction.message.edit(view=self)
            except discord.HTTPException:
                pass


class EventRemovalView(discord.ui.View):
    def __init__(self, cog, ctx, missions, settings: dict):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.missions = missions
        self.settings = settings
        self.add_item(EventRemovalSelect(cog, ctx, missions, settings))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.ctx.interaction and self.ctx.interaction.message:
            try:
                await self.ctx.interaction.message.edit(view=self)
            except discord.HTTPException:
                pass


class EventRemovalSelect(discord.ui.Select):
    def __init__(self, cog, ctx, missions, settings: dict):
        options = []
        self.mission_map = {}
        self.missions = missions
        self.settings = settings
        for mission in missions[:25]:
            target = datetime.fromisoformat(mission["target_utc"]).astimezone(timezone.utc)
            time_label = format_game(target)
            label = f"{mission['codename']} • {time_label}"
            if len(label) > 100:
                label = label[:97] + "…"
            description = _template_summary(mission)
            options.append(
                discord.SelectOption(
                    label=label,
                    value=mission["codename"],
                    description=description,
                    emoji="🗑️",
                )
            )
            self.mission_map[mission["codename"]] = mission
        super().__init__(placeholder="Choose an event to remove...", options=options)
        self.cog = cog
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction):
        codename = self.values[0]
        mission = self.mission_map.get(codename)
        if not mission:
            return await interaction.response.edit_message(
                content="❌ Event not found. Run `/gyper event` again.",
                view=None,
                embed=None,
            )
        embed = self.cog._build_event_removal_embed(interaction.guild, mission)
        await interaction.response.edit_message(
            content="Confirm removal below.",
            embed=embed,
            view=EventRemovalConfirmView(self.cog, self.ctx, mission, self.missions, self.settings),
        )


class EventRemovalConfirmView(discord.ui.View):
    def __init__(self, cog, ctx, mission, missions, settings: dict):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.mission = mission
        self.missions = missions
        self.settings = settings

    @discord.ui.button(label="Confirm removal", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "🔒 You need Manage Server permissions to remove events.",
                ephemeral=True,
            )
        codename = self.mission["codename"]
        await delete_mission(interaction.guild.id, codename)
        self.cog.cancel_mission_task(interaction.guild.id, codename)
        await interaction.response.edit_message(
            content=f"🗑️ Event **{codename}** removed.",
            embed=None,
            view=None,
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

# --- COG MAIN ---

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.running_tasks = {}
        self.cycle_status.start()
        self.check_duel_reset.start()
        create_tracked_task(
            self.recover_missions(),
            name="recover-missions",
            logger=logger,
        )

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

    @staticmethod
    def _build_event_menu_embed() -> discord.Embed:
        embed = discord.Embed(
            title="📡 Mission Control // Marcia",
            description=(
                "Pick how you want me to broadcast your operation.\n"
                "`New Event` opens a DM interview, `Use Template` pulls from your archive.\n"
                "`Archive Template` saves a new template for reuse.\n"
                "`Upcoming Events` previews the next ops list for this sector.\n"
                "`Remove Event` lets you delete a scheduled op without leaving this menu.\n"
                "I track everything in UTC-2 (Dark War Survival)."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Marcia drones on standby. Keep it sharp.")
        return embed

    async def recover_missions(self):
        """Reloads active missions from SQL on startup."""
        await self.bot.wait_until_ready()
        all_missions = await get_all_active_missions()
        for m in all_missions:
            try:
                utc_dt = datetime.fromisoformat(m['target_utc']).astimezone(timezone.utc)
                if utc_dt > datetime.now(timezone.utc):
                    task_key = f"{m['guild_id']}_{m['codename']}"
                    self.running_tasks[task_key] = create_tracked_task(
                        self.manage_reminders(
                            m['codename'],
                            m['description'],
                            utc_dt,
                            m['guild_id'],
                            location=m.get('location'),
                            ping_role_id=m.get('ping_role_id'),
                        ),
                        name=f"mission-reminder-{task_key}",
                        logger=logger,
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
                        try:
                            await chan.send(
                                f"Good morning @everyone,\n\n"
                                f"📡 **MARCIA OS | DUEL DIRECTIVE – {day_name.upper()}**\n\n"
                                f"{info}\n\n"
                                f"Stay sharp and keep those points climbing. I'm tracking your progress.",
                                allowed_mentions=discord.AllowedMentions(everyone=True),
                            )
                            await mark_task_complete(task_id, date_str=date_key)
                        except discord.Forbidden:
                            logger.warning(
                                "Missing access to send duel directive in %s (%s).",
                                guild.name,
                                chan.id,
                            )
            # Saturday (weekday 5) - Kill Event Shield Reminders
            if now_server.weekday() == 5 and now_server.hour in KILL_EVENT_SHIELD_REMINDERS:
                date_key = now_server.strftime("%Y-%m-%d")
                task_id = f"duel_shield_{guild.id}_{now_server.hour}"
                if await can_run_daily_task(task_id, date_str=date_key):
                    chan = guild.get_channel(settings['event_channel_id'])
                    if chan and not await is_channel_ignored(guild.id, chan.id):
                        hours_left = max(0, 24 - now_server.hour)
                        reminder_line = KILL_EVENT_SHIELD_REMINDERS[now_server.hour]
                        try:
                            await chan.send(
                                "Dear @everyone,\n\n"
                                "🛡️ **KILL EVENT SHIELD CHECK**\n\n"
                                f"{reminder_line}\n"
                                f"⏳ **{hours_left}h** remaining in the kill event.\n"
                                "If you can't maintain 24h shields, set alarms to refresh before they expire.\n"
                                "Marcia's monitoring the grid-keep your squad protected. 💙",
                                allowed_mentions=discord.AllowedMentions(everyone=True),
                            )
                            await mark_task_complete(task_id, date_str=date_key)
                        except discord.Forbidden:
                            logger.warning(
                                "Missing access to send kill event reminder in %s (%s).",
                                guild.name,
                                chan.id,
                            )
            
            # Friday (weekday 4) - Pre-Kill Event Shield Reminders
            if now_server.weekday() == 4 and now_server.hour in KILL_EVENT_PRE_SHIELD_REMINDERS:
                date_key = now_server.strftime("%Y-%m-%d")
                task_id = f"duel_pre_shield_{guild.id}_{now_server.hour}"
                if await can_run_daily_task(task_id, date_str=date_key):
                    chan = guild.get_channel(settings['event_channel_id'])
                    if chan and not await is_channel_ignored(guild.id, chan.id):
                        hours_until = 24 - now_server.hour
                        reminder_line = KILL_EVENT_PRE_SHIELD_REMINDERS[now_server.hour]
                        try:
                            await chan.send(
                                "Attention @everyone,\n\n"
                                "🛡️ **PRE-KILL EVENT PREPARATION**\n\n"
                                f"{reminder_line}\n"
                                f"⏰ Kill event begins at midnight (in **{hours_until}h**).\n"
                                "Stack your shields, coordinate with your alliance, and be ready.\n"
                                "Marcia's got your back-but only if you prep smart. 💙",
                                allowed_mentions=discord.AllowedMentions(everyone=True),
                            )
                            await mark_task_complete(task_id, date_str=date_key)
                        except discord.Forbidden:
                            logger.warning(
                                "Missing access to send pre-kill reminder in %s (%s).",
                                guild.name,
                                chan.id,
                            )

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
        settings = await get_settings(ctx.guild.id)
        if not settings or not settings.get("event_channel_id"):
            return await self._safe_send(
                ctx,
                content="📌 Set an events channel first with `/gyper setup` so I know where to post ops.",
                ephemeral=True,
            )
        embed = self._build_event_menu_embed()
        await self._safe_send(ctx, embed=embed, view=EventMenuView(self, ctx, settings))

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
            await ctx.author.send("⌛ Timed out. Ping me again with `/gyper event` when you're ready.")

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
            await ctx.author.send("⌛ Timed out. Ping me again with `/gyper event` when you're ready.")

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
                content="❌ Template not found. Try again from `/gyper event`.",
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
            color=0x5865F2,
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

    def _build_event_removal_embed(self, guild, mission):
        mission_data = dict(mission) if not isinstance(mission, dict) else mission
        target_value = mission_data.get("target_utc")
        try:
            target = (
                datetime.fromisoformat(target_value).astimezone(timezone.utc)
                if target_value
                else None
            )
        except (TypeError, ValueError):
            target = None
        scheduled_value = format_game(target) if target else "Unknown schedule"
        embed = discord.Embed(
            title="🗑️ Remove Operation",
            description="Confirm the event you want to scrub from the docket.",
            color=0x5865F2,
        )
        embed.add_field(name="Codename", value=mission_data.get("codename", "Unknown"), inline=False)
        embed.add_field(name="Scheduled", value=scheduled_value, inline=True)
        description = mission_data.get("description") or "No description"
        embed.add_field(name="Briefing", value=description, inline=False)
        embed.set_footer(text=f"Sector: {guild.name} | Clock: UTC-2")
        return embed

    def cancel_mission_task(self, guild_id: int, codename: str) -> None:
        task_key = f"{guild_id}_{codename}"
        task = self.running_tasks.pop(task_key, None)
        if task:
            task.cancel()

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
            task_key = f"{ctx.guild.id}_{name}"
            self.running_tasks[task_key] = create_tracked_task(
                self.manage_reminders(name, desc, utc_dt, ctx.guild.id, location, ping_role_id),
                name=f"mission-reminder-{task_key}",
                logger=logger,
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
            if mins == 60:
                if not (settings and settings['event_channel_id']):
                    continue

                chan = self.bot.get_channel(settings['event_channel_id'])
                if not chan or await is_channel_ignored(guild_id, chan.id):
                    continue

                drone = random.choice(DRONE_NAMES)
                guild = chan.guild
                role = guild.get_role(ping_role_id) if isinstance(ping_role_id, int) and ping_role_id >= 0 else None
                location_line = f"\n📍 {location}" if location else ""
                title, body = random.choice(TIMED_REMINDERS.get(mins, [("", "`{name}` is coming up.")]))
                body = body.format(name=name, drone=drone)
                quote = random.choice(MARCIA_SYSTEM_LINES)

                greetings = ["Dear", "Hello", "Attention", "Listen up,", "Heads up,"]
                role_line = f" {role.mention}" if role else ""
                natural_mention = f"{random.choice(greetings)} @everyone{role_line}"

                msg = (
                    f"{natural_mention},\n\n"
                    f"{quote}\n\n"
                    f"{body}\n\n"
                    f"{desc}{location_line}\n\n"
                    f"React with {JOIN_EVENT_EMOJI} to join this event and receive DM reminders."
                    f"\n\n*Drone: {drone}*"
                )
                sent = await chan.send(
                    msg,
                    allowed_mentions=discord.AllowedMentions(everyone=True, roles=bool(role)),
                )

                try:
                    await sent.add_reaction(JOIN_EVENT_EMOJI)
                except Exception:
                    logger.warning("Could not add join reaction for %s", name)
                await upsert_rsvp_prompt(guild_id, name, sent.id)
            else:
                if mins == 0:
                    await self._announce_event_start(
                        guild_id,
                        name,
                        desc,
                        location,
                        ping_role_id,
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

    async def _announce_event_start(
        self,
        guild_id: int,
        name: str,
        desc: str,
        location: str | None,
        ping_role_id: int | None,
    ) -> None:
        settings = await get_settings(guild_id)
        if not (settings and settings.get("event_channel_id")):
            return

        chan = self.bot.get_channel(settings["event_channel_id"])
        if not chan or await is_channel_ignored(guild_id, chan.id):
            return

        role = None
        if isinstance(ping_role_id, int) and ping_role_id >= 0:
            role = chan.guild.get_role(ping_role_id)

        mention = ""
        if ping_role_id == -1:
            mention = "@everyone"
        elif role:
            mention = role.mention

        mention_line = f"{mention}\n\n" if mention else ""
        location_line = f"\n📍 {location}" if location else ""
        message = (
            f"{mention_line}"
            "📡 **Operation Live**\n\n"
            f"**{name}** is starting now.\n\n"
            f"{desc}{location_line}"
        )

        try:
            await chan.send(
                message,
                allowed_mentions=discord.AllowedMentions(
                    everyone=ping_role_id == -1,
                    roles=bool(role),
                ),
            )
        except discord.Forbidden:
            logger.warning(
                "Missing access to send event kickoff in %s (%s).",
                chan.guild.name,
                chan.id,
            )

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
