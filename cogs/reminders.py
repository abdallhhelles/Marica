"""
FILE: cogs/reminders.py
USE: Reminder broadcasting with template management.
FEATURES: Guild-scoped template archive, one-time and recurring schedules, and ignore-list compliance.
"""

from datetime import datetime, timedelta, timezone
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
    update_scheduled_reminder,
    delete_scheduled_reminder,
    get_scheduled_reminders,
    get_settings,
    is_channel_ignored,
)
from utils.time_utils import GAME_TZ, game_to_utc, format_game
from utils.async_utils import create_tracked_task


WEEKDAY_ALIASES = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}
WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
BULK_REMINDER_HEADER = "body | when | repeat | weekdays | channel"
BULK_REMINDER_EXAMPLE = (
    "Shield before reset | 2026-03-27 17:00 | once | - | #events\n"
    "Gather for rally | 2026-03-28 20:00 | daily | - | -\n"
    "Officer prep | 2026-03-31 19:00 | weekdays | Mon,Wed,Fri | #officers"
)


def _is_skipped_value(raw_value: str | None) -> bool:
    if raw_value is None:
        return True
    return raw_value.strip() in {"", "-", "—"}


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

    def _parse_when(self, raw_value: str | None) -> datetime | None:
        if not raw_value:
            return None

        try:
            parsed = datetime.strptime(raw_value.strip(), "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise ValueError(
                "Use `YYYY-MM-DD` + `HH:MM` in game time (UTC-2). Example: 2024-12-31 18:30"
            ) from exc

        return game_to_utc(parsed.replace(tzinfo=GAME_TZ))

    def _parse_channel(self, guild: discord.Guild, channel_input: str):
        value = channel_input.strip()
        if not value:
            return None
        if value.startswith("<#") and value.endswith(">") and value[2:-1].isdigit():
            return guild.get_channel(int(value[2:-1]))
        if value.isdigit():
            return guild.get_channel(int(value))
        return discord.utils.get(guild.text_channels, name=value.lstrip("#"))

    def _normalize_weekdays(self, raw_value: str | None) -> list[int]:
        if not raw_value:
            raise ValueError("Pick at least one day for custom weekday schedules.")
        tokens = [token.strip().lower() for token in raw_value.split(",") if token.strip()]
        if not tokens:
            raise ValueError("Pick at least one day for custom weekday schedules.")

        values = []
        for token in tokens:
            if token not in WEEKDAY_ALIASES:
                raise ValueError(
                    "Unknown weekday. Use names like `Monday, Wednesday` or `Mon,Wed,Fri`."
                )
            values.append(WEEKDAY_ALIASES[token])
        return sorted(set(values))

    def _next_monthly_time(self, base_utc: datetime, day_of_month: int, minute_of_day: int) -> datetime:
        base_game = base_utc.astimezone(GAME_TZ)
        year = base_game.year
        month = base_game.month
        hour = minute_of_day // 60
        minute = minute_of_day % 60

        for _ in range(24):
            # Try this month
            try:
                candidate_game = datetime(year, month, day_of_month, hour, minute, tzinfo=GAME_TZ)
            except ValueError:
                candidate_game = None
            if candidate_game:
                candidate_utc = candidate_game.astimezone(timezone.utc)
                if candidate_utc > base_utc:
                    return candidate_utc

            # Move to next month
            month += 1
            if month > 12:
                month = 1
                year += 1

        raise ValueError("Could not compute next monthly reminder.")

    def _compute_next_run(self, current_send_at_utc: datetime, recurrence_type: str, recurrence_value: str | None) -> datetime | None:
        if recurrence_type == "once":
            return None
        if recurrence_type == "daily":
            return current_send_at_utc + timedelta(days=1)
        if recurrence_type == "weekly":
            return current_send_at_utc + timedelta(days=7)
        if recurrence_type == "monthly":
            if not recurrence_value or "|" not in recurrence_value:
                return None
            day_raw, minute_raw = recurrence_value.split("|", 1)
            return self._next_monthly_time(current_send_at_utc, int(day_raw), int(minute_raw))
        if recurrence_type == "custom_weekdays":
            if not recurrence_value or "|" not in recurrence_value:
                return None
            day_tokens, minute_raw = recurrence_value.split("|", 1)
            weekdays = sorted({int(part) for part in day_tokens.split(",") if part.strip() != ""})
            minute_of_day = int(minute_raw)
            hour = minute_of_day // 60
            minute = minute_of_day % 60

            current_game = current_send_at_utc.astimezone(GAME_TZ)
            for offset in range(1, 15):
                probe = current_game + timedelta(days=offset)
                if probe.weekday() not in weekdays:
                    continue
                candidate_game = datetime(probe.year, probe.month, probe.day, hour, minute, tzinfo=GAME_TZ)
                candidate_utc = candidate_game.astimezone(timezone.utc)
                if candidate_utc > current_send_at_utc:
                    return candidate_utc
        return None

    def _advance_to_future(
        self,
        send_at_utc: datetime,
        recurrence_type: str,
        recurrence_value: str | None,
        now_utc: datetime | None = None,
    ) -> datetime | None:
        """Advance recurring reminders until the next valid future run."""
        if recurrence_type == "once":
            return send_at_utc if send_at_utc > (now_utc or datetime.now(timezone.utc)) else None

        current = send_at_utc
        horizon = (now_utc or datetime.now(timezone.utc))
        for _ in range(366):
            if current > horizon:
                return current
            nxt = self._compute_next_run(current, recurrence_type, recurrence_value)
            if not nxt or nxt <= current:
                return None
            current = nxt
        return None

    def _describe_recurrence(self, recurrence_type: str, recurrence_value: str | None) -> str:
        if recurrence_type == "once":
            return "One-time"
        if recurrence_type == "daily":
            return "Daily"
        if recurrence_type == "weekly":
            return "Weekly"
        if recurrence_type == "monthly":
            if recurrence_value and "|" in recurrence_value:
                day_raw, _ = recurrence_value.split("|", 1)
                return f"Monthly (day {day_raw})"
            return "Monthly"
        if recurrence_type == "custom_weekdays":
            if recurrence_value and "|" in recurrence_value:
                day_tokens, _ = recurrence_value.split("|", 1)
                labels = []
                for token in day_tokens.split(","):
                    if token.strip().isdigit():
                        idx = int(token)
                        if 0 <= idx < len(WEEKDAY_LABELS):
                            labels.append(WEEKDAY_LABELS[idx])
                if labels:
                    return f"Custom weekdays ({', '.join(labels)})"
            return "Custom weekdays"
        return recurrence_type

    def _build_bulk_reminder_help_embed(self, event_channel: discord.TextChannel | None) -> discord.Embed:
        channel_label = event_channel.mention if event_channel else "your default events channel"
        embed = discord.Embed(
            title="📦 Bulk Reminder Import",
            description=(
                "Paste one reminder per line using the exact format below.\n"
                "Use `-` to skip optional fields and fall back to defaults."
            ),
            color=0x5865F2,
        )
        embed.add_field(
            name="Format",
            value=f"```text\n{BULK_REMINDER_HEADER}\n```",
            inline=False,
        )
        embed.add_field(
            name="Rules",
            value=(
                "• `when` uses `YYYY-MM-DD HH:MM` in game time (UTC-2)\n"
                "• `repeat` = `once`, `daily`, `weekly`, `monthly`, or `weekdays`\n"
                "• `weekdays` is only used with `repeat=weekdays`\n"
                f"• `channel` can be a #mention, channel id, or `-` for {channel_label}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Example",
            value=f"```text\n{BULK_REMINDER_EXAMPLE}\n```",
            inline=False,
        )
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

    async def _collect_bulk_reminder_message(
        self,
        interaction: discord.Interaction,
        ctx: commands.Context,
        event_channel_id: int | None,
    ) -> None:
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

        default_channel = ctx.guild.get_channel(event_channel_id) if event_channel_id else None
        parsed_rows, errors = self._parse_bulk_reminder_rows(
            ctx.guild,
            self._normalize_bulk_message_content(message.content),
            default_channel,
        )
        embed = self._build_bulk_reminder_preview_embed(ctx.guild, parsed_rows, errors)
        if not parsed_rows:
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        await interaction.followup.send(
            embed=embed,
            view=BulkReminderPreviewView(self, ctx, parsed_rows, errors),
            ephemeral=True,
        )

    def _parse_bulk_reminder_rows(
        self,
        guild: discord.Guild,
        raw_text: str,
        default_channel: discord.TextChannel | None,
    ) -> tuple[list[dict], list[str]]:
        parsed_rows: list[dict] = []
        errors: list[str] = []
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            return parsed_rows, ["Add at least one reminder row before importing."]

        start_index = 0
        if lines and lines[0].lower() == BULK_REMINDER_HEADER:
            start_index = 1

        if start_index >= len(lines):
            return parsed_rows, ["Add at least one reminder row below the header."]

        for row_number, line in enumerate(lines[start_index:], start=1):
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 5:
                errors.append(
                    f"Row {row_number}: expected 5 columns (`body | when | repeat | weekdays | channel`)."
                )
                continue

            body, when_raw, repeat_raw, weekdays_raw, channel_raw = parts
            if _is_skipped_value(body):
                errors.append(f"Row {row_number}: `body` is required.")
                continue

            mode = "once" if _is_skipped_value(repeat_raw) else repeat_raw.strip().lower()
            if mode not in {"once", "daily", "weekly", "monthly", "weekdays"}:
                errors.append(
                    f"Row {row_number}: `repeat` must be once, daily, weekly, monthly, or weekdays."
                )
                continue

            when_utc = None
            if not _is_skipped_value(when_raw):
                try:
                    when_utc = self._parse_when(when_raw)
                except ValueError as exc:
                    errors.append(f"Row {row_number}: {exc}")
                    continue
            elif mode != "once":
                errors.append(f"Row {row_number}: recurring reminders need `when` for the first run.")
                continue

            if when_utc and when_utc <= datetime.now(timezone.utc):
                errors.append(f"Row {row_number}: `when` must be in the future.")
                continue

            recurrence_type = "once"
            recurrence_value = None
            if mode in {"daily", "weekly"}:
                recurrence_type = mode
            elif mode == "monthly":
                recurrence_type = "monthly"
                run_game = when_utc.astimezone(GAME_TZ)
                minute_of_day = run_game.hour * 60 + run_game.minute
                recurrence_value = f"{run_game.day}|{minute_of_day}"
            elif mode == "weekdays":
                try:
                    weekday_indexes = self._normalize_weekdays(
                        None if _is_skipped_value(weekdays_raw) else weekdays_raw
                    )
                except ValueError as exc:
                    errors.append(f"Row {row_number}: {exc}")
                    continue
                recurrence_type = "custom_weekdays"
                run_game = when_utc.astimezone(GAME_TZ)
                minute_of_day = run_game.hour * 60 + run_game.minute
                recurrence_value = f"{','.join(str(x) for x in weekday_indexes)}|{minute_of_day}"

            channel = default_channel
            if not _is_skipped_value(channel_raw):
                channel = self._parse_channel(guild, channel_raw)
                if not channel:
                    errors.append(f"Row {row_number}: channel not found.")
                    continue
            if not channel:
                errors.append(f"Row {row_number}: no default events channel is configured.")
                continue

            parsed_rows.append(
                {
                    "row_number": row_number,
                    "body": body,
                    "when_utc": when_utc,
                    "channel": channel,
                    "recurrence_type": recurrence_type,
                    "recurrence_value": recurrence_value,
                }
            )

        return parsed_rows, errors

    def _build_bulk_reminder_preview_embed(
        self,
        guild: discord.Guild,
        parsed_rows: list[dict],
        errors: list[str],
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🛰️ Bulk Reminder Preview",
            description=(
                f"Ready to queue **{len(parsed_rows)}** reminder(s). "
                f"I found **{len(errors)}** issue(s)."
            ),
            color=0x5865F2 if parsed_rows else 0xED4245,
        )
        if parsed_rows:
            preview_lines = []
            for row in parsed_rows[:8]:
                when_label = format_game(row["when_utc"]) if row["when_utc"] else "Send now"
                cadence = self._describe_recurrence(row["recurrence_type"], row["recurrence_value"])
                body = row["body"][:40] + ("…" if len(row["body"]) > 40 else "")
                preview_lines.append(
                    f"• Row {row['row_number']} • {when_label} • {cadence} • {row['channel'].mention}\n"
                    f"  └ {body}"
                )
            embed.add_field(name="Valid rows", value="\n".join(preview_lines), inline=False)
            if len(parsed_rows) > 8:
                embed.add_field(
                    name="More rows",
                    value=f"...and **{len(parsed_rows) - 8}** more ready to import.",
                    inline=False,
                )
        if errors:
            error_preview = "\n".join(f"• {item}" for item in errors[:8])
            embed.add_field(name="Issues to review", value=error_preview, inline=False)
            if len(errors) > 8:
                embed.add_field(
                    name="More issues",
                    value=f"...and **{len(errors) - 8}** more issue(s).",
                    inline=False,
                )
        embed.set_footer(text=f"Sector: {guild.name} | Times use game time (UTC-2).")
        return embed

    async def _commit_bulk_reminders(self, ctx: commands.Context, parsed_rows: list[dict]) -> tuple[int, int]:
        imported = 0
        sent_now = 0
        for row in parsed_rows:
            await self._send_or_schedule(
                ctx,
                row["channel"],
                row["body"],
                row["when_utc"],
                recurrence_type=row["recurrence_type"],
                recurrence_value=row["recurrence_value"],
            )
            imported += 1
            if row["when_utc"] is None:
                sent_now += 1
        return imported, sent_now

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild and await is_channel_ignored(ctx.guild.id, ctx.channel.id):
            return False
        return True

    def _build_reminder_menu_embed(self, event_channel: discord.TextChannel | None) -> discord.Embed:
        channel_label = event_channel.mention if event_channel else "Not configured"
        embed = discord.Embed(
            title="📡 Reminder Console",
            description="Manage one-time and recurring reminders from a single command hub.",
            color=0x5865F2,
        )
        embed.add_field(name="Default Channel", value=channel_label, inline=False)
        embed.add_field(
            name="Available Actions",
            value=(
                "• **One-Time Reminder**: send now or choose date/time\n"
                "• **Schedule Reminder**: daily/weekly/monthly/weekday cadence\n"
                "• **Bulk Import**: paste multiple reminders at once with examples\n"
                "• **Use Template**: send from saved reminder templates\n"
                "• **Upcoming / Remove**: review or cancel scheduled reminders"
            ),
            inline=False,
        )
        embed.set_footer(text="Times use game time (UTC-2).")
        return embed

    @commands.hybrid_command(
        name="reminder",
        aliases=["remind"],
        description="Send now or schedule one recurring reminder.",
    )
    @discord.app_commands.describe(
        body="Reminder message to send.",
        when="Optional first run in game time: YYYY-MM-DD HH:MM (UTC-2).",
        repeat="once | daily | weekly | monthly | weekdays",
        weekdays="For repeat=weekdays: comma-separated days, e.g. Mon,Wed,Fri.",
        channel="Optional target channel (default: configured events channel).",
    )
    async def remind(
        self,
        ctx: commands.Context,
        body: str | None = None,
        when: str | None = None,
        repeat: str = "once",
        weekdays: str | None = None,
        channel: discord.TextChannel | None = None,
    ):
        if not ctx.guild:
            await ctx.send("❌ Reminders can only be managed inside a server.")
            return

        settings = await get_settings(ctx.guild.id)
        default_channel = None
        if settings and settings.get("event_channel_id"):
            default_channel = ctx.guild.get_channel(settings["event_channel_id"])

        if body is None:
            if not default_channel:
                await ctx.send("📌 Set an events channel first with `/setup` so reminders have a default destination.")
                return
            embed = self._build_reminder_menu_embed(default_channel)
            await ctx.send(embed=embed, view=ReminderMenuView(self, ctx, default_channel.id))
            return

        target_channel = channel or default_channel
        if not target_channel:
            await ctx.send("📌 Set an events channel with `/setup` or provide a channel.")
            return

        if await is_channel_ignored(ctx.guild.id, target_channel.id):
            await ctx.send("🚫 That channel is muted for Marcia. Pick another sector.")
            return

        mode = (repeat or "once").strip().lower()
        if mode not in {"once", "daily", "weekly", "monthly", "weekdays"}:
            await ctx.send("❌ `repeat` must be one of: `once`, `daily`, `weekly`, `monthly`, `weekdays`.")
            return

        when_utc = None
        if when:
            try:
                when_utc = self._parse_when(when)
            except ValueError as exc:
                await ctx.send(str(exc))
                return

        recurrence_type = "once"
        recurrence_value = None

        if mode == "once":
            recurrence_type = "once"
        elif mode in {"daily", "weekly"}:
            if not when_utc:
                await ctx.send("❌ Recurring reminders need `when` for the first run.")
                return
            recurrence_type = mode
        elif mode == "monthly":
            if not when_utc:
                await ctx.send("❌ Monthly reminders need `when` for the first run.")
                return
            recurrence_type = "monthly"
            run_game = when_utc.astimezone(GAME_TZ)
            minute_of_day = run_game.hour * 60 + run_game.minute
            recurrence_value = f"{run_game.day}|{minute_of_day}"
        elif mode == "weekdays":
            if not when_utc:
                await ctx.send("❌ Weekday reminders need `when` for the first run.")
                return
            try:
                weekday_indexes = self._normalize_weekdays(weekdays)
            except ValueError as exc:
                await ctx.send(str(exc))
                return
            recurrence_type = "custom_weekdays"
            run_game = when_utc.astimezone(GAME_TZ)
            minute_of_day = run_game.hour * 60 + run_game.minute
            recurrence_value = f"{','.join(str(x) for x in weekday_indexes)}|{minute_of_day}"

        if when_utc and when_utc <= datetime.now(timezone.utc):
            await ctx.send("❌ `when` must be in the future.")
            return

        await self._send_or_schedule(
            ctx,
            target_channel,
            body,
            when_utc,
            recurrence_type=recurrence_type,
            recurrence_value=recurrence_value,
        )
    async def _send_or_schedule(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel | discord.Thread,
        body: str,
        when_utc: datetime | None,
        recurrence_type: str = "once",
        recurrence_value: str | None = None,
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
                recurrence_type=recurrence_type,
                recurrence_value=recurrence_value,
            )
            self._schedule_reminder(reminder_id, channel, body, when_utc)
            recur_text = self._describe_recurrence(recurrence_type, recurrence_value)
            await ctx.send(
                f"⏳ Reminder scheduled for {format_game(when_utc)} in {channel.mention}. ({recur_text})",
                delete_after=12,
            )
        else:
            await _post()
            await ctx.send(f"✅ Reminder sent to {channel.mention}.", delete_after=8)

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
        guild_id = channel.guild.id
        try:
            reminders = await get_scheduled_reminders(guild_id)
            record = next((item for item in reminders if item["id"] == reminder_id), None)
            if not record:
                return

            if not await is_channel_ignored(guild_id, channel.id):
                reminder_message = self._format_reminder_message(body)
                await channel.send(
                    f"{reminder_message}\n\n{random.choice(MARCIA_SYSTEM_LINES)}",
                    allowed_mentions=discord.AllowedMentions(everyone=True),
                )

            recurrence_type = record["recurrence_type"]
            recurrence_value = record["recurrence_value"]
            next_run = self._advance_to_future(
                self._compute_next_run(when_utc, recurrence_type, recurrence_value) or when_utc,
                recurrence_type,
                recurrence_value,
            )
            if recurrence_type != "once" and next_run:
                await update_scheduled_reminder(guild_id, reminder_id, next_run.isoformat())
                self._schedule_reminder(reminder_id, channel, body, next_run)
            else:
                await delete_scheduled_reminder(guild_id, reminder_id)
        finally:
            current = asyncio.current_task()
            if self.scheduled_tasks.get(reminder_id) is current:
                self.scheduled_tasks.pop(reminder_id, None)

    async def _restore_scheduled_reminders(self) -> None:
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            reminders = await get_scheduled_reminders(guild.id)
            now_utc = datetime.now(timezone.utc)
            for reminder in reminders:
                send_at = datetime.fromisoformat(reminder["send_at_utc"]).astimezone(timezone.utc)
                next_run = self._advance_to_future(
                    send_at,
                    reminder["recurrence_type"],
                    reminder["recurrence_value"],
                    now_utc=now_utc,
                )
                if not next_run:
                    await delete_scheduled_reminder(guild.id, reminder["id"])
                    continue
                if next_run != send_at:
                    await update_scheduled_reminder(guild.id, reminder["id"], next_run.isoformat())
                    send_at = next_run
                channel = guild.get_channel(reminder["channel_id"])
                if not channel:
                    await delete_scheduled_reminder(guild.id, reminder["id"])
                    continue
                self._schedule_reminder(reminder["id"], channel, reminder["body"], send_at)

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
        for reminder in reminders[:15]:
            send_at = datetime.fromisoformat(reminder["send_at_utc"]).astimezone(timezone.utc)
            channel = guild.get_channel(reminder["channel_id"])
            channel_label = channel.mention if channel else f"<#{reminder['channel_id']}>"
            preview = reminder["body"]
            if len(preview) > 56:
                preview = preview[:53] + "…"
            cadence = self._describe_recurrence(reminder["recurrence_type"], reminder["recurrence_value"])
            lines.append(f"• **{format_game(send_at)}** • {cadence} • {channel_label}\n  └ {preview}")
        chunks: list[str] = []
        current_chunk = ""
        for line in lines:
            candidate = f"{current_chunk}\n{line}".strip() if current_chunk else line
            if len(candidate) <= 1024:
                current_chunk = candidate
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(line) <= 1024:
                    current_chunk = line
                else:
                    truncated = line[:1021] + "…"
                    chunks.append(truncated)
                    current_chunk = ""
        if current_chunk:
            chunks.append(current_chunk)

        for index, chunk in enumerate(chunks):
            field_name = "Scheduled" if index == 0 else f"Scheduled (cont. {index + 1})"
            embed.add_field(name=field_name, value=chunk, inline=False)
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

    @discord.ui.button(label="One-Time Reminder", style=discord.ButtonStyle.primary, emoji="🆕", row=0)
    async def one_time_reminder(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        await interaction.response.send_modal(
            ReminderModal(self.cog, self.ctx, self.event_channel_id)
        )

    @discord.ui.button(label="Schedule Reminder", style=discord.ButtonStyle.primary, emoji="🗓️", row=0)
    async def schedule_recurring(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        await interaction.response.send_modal(
            RecurringReminderModal(self.cog, self.ctx, self.event_channel_id)
        )

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.success, emoji="📋", row=1)
    async def send_from_template(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        templates = await get_reminder_templates(self.ctx.guild.id)
        if not templates:
            await interaction.response.send_message("📂 No templates saved yet.", ephemeral=True)
            return

        await interaction.response.send_message(
            "Select a template to use.",
            view=TemplateSelectView(self.cog, self.ctx, templates, self.event_channel_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Bulk Import", style=discord.ButtonStyle.success, emoji="📦", row=1)
    async def bulk_import(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        default_channel = self.ctx.guild.get_channel(self.event_channel_id) if self.event_channel_id else None
        embed = self.cog._build_bulk_reminder_help_embed(default_channel)
        await interaction.response.send_message(
            embed=embed,
            view=BulkReminderLauncherView(self.cog, self.ctx, self.event_channel_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Archive Template", style=discord.ButtonStyle.secondary, emoji="💾", row=1)
    async def archive_template(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        await interaction.response.send_modal(TemplateCreateModal(self.ctx))

    @discord.ui.button(label="Delete Template", style=discord.ButtonStyle.danger, emoji="🗂️", row=1)
    async def delete_template(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        templates = await get_reminder_templates(self.ctx.guild.id)
        if not templates:
            await interaction.response.send_message("📂 No templates to delete.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Select a template to delete.",
            view=TemplateDeleteView(self.ctx, templates),
            ephemeral=True,
        )

    @discord.ui.button(label="Upcoming Reminders", style=discord.ButtonStyle.secondary, emoji="📆", row=2)
    async def upcoming_reminders(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        embed = await self.cog._build_upcoming_reminders_embed(self.ctx.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Remove Reminder", style=discord.ButtonStyle.danger, emoji="🗑️", row=2)
    async def remove_reminder(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not self._is_requester(interaction):
            return await interaction.response.send_message("Only the requester can use this menu.", ephemeral=True)
        reminders = await get_scheduled_reminders(self.ctx.guild.id)
        if not reminders:
            await interaction.response.send_message("📭 No scheduled reminders to remove.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Select a reminder to remove.",
            view=ReminderRemoveView(self.cog, self.ctx, reminders),
            ephemeral=True,
        )


class BulkReminderLauncherView(discord.ui.View):
    def __init__(self, cog: Reminders, ctx: commands.Context, event_channel_id: int | None):
        super().__init__(timeout=180)
        self.cog = cog
        self.ctx = ctx
        self.event_channel_id = event_channel_id

    @discord.ui.button(label="Paste in Chat", style=discord.ButtonStyle.primary, emoji="📝")
    async def launch_chat_import(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Only the requester can use this import.", ephemeral=True)
        await interaction.response.send_message(
            "📝 Paste your reminder batch as your next message in this channel within 3 minutes. "
            "You can paste plain lines or wrap them in a ```text``` code block.",
            ephemeral=True,
        )
        await self.cog._collect_bulk_reminder_message(interaction, self.ctx, self.event_channel_id)


class BulkReminderPreviewView(discord.ui.View):
    def __init__(self, cog: Reminders, ctx: commands.Context, parsed_rows: list[dict], errors: list[str]):
        super().__init__(timeout=180)
        self.cog = cog
        self.ctx = ctx
        self.parsed_rows = parsed_rows
        self.errors = errors

    @discord.ui.button(label="Import Valid Rows", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Only the requester can confirm this import.", ephemeral=True)
        if not self.parsed_rows:
            return await interaction.response.send_message("❌ There are no valid rows to import yet.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        imported, sent_now = await self.cog._commit_bulk_reminders(self.ctx, self.parsed_rows)
        scheduled = imported - sent_now
        summary = (
            f"✅ Imported **{imported}** reminder(s): **{scheduled}** scheduled, **{sent_now}** sent now."
        )
        if self.errors:
            summary += f" Skipped **{len(self.errors)}** issue(s) listed in the preview."
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            content=summary,
            embed=None,
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="🛑")
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Only the requester can cancel this import.", ephemeral=True)
        await interaction.response.edit_message(
            content="📭 Bulk reminder import cancelled.",
            embed=None,
            view=None,
        )


class ReminderModal(discord.ui.Modal):
    def __init__(self, cog: Reminders, ctx: commands.Context, event_channel_id: int | None = None):
        super().__init__(title="One-Time Reminder")
        self.cog = cog
        self.ctx = ctx
        self.event_channel_id = event_channel_id

        self.channel_input = discord.ui.TextInput(
            label="Channel",
            required=False,
            placeholder="#events, channel id, or leave blank for default events channel",
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
            placeholder="YYYY-MM-DD (UTC-2), blank = send now",
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

        channel_value = str(self.channel_input.value).strip()
        if channel_value:
            channel = self.cog._parse_channel(self.ctx.guild, channel_value)
            if not channel:
                await interaction.followup.send(
                    "❌ Channel not found. Use #mention, id, or channel name.",
                    ephemeral=True,
                )
                return
        else:
            channel = self.ctx.guild.get_channel(self.event_channel_id) if self.event_channel_id else None

        if not channel:
            await interaction.followup.send(
                "📌 Set an events channel first with `/setup` or provide a valid channel.",
                ephemeral=True,
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
            try:
                when_utc = self.cog._parse_when(f"{date_value} {time_value}")
            except ValueError as exc:
                await interaction.followup.send(str(exc), ephemeral=True)
                return
        else:
            when_utc = None

        await self.cog._send_or_schedule(self.ctx, channel, str(self.body.value), when_utc)
        await interaction.followup.send("✅ Reminder queued.", ephemeral=True)


class RecurringReminderModal(discord.ui.Modal):
    def __init__(self, cog: Reminders, ctx: commands.Context, event_channel_id: int | None = None):
        super().__init__(title="Schedule Reminder")
        self.cog = cog
        self.ctx = ctx
        self.event_channel_id = event_channel_id

        self.channel_input = discord.ui.TextInput(
            label="Channel",
            required=False,
            placeholder="#events, channel id, or blank for default events channel",
            max_length=100,
        )
        self.body = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.long,
            max_length=800,
            placeholder="Reminder text",
        )
        self.mode = discord.ui.TextInput(
            label="Schedule type",
            placeholder="daily | weekly | monthly | weekdays",
            max_length=24,
        )
        self.date_time = discord.ui.TextInput(
            label="First run",
            placeholder="YYYY-MM-DD HH:MM (UTC-2)",
            max_length=32,
        )
        self.details = discord.ui.TextInput(
            label="Details (optional)",
            required=False,
            placeholder="For weekdays: Monday,Wednesday. Monthly uses day from first run.",
            max_length=100,
        )
        self.add_item(self.channel_input)
        self.add_item(self.body)
        self.add_item(self.mode)
        self.add_item(self.date_time)
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        channel_value = str(self.channel_input.value).strip()
        if channel_value:
            channel = self.cog._parse_channel(self.ctx.guild, channel_value)
            if not channel:
                await interaction.followup.send(
                    "❌ Channel not found. Use #mention, id, or channel name.",
                    ephemeral=True,
                )
                return
        else:
            channel = self.ctx.guild.get_channel(self.event_channel_id) if self.event_channel_id else None

        if not channel:
            await interaction.followup.send(
                "📌 Set an events channel first with `/setup` or provide a valid channel.",
                ephemeral=True,
            )
            return

        try:
            when_utc = self.cog._parse_when(str(self.date_time.value).strip())
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        if not when_utc or when_utc <= datetime.now(timezone.utc):
            await interaction.followup.send(
                "❌ First run must be in the future.",
                ephemeral=True,
            )
            return

        mode_raw = str(self.mode.value).strip().lower()
        details_raw = str(self.details.value).strip()
        recurrence_type = "once"
        recurrence_value = None

        if mode_raw == "daily":
            recurrence_type = "daily"
        elif mode_raw == "weekly":
            recurrence_type = "weekly"
        elif mode_raw == "monthly":
            recurrence_type = "monthly"
            run_game = when_utc.astimezone(GAME_TZ)
            minute_of_day = run_game.hour * 60 + run_game.minute
            recurrence_value = f"{run_game.day}|{minute_of_day}"
        elif mode_raw in {"weekdays", "custom", "days"}:
            recurrence_type = "custom_weekdays"
            try:
                weekday_indexes = self.cog._normalize_weekdays(details_raw)
            except ValueError as exc:
                await interaction.followup.send(str(exc), ephemeral=True)
                return
            run_game = when_utc.astimezone(GAME_TZ)
            minute_of_day = run_game.hour * 60 + run_game.minute
            recurrence_value = f"{','.join(str(x) for x in weekday_indexes)}|{minute_of_day}"
        else:
            await interaction.followup.send(
                "❌ Schedule type must be one of: `daily`, `weekly`, `monthly`, `weekdays`.",
                ephemeral=True,
            )
            return

        await self.cog._send_or_schedule(
            self.ctx,
            channel,
            str(self.body.value),
            when_utc,
            recurrence_type=recurrence_type,
            recurrence_value=recurrence_value,
        )
        await interaction.followup.send("✅ Recurring reminder queued.", ephemeral=True)


class TemplateSelect(discord.ui.Select):
    def __init__(self, cog: Reminders, ctx: commands.Context, templates: list[dict], event_channel_id: int | None = None):
        options = [
            discord.SelectOption(label=t["template_name"], description=t["body"][:90])
            for t in templates[:25]
        ]
        super().__init__(placeholder="Choose a template", options=options, min_values=1, max_values=1)
        self.cog = cog
        self.ctx = ctx
        self.templates = templates
        self.event_channel_id = event_channel_id

    async def callback(self, interaction: discord.Interaction):
        template = next((t for t in self.templates if t["template_name"] == self.values[0]), None)
        if not template:
            await interaction.response.send_message("Template not found.", ephemeral=True)
            return

        view = TemplateActionView(self.cog, self.ctx, template, self.event_channel_id)
        await interaction.response.send_message(
            f"Template selected: **{template['template_name']}**. Choose how to use it.",
            view=view,
            ephemeral=True,
        )


class TemplateSelectView(discord.ui.View):
    def __init__(self, cog: Reminders, ctx: commands.Context, templates: list[dict], event_channel_id: int | None = None):
        super().__init__(timeout=60)
        self.add_item(TemplateSelect(cog, ctx, templates, event_channel_id))


class TemplateActionView(discord.ui.View):
    def __init__(self, cog: Reminders, ctx: commands.Context, template: dict, event_channel_id: int | None):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.template = template
        self.event_channel_id = event_channel_id

    @discord.ui.button(label="Use as One-Time", style=discord.ButtonStyle.primary, emoji="🆕")
    async def one_time(self, interaction: discord.Interaction, _button: discord.ui.Button):
        modal = ReminderModal(self.cog, self.ctx, self.event_channel_id)
        modal.body.default = self.template["body"]
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Use as Scheduled", style=discord.ButtonStyle.success, emoji="🗓️")
    async def scheduled(self, interaction: discord.Interaction, _button: discord.ui.Button):
        modal = RecurringReminderModal(self.cog, self.ctx, self.event_channel_id)
        modal.body.default = self.template["body"]
        await interaction.response.send_modal(modal)


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
            cadence = cog._describe_recurrence(reminder["recurrence_type"], reminder["recurrence_value"])
            label = f"{format_game(send_at)} • {cadence}"
            preview = reminder["body"][:70]
            options.append(
                discord.SelectOption(
                    label=label[:100],
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
    def __init__(self, cog: Reminders, ctx: commands.Context, reminders):
        super().__init__(timeout=60)
        self.add_item(ReminderRemoveSelect(cog, ctx, reminders))


class TemplateDeleteSelect(discord.ui.Select):
    def __init__(self, ctx: commands.Context, templates: list[dict]):
        options = [
            discord.SelectOption(label=t["template_name"], description=t["body"][:90])
            for t in templates[:25]
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
