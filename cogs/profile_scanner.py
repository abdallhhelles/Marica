"""
FILE: cogs/profile_scanner.py
USE: Capture profile screenshots, OCR key stats, and surface stat leaderboards.
FEATURES: Channel-scoped intake, OCR parsing, profile views, and leaderboard queries.
"""

import asyncio
import importlib.util
import io
import logging
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database import (
    get_profile_channel,
    get_profile_snapshot,
    set_profile_channel,
    top_profile_stat,
    upsert_profile_snapshot,
)

_PIL_SPEC = importlib.util.find_spec("PIL")
_PYTESSERACT_SPEC = importlib.util.find_spec("pytesseract")

if _PIL_SPEC:
    from PIL import Image
else:  # pragma: no cover - optional dependency guard
    Image = None

if _PYTESSERACT_SPEC:
    import pytesseract
else:  # pragma: no cover - optional dependency guard
    pytesseract = None


NUMBER_RE = re.compile(r"(?P<value>[\d.,]+)\s*(?P<suffix>[kmbKMB]?)")
LABEL_HINTS = {
    "cp": ("cp", "power"),
    "kills": ("kills",),
    "likes": ("likes", "thumb"),
    "alliance": ("alliance", "all", "guild"),
    "server": ("server", "state"),
    "vip_level": ("vip",),
    "level": ("level",),
}


def _extract_number(chunk: str) -> int | None:
    match = NUMBER_RE.search(chunk)
    if not match:
        return None

    raw = match.group("value").replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None

    suffix = match.group("suffix").lower()
    if suffix == "k":
        value *= 1_000
    elif suffix == "m":
        value *= 1_000_000
    elif suffix == "b":
        value *= 1_000_000_000

    return int(value)


def _parse_profile_text(text: str) -> dict:
    """Pull out the most likely values for each supported field."""

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    results: dict[str, str | int | None] = {}

    if lines:
        results["player_name"] = lines[0]

    for line in lines:
        lowered = line.lower()
        for field, hints in LABEL_HINTS.items():
            if field in results and results[field] is not None:
                continue
            if any(hint in lowered for hint in hints):
                if field in {"alliance", "server"}:
                    value = line.split(":", 1)[-1].strip() if ":" in line else line
                    results[field] = value
                else:
                    results[field] = _extract_number(line)
    return results


def _format_metric(value: int | None) -> str:
    return f"{value:,}" if isinstance(value, int) else "—"


class ProfileScanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger("MarciaOS.ProfileScanner")

    async def cog_unload(self):
        pass

    async def _safe_send(self, ctx, **kwargs):
        interaction = getattr(ctx, "interaction", None)
        if interaction:
            if interaction.response.is_done():
                return await interaction.followup.send(**kwargs)
            return await interaction.response.send_message(**kwargs)

        kwargs.pop("ephemeral", None)
        return await ctx.send(**kwargs)

    # --------------------
    # Commands
    # --------------------
    @commands.hybrid_command(
        name="setup_profile_channel",
        description="Choose the channel where Marcia will read profile screenshots.",
    )
    @commands.has_permissions(manage_guild=True)
    async def setup_profile_channel(self, ctx, channel: discord.TextChannel):
        await set_profile_channel(ctx.guild.id, channel.id)
        embed = discord.Embed(
            title="📡 Profile Scanner Armed",
            description=(
                "I'll watch this channel for profile screenshots and log stats to the "
                "uploader."
            ),
            color=0x5865F2,
        )
        embed.add_field(name="Channel", value=channel.mention, inline=False)
        await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(
        name="profile_stats",
        description="Show the parsed profile stats for you or another survivor.",
    )
    async def profile_stats(self, ctx, member: discord.Member | None = None):
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Profiles only work inside servers.",
                ephemeral=True,
            )

        target = member or ctx.author
        data = await get_profile_snapshot(ctx.guild.id, target.id)
        if not data:
            return await self._safe_send(
                ctx,
                content=(
                    "No profile stored yet. Drop a screenshot in the configured channel first."
                ),
                ephemeral=True,
            )

        embed = discord.Embed(
            title=f"📄 Profile: {data['player_name'] or target.display_name}",
            color=0x2ecc71,
        )
        embed.set_thumbnail(url=data["avatar_url"] or target.display_avatar.url)
        embed.add_field(name="CP", value=_format_metric(data["cp"]), inline=True)
        embed.add_field(name="Kills", value=_format_metric(data["kills"]), inline=True)
        embed.add_field(name="Likes", value=_format_metric(data["likes"]), inline=True)
        embed.add_field(name="VIP", value=data.get("vip_level") or "—", inline=True)
        embed.add_field(name="Level", value=data.get("level") or "—", inline=True)
        embed.add_field(name="Alliance", value=data.get("alliance") or "—", inline=True)
        embed.add_field(name="Server", value=data.get("server") or "—", inline=True)
        if data.get("last_updated"):
            dt = datetime.fromtimestamp(data["last_updated"], tz=timezone.utc)
            embed.set_footer(text=f"Last scanned {dt.strftime('%Y-%m-%d %H:%M UTC')}")
        await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(
        name="profile_leaderboard",
        description="Show the top survivors for a scanned profile stat.",
    )
    @app_commands.choices(
        stat=[
            app_commands.Choice(name="Combat Power", value="cp"),
            app_commands.Choice(name="Kills", value="kills"),
            app_commands.Choice(name="Likes", value="likes"),
            app_commands.Choice(name="VIP", value="vip"),
            app_commands.Choice(name="Level", value="level"),
        ]
    )
    async def profile_leaderboard(self, ctx, stat: app_commands.Choice[str]):
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Leaderboards only work inside servers.",
                ephemeral=True,
            )

        rows = await top_profile_stat(ctx.guild.id, stat.value)
        if not rows:
            return await self._safe_send(
                ctx, content="No scanned profiles yet.", ephemeral=True
            )

        lines = []
        for idx, row in enumerate(rows, start=1):
            user = ctx.guild.get_member(row["user_id"])
            name = row["player_name"] or (user.display_name if user else f"User {row['user_id']}")
            lines.append(f"**{idx}.** {name} — {_format_metric(row['value'])}")

        embed = discord.Embed(
            title=f"🏅 {stat.name} Leaderboard",
            description="\n".join(lines),
            color=0xf1c40f,
        )
        await self._safe_send(ctx, embed=embed)

    # --------------------
    # Intake listener
    # --------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        channel_id = await get_profile_channel(message.guild.id)
        if not channel_id or message.channel.id != channel_id:
            return

        attachment = next(
            (
                a
                for a in message.attachments
                if (a.content_type or "").startswith("image")
            ),
            None,
        )
        if not attachment:
            return

        asyncio.create_task(self._process_profile_upload(message, attachment))

    async def _process_profile_upload(
        self, message: discord.Message, attachment: discord.Attachment
    ) -> None:
        try:
            image_bytes = await attachment.read()
        except Exception as exc:  # pragma: no cover - network edge
            self.log.warning("Could not read attachment: %s", exc)
            return

        ocr_text = await self._perform_ocr(image_bytes)
        parsed = _parse_profile_text(ocr_text) if ocr_text else {}

        parsed_payload = {
            "player_name": parsed.get("player_name") or message.author.display_name,
            "alliance": parsed.get("alliance"),
            "server": parsed.get("server"),
            "cp": parsed.get("cp"),
            "kills": parsed.get("kills"),
            "likes": parsed.get("likes"),
            "vip_level": parsed.get("vip_level"),
            "level": parsed.get("level"),
            "avatar_url": str(message.author.display_avatar.url),
            "last_image_url": attachment.url,
            "raw_ocr": ocr_text,
        }

        await upsert_profile_snapshot(message.guild.id, message.author.id, **parsed_payload)
        await self._post_confirmation(message, parsed_payload)

    async def _perform_ocr(self, image_bytes: bytes) -> str:
        if not (pytesseract and Image):
            return ""

        loop = asyncio.get_running_loop()

        def _scan() -> str:
            with Image.open(io.BytesIO(image_bytes)) as img:
                return pytesseract.image_to_string(img)

        return await loop.run_in_executor(None, _scan)

    async def _post_confirmation(self, message: discord.Message, payload: dict) -> None:
        embed = discord.Embed(
            title="🛰️ Profile logged",
            description=(
                "Snapshot captured. Use `/profile_stats` to review or `/profile_leaderboard` "
                "to compare stats."
            ),
            color=0x3498db,
        )

        embed.add_field(name="CP", value=_format_metric(payload.get("cp")), inline=True)
        embed.add_field(name="Kills", value=_format_metric(payload.get("kills")), inline=True)
        embed.add_field(name="Likes", value=_format_metric(payload.get("likes")), inline=True)
        embed.add_field(name="VIP", value=payload.get("vip_level") or "—", inline=True)
        embed.add_field(name="Level", value=payload.get("level") or "—", inline=True)
        embed.add_field(name="Alliance", value=payload.get("alliance") or "—", inline=True)
        embed.add_field(name="Server", value=payload.get("server") or "—", inline=True)

        if not payload.get("raw_ocr"):
            embed.set_footer(text="OCR unavailable. Install Tesseract + pytesseract for auto-parsing.")

        try:
            await message.reply(embed=embed, mention_author=False)
        except Exception:  # pragma: no cover - Discord edge
            self.log.exception("Failed to reply with profile confirmation")


async def setup(bot):
    await bot.add_cog(ProfileScanner(bot))

