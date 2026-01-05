"""
FILE: cogs/profile_scanner.py
USE: Capture profile screenshots, OCR key stats, and surface stat leaderboards.
FEATURES: Channel-scoped intake, OCR parsing, profile views, and leaderboard queries.
"""

import asyncio
import importlib.util
import io
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.errors import HTTPException
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
_CV2_SPEC = importlib.util.find_spec("cv2")
_EASYOCR_SPEC = importlib.util.find_spec("easyocr")

if _PIL_SPEC:
    from PIL import Image
else:  # pragma: no cover - optional dependency guard
    Image = None

if _PYTESSERACT_SPEC:
    import pytesseract
else:  # pragma: no cover - optional dependency guard
    pytesseract = None

if _CV2_SPEC and _EASYOCR_SPEC:
    import cv2
    import easyocr
    import numpy as np
else:  # pragma: no cover - optional dependency guard
    cv2 = None
    easyocr = None
    np = None


NUMBER_RE = re.compile(r"(?P<value>[\d.,]+)\s*(?P<suffix>[kmbKMB]?)")
LABEL_HINTS = {
    "cp": ("cp", "power"),
    "kills": ("kills",),
    "alliance": ("alliance", "all", "guild"),
    "server": ("server", "state"),
}

BOXES_PATH = Path(__file__).resolve().parent.parent / "ocr" / "boxes_ratios.json"
EASYOCR_LANGS = ["en"]
EASYOCR_MIN_CONF = 0.45
EASYOCR_FIELDS = {
    "name": "player_name",
    "power_cp": "cp",
    "kills": "kills",
    "alliance": "alliance",
    "state": "server",
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
        self._easyocr_reader: easyocr.Reader | None = None
        self._easyocr_boxes: dict[str, list[float]] | None = None
        self._easyocr_ready: bool | None = None
        self._easyocr_lock = asyncio.Lock()

    async def cog_unload(self):
        pass

    async def _safe_send(self, ctx, *, ephemeral: bool = False, **kwargs):
        interaction = getattr(ctx, "interaction", None)
        if interaction:
            try:
                if interaction.response.is_done():
                    return await interaction.followup.send(**kwargs, ephemeral=ephemeral)
                return await interaction.response.send_message(**kwargs, ephemeral=ephemeral)
            except HTTPException as exc:
                if exc.code == 40060:
                    return await interaction.followup.send(**kwargs, ephemeral=ephemeral)
                raise

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
        name="scan_profile",
        description="Scan a profile screenshot and save the stats for this server.",
    )
    async def scan_profile(self, ctx, image: discord.Attachment):
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Profiles only work inside servers.",
                ephemeral=True,
            )

        if not self._is_image_attachment(image):
            return await self._safe_send(
                ctx,
                content="Please upload a PNG, JPEG, or WEBP screenshot.",
                ephemeral=True,
            )

        await ctx.defer(ephemeral=True)

        try:
            image_bytes = await image.read()
        except Exception as exc:  # pragma: no cover - network edge
            self.log.warning("Could not read attachment: %s", exc)
            return await self._safe_send(ctx, content="I couldn't read that image.", ephemeral=True)

        parsed, raw_text = await self._perform_ocr(image_bytes)
        payload = self._build_payload(ctx.author, image.url, parsed, raw_text)
        await upsert_profile_snapshot(ctx.guild.id, ctx.author.id, **payload)

        embed = self._build_confirmation_embed(payload)
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
            (a for a in message.attachments if self._is_image_attachment(a)),
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

        parsed, raw_text = await self._perform_ocr(image_bytes)
        payload = self._build_payload(message.author, attachment.url, parsed, raw_text)

        await upsert_profile_snapshot(message.guild.id, message.author.id, **payload)
        await self._post_confirmation(message, payload)

    async def _perform_ocr(self, image_bytes: bytes) -> tuple[dict, str]:
        parsed: dict[str, str | int | None] = {}
        raw_text = ""

        easyocr_results = await self._run_easyocr(image_bytes)
        if easyocr_results:
            parsed.update(easyocr_results["parsed"])
            raw_text = easyocr_results["raw"]

        if not parsed:
            pytesseract_text = await self._run_pytesseract(image_bytes)
            raw_text = pytesseract_text or raw_text
            if pytesseract_text:
                parsed.update(_parse_profile_text(pytesseract_text))

        return parsed, raw_text

    async def _run_pytesseract(self, image_bytes: bytes) -> str:
        if not (pytesseract and Image):
            return ""

        loop = asyncio.get_running_loop()

        def _scan() -> str:
            try:
                with Image.open(io.BytesIO(image_bytes)) as img:
                    return pytesseract.image_to_string(img)
            except Exception as exc:
                # Gracefully handle missing tesseract binaries instead of crashing the task
                if hasattr(pytesseract, "TesseractNotFoundError") and isinstance(
                    exc, pytesseract.TesseractNotFoundError
                ):
                    self.log.warning("Tesseract binary missing; skipping pytesseract fallback")
                    return ""
                raise

        return await loop.run_in_executor(None, _scan)

    async def _ensure_easyocr(self) -> bool:
        if self._easyocr_ready is not None:
            return self._easyocr_ready

        if not (easyocr and cv2 and np):
            self._easyocr_ready = False
            return False

        async with self._easyocr_lock:
            if self._easyocr_ready is not None:
                return self._easyocr_ready

            if not BOXES_PATH.exists():
                self._easyocr_ready = False
                return False

            loop = asyncio.get_running_loop()

            def _load():
                with BOXES_PATH.open("r", encoding="utf-8") as fp:
                    data = json.load(fp)
                boxes = data.get("template_ratios") or {}
                reader = easyocr.Reader(EASYOCR_LANGS, gpu=False)
                return boxes, reader

            boxes, reader = await loop.run_in_executor(None, _load)
            self._easyocr_boxes = boxes
            self._easyocr_reader = reader
            self._easyocr_ready = bool(boxes)
            return self._easyocr_ready

    async def _run_easyocr(self, image_bytes: bytes):
        ready = await self._ensure_easyocr()
        if not ready or not self._easyocr_reader or not self._easyocr_boxes:
            return None

        loop = asyncio.get_running_loop()

        def _scan():
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None

            results: dict[str, str | int | None] = {}
            raw_lines: list[str] = []

            for field, ratios in self._easyocr_boxes.items():
                crop = self._crop_by_ratio(img, ratios)
                if crop is None:
                    continue

                proc = self._preprocess_crop(crop)
                detections = self._easyocr_reader.readtext(proc)
                if not detections:
                    continue

                detections.sort(key=lambda item: item[2], reverse=True)
                best_text = detections[0][1].strip()
                best_conf = float(detections[0][2])
                raw_lines.append(f"{field}: {best_text} ({best_conf:.2f})")

                if best_conf < EASYOCR_MIN_CONF:
                    continue

                mapped = EASYOCR_FIELDS.get(field)
                if not mapped:
                    continue

                if mapped in {"cp", "kills"}:
                    cleaned = re.sub(r"[^\d]", "", best_text)
                    if cleaned:
                        results[mapped] = int(cleaned)
                elif mapped == "server":
                    results[mapped] = best_text
                else:
                    results[mapped] = best_text

            raw = "\n".join(raw_lines)
            return {"parsed": results, "raw": raw}

        return await loop.run_in_executor(None, _scan)

    def _crop_by_ratio(self, img, box):
        h, w = img.shape[:2]
        x1 = int(w * box[0])
        y1 = int(h * box[1])
        x2 = int(w * box[2])
        y2 = int(h * box[3])

        x1 = max(0, min(x1, w - 1))
        x2 = max(1, min(x2, w))
        y1 = max(0, min(y1, h - 1))
        y2 = max(1, min(y2, h))

        if x2 <= x1 or y2 <= y1:
            return None

        return img[y1:y2, x1:x2]

    def _preprocess_crop(self, crop):
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        return gray

    def _build_payload(
        self,
        member: discord.Member,
        image_url: str,
        parsed: dict[str, str | int | None],
        raw_text: str,
    ) -> dict:
        return {
            "player_name": parsed.get("player_name") or member.display_name,
            "alliance": parsed.get("alliance"),
            "server": parsed.get("server"),
            "cp": parsed.get("cp"),
            "kills": parsed.get("kills"),
            "avatar_url": str(member.display_avatar.url),
            "last_image_url": image_url,
            "raw_ocr": raw_text,
        }

    def _is_image_attachment(self, attachment: discord.Attachment) -> bool:
        if not attachment.content_type:
            return False
        content_type = attachment.content_type.lower()
        allowed = {"image/png", "image/jpeg", "image/webp"}
        return content_type in allowed

    async def _post_confirmation(self, message: discord.Message, payload: dict) -> None:
        embed = self._build_confirmation_embed(payload)

        if not payload.get("raw_ocr"):
            embed.set_footer(
                text=(
                    "OCR unavailable. Install Tesseract + pytesseract or easyocr + opencv for"
                    " auto-parsing."
                )
            )

        try:
            await message.reply(embed=embed, mention_author=False)
        except Exception:  # pragma: no cover - Discord edge
            self.log.exception("Failed to reply with profile confirmation")

    def _build_confirmation_embed(self, payload: dict) -> discord.Embed:
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
        embed.add_field(name="Alliance", value=payload.get("alliance") or "—", inline=True)
        embed.add_field(name="Server", value=payload.get("server") or "—", inline=True)
        return embed


async def setup(bot):
    await bot.add_cog(ProfileScanner(bot))

