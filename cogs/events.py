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
MISSED_EVENT_GRACE = timedelta(minutes=10)
EVENT_BULK_HEADER = "name | date | time | desc | location | ping"
MAX_BULK_EVENT_ROWS = 50
EVENT_BULK_EXAMPLE = (
    "Fortress Push | 2026-03-27 | 20:00 | Rally center target | VC 2 | @Raid Team\n"
    "Desert Reset | 2026-03-28 | 18:30 | Be online 10 min early | - | everyone\n"
    "Trap Defense | 2026-03-29 | 21:15 | - | - | none"
)

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
    0: [
        "🛰️ Kill day is live with **24h** on the clock. Drop a full shield and lock down your base.",
        "🌌 Event start. You've got **24h**-fortify now so you don't scramble later.",
        "🚨 Opening bell. **24h** remain-raise shields and settle in for the long haul.",
    ],
    8: [
        "☀️ Eight hours in. Plenty of time left-keep your bubble solid and timers clean.",
        "🌤️ Mid-morning pass. Still a long stretch ahead-refresh if your timers look shaky.",
        "🕊️ Eight-hour check. Protect the base and wake anyone drifting off timers.",
    ],
    16: [
        "🌆 **8h left.** Perfect time to swap into an **8h shield** and cruise to reset.",
        "🌇 **8 hours remaining.** If you can't hold a 24h, lock an **8h** now.",
        "🚦 **8h to go.** Flip to an **8h shield** and ride the finish line.",
    ],
}

# Reminders for the day BEFORE kill event (Friday)
KILL_EVENT_PRE_SHIELD_REMINDERS = {
    16: [
        "🛡️ Kill event starts in **8 hours**. Set shields now so no one is caught at reset.",
        "⏳ Eight hours out. Prep protection and confirm everyone knows the plan.",
        "📣 **8h warning.** Stage shields and make sure every base is ready.",
    ],
    22: [
        "🛡️ Kill event starts in **2 hours**. Last call to bubble up and lock in protection.",
        "🚨 Two hours out. Time to shield and get comfortable.",
        "⌛ **2h ping.** Shield now or be the story tomorrow.",
    ],
}


def _pick_reminder_line(reminder_map: dict[int, list[str]], hour: int) -> str:
    return random.choice(reminder_map[hour])


def _shield_recommendation(hours_left: int) -> str:
    if hours_left > 8:
        return "🛡️ **Shield call:** Go for a **24h shield** to cover the remaining hours."
    return "🛡️ **Shield call:** An **8h shield** will carry you through the rest of the event."


def _marcia_quip():
    return random.choice(MARCIA_SYSTEM_LINES)


def _is_skipped_value(raw_value: str | None) -> bool:
    if raw_value is None:
        return True
    return raw_value.strip() in {"", "-", "—"}

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


class EventDraftModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        title: str,
        name: str = "",
        desc: str = "",
        date_value: str = "",
        time_value: str = "",
        on_submit_callback,
    ):
        super().__init__(title=title)
        self.event_name = discord.ui.TextInput(
            label="Event name",
            default=name,
            max_length=100,
        )
        self.event_desc = discord.ui.TextInput(
            label="Briefing",
            style=discord.TextStyle.paragraph,
            default=desc,
            max_length=1500,
        )
        self.event_date = discord.ui.TextInput(
            label="Date (YYYY-MM-DD, UTC-2)",
            default=date_value,
            max_length=10,
        )
        self.event_time = discord.ui.TextInput(
            label="Time (HH:MM, UTC-2)",
            default=time_value,
            max_length=5,
        )
        self.add_item(self.event_name)
        self.add_item(self.event_desc)
        self.add_item(self.event_date)
        self.add_item(self.event_time)
        self.on_submit_callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(
            interaction,
            self.event_name.value.strip(),
            self.event_desc.value.strip(),
            self.event_date.value.strip(),
            self.event_time.value.strip(),
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

    @discord.ui.button(label="Schedule Template", style=discord.ButtonStyle.success, emoji="✅", row=0)
    async def use_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.open_event_draft_modal(
            interaction,
            self.ctx,
            name=self.template_name,
            desc=self.template_desc,
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


class EventDraftView(discord.ui.View):
    def __init__(self, cog, ctx, draft: dict, message_id: int | None = None):
        super().__init__(timeout=180)
        self.cog = cog
        self.ctx = ctx
        self.draft = draft
        self.message_id = message_id

    @discord.ui.button(label="Confirm & Schedule", style=discord.ButtonStyle.success, emoji="✅", row=0)
    async def confirm_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.cog.finalize_mission(
            self.ctx,
            self.draft["name"],
            self.draft["desc"],
            self.draft["t_str"],
            self.draft["location"],
            self.draft["ping_role_id"],
        )
        try:
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                content="✅ Mission scheduled. I’ll post the preview in the events channel.",
                embed=None,
                view=None,
            )
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Edit Details", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
    async def edit_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.open_event_draft_modal(
            interaction,
            self.ctx,
            name=self.draft["name"],
            desc=self.draft["desc"],
            date_value=self.draft["date_value"],
            time_value=self.draft["time_value"],
            existing_message_id=interaction.message.id if interaction.message else None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="🛑", row=0)
    async def cancel_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="📡 Draft cancelled. Run `/event` when you're ready to reschedule.",
            embed=None,
            view=None,
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message_id is not None and self.ctx.interaction:
            try:
                await self.ctx.interaction.followup.edit_message(message_id=self.message_id, view=self)
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
        await self.cog.open_event_draft_modal(it, self.ctx)

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

    @discord.ui.button(label="Bulk Import", style=discord.ButtonStyle.success, emoji="📦", row=1)
    async def bulk_import(self, it, btn):
        if not await self._require_manage_events(it):
            return
        await it.response.send_message(
            embed=self.cog._build_bulk_event_help_embed(),
            view=BulkEventLauncherView(self.cog, self.ctx),
            ephemeral=True,
        )

    @discord.ui.button(label="Upcoming Events", style=discord.ButtonStyle.secondary, emoji="📆", row=2)
    async def upcoming_events(self, it, btn):
        missions = await get_upcoming_missions(it.guild.id, limit=10)
        if not missions:
            return await it.response.send_message(
                "📡 *No upcoming events logged for this sector.*",
                ephemeral=True,
            )
        embed = self.cog._build_upcoming_events_embed(it.guild, missions)
        await it.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Share Upcoming", style=discord.ButtonStyle.secondary, emoji="📣", row=2)
    async def share_upcoming(self, it, btn):
        if not await self._require_manage_events(it):
            return
        missions = await get_upcoming_missions(it.guild.id, limit=10)
        if not missions:
            return await it.response.send_message(
                "📡 *No upcoming events logged for this sector.*",
                ephemeral=True,
            )
        embed = self.cog._build_upcoming_events_embed(it.guild, missions)
        channel = it.guild.get_channel(self.event_channel_id) if self.event_channel_id else None
        if channel and not await is_channel_ignored(it.guild.id, channel.id):
            try:
                await channel.send("🛰️ **Upcoming Operations**", embed=embed)
                return await it.response.send_message(
                    f"✅ Posted the queue in {channel.mention}.",
                    ephemeral=True,
                )
            except discord.Forbidden:
                return await it.response.send_message(
                    "❌ I can't post in the events channel. Check permissions.",
                    ephemeral=True,
                )
        await it.response.send_message(
            "❌ Events channel not found. Run `/setup` to link one.",
            ephemeral=True,
        )

    @discord.ui.button(label="Remove Event", style=discord.ButtonStyle.danger, emoji="🗑️", row=2)
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


class BulkEventLauncherView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=180)
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="Paste in Chat", style=discord.ButtonStyle.primary, emoji="📝")
    async def launch_chat_import(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Only the requester can use this import.", ephemeral=True)
        await interaction.response.send_message(
            "📝 Paste your event batch as your next message in this channel within 3 minutes. "
            "You can paste plain lines or wrap them in a ```text``` code block.",
            ephemeral=True,
        )
        await self.cog._collect_bulk_event_message(interaction, self.ctx)


class BulkEventPreviewView(discord.ui.View):
    def __init__(self, cog, ctx, parsed_rows: list[dict], errors: list[str]):
        super().__init__(timeout=180)
        self.cog = cog
        self.ctx = ctx
        self.parsed_rows = parsed_rows
        self.errors = errors

    @discord.ui.button(label="Schedule Valid Rows", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Only the requester can confirm this import.", ephemeral=True)
        if not self.parsed_rows:
            return await interaction.response.send_message("❌ There are no valid rows to schedule yet.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        imported = await self.cog._commit_bulk_events(self.ctx, self.parsed_rows)
        summary = f"✅ Scheduled **{imported}** event(s)."
        if self.errors:
            summary += f" Skipped **{len(self.errors)}** issue(s) listed in the preview."
        await self.ctx.send(summary, delete_after=12)
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            content="✅ Scheduled. Confirmation posted in-channel.",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="🛑")
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Only the requester can cancel this import.", ephemeral=True)
        await interaction.response.edit_message(
            content="📭 Bulk event import cancelled.",
            embed=None,
            view=None,
        )


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
                content="❌ Event not found. Run `/event` again.",
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

    def _parse_ping_target(self, guild: discord.Guild, raw_value: str) -> tuple[int | None, str]:
        raw = (raw_value or "").strip()
        if not raw:
            return -1, "@everyone"
        lowered = raw.lower()
        if lowered in {"everyone", "@everyone", "all"}:
            return -1, "@everyone"
        if lowered in {"none", "no", "off"}:
            return None, "none"
        role_id = None
        if raw.startswith("<@&") and raw.endswith(">"):
            try:
                role_id = int(raw[3:-1])
            except ValueError:
                role_id = None
        elif raw.isdigit():
            role_id = int(raw)
        if role_id is not None:
            role = guild.get_role(role_id)
            if role:
                return role.id, role.name
        return -1, "@everyone"

    def _parse_optional_ping_target(self, guild: discord.Guild, raw_value: str) -> tuple[int | None, str]:
        raw = (raw_value or "").strip()
        if _is_skipped_value(raw):
            return None, "none"
        lowered = raw.lower()
        if lowered in {"none", "no", "off"}:
            return None, "none"
        if lowered in {"everyone", "@everyone", "all"}:
            return -1, "@everyone"
        role_id = None
        if raw.startswith("<@&") and raw.endswith(">"):
            try:
                role_id = int(raw[3:-1])
            except ValueError:
                role_id = None
        elif raw.isdigit():
            role_id = int(raw)
        if role_id is not None:
            role = guild.get_role(role_id)
            if role:
                return role.id, role.name
        role_by_name = discord.utils.get(guild.roles, name=raw.lstrip("@"))
        if role_by_name:
            return role_by_name.id, role_by_name.name
        raise ValueError("ping must be `everyone`, `none`, `-`, or a valid role mention/name.")

    def _build_bulk_event_help_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📦 Bulk Event Import",
            description=(
                "Paste one event per line using the exact format below.\n"
                "Use `-` to skip optional fields like briefing, location, or ping."
            ),
            color=0x5865F2,
        )
        embed.add_field(name="Format", value=f"```text\n{EVENT_BULK_HEADER}\n```", inline=False)
        embed.add_field(
            name="Rules",
            value=(
                "• `date` = `YYYY-MM-DD`\n"
                "• `time` = `HH:MM` in game time (UTC-2)\n"
                "• `ping` can be `everyone`, `none`, `-`, or a role mention/name\n"
                "• I validate every row before anything is scheduled"
            ),
            inline=False,
        )
        embed.add_field(name="Example", value=f"```text\n{EVENT_BULK_EXAMPLE}\n```", inline=False)
        embed.set_footer(text="Click “Paste in Chat”, then send your batch as a normal message.")
        return embed

    @staticmethod
    def _normalize_bulk_message_content(raw_text: str) -> str:
        cleaned = (raw_text or "").strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            lines = cleaned.splitlines()
            if len(lines) >= 2:
                cleaned = "\n".join(lines[1:-1]).strip()
        return cleaned

    async def _collect_bulk_event_message(self, interaction: discord.Interaction, ctx) -> None:
        def check(message: discord.Message) -> bool:
            return (
                message.author.id == ctx.author.id
                and message.guild
                and ctx.guild
                and message.guild.id == ctx.guild.id
                and message.channel.id == ctx.channel.id
            )

        try:
            message = await self.bot.wait_for("message", check=check, timeout=180)
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "⌛ Bulk import timed out. Click **Bulk Import** again when you're ready.",
                ephemeral=True,
            )
            return

        parsed_rows, errors = self._parse_bulk_event_rows(
            ctx.guild,
            self._normalize_bulk_message_content(message.content),
        )
        embed = self._build_bulk_event_preview_embed(ctx.guild, parsed_rows, errors)
        if not parsed_rows:
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        await interaction.followup.send(
            embed=embed,
            view=BulkEventPreviewView(self, ctx, parsed_rows, errors),
            ephemeral=True,
        )

    def _parse_bulk_event_rows(self, guild: discord.Guild, raw_text: str) -> tuple[list[dict], list[str]]:
        parsed_rows: list[dict] = []
        errors: list[str] = []
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            return parsed_rows, ["Add at least one event row before importing."]

        start_index = 0
        if lines[0].lower() == EVENT_BULK_HEADER:
            start_index = 1
        if start_index >= len(lines):
            return parsed_rows, ["Add at least one event row below the header."]

        data_lines = lines[start_index:]
        if len(data_lines) > MAX_BULK_EVENT_ROWS:
            errors.append(
                f"Only {MAX_BULK_EVENT_ROWS} rows can be imported at once. Extra rows were ignored."
            )
            data_lines = data_lines[:MAX_BULK_EVENT_ROWS]

        now_utc = datetime.now(timezone.utc)
        for row_number, line in enumerate(data_lines, start=1):
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 6:
                errors.append(
                    f"Row {row_number}: expected 6 columns (`name | date | time | desc | location | ping`)."
                )
                continue

            name, date_raw, time_raw, desc_raw, location_raw, ping_raw = parts
            if _is_skipped_value(name):
                errors.append(f"Row {row_number}: `name` is required.")
                continue
            if _is_skipped_value(date_raw) or _is_skipped_value(time_raw):
                errors.append(f"Row {row_number}: both `date` and `time` are required.")
                continue

            t_str = f"{date_raw} {time_raw}"
            try:
                target_dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
            except ValueError:
                errors.append(f"Row {row_number}: use `YYYY-MM-DD` and `HH:MM`.")
                continue
            utc_dt = game_to_utc(target_dt)
            if utc_dt <= now_utc:
                errors.append(f"Row {row_number}: event time must be in the future.")
                continue

            try:
                ping_role_id, ping_raw = self._parse_optional_ping_target(guild, ping_raw)
            except ValueError as exc:
                errors.append(f"Row {row_number}: {exc}")
                continue

            parsed_rows.append(
                {
                    "row_number": row_number,
                    "name": name,
                    "desc": "" if _is_skipped_value(desc_raw) else desc_raw,
                    "location": None if _is_skipped_value(location_raw) else location_raw,
                    "ping_role_id": ping_role_id,
                    "ping_raw": ping_raw,
                    "t_str": t_str,
                    "utc_dt": utc_dt,
                }
            )

        return parsed_rows, errors

    def _build_bulk_event_preview_embed(
        self,
        guild: discord.Guild,
        parsed_rows: list[dict],
        errors: list[str],
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🛰️ Bulk Event Preview",
            description=(
                f"Ready to schedule **{len(parsed_rows)}** event(s). "
                f"I found **{len(errors)}** issue(s)."
            ),
            color=0x5865F2 if parsed_rows else 0xED4245,
        )
        if parsed_rows:
            lines = []
            for row in parsed_rows[:8]:
                ping_label = row["ping_raw"]
                location = row["location"] or "No location"
                lines.append(
                    f"• Row {row['row_number']} • **{row['name']}** • {format_game(row['utc_dt'])}\n"
                    f"  └ {location} • Ping: {ping_label}"
                )
            embed.add_field(name="Valid rows", value="\n".join(lines), inline=False)
            if len(parsed_rows) > 8:
                embed.add_field(
                    name="More rows",
                    value=f"...and **{len(parsed_rows) - 8}** more ready to schedule.",
                    inline=False,
                )
        if errors:
            embed.add_field(
                name="Issues to review",
                value="\n".join(f"• {item}" for item in errors[:8]),
                inline=False,
            )
            if len(errors) > 8:
                embed.add_field(
                    name="More issues",
                    value=f"...and **{len(errors) - 8}** more issue(s).",
                    inline=False,
                )
        embed.set_footer(text=f"Sector: {guild.name} | Clock: UTC-2")
        return embed

    async def _commit_bulk_events(self, ctx, parsed_rows: list[dict]) -> int:
        for row in parsed_rows:
            await self.finalize_mission(
                ctx,
                row["name"],
                row["desc"],
                row["t_str"],
                row["location"],
                row["ping_role_id"],
            )
        return len(parsed_rows)

    async def open_event_draft_modal(
        self,
        interaction: discord.Interaction,
        ctx,
        *,
        name: str = "",
        desc: str = "",
        date_value: str = "",
        time_value: str = "",
        existing_message_id: int | None = None,
    ) -> None:
        async def _handle_submit(
            submit_interaction: discord.Interaction,
            event_name: str,
            event_desc: str,
            date_input: str,
            time_input: str,
        ):
            if not event_name:
                return await submit_interaction.response.send_message(
                    "❌ Please provide an event name.",
                    ephemeral=True,
                )
            t_str = f"{date_input} {time_input}"
            try:
                target_dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
            except ValueError:
                return await submit_interaction.response.send_message(
                    "❌ Please use `YYYY-MM-DD` and `HH:MM` (UTC-2).",
                    ephemeral=True,
                )
            utc_dt = game_to_utc(target_dt)
            if utc_dt < datetime.now(timezone.utc):
                return await submit_interaction.response.send_message(
                    "❌ That time is in the past. Pick a future window.",
                    ephemeral=True,
                )
            draft = {
                "name": event_name,
                "desc": event_desc,
                "t_str": t_str,
                "utc_dt": utc_dt,
                "location": None,
                "ping_role_id": -1,
                "ping_raw": "@everyone",
                "date_value": date_input,
                "time_value": time_input,
            }
            embed = self._build_event_embed(
                submit_interaction.guild,
                event_name,
                event_desc,
                utc_dt,
                None,
                -1,
            )
            view = EventDraftView(self, ctx, draft, message_id=existing_message_id)
            if existing_message_id is not None:
                await submit_interaction.response.defer()
                await submit_interaction.followup.edit_message(
                    message_id=existing_message_id,
                    content="Review the event details below before confirming.",
                    embed=embed,
                    view=view,
                )
            else:
                await submit_interaction.response.send_message(
                    content="Review the event details below before confirming.",
                    embed=embed,
                    view=view,
                    ephemeral=True,
                )

        modal = EventDraftModal(
            title="Schedule Event",
            name=name,
            desc=desc,
            date_value=date_value,
            time_value=time_value,
            on_submit_callback=_handle_submit,
        )
        await interaction.response.send_modal(modal)

    async def _resolve_event_channel(self, guild_id: int) -> discord.abc.Messageable | None:
        settings = await get_settings(guild_id)
        if not settings or not settings.get("event_channel_id"):
            return None

        channel_id = settings["event_channel_id"]
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException as exc:
                logger.warning(
                    "Failed to fetch event channel %s in guild %s: %s",
                    channel_id,
                    guild_id,
                    exc,
                )
                return None

        if channel is None or await is_channel_ignored(guild_id, channel.id):
            return None

        return channel

    @staticmethod
    def _build_event_menu_embed() -> discord.Embed:
        embed = discord.Embed(
            title="📡 Mission Control // Marcia",
            description=(
                "Pick what you want to do:\n"
                "`New Event` opens a quick form here.\n"
                "`Use Template` schedules from a saved briefing.\n"
                "`Archive Template` saves a briefing for reuse.\n"
                "`Bulk Import` gives you a copy-paste format for mass scheduling.\n"
                "`Upcoming Events` shows the next ops list.\n"
                "`Share Upcoming` posts the queue in #events.\n"
                "`Remove Event` deletes a scheduled op.\n"
                "Times use the game clock (UTC-2)."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Marcia drones on standby. Keep it sharp.")
        return embed

    async def recover_missions(self):
        """Reloads active missions from SQL on startup."""
        await self.bot.wait_until_ready()
        all_missions = await get_all_active_missions()
        now_utc = datetime.now(timezone.utc)
        for m in all_missions:
            try:
                utc_dt = datetime.fromisoformat(m['target_utc']).astimezone(timezone.utc)
                if utc_dt > now_utc:
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
                elif now_utc - utc_dt <= MISSED_EVENT_GRACE:
                    logger.info(
                        "Recovering missed mission %s in guild %s (late by %s).",
                        m['codename'],
                        m['guild_id'],
                        now_utc - utc_dt,
                    )
                    await self._announce_event_start(
                        m['guild_id'],
                        m['codename'],
                        m['description'],
                        m.get('location'),
                        m.get('ping_role_id'),
                    )
                    await self._notify_dm_participants(
                        m['guild_id'],
                        m['codename'],
                        0,
                        m['description'],
                        m.get('location'),
                    )
                    await delete_mission(m['guild_id'], m['codename'])
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
                                f"Up and on-grid, @everyone.\n\n"
                                f"📡 **MARCIA // DUEL DIRECTIVE – {day_name.upper()}**\n\n"
                                f"{info}\n\n"
                                f"Points don't climb themselves. Execute clean and report stronger.",
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
                        reminder_line = _pick_reminder_line(KILL_EVENT_SHIELD_REMINDERS, now_server.hour)
                        shield_line = _shield_recommendation(hours_left)
                        try:
                            await chan.send(
                                "Dear @everyone,\n\n"
                                "🛡️ **KILL EVENT SHIELD CHECK**\n\n"
                                f"{reminder_line}\n"
                                f"⏳ **{hours_left}h** remaining in the kill event.\n"
                                f"{shield_line}\n"
                                "If you can't maintain 24h shields, chain 8h shields and set alarms to refresh.\n"
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
                        reminder_line = _pick_reminder_line(KILL_EVENT_PRE_SHIELD_REMINDERS, now_server.hour)
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
                content="📌 Set an events channel first with `/setup` so I know where to post ops.",
                ephemeral=True,
            )
        embed = self._build_event_menu_embed()
        await self._safe_send(ctx, embed=embed, view=EventMenuView(self, ctx, settings))

    async def create_template_flow(self, ctx):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send("💾 **Template name?**")
            title = (await self.bot.wait_for('message', check=check, timeout=120)).content
            await ctx.author.send("📝 **Briefing text?**")
            desc = (await self.bot.wait_for('message', check=check, timeout=300)).content
            await add_template(ctx.guild.id, title, desc)
            await ctx.author.send(f"✅ Protocol `{title}` archived. {_marcia_quip()}")
        except: await ctx.author.send("❌ Timeout.")

    async def create_mission_flow(self, ctx):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send("📡 Name?")
            name_msg = await self.bot.wait_for('message', check=check, timeout=120)
            name = name_msg.content

            await ctx.author.send("📝 Orders?")
            desc_msg = await self.bot.wait_for('message', check=check, timeout=300)
            desc = desc_msg.content

            await ctx.author.send("📅 Date? `YYYY-MM-DD` (UTC-2).")
            date_msg = await self.bot.wait_for('message', check=check, timeout=180)

            await ctx.author.send("⏰ Time? `HH:MM` (UTC-2).")
            time_msg = await self.bot.wait_for('message', check=check, timeout=180)
            await self.finalize_mission(
                ctx,
                name,
                desc,
                f"{date_msg.content} {time_msg.content}",
                None,
                -1,
            )
        except asyncio.TimeoutError:
            await ctx.author.send("⌛ Timed out. Ping me again with `/event` when you're ready.")

    async def create_template_mission_flow(self, ctx, template_name, template_desc):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send(
                f"📋 Template loaded: `{template_name}`\n{template_desc}\n\n"
                "New name or `skip`?"
            )
            name_msg = await self.bot.wait_for('message', check=check, timeout=120)
            name = template_name if name_msg.content.lower().strip() == "skip" else name_msg.content

            await ctx.author.send("📅 Date? `YYYY-MM-DD` (UTC-2).")
            date_msg = await self.bot.wait_for('message', check=check, timeout=180)

            await ctx.author.send("⏰ Time? `HH:MM` (UTC-2).")
            time_msg = await self.bot.wait_for('message', check=check, timeout=180)
            await self.finalize_mission(
                ctx,
                name,
                template_desc,
                f"{date_msg.content} {time_msg.content}",
                None,
                -1,
            )
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
                    try:
                        await chan.send("🛰️ **Operation Scheduled**", embed=preview)
                    except discord.Forbidden:
                        logger.warning(
                            "Missing access to post scheduled mission in %s (%s).",
                            ctx.guild.name,
                            chan.id,
                        )
                    except discord.HTTPException as exc:
                        logger.warning(
                            "Failed to post scheduled mission in %s (%s): %s",
                            ctx.guild.name,
                            chan.id,
                            exc,
                        )
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

            if mins == 60:
                chan = await self._resolve_event_channel(guild_id)
                if not chan:
                    continue

                drone = random.choice(DRONE_NAMES)
                guild = chan.guild
                role = guild.get_role(ping_role_id) if isinstance(ping_role_id, int) and ping_role_id >= 0 else None
                location_line = f"\n📍 {location}" if location else ""
                title, body = random.choice(TIMED_REMINDERS.get(mins, [("", "`{name}` is coming up.")]))
                body = body.format(name=name, drone=drone)
                quote = random.choice(MARCIA_SYSTEM_LINES)

                greetings = ["Dear", "Hello", "Attention", "Listen up,", "Heads up,"]
                if ping_role_id == -1:
                    mention_target = "@everyone"
                elif role:
                    mention_target = role.mention
                else:
                    mention_target = ""
                if mention_target:
                    natural_mention = f"{random.choice(greetings)} {mention_target}"
                else:
                    natural_mention = f"{random.choice(greetings)}, team"

                msg = (
                    f"{natural_mention},\n\n"
                    f"{quote}\n\n"
                    f"{body}\n\n"
                    f"{desc}{location_line}\n\n"
                    f"React with {JOIN_EVENT_EMOJI} to join this event and receive DM reminders."
                    f"\n\n*Drone: {drone}*"
                )
                sent = None
                try:
                    sent = await chan.send(
                        msg,
                        allowed_mentions=discord.AllowedMentions(
                            everyone=ping_role_id == -1,
                            roles=bool(role),
                        ),
                    )
                except discord.Forbidden:
                    logger.warning(
                        "Missing access to send mission reminder in %s (%s).",
                        chan.guild.name,
                        chan.id,
                    )
                except discord.HTTPException as exc:
                    logger.warning(
                        "Failed to send mission reminder in %s (%s): %s",
                        chan.guild.name,
                        chan.id,
                        exc,
                    )

                if sent:
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
            color=0x5865f2,
        )
        briefing = desc or "No briefing provided."
        embed.add_field(name="📝 Briefing", value=briefing, inline=False)
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
        chan = await self._resolve_event_channel(guild_id)
        if not chan:
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
        except discord.HTTPException as exc:
            logger.warning(
                "Failed to send event kickoff in %s (%s): %s",
                chan.guild.name,
                chan.id,
                exc,
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
