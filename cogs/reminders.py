"""
FILE: cogs/reminders.py
USE: Reminder broadcasting with template management.
FEATURES: Guild-scoped template archive, default starter prompts, and ignore-list compliance.
"""

from datetime import datetime, timezone
import asyncio
import logging
import random

import discord
from discord.ext import commands

from utils.assets import MARCIA_SYSTEM_LINES
from database import (
    add_reminder_template,
    delete_reminder_template,
    get_reminder_templates,
    add_scheduled_reminder,
    delete_scheduled_reminder,
    get_scheduled_reminders,
    get_settings,
    is_channel_ignored,
)
from utils.time_utils import GAME_TZ, game_to_utc, format_game
from utils.async_utils import create_tracked_task


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger("MarciaOS.Reminders")
        self.scheduled_tasks: dict[int, asyncio.Task] = {}
        create_tracked_task(
            self._restore_scheduled_reminders(),
            name="restore-reminders",
            logger=self.log,
        )

    def _format_reminder_message(self, body: str, template_name: str | None = None) -> str:
        parts = [part for part in (template_name, body) if part]
        combined = "\n".join(parts)
        cleaned = combined.lstrip("* ").lower()
        prefix = "@everyone\n\n"
        if cleaned.startswith("reminder"):
            return f"{prefix}📡 {combined}"
        return f"{prefix}📡 **Reminder:** {combined}"

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild and await is_channel_ignored(ctx.guild.id, ctx.channel.id):
            return False
        return True

    @commands.hybrid_group(
        name="remind",
        invoke_without_command=True,
        description="Send a reminder from a saved template or manage the archive.",
    )
    async def remind(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send("❌ Reminders can only be managed inside a server.")

        settings = await get_settings(ctx.guild.id)
        if not settings or not settings.get("event_channel_id"):
            return await ctx.send(
                "📌 Set an events channel first with `/setup` so I know where to post reminders."
            )

        view = ReminderMenuView(self, ctx, settings["event_channel_id"])
        embed = discord.Embed(
            title="🛰️ Reminder Control",
            description=(
                "Pick your move:\n\n"
                "**New Reminder**: Write a reminder.\n"
                "**Use Template**: Send a saved reminder.\n"
                "**Archive Template**: Save a reminder template.\n"
                "**Upcoming Reminders**: See what is scheduled.\n"
                "**Remove Reminder**: Cancel a scheduled reminder."
            ),
            color=0x5865F2,
        )
        embed.add_field(
            name="📅 Scheduling Options",
            value=(
                "Send now: leave date + time empty.\n"
                "Schedule: date + time only.\n"
                f"`YYYY-MM-DD` + `HH:MM` (Now: {format_game(datetime.now(timezone.utc))})"
            ),
            inline=False,
        )
        embed.set_footer(text="Marcia keeps your reminders sharp and on schedule.")
        await ctx.send(embed=embed, view=view)

    async def _send_or_schedule(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel | discord.Thread,
        body: str,
        when_utc: datetime | None,
    ) -> None:
        if not channel:
            await ctx.send("❌ I can't find that channel.")
            return

        if await is_channel_ignored(ctx.guild.id, channel.id):
            await ctx.send("🚫 That channel is muted for Marcia. Pick another sector.")
            return

        quote = random.choice(MARCIA_SYSTEM_LINES)

        async def _post():
            reminder_message = self._format_reminder_message(body)
            await channel.send(
                f"{reminder_message}\n\n{quote}",
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )

        if when_utc and when_utc > datetime.now(timezone.utc):
            reminder_id = await add_scheduled_reminder(
                ctx.guild.id,
                channel.id,
                ctx.author.id,
                body,
                when_utc.isoformat(),
            )
            self._schedule_reminder(reminder_id, channel, body, when_utc)
            await ctx.send(
                f"⏳ Reminder scheduled for {format_game(when_utc)} in {channel.mention}.",
                delete_after=10,
            )
        else:
            await _post()
            await ctx.send(f"✅ Reminder sent to {channel.mention}.", delete_after=8)

    async def _delayed_send(
        self,
        coro_fn,
        ctx: commands.Context,
        when_utc: datetime,
    ):
        await discord.utils.sleep_until(when_utc)
        try:
            await coro_fn()
        except Exception:
            try:
                await ctx.send("⚠️ Scheduled reminder failed to send.", delete_after=10)
            except Exception:
                pass

    def _schedule_reminder(
        self,
        reminder_id: int,
        channel: discord.TextChannel | discord.Thread,
        body: str,
        when_utc: datetime,
    ) -> None:
        task = create_tracked_task(
            self._run_scheduled_reminder(reminder_id, channel, body, when_utc),
            name=f"scheduled-reminder-{reminder_id}",
            logger=self.log,
        )
        self.scheduled_tasks[reminder_id] = task

    async def _run_scheduled_reminder(
        self,
        reminder_id: int,
        channel: discord.TextChannel | discord.Thread,
        body: str,
        when_utc: datetime,
    ) -> None:
        await discord.utils.sleep_until(when_utc)
        try:
            reminder_message = self._format_reminder_message(body)
            await channel.send(
                f"{reminder_message}\n\n{random.choice(MARCIA_SYSTEM_LINES)}",
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )
        finally:
            await delete_scheduled_reminder(channel.guild.id, reminder_id)
            self.scheduled_tasks.pop(reminder_id, None)

    async def _restore_scheduled_reminders(self) -> None:
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            reminders = await get_scheduled_reminders(guild.id)
            for reminder in reminders:
                send_at = datetime.fromisoformat(reminder["send_at_utc"]).astimezone(timezone.utc)
                if send_at <= datetime.now(timezone.utc):
                    await delete_scheduled_reminder(guild.id, reminder["id"])
                    continue
                channel = guild.get_channel(reminder["channel_id"])
                if not channel:
                    await delete_scheduled_reminder(guild.id, reminder["id"])
                    continue
                self._schedule_reminder(reminder["id"], channel, reminder["body"], send_at)

    def _parse_when(self, raw_value: str | None) -> datetime | None:
        if not raw_value:
            return None

        try:
            parsed = datetime.strptime(raw_value.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError(
                "Use `YYYY-MM-DD` + `HH:MM` in game time (UTC-2). Example: 2024-12-31 18:30"
            )

        return game_to_utc(parsed.replace(tzinfo=GAME_TZ))

    async def _resolve_event_channel(self, ctx: commands.Context):
        settings = await get_settings(ctx.guild.id)
        if settings and settings.get("event_channel_id"):
            channel = ctx.guild.get_channel(settings["event_channel_id"])
            if channel:
                return channel
        return None

    async def _build_upcoming_reminders_embed(self, guild: discord.Guild) -> discord.Embed:
        reminders = await get_scheduled_reminders(guild.id)
        embed = discord.Embed(
            title="📆 Upcoming Reminders",
            description="Scheduled reminders for this sector.",
            color=0x5865F2,
        )
        if not reminders:
            embed.add_field(name="Status", value="No reminders scheduled yet.", inline=False)
            return embed

        lines = []
        for reminder in reminders[:10]:
            send_at = datetime.fromisoformat(reminder["send_at_utc"]).astimezone(timezone.utc)
            channel = guild.get_channel(reminder["channel_id"])
            channel_label = channel.mention if channel else f"<#{reminder['channel_id']}>"
            preview = reminder["body"]
            if len(preview) > 70:
                preview = preview[:67] + "…"
            lines.append(
                f"• **{format_game(send_at)}** → {channel_label} - {preview}"
            )
        embed.add_field(name="Scheduled", value="\n".join(lines), inline=False)
        embed.set_footer(text="Times shown in game time (UTC-2).")
        return embed


class ReminderMenuView(discord.ui.View):
    def __init__(self, cog: Reminders, ctx: commands.Context, event_channel_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.event_channel_id = event_channel_id

    def _is_requester(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.ctx.author.id

    @discord.ui.button(label="New Reminder", style=discord.ButtonStyle.primary, emoji="🆕", row=0)
    async def new_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        await interaction.response.send_modal(
            ReminderModal(self.cog, self.ctx, target="events", event_channel_id=self.event_channel_id)
        )

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.success, emoji="📋", row=0)
    async def send_from_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        templates = await get_reminder_templates(self.ctx.guild.id)
        if not templates:
            await interaction.response.send_message(
                "📂 No templates saved yet.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Select a template to send.",
            view=TemplateSelectView(self.cog, self.ctx, templates, target="events", event_channel_id=self.event_channel_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Archive Template", style=discord.ButtonStyle.secondary, emoji="💾", row=0)
    async def archive_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        await interaction.response.send_modal(TemplateCreateModal(self.ctx))

    @discord.ui.button(label="Upcoming Reminders", style=discord.ButtonStyle.secondary, emoji="📆", row=1)
    async def upcoming_reminders(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        embed = await self.cog._build_upcoming_reminders_embed(self.ctx.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Remove Reminder", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def remove_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        reminders = await get_scheduled_reminders(self.ctx.guild.id)
        if not reminders:
            await interaction.response.send_message("📭 No scheduled reminders to remove.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Select a reminder to remove.",
            view=ReminderRemoveView(self.cog, self.ctx, reminders, self.event_channel_id),
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


class ReminderChannelModal(discord.ui.Modal):
    def __init__(self, cog: Reminders, ctx: commands.Context):
        super().__init__(title="Schedule Reminder to Channel")
        self.cog = cog
        self.ctx = ctx

        self.channel_input = discord.ui.TextInput(
            label="Channel",
            placeholder="#events or 1234567890",
            max_length=100,
        )
        self.body = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.long,
            max_length=800,
            placeholder="Tell Marcia what to announce",
        )
        self.date = discord.ui.TextInput(
            label="Date",
            required=False,
            placeholder="YYYY-MM-DD (UTC-2)",
            max_length=32,
        )
        self.time = discord.ui.TextInput(
            label="Time",
            required=False,
            placeholder="HH:MM (UTC-2)",
            max_length=32,
        )
        self.add_item(self.channel_input)
        self.add_item(self.body)
        self.add_item(self.date)
        self.add_item(self.time)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Parse channel
        channel_str = str(self.channel_input.value).strip()
        channel = None
        
        # Try to extract channel ID from mention format (#channel)
        if channel_str.startswith("<#") and channel_str.endswith(">"):
            channel_id = int(channel_str[2:-1])
            channel = self.ctx.guild.get_channel(channel_id)
        # Try as direct ID
        elif channel_str.isdigit():
            channel = self.ctx.guild.get_channel(int(channel_str))
        # Try as channel name
        else:
            channel_name = channel_str.lstrip("#")
            channel = discord.utils.get(self.ctx.guild.text_channels, name=channel_name)
        
        if not channel:
            await interaction.followup.send(
                f"❌ Could not find channel: {channel_str}\n"
                "Please use #channel mention, channel ID, or channel name.",
                ephemeral=True
            )
            return

        date_value = str(self.date.value).strip()
        time_value = str(self.time.value).strip()
        if date_value or time_value:
            if not (date_value and time_value):
                await interaction.followup.send(
                    "❌ I need both date + time (or leave both blank to send now).",
                    ephemeral=True,
                )
                return
            raw_when = f"{date_value} {time_value}"
            try:
                when_utc = self.cog._parse_when(raw_when)
            except ValueError as e:
                await interaction.followup.send(str(e), ephemeral=True)
                return
        else:
            when_utc = None

        await self.cog._send_or_schedule(self.ctx, channel, str(self.body.value), when_utc)
        await interaction.followup.send(f"✅ Reminder queued for {channel.mention}.", ephemeral=True)


class ReminderModal(discord.ui.Modal):
    def __init__(
        self,
        cog: Reminders,
        ctx: commands.Context,
        target: str,
        event_channel_id: int | None = None,
    ):
        super().__init__(title="Schedule reminder")
        self.cog = cog
        self.ctx = ctx
        self.target = target
        self.event_channel_id = event_channel_id

        self.body = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.long,
            max_length=800,
            placeholder="Tell Marcia what to announce",
        )
        self.date = discord.ui.TextInput(
            label="Date",
            required=False,
            placeholder="YYYY-MM-DD (UTC-2)",
            max_length=32,
        )
        self.time = discord.ui.TextInput(
            label="Time",
            required=False,
            placeholder="HH:MM (UTC-2)",
            max_length=32,
        )
        self.add_item(self.body)
        self.add_item(self.date)
        self.add_item(self.time)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        date_value = str(self.date.value).strip()
        time_value = str(self.time.value).strip()
        if date_value or time_value:
            if not (date_value and time_value):
                await interaction.followup.send(
                    "❌ I need both date + time (or leave both blank to send now).",
                    ephemeral=True,
                )
                return
            raw_when = f"{date_value} {time_value}"
            try:
                when_utc = self.cog._parse_when(raw_when)
            except ValueError as e:
                await interaction.followup.send(str(e), ephemeral=True)
                return
        else:
            when_utc = None

        if self.target == "events":
            channel = (
                self.ctx.guild.get_channel(self.event_channel_id)
                if self.event_channel_id
                else None
            )
            if not channel:
                await interaction.followup.send(
                    "📌 Set an events channel first with `/setup` so I know where to post reminders.",
                    ephemeral=True,
                )
                return
        else:
            channel = self.ctx.channel

        await self.cog._send_or_schedule(self.ctx, channel, str(self.body.value), when_utc)
        await interaction.followup.send("Reminder queued.", ephemeral=True)


class TemplateSelect(discord.ui.Select):
    def __init__(
        self,
        cog: Reminders,
        ctx: commands.Context,
        templates: list[dict],
        target: str,
        event_channel_id: int | None = None,
    ):
        options = [
            discord.SelectOption(label=t["template_name"], description=t["body"][:90])
            for t in templates
        ]
        super().__init__(placeholder="Choose a template", options=options, min_values=1, max_values=1)
        self.cog = cog
        self.ctx = ctx
        self.templates = templates
        self.target = target
        self.event_channel_id = event_channel_id

    async def callback(self, interaction: discord.Interaction):
        template = next(
            (t for t in self.templates if t["template_name"] == self.values[0]), None
        )
        if not template:
            await interaction.response.send_message("Template not found.", ephemeral=True)
            return

        modal = ReminderModal(
            self.cog,
            self.ctx,
            target=self.target,
            event_channel_id=self.event_channel_id,
        )
        modal.body.default = template["body"]
        await interaction.response.send_modal(modal)


class TemplateSelectView(discord.ui.View):
    def __init__(
        self,
        cog: Reminders,
        ctx: commands.Context,
        templates: list[dict],
        target: str,
        event_channel_id: int | None = None,
    ):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.target = target
        self.event_channel_id = event_channel_id
        self.add_item(TemplateSelect(cog, ctx, templates, target, event_channel_id))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class TemplateCreateModal(discord.ui.Modal):
    def __init__(self, ctx: commands.Context):
        super().__init__(title="Archive Reminder Template")
        self.ctx = ctx
        self.name = discord.ui.TextInput(
            label="Template name",
            max_length=60,
            placeholder="e.g. Rally Alert",
        )
        self.body = discord.ui.TextInput(
            label="Template message",
            style=discord.TextStyle.long,
            max_length=800,
            placeholder="Type the reminder",
        )
        self.add_item(self.name)
        self.add_item(self.body)

    async def on_submit(self, interaction: discord.Interaction):
        await add_reminder_template(self.ctx.guild.id, str(self.name.value), str(self.body.value))
        await interaction.response.send_message(
            f"✅ Template `{self.name.value}` saved to the archive.",
            ephemeral=True,
        )


class ReminderRemoveSelect(discord.ui.Select):
    def __init__(self, cog: Reminders, ctx: commands.Context, reminders):
        self.cog = cog
        self.ctx = ctx
        options = []
        for reminder in reminders[:25]:
            send_at = datetime.fromisoformat(reminder["send_at_utc"]).astimezone(timezone.utc)
            label = f"{format_game(send_at)}"
            preview = reminder["body"][:70]
            options.append(
                discord.SelectOption(
                    label=label,
                    description=preview,
                    value=str(reminder["id"]),
                )
            )
        super().__init__(placeholder="Select a reminder to remove", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        reminder_id = int(self.values[0])
        task = self.cog.scheduled_tasks.pop(reminder_id, None)
        if task:
            task.cancel()
        await delete_scheduled_reminder(self.ctx.guild.id, reminder_id)
        await interaction.response.send_message("🗑️ Reminder removed.", ephemeral=True)


class ReminderRemoveView(discord.ui.View):
    def __init__(self, cog: Reminders, ctx: commands.Context, reminders, event_channel_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.reminders = reminders
        self.event_channel_id = event_channel_id
        self.add_item(ReminderRemoveSelect(cog, ctx, reminders))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class TemplateDeleteSelect(discord.ui.Select):
    def __init__(self, ctx: commands.Context, templates: list[dict]):
        options = [
            discord.SelectOption(label=t["template_name"], description=t["body"][:90])
            for t in templates
        ]
        super().__init__(placeholder="Template to delete", options=options, min_values=1, max_values=1)
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        await delete_reminder_template(self.ctx.guild.id, choice)
        await interaction.response.send_message(
            f"🗑️ Template `{choice}` deleted.", ephemeral=True
        )


class TemplateDeleteView(discord.ui.View):
    def __init__(self, ctx: commands.Context, templates: list[dict]):
        super().__init__(timeout=60)
        self.add_item(TemplateDeleteSelect(ctx, templates))


async def setup(bot):
    await bot.add_cog(Reminders(bot))
