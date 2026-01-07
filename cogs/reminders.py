"""
FILE: cogs/reminders.py
USE: Reminder broadcasting with template management.
FEATURES: Guild-scoped template archive, default starter prompts, and ignore-list compliance.
"""

from datetime import datetime, timezone
import random

import discord
from discord.ext import commands

from assets import MARCIA_QUOTES
from database import (
    add_reminder_template,
    delete_reminder_template,
    get_reminder_templates,
    get_settings,
    is_channel_ignored,
)
from time_utils import GAME_TZ, game_to_utc, format_game


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild and await is_channel_ignored(ctx.guild.id, ctx.channel.id):
            return False
        return True

    @commands.hybrid_group(
        name="remind",
        invoke_without_command=True,
        description="Send a reminder from a saved template or manage the archive.",
    )
    async def remind(self, ctx: commands.Context, *, template: str | None = None):
        if not ctx.guild:
            return await ctx.send("❌ Reminders can only be managed inside a server.")

        if template:
            return await self._send_template(ctx, template)

        view = ReminderMenuView(self, ctx)
        embed = discord.Embed(
            title="🛰️ Reminder Control",
            description=(
                "Choose how you want to broadcast a reminder. Options include sending to the "
                "configured events channel, posting a custom message, broadcasting a saved "
                "template, or cleaning up templates you no longer need."
            ),
            color=0x2b2d31,
        )
        embed.add_field(
            name="Send timing",
            value=(
                "Every send flow allows you to pick **Send now** or enter a custom date/time in "
                f"game time ({format_game(datetime.now(timezone.utc))})."
            ),
            inline=False,
        )
        await ctx.send(embed=embed, view=view)

    async def _send_template(self, ctx: commands.Context, template: str):
        templates = await get_reminder_templates(ctx.guild.id)
        match = next((t for t in templates if t['template_name'].lower() == template.lower()), None)
        if not match:
            names = ", ".join(t['template_name'] for t in templates) or "none"
            return await ctx.send(f"❌ Template not found. Available: {names}")

        quote = random.choice(MARCIA_QUOTES)
        await ctx.send(f"📡 **Reminder:** {match['template_name']}\n{match['body']}\n\n{quote}")

    @remind.command(name="send", description="Broadcast a saved reminder template.")
    async def remind_send(self, ctx: commands.Context, *, template: str):
        await self._send_template(ctx, template)

    @remind.command(name="add", description="Archive a new reminder template.")
    @commands.has_permissions(manage_guild=True)
    async def remind_add(self, ctx: commands.Context, name: str, *, body: str):
        await add_reminder_template(ctx.guild.id, name, body)
        await ctx.send(f"✅ Template `{name}` saved to the archive.")

    @remind.command(name="remove", description="Delete a saved reminder template.")
    @commands.has_permissions(manage_guild=True)
    async def remind_remove(self, ctx: commands.Context, *, name: str):
        await delete_reminder_template(ctx.guild.id, name)
        await ctx.send(f"🗑️ Template `{name}` deleted.")

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

        quote = random.choice(MARCIA_QUOTES)

        async def _post():
            await channel.send(f"📡 **Reminder:** {body}\n\n{quote}")

        if when_utc and when_utc > datetime.now(timezone.utc):
            self.bot.loop.create_task(self._delayed_send(_post, ctx, when_utc))
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

    def _parse_when(self, raw_value: str | None) -> datetime | None:
        if not raw_value:
            return None

        try:
            parsed = datetime.strptime(raw_value.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError(
                "Use YYYY-MM-DD HH:MM in game time (UTC-2). Example: 2024-12-31 18:30"
            )

        return game_to_utc(parsed.replace(tzinfo=GAME_TZ))

    async def _resolve_event_channel(self, ctx: commands.Context):
        settings = await get_settings(ctx.guild.id)
        if settings and settings.get("event_channel_id"):
            channel = ctx.guild.get_channel(settings["event_channel_id"])
            if channel:
                return channel
        return ctx.channel


class ReminderMenuView(discord.ui.View):
    def __init__(self, cog: Reminders, ctx: commands.Context):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="Events channel", style=discord.ButtonStyle.primary)
    async def send_events(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            ReminderModal(self.cog, self.ctx, target="events")
        )

    @discord.ui.button(label="Custom message", style=discord.ButtonStyle.secondary)
    async def send_custom(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            ReminderModal(self.cog, self.ctx, target="custom")
        )

    @discord.ui.button(label="From template", style=discord.ButtonStyle.success)
    async def send_from_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        templates = await get_reminder_templates(self.ctx.guild.id)
        if not templates:
            await interaction.response.send_message(
                "📂 No templates saved yet.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Select a template to send.",
            view=TemplateSelectView(self.cog, self.ctx, templates),
            ephemeral=True,
        )

    @discord.ui.button(label="Delete template", style=discord.ButtonStyle.danger)
    async def delete_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        templates = await get_reminder_templates(self.ctx.guild.id)
        if not templates:
            await interaction.response.send_message(
                "📂 No templates saved yet.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Pick a template to delete.",
            view=TemplateDeleteView(self.ctx, templates),
            ephemeral=True,
        )


class ReminderModal(discord.ui.Modal):
    def __init__(self, cog: Reminders, ctx: commands.Context, target: str):
        super().__init__(title="Schedule reminder")
        self.cog = cog
        self.ctx = ctx
        self.target = target

        self.body = discord.ui.TextInput(
            label="Reminder text",
            style=discord.TextStyle.long,
            max_length=800,
            placeholder="What should Marcia announce?",
        )
        self.when = discord.ui.TextInput(
            label="Send at (game time)",
            required=False,
            placeholder="YYYY-MM-DD HH:MM (UTC-2) — leave blank for now",
            max_length=32,
        )
        self.add_item(self.body)
        self.add_item(self.when)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            when_utc = self.cog._parse_when(str(self.when.value))
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        channel = (
            await self.cog._resolve_event_channel(self.ctx)
            if self.target == "events"
            else self.ctx.channel
        )

        await self.cog._send_or_schedule(self.ctx, channel, str(self.body.value), when_utc)
        await interaction.followup.send("Reminder queued.", ephemeral=True)


class TemplateSelect(discord.ui.Select):
    def __init__(self, cog: Reminders, ctx: commands.Context, templates: list[dict]):
        options = [
            discord.SelectOption(label=t["template_name"], description=t["body"][:90])
            for t in templates
        ]
        super().__init__(placeholder="Choose a template", options=options, min_values=1, max_values=1)
        self.cog = cog
        self.ctx = ctx
        self.templates = templates

    async def callback(self, interaction: discord.Interaction):
        template = next(
            (t for t in self.templates if t["template_name"] == self.values[0]), None
        )
        if not template:
            await interaction.response.send_message("Template not found.", ephemeral=True)
            return

        modal = ReminderModal(self.cog, self.ctx, target="custom")
        modal.body.default = template["body"]
        await interaction.response.send_modal(modal)


class TemplateSelectView(discord.ui.View):
    def __init__(self, cog: Reminders, ctx: commands.Context, templates: list[dict]):
        super().__init__(timeout=60)
        self.add_item(TemplateSelect(cog, ctx, templates))


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
