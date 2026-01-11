"""
FILE: cogs/profile_scanner.py
USE: Capture profile screenshots, scan key stats, and surface stat leaderboards.
FEATURES: Channel-scoped intake, scan parsing, profile views, and leaderboard queries.
"""

import asyncio
import importlib.util
import io
import json
import logging
import re
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.errors import HTTPException
from discord.ext import commands
import httpx

from database import (
    get_profile_channel,
    get_profile_snapshot,
    get_profile_snapshots,
    increment_activity_metric,
    delete_profile_snapshot,
    set_profile_scan_valid,
    set_profile_channel,
    upsert_profile_snapshot,
)
from utils.assets import PROFILE_SEALS, PROFILE_TAGLINES
from ocr.diagnostics import collect_ocr_diagnostics

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
    "cp": ("cp", "power", "battle power", "total power", "combat power"),
    "kills": ("kills", "defeats", "defeated", "eliminations", "total kills"),
    "likes": ("likes", "like", "likes received"),
    "vip_level": ("vip", "vip level", "vip lvl", "vip lv"),
    "alliance": ("alliance", "all", "guild"),
    "server": ("server", "state", "world"),
}

BOXES_PATH = Path(__file__).resolve().parent.parent / "ocr" / "boxes_ratios.json"
EASYOCR_LANGS = ["en"]
EASYOCR_MIN_CONF = 0.45
EASYOCR_FIELDS = {
    "name": "player_name",
    "cp": "cp",
    "kills": "kills",
    "alliance": "alliance",
    "server": "server",
    "likes": "likes",
    "vip": "vip_level",
}
VERIFY_FIELDS = {"account_btn", "settings_btn"}
VERIFY_MIN_CONF = 0.25
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")
OCR_SPACE_ENDPOINT = "https://api.ocr.space/parse/image"


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
        self._easyocr_failure_reason: str | None = None
        self._easyocr_lock = asyncio.Lock()
        self._pytesseract_missing = False
        self._scan_semaphore = asyncio.Semaphore(
            int(os.getenv("PROFILE_SCAN_CONCURRENCY", "2"))
        )

    async def cog_unload(self):
        pass

    async def _safe_send(self, ctx, *, ephemeral: bool = False, **kwargs):
        interaction = getattr(ctx, "interaction", None)
        if interaction:
            return await self.bot._safe_interaction_reply(
                interaction, ephemeral=ephemeral, **kwargs
            )

        kwargs.pop("ephemeral", None)
        return await ctx.send(**kwargs)

    async def _safe_defer(self, ctx, *, ephemeral: bool = False):
        interaction = getattr(ctx, "interaction", None)
        if not interaction:
            return await ctx.defer()

        try:
            if interaction.response.is_done() or getattr(interaction, "is_expired", lambda: False)():
                return None
            return await interaction.response.defer(ephemeral=ephemeral)
        except HTTPException as exc:
            if exc.code == 40060:
                self.log.debug(
                    "Skipped duplicate defer for %s",
                    getattr(getattr(interaction, "command", None), "qualified_name", "unknown"),
                )
                return None
            self.log.exception("Failed to defer interaction")
        except Exception:
            self.log.exception("Failed to defer interaction")
        return None

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

        await self._safe_defer(ctx, ephemeral=True)

        try:
            image_bytes = await image.read()
        except Exception as exc:  # pragma: no cover - network edge
            self.log.warning("Could not read attachment: %s", exc)
            return await self._safe_send(ctx, content="I couldn't read that image.", ephemeral=True)

        cached_path = self._persist_profile_image(
            ctx.guild.id, ctx.author.id, image_bytes, image.filename
        )
        parsed, raw_text, ocr_note = await self._perform_ocr(
            image_bytes, filename=image.filename, persisted_path=cached_path
        )
        payload = self._build_payload(
            ctx.author, image.url, parsed, raw_text, cached_path
        )
        if payload.get("ownership_verified") is False:
            return await self._safe_send(
                ctx,
                content=(
                    "🚫 Those aren't your buttons. Snap your own profile before trying to flex."
                ),
                ephemeral=True,
            )
        await upsert_profile_snapshot(ctx.guild.id, ctx.author.id, **payload)

        embed = self._build_confirmation_embed(payload, ocr_note)
        await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(
        name="profile_stats",
        description="Show the parsed profile stats for you or another survivor.",
    )
    async def profile_stats(self, ctx, member: discord.Member | None = None):
        leveling = self.bot.get_cog("Leveling")
        if leveling and hasattr(leveling, "_send_profile_overview"):
            return await leveling._send_profile_overview(ctx, member)

        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Profiles only work inside servers.",
                ephemeral=True,
            )

        target = member or ctx.author
        data = await get_profile_snapshot(ctx.guild.id, target.id)
        if not data or data.get("scan_valid") == 0:
            return await self._safe_send(
                ctx,
                content=(
                    "No valid profile stored yet. Drop a screenshot in the configured channel first."
                ),
                ephemeral=True,
            )

        name = data["player_name"] or target.display_name
        embed = discord.Embed(
            title=f"📡 Sector dossier | {name}",
            description=(
                "Latest profile scan stats saved for this survivor. Use `/leaderboard` to compare "
                "against the rest of the sector."
            ),
            color=0x2ecc71,
        )
        embed.set_thumbnail(url=data["avatar_url"] or target.display_avatar.url)
        ingame = [
            f"🪪 Name: {data.get('player_name') or target.display_name}",
            f"🏰 Alliance: {data.get('alliance') or '—'}",
            f"🌐 Server: {data.get('server') or '—'}",
            f"🎖️ VIP: {_format_metric(data.get('vip_level'))} | 👍 Likes: {_format_metric(data.get('likes'))}",
            f"⚔️ CP: {_format_metric(data['cp'])} | ☠️ Kills: {_format_metric(data['kills'])}",
        ]
        if data.get("ownership_verified") is not None:
            status = "✅ Self-view detected" if data["ownership_verified"] else "⚠️ Could not confirm this is your own profile"
            ingame.append(status)
        if data.get("last_image_url"):
            ingame.append(f"🖼️ [Latest scan]({data['last_image_url']})")

        embed.add_field(name="In-game Profile Scan", value="\n".join(ingame), inline=False)
        embed.add_field(name="Vault Seal", value=random.choice(PROFILE_SEALS), inline=False)

        if data.get("last_updated"):
            dt = datetime.fromtimestamp(data["last_updated"], tz=timezone.utc)
            embed.set_footer(text=f"Last scanned {dt.strftime('%Y-%m-%d %H:%M UTC')}")

        await increment_activity_metric(ctx.guild.id, "profile_views")
        await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(
        name="profile_review",
        description="Review, invalidate, or delete recent profile scans.",
    )
    @commands.has_permissions(manage_guild=True)
    async def profile_review(self, ctx):
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Profile reviews only work inside servers.",
                ephemeral=True,
            )

        snapshots = await get_profile_snapshots(ctx.guild.id, limit=25, include_invalid=True)
        if not snapshots:
            return await self._safe_send(
                ctx,
                content="No profile scans found yet.",
                ephemeral=True,
            )

        view = ProfileReviewView(self, ctx.guild.id, snapshots)
        embed = view.build_embed()
        message = await self._safe_send(ctx, embed=embed, view=view, ephemeral=True)
        if isinstance(message, discord.Message):
            view.bind_message(message)

    @commands.hybrid_command(
        name="ocr_status",
        description="Check whether profile scan dependencies and templates are ready.",
    )
    @commands.has_permissions(manage_guild=True)
    async def ocr_status(self, ctx):
        await ctx.defer(ephemeral=True)

        easyocr_ready = await self._ensure_easyocr()
        diag = collect_ocr_diagnostics()
        diag.easyocr_ready = bool(easyocr_ready)
        diag.easyocr_failure = self._easyocr_failure_reason
        diag.box_count = len(self._easyocr_boxes or {}) or diag.box_count
        diag.boxes_present = BOXES_PATH.exists()

        box_status = (
            f"Loaded {diag.box_count} fields from {BOXES_PATH.name}" if diag.box_count else "No templates loaded"
        )
        box_details = (
            f"Box file present at {BOXES_PATH}" if diag.boxes_present else "Missing boxes_ratios.json"
        )

        easyocr_label = "Ready" if diag.easyocr_ready else "Not ready" if diag.easyocr else "Not installed"
        if diag.easyocr_failure:
            easyocr_label += f" — {diag.easyocr_failure}"

        pytess_label = "Installed" if diag.pytesseract else "Missing"
        if diag.tesseract_binary is True:
            pytess_label += " (binary found)"
        elif diag.tesseract_binary is False:
            pytess_label += " (install the Tesseract CLI)"

        embed = discord.Embed(title="🛰️ Profile Scan Status", color=0x3498db)
        if diag.install_tips:
            embed.description = (
                "⚠️ Profile scans will stay blank until you finish the fixes below."
            )
        elif diag.easyocr_ready:
            embed.description = "✅ Profile scan dependencies and templates look ready."
        embed.add_field(name="EasyOCR", value=easyocr_label, inline=False)
        embed.add_field(name="Templates", value=f"{box_status}\n{box_details}", inline=False)
        embed.add_field(name="Pillow", value="Installed" if diag.pillow else "Missing", inline=True)
        embed.add_field(name="pytesseract", value=pytess_label, inline=True)

        if diag.install_tips:
            embed.add_field(
                name="Blocking fixes",
                value="\n".join(f"• {tip}" for tip in diag.install_tips),
                inline=False,
            )

        await self._safe_send(ctx, embed=embed, ephemeral=True)

    # --------------------
    # Intake listener
    # --------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if getattr(message, "interaction_metadata", None):
            return

        if message.type is not discord.MessageType.default:
            return

        # Ignore messages that are already being handled as bot commands to avoid
        # double-processing an uploaded screenshot (e.g., when invoking the hybrid
        # command with an attachment).
        ctx = await self.bot.get_context(message)
        if ctx.valid:
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

        cached_path = self._persist_profile_image(
            message.guild.id, message.author.id, image_bytes, attachment.filename
        )
        parsed, raw_text, ocr_note = await self._perform_ocr(
            image_bytes, filename=attachment.filename, persisted_path=cached_path
        )
        payload = self._build_payload(
            message.author, attachment.url, parsed, raw_text, cached_path
        )

        if payload.get("ownership_verified") is False:
            await message.reply(
                content=(
                    "🚫 Those aren't your buttons. Snap your own profile before trying to flex."
                ),
                mention_author=False,
            )
            return

        await upsert_profile_snapshot(message.guild.id, message.author.id, **payload)
        await self._post_confirmation(message, payload, ocr_note)

    async def _perform_ocr(
        self,
        image_bytes: bytes,
        *,
        filename: str | None = None,
        persisted_path: Path | None = None,
    ) -> tuple[dict, str, str | None]:
        parsed: dict[str, str | int | None] = {}
        raw_text = ""
        ocr_note: str | None = None

        async with self._scan_semaphore:
            temp_path = persisted_path or self._stash_temp_image(image_bytes, filename)

            try:
                easyocr_results = await self._run_easyocr(image_bytes, temp_path)
                if easyocr_results:
                    parsed.update(easyocr_results["parsed"])
                    raw_text = easyocr_results["raw"]
                    if not self._has_profile_metrics(parsed):
                        easyocr_full = await self._run_easyocr_full_text(
                            image_bytes, temp_path=temp_path
                        )
                        if easyocr_full:
                            raw_text = raw_text or easyocr_full
                            parsed.update(_parse_profile_text(easyocr_full))
                elif self._easyocr_ready is False and self._easyocr_failure_reason:
                    ocr_note = self._easyocr_failure_reason

                if not parsed:
                    pytesseract_text = await self._run_pytesseract(image_bytes)
                    raw_text = pytesseract_text or raw_text
                    if pytesseract_text:
                        parsed.update(_parse_profile_text(pytesseract_text))
                    elif ocr_note is None:
                        if self._pytesseract_missing:
                            ocr_note = "Pytesseract is installed but the Tesseract binary is missing."
                        elif not (pytesseract and Image):
                            ocr_note = (
                                "Profile scan dependencies are missing; install them from requirements.txt."
                            )
                        else:
                            ocr_note = "Profile scan could not read this image."

                if not parsed and OCR_SPACE_API_KEY:
                    api_text, api_note = await self._run_ocr_space(image_bytes, filename)
                    raw_text = raw_text or api_text
                    if api_text:
                        parsed.update(_parse_profile_text(api_text))
                    if ocr_note is None and api_note:
                        ocr_note = api_note
            finally:
                if temp_path and temp_path != persisted_path:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:  # pragma: no cover - best-effort cleanup
                        self.log.debug("Temp profile image cleanup failed for %s", temp_path)

        self.log.info(
            "Profile OCR summary | fields=%s | raw_lines=%s | note=%s",
            {k: v for k, v in parsed.items() if v is not None},
            self._raw_line_count(raw_text),
            ocr_note,
        )

        return parsed, raw_text, ocr_note

    async def _run_ocr_space(
        self, image_bytes: bytes, filename: str | None = None
    ) -> tuple[str, str | None]:
        """Fallback to the OCR.space API when local OCR dependencies are unavailable."""

        headers = {"apikey": OCR_SPACE_API_KEY}
        data = {"language": "eng", "isOverlayRequired": False}
        files = {"file": (filename or "profile.png", image_bytes, "application/octet-stream")}

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    OCR_SPACE_ENDPOINT, headers=headers, data=data, files=files
                )
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover - network edge
            self.log.warning("OCR.space request failed: %s", exc)
            return "", "External OCR request failed."

        try:
            payload = resp.json()
        except ValueError:
            self.log.warning("OCR.space returned non-JSON response")
            return "", "External OCR response was malformed."

        if payload.get("IsErroredOnProcessing"):
            msg = payload.get("ErrorMessage") or payload.get("ErrorMessageText")
            note = msg if isinstance(msg, str) else "External OCR service reported an error."
            return "", note

        results = payload.get("ParsedResults") or []
        text_blocks = [item.get("ParsedText", "") for item in results if item]
        combined = "\n".join(filter(None, text_blocks)).strip()

        if not combined:
            return "", "External OCR did not return any text."

        return combined, None

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
                    self._pytesseract_missing = True
                    self.log.warning("Tesseract binary missing; skipping pytesseract fallback")
                    return ""
                raise

        return await loop.run_in_executor(None, _scan)

    def _stash_temp_image(
        self, image_bytes: bytes, filename: str | None = None
    ) -> Path | None:
        """Persist an uploaded image for OCR routines that prefer file paths."""

        shots_dir = Path(__file__).resolve().parent.parent / "shots" / "temp"
        shots_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(filename).suffix if filename else ".png"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        temp_path = shots_dir / f"profile_{timestamp}{suffix}"

        try:
            temp_path.write_bytes(image_bytes)
        except Exception:
            self.log.exception("Failed to stash profile image to %s", temp_path)
            return None

        return temp_path

    def _persist_profile_image(
        self, guild_id: int, user_id: int, image_bytes: bytes, filename: str | None = None
    ) -> Path | None:
        """Save the raw upload so rescans avoid refetching from Discord CDN."""

        base = Path(__file__).resolve().parent.parent / "shots" / "profiles" / str(guild_id)
        base.mkdir(parents=True, exist_ok=True)

        suffix = Path(filename).suffix if filename else ".png"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        path = base / f"{user_id}_{timestamp}{suffix}"

        try:
            path.write_bytes(image_bytes)
        except Exception:
            self.log.exception("Failed to persist profile image to %s", path)
            return None

        # Keep a short history per user to avoid filling disk.
        user_stash = sorted(base.glob(f"{user_id}_*"))
        for old in user_stash[:-5]:
            try:
                old.unlink(missing_ok=True)
            except Exception:  # pragma: no cover - best-effort cleanup
                self.log.debug("Could not trim cached profile image %s", old)

        return path

    async def _ensure_easyocr(self) -> bool:
        if self._easyocr_ready is not None:
            return self._easyocr_ready

        if not (easyocr and cv2 and np):
            self._easyocr_ready = False
            self._easyocr_failure_reason = (
                "EasyOCR unavailable. Install OCR extras with `pip install -r requirements.txt`."
            )
            self.log.warning(self._easyocr_failure_reason)
            return False

        async with self._easyocr_lock:
            if self._easyocr_ready is not None:
                return self._easyocr_ready

            if not BOXES_PATH.exists():
                self._easyocr_ready = False
                self._easyocr_failure_reason = f"OCR bounding boxes not found at {BOXES_PATH}."
                self.log.warning(self._easyocr_failure_reason)
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
            self._easyocr_failure_reason = None if self._easyocr_ready else "OCR templates are empty."
            if not self._easyocr_ready:
                self.log.warning(self._easyocr_failure_reason)
            return self._easyocr_ready

    async def _run_easyocr(self, image_bytes: bytes, temp_path: Path | None = None):
        ready = await self._ensure_easyocr()
        if not ready or not self._easyocr_reader or not self._easyocr_boxes:
            return None

        loop = asyncio.get_running_loop()

        def _scan():
            if temp_path and temp_path.exists():
                img = cv2.imread(str(temp_path))
            else:
                arr = np.frombuffer(image_bytes, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None

            results: dict[str, str | int | None] = {}
            raw_lines: list[str] = []

            verification_hits: set[str] = set()

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

                if field in VERIFY_FIELDS:
                    if best_conf >= VERIFY_MIN_CONF:
                        verification_hits.add(field)
                    continue

                if best_conf < EASYOCR_MIN_CONF:
                    continue

                mapped = EASYOCR_FIELDS.get(field)
                if not mapped:
                    continue

                if mapped in {"cp", "kills", "likes", "vip_level"}:
                    cleaned = re.sub(r"[^\d]", "", best_text)
                    if cleaned:
                        results[mapped] = int(cleaned)
                elif mapped == "server":
                    results[mapped] = best_text
                else:
                    results[mapped] = best_text

            if verification_hits:
                results["ownership_verified"] = len(verification_hits) == len(VERIFY_FIELDS)
            else:
                results["ownership_verified"] = None

            raw = "\n".join(raw_lines)
            return {"parsed": results, "raw": raw}

        return await loop.run_in_executor(None, _scan)

    async def _run_easyocr_full_text(
        self, image_bytes: bytes, temp_path: Path | None = None
    ) -> str:
        ready = await self._ensure_easyocr()
        if not ready or not self._easyocr_reader:
            return ""

        loop = asyncio.get_running_loop()

        def _scan() -> str:
            if temp_path and temp_path.exists():
                img = cv2.imread(str(temp_path))
            else:
                arr = np.frombuffer(image_bytes, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return ""

            detections = self._easyocr_reader.readtext(img)
            if not detections:
                return ""
            return "\n".join(item[1].strip() for item in detections if item[1].strip())

        return await loop.run_in_executor(None, _scan)

    @staticmethod
    def _has_profile_metrics(parsed: dict[str, str | int | None]) -> bool:
        return any(
            parsed.get(field)
            for field in ("player_name", "cp", "kills", "likes", "vip_level", "alliance", "server")
        )

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
        cached_path: Path | None = None,
    ) -> dict:
        ownership_verified = parsed.get("ownership_verified")

        return {
            "player_name": parsed.get("player_name") or member.display_name,
            "alliance": parsed.get("alliance"),
            "server": parsed.get("server"),
            "cp": parsed.get("cp"),
            "kills": parsed.get("kills"),
            "likes": parsed.get("likes"),
            "vip_level": parsed.get("vip_level"),
            "level": parsed.get("level"),
            "ownership_verified": bool(ownership_verified) if ownership_verified is not None else None,
            "avatar_url": str(member.display_avatar.url),
            "last_image_url": image_url,
            "local_image_path": str(cached_path) if cached_path else None,
            "raw_ocr": raw_text,
        }

    def _is_image_attachment(self, attachment: discord.Attachment) -> bool:
        allowed = {"png", "jpeg", "jpg", "webp"}

        if attachment.content_type:
            content_type = attachment.content_type.lower()
            if any(content_type.endswith(ext) for ext in allowed):
                return True

        suffix = Path(attachment.filename).suffix.lower().lstrip(".") if attachment.filename else ""
        return suffix in allowed

    async def _post_confirmation(
        self,
        message: discord.Message,
        payload: dict,
        ocr_note: str | None,
    ) -> None:
        embed = self._build_confirmation_embed(payload, ocr_note)

        try:
            await message.reply(embed=embed, mention_author=False)
        except Exception:  # pragma: no cover - Discord edge
            self.log.exception("Failed to reply with profile confirmation")

    def _build_confirmation_embed(
        self, payload: dict, ocr_note: str | None = None
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🛰️ Profile logged",
            description=(
                f"{random.choice(PROFILE_TAGLINES)}\n\n"
                "`/profile_stats` shows your dossier; `/leaderboard` compares XP and scan stats side by side."
            ),
            color=0x3498db,
        )

        ingame = [
            f"🎖️ VIP: {_format_metric(payload.get('vip_level'))} | 👍 Likes: {_format_metric(payload.get('likes'))}",
            f"⚔️ CP: {_format_metric(payload.get('cp'))} | ☠️ Kills: {_format_metric(payload.get('kills'))}",
            f"🏰 Alliance: {payload.get('alliance') or '—'}",
            f"🌐 Server: {payload.get('server') or '—'}",
        ]
        if payload.get("ownership_verified") is not None:
            status = "✅ Self-view detected" if payload["ownership_verified"] else "⚠️ Could not confirm this is your own profile"
            ingame.append(status)

        embed.add_field(name="In-game Profile", value="\n".join(ingame), inline=False)
        embed.add_field(name="Vault Seal", value=random.choice(PROFILE_SEALS), inline=False)

        if not payload.get("raw_ocr"):
            footer = ocr_note or (
                "Profile scan unavailable. Install Tesseract + pytesseract or easyocr + opencv for"
                " auto-parsing."
            )
            embed.set_footer(text=footer)
        return embed

    @staticmethod
    def _append_unique(notes: list[str], text: str) -> None:
        if text and text not in notes:
            notes.append(text)

    @staticmethod
    def _raw_line_count(raw_text: str) -> int:
        """Count OCR output lines while tolerating empty payloads."""
        return raw_text.count("\n") + (1 if raw_text else 0)


class ProfileReviewSelect(discord.ui.Select):
    def __init__(self, review_view: "ProfileReviewView"):
        self.review_view = review_view
        super().__init__(
            placeholder="Select a scanned profile...",
            options=review_view.build_options(),
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.review_view.authorize(interaction):
            return
        self.review_view.selected_user_id = int(self.values[0])
        await interaction.response.edit_message(
            embed=self.review_view.build_embed(), view=self.review_view
        )


class ProfileReviewView(discord.ui.View):
    def __init__(self, cog: ProfileScanner, guild_id: int, snapshots: list[dict]):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.snapshots = {row["user_id"]: row for row in snapshots}
        self.selected_user_id = next(iter(self.snapshots), None)
        self.message: discord.Message | None = None
        self.select = ProfileReviewSelect(self)
        self.add_item(self.select)

    def bind_message(self, message: discord.Message) -> None:
        self.message = message

    async def authorize(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        perms = interaction.user.guild_permissions
        if not perms.manage_guild:
            await interaction.response.send_message(
                "🔒 Manage Server permission required.", ephemeral=True
            )
            return False
        return True

    def build_options(self) -> list[discord.SelectOption]:
        options: list[discord.SelectOption] = []
        guild = self.cog.bot.get_guild(self.guild_id)
        for user_id, row in list(self.snapshots.items())[:25]:
            member = guild.get_member(user_id) if guild else None
            name = row.get("player_name") or (member.display_name if member else f"User {user_id}")
            status = "✅" if row.get("scan_valid", 1) else "⚠️"
            details = f"{status} CP {row.get('cp') or '—'} • Kills {row.get('kills') or '—'}"
            options.append(
                discord.SelectOption(
                    label=name[:100],
                    description=details[:100],
                    value=str(user_id),
                )
            )
        if not options:
            options.append(
                discord.SelectOption(label="No scans available", value="0", default=True)
            )
        return options

    def _selected_snapshot(self) -> dict | None:
        if self.selected_user_id is None:
            return None
        return self.snapshots.get(self.selected_user_id)

    def build_embed(self) -> discord.Embed:
        snapshot = self._selected_snapshot()
        if not snapshot:
            return discord.Embed(
                title="🛰️ Profile Review",
                description="No scans available.",
                color=0xe67e22,
            )

        guild = self.cog.bot.get_guild(self.guild_id)
        member = guild.get_member(snapshot["user_id"]) if guild else None
        name = snapshot.get("player_name") or (member.display_name if member else f"User {snapshot['user_id']}")
        status = "✅ Active" if snapshot.get("scan_valid", 1) else "⚠️ Invalidated"
        embed = discord.Embed(
            title=f"🛰️ Profile Review | {name}",
            description=f"Scan status: **{status}**",
            color=0x3498db if snapshot.get("scan_valid", 1) else 0xe74c3c,
        )
        embed.add_field(name="🏰 Alliance", value=snapshot.get("alliance") or "—", inline=True)
        embed.add_field(name="🌐 Server", value=snapshot.get("server") or "—", inline=True)
        embed.add_field(
            name="🎖️ VIP / Likes",
            value=f"{_format_metric(snapshot.get('vip_level'))} / {_format_metric(snapshot.get('likes'))}",
            inline=True,
        )
        embed.add_field(
            name="⚔️ CP / ☠️ Kills",
            value=f"{_format_metric(snapshot.get('cp'))} / {_format_metric(snapshot.get('kills'))}",
            inline=True,
        )
        if snapshot.get("ownership_verified") is not None:
            status_line = (
                "✅ Self-view detected" if snapshot["ownership_verified"] else "⚠️ Ownership unverified"
            )
            embed.add_field(name="Ownership", value=status_line, inline=False)
        if snapshot.get("last_image_url"):
            embed.add_field(name="Latest scan", value=f"[View image]({snapshot['last_image_url']})", inline=False)
        if snapshot.get("last_updated"):
            dt = datetime.fromtimestamp(snapshot["last_updated"], tz=timezone.utc)
            embed.set_footer(text=f"Last scanned {dt.strftime('%Y-%m-%d %H:%M UTC')}")
        return embed

    def _refresh_options(self) -> None:
        self.select.options = self.build_options()
        if self.selected_user_id not in self.snapshots:
            self.selected_user_id = next(iter(self.snapshots), None)

    @discord.ui.button(label="Invalidate", style=discord.ButtonStyle.danger)
    async def invalidate_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.authorize(interaction):
            return
        snapshot = self._selected_snapshot()
        if not snapshot:
            return await interaction.response.send_message(
                "No scan selected.", ephemeral=True
            )
        await set_profile_scan_valid(self.guild_id, snapshot["user_id"], False)
        snapshot["scan_valid"] = 0
        self._refresh_options()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Restore", style=discord.ButtonStyle.success)
    async def restore_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.authorize(interaction):
            return
        snapshot = self._selected_snapshot()
        if not snapshot:
            return await interaction.response.send_message(
                "No scan selected.", ephemeral=True
            )
        await set_profile_scan_valid(self.guild_id, snapshot["user_id"], True)
        snapshot["scan_valid"] = 1
        self._refresh_options()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.secondary)
    async def delete_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.authorize(interaction):
            return
        snapshot = self._selected_snapshot()
        if not snapshot:
            return await interaction.response.send_message(
                "No scan selected.", ephemeral=True
            )
        await delete_profile_snapshot(self.guild_id, snapshot["user_id"])
        self.snapshots.pop(snapshot["user_id"], None)
        self._refresh_options()
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)


async def setup(bot):
    await bot.add_cog(ProfileScanner(bot))
