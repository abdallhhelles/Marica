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
import random
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

import discord
from discord.errors import HTTPException
from discord.ext import commands
from utils.http_client import CircuitBreakerOpen

from database import (
    get_profile_snapshots,
    delete_profile_snapshot,
    set_profile_scan_valid,
    upsert_profile_snapshot,
    add_duel_score,
)
from utils.assets import PROFILE_SEALS, PROFILE_TAGLINES
from utils.async_utils import create_tracked_task
from utils.time_utils import now_game

_PIL_SPEC = importlib.util.find_spec("PIL")
_PYTESSERACT_SPEC = importlib.util.find_spec("pytesseract")
_CV2_SPEC = importlib.util.find_spec("cv2")
_EASYOCR_SPEC = importlib.util.find_spec("easyocr")

if _PIL_SPEC:
    from PIL import Image, ImageFilter, ImageOps
else:  # pragma: no cover - optional dependency guard
    Image = None

if _PYTESSERACT_SPEC:
    import pytesseract
else:  # pragma: no cover - optional dependency guard
    pytesseract = None

if _CV2_SPEC:
    import cv2
    import numpy as np
else:  # pragma: no cover - optional dependency guard
    cv2 = None
    np = None

if _EASYOCR_SPEC:
    import easyocr
else:  # pragma: no cover - optional dependency guard
    easyocr = None


NUMBER_RE = re.compile(r"(?P<value>[\d.,\s]+)\s*(?P<suffix>[kmbKMB]?)")
LABEL_HINTS = {
    "cp": ("cp", "power", "battle power", "total power", "combat power"),
    "kills": ("kills", "defeats", "defeated", "eliminations", "total kills"),
    "likes": ("likes", "like", "likes received"),
    "vip_level": ("vip", "vip level", "vip lvl", "vip lv"),
    "alliance": ("alliance", "all", "guild"),
    "server": ("server", "state", "world"),
}
DUEL_WEEK_ROI = (0.362887, 0.211429, 0.278351, 0.049524)
OWNER_NAME_ROI = (0.331959, 0.737143, 0.25567, 0.035238)
OWNER_SCORE_ROI = (0.690722, 0.740952, 0.197938, 0.058095)

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
OCR_SPACE_ENDPOINT = "https://api.ocr.space/parse/image"


@dataclass(slots=True)
class PendingScan:
    scan_type: str
    guild_id: int
    requested_at: datetime


@dataclass(slots=True)
class ScanJob:
    scan_type: str
    guild_id: int
    user: discord.User | discord.Member
    message: discord.Message
    attachment: discord.Attachment
    image_bytes: bytes
    filename: str | None


def _extract_number(chunk: str) -> int | None:
    match = NUMBER_RE.search(chunk)
    if not match:
        return None

    raw = match.group("value").replace(",", "").replace(" ", "")
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


def _normalize_server_value(value: str) -> str:
    match = re.search(r"\d+", value)
    if match:
        return match.group(0)
    return value.strip()


def _clean_label(value: str, *labels: str) -> str:
    cleaned = value
    for label in labels:
        cleaned = re.sub(rf"(?i){re.escape(label)}", "", cleaned)
    cleaned = cleaned.replace(":", "")
    return cleaned.strip()


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
                if field == "alliance":
                    value = line.split(":", 1)[-1] if ":" in line else line
                    results[field] = _clean_label(value, "alliance", "guild")
                elif field == "server":
                    value = line.split(":", 1)[-1] if ":" in line else line
                    results[field] = _normalize_server_value(value)
                else:
                    results[field] = _extract_number(line)
    return results


def _format_metric(value: int | None) -> str:
    return f"{value:,}" if isinstance(value, int) else "-"


def _crop_norm(image, roi: tuple[float, float, float, float]):
    height, width = image.shape[:2]
    x_norm, y_norm, width_norm, height_norm = roi
    x = int(x_norm * width)
    y = int(y_norm * height)
    crop_width = max(1, int(width_norm * width))
    crop_height = max(1, int(height_norm * height))
    return image[y : y + crop_height, x : x + crop_width]


def _prep_duel_image(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return gray


def _ocr_duel_text(image, *, psm: int = 7, whitelist: str | None = None) -> str:
    config = f"--psm {psm}"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"
    try:
        return pytesseract.image_to_string(image, config=config).strip()
    except Exception as exc:  # pragma: no cover - dependency edge
        if hasattr(pytesseract, "TesseractNotFoundError") and isinstance(
            exc, pytesseract.TesseractNotFoundError
        ):
            return ""
        raise


def _is_duel_week(image) -> bool:
    text = _ocr_duel_text(_prep_duel_image(_crop_norm(image, DUEL_WEEK_ROI)), psm=7).lower()
    compact = re.sub(r"[^a-z]", "", text)
    return "duelweek" in compact


def _normalize_duel_score_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text.upper()
    cleaned = cleaned.translate(str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1", "S": "5"}))
    return cleaned.replace(" ", "")


def _format_duel_score_text(score_int: int, suffix: str | None, raw_number: str) -> str:
    if suffix:
        return f"{raw_number}{suffix}"
    return f"{score_int:,}"


def _parse_duel_score(text: str) -> tuple[str | None, int | None]:
    cleaned = _normalize_duel_score_text(text)
    if not cleaned:
        return None, None

    candidates: list[dict[str, int | str | bool]] = []
    for match in re.finditer(r"(\d[\d,\.]*)([KMB]?)", cleaned):
        number = match.group(1)
        suffix = match.group(2)
        raw = number.replace(",", "")
        if raw.count(".") > 1:
            parts = raw.split(".")
            raw = parts[0] + "." + "".join(parts[1:])
        try:
            value = float(raw)
        except ValueError:
            continue
        multiplier = 1
        if suffix == "K":
            multiplier = 1_000
        elif suffix == "M":
            multiplier = 1_000_000
        elif suffix == "B":
            multiplier = 1_000_000_000
        score_int = int(value * multiplier)
        if score_int <= 0:
            continue
        candidates.append(
            {
                "score_int": score_int,
                "score_text": _format_duel_score_text(score_int, suffix or None, raw),
                "has_suffix": bool(suffix),
                "digits": len(re.sub(r"\\D", "", raw)),
            }
        )

    if not candidates:
        return None, None

    best = max(
        candidates,
        key=lambda item: (
            bool(item["has_suffix"]),
            int(item["score_int"]),
            int(item["digits"]),
        ),
    )
    return str(best["score_text"]), int(best["score_int"])


def _duel_week_key(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


class ProfileScanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger("MarciaOS.ProfileScanner")
        self.ocr_space_api_key = bot.config.ocr_space_api_key
        self.ocr_space_timeout = bot.config.ocr_space_timeout
        self.scan_review_timeout = bot.config.profile_scan_review_timeout
        self.scan_worker_count = bot.config.profile_scan_workers
        self._easyocr_reader: easyocr.Reader | None = None
        self._easyocr_boxes: dict[str, list[float]] | None = None
        self._easyocr_ready: bool | None = None
        self._easyocr_failure_reason: str | None = None
        self._easyocr_lock = asyncio.Lock()
        self._pytesseract_missing = False
        self._pending_scans: dict[int, PendingScan] = {}
        self._scan_queue: asyncio.Queue[ScanJob] = asyncio.Queue()
        self._scan_workers: list[asyncio.Task] = []
        self._scan_menu_cooldowns: dict[int, float] = {}
        self._scan_semaphore = asyncio.Semaphore(bot.config.profile_scan_concurrency)

    async def cog_load(self):
        for idx in range(max(1, self.scan_worker_count)):
            task = create_tracked_task(
                self._scan_worker(idx),
                name=f"profile-scan-worker-{idx}",
                logger=self.log,
            )
            self._scan_workers.append(task)

    async def cog_unload(self):
        for task in self._scan_workers:
            task.cancel()
        if self._scan_workers:
            await asyncio.gather(*self._scan_workers, return_exceptions=True)
        self._scan_workers.clear()

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
        name="scan",
        description="Open the scan menu.",
    )
    async def scan(self, ctx):
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Run `/gyper scan` inside a server so I can link the scan to your guild.",
                ephemeral=True,
            )

        try:
            dm_channel = await ctx.author.create_dm()
        except Exception:  # pragma: no cover - Discord edge
            return await self._safe_send(
                ctx,
                content="I couldn't open your DMs. Enable DMs and try `/gyper scan` again.",
                ephemeral=True,
            )

        now = time.monotonic()
        last_sent = self._scan_menu_cooldowns.get(ctx.author.id)
        if last_sent and (now - last_sent) < 5:
            return await self._safe_send(
                ctx,
                content="📨 Scan menu already sent. Check your DMs to finish the scan.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title="🛰️ Scan menu",
            description="Pick a scan type and send your screenshot here.",
            color=0x3498DB,
        )
        embed.add_field(
            name="Profile scan",
            value="Capture stats from a profile screenshot.",
            inline=False,
        )
        embed.add_field(
            name="Duel score scan",
            value="Capture Duel Week off-day scores.",
            inline=False,
        )
        view = ScanMenuView(self, ctx.author.id, ctx.guild.id)
        await dm_channel.send(embed=embed, view=view)
        self._scan_menu_cooldowns[ctx.author.id] = now
        return await self._safe_send(
            ctx,
            content="📨 Check your DMs to finish the scan.",
            ephemeral=True,
        )

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

    # --------------------
    # Intake listener
    # --------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.guild:
            return

        if message.type is not discord.MessageType.default:
            return

        pending = self._pending_scans.get(message.author.id)
        if not pending:
            return

        attachment = next(
            (a for a in message.attachments if self._is_image_attachment(a)),
            None,
        )
        if not attachment:
            await message.reply(
                "Send a PNG, JPEG, or WEBP screenshot to continue the scan."
            )
            return

        if pending.scan_type == "duel" and not (cv2 and pytesseract and np):
            await message.reply(
                "Duel score scan unavailable. Install Tesseract + pytesseract and OpenCV to enable OCR."
            )
            self._pending_scans.pop(message.author.id, None)
            return

        try:
            image_bytes = await attachment.read()
        except Exception as exc:  # pragma: no cover - network edge
            self.log.warning("Could not read attachment: %s", exc)
            await message.reply("I couldn't read that image.")
            return

        if pending.scan_type == "profile" and cv2 and pytesseract and np:
            try:
                arr = np.frombuffer(image_bytes, dtype=np.uint8)
                image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if image is not None and _is_duel_week(image):
                    await message.reply(
                        "That looks like a Duel Week off-day screenshot. Pick Duel score scan and resend."
                    )
                    return
            except Exception:  # pragma: no cover - best-effort hint
                pass

        job = ScanJob(
            scan_type=pending.scan_type,
            guild_id=pending.guild_id,
            user=message.author,
            message=message,
            attachment=attachment,
            image_bytes=image_bytes,
            filename=attachment.filename,
        )
        await self._scan_queue.put(job)
        position = self._scan_queue.qsize()
        queue_note = f"Global queue position: {position}."
        await message.reply(
            f"📡 Scan queued for **{pending.scan_type}**. {queue_note} I'll DM results when ready."
        )
        self._pending_scans.pop(message.author.id, None)

    async def _scan_worker(self, worker_id: int) -> None:
        while True:
            job = await self._scan_queue.get()
            try:
                await self._process_scan_job(job)
            except Exception:
                self.log.exception("Profile scan worker %s failed", worker_id)
            finally:
                self._scan_queue.task_done()

    async def _process_scan_job(self, job: ScanJob) -> None:
        guild = self.bot.get_guild(job.guild_id)
        member = guild.get_member(job.user.id) if guild else None
        user = member or job.user

        if job.scan_type == "profile":
            image_url = job.attachment.url
            cached_path = await self._persist_profile_image(
                job.guild_id,
                user.id,
                job.image_bytes,
                job.filename,
            )
            parsed, raw_text, ocr_note = await self._perform_ocr(
                job.image_bytes, filename=job.filename, persisted_path=cached_path
            )
            payload = self._build_payload(
                user, image_url, parsed, raw_text, cached_path
            )

            if payload.get("ownership_verified") is False:
                await job.message.reply(
                    "🚫 Those aren't your buttons. Snap your own profile before trying to flex."
                )
                return

            view = ProfileScanReviewView(
                self,
                job.guild_id,
                user.id,
                payload,
                ocr_note,
                timeout=self.scan_review_timeout,
            )
            embed = self._build_review_embed(payload, ocr_note)
            try:
                message = await job.message.reply(embed=embed, view=view, mention_author=False)
            except Exception:  # pragma: no cover - Discord edge
                self.log.exception("Failed to reply with profile review")
                return
            if isinstance(message, discord.Message):
                view.bind_message(message)
            return

        if job.scan_type == "duel":
            loop = asyncio.get_running_loop()
            use_easyocr = await self._ensure_easyocr()
            result = await loop.run_in_executor(
                None,
                self._duel_score_extract,
                job.image_bytes,
                use_easyocr,
            )
            if not result["valid"]:
                error = result.get("error", "unknown")
                if error == "not_duel_week":
                    message = "That screenshot doesn't look like the Duel Week off-day screen."
                elif error == "ocr_missing":
                    message = (
                        "Duel score scan unavailable. Install Tesseract + pytesseract and OpenCV to enable OCR."
                    )
                elif error == "tesseract_missing":
                    message = (
                        "Duel score scan unavailable. Install the Tesseract binary to enable OCR."
                    )
                else:
                    message = "I couldn't read that duel score screenshot."
                await job.message.reply(message)
                return

            week_key = _duel_week_key(now_game())
            payload = {
                "player_name": result.get("player_name") or user.display_name,
                "score_text": result.get("score_text"),
                "score_int": result.get("score_int"),
                "raw_score_ocr": result.get("raw_score_ocr"),
                "week_key": week_key,
                "duel_week_confirmed": result.get("duel_week_confirmed", False),
            }
            embed = self._build_duel_review_embed(payload)
            view = DuelScanReviewView(
                self,
                job.guild_id,
                user.id,
                payload,
                timeout=self.scan_review_timeout,
            )
            try:
                message = await job.message.reply(embed=embed, view=view, mention_author=False)
            except Exception:  # pragma: no cover - Discord edge
                self.log.exception("Failed to reply with duel scan review")
                return
            if isinstance(message, discord.Message):
                view.bind_message(message)

    def _duel_score_extract(self, image_bytes: bytes, use_easyocr: bool = False) -> dict:
        if not (cv2 and np):
            return {"valid": False, "error": "ocr_missing"}
        if not use_easyocr and not pytesseract:
            return {"valid": False, "error": "ocr_missing"}

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            return {"valid": False, "error": "image_load_failed"}

        duel_week_confirmed = False
        duel_week_text = ""
        try:
            duel_week_text = self._duel_read_text(
                image, DUEL_WEEK_ROI, use_easyocr=use_easyocr
            )
            compact = re.sub(r"[^a-z]", "", duel_week_text.lower())
            duel_week_confirmed = "duelweek" in compact
        except Exception as exc:  # pragma: no cover - dependency edge
            if pytesseract and hasattr(pytesseract, "TesseractNotFoundError") and isinstance(
                exc, pytesseract.TesseractNotFoundError
            ):
                return {"valid": False, "error": "tesseract_missing"}
            raise

        name = self._duel_read_text(image, OWNER_NAME_ROI, use_easyocr=use_easyocr)
        name = re.sub(r"\s+", " ", name).strip()

        raw_score = self._duel_read_text(
            image,
            OWNER_SCORE_ROI,
            whitelist="0123456789.MK",
            use_easyocr=use_easyocr,
        )
        score_text, score_int = _parse_duel_score(raw_score)

        if not score_text and score_int is None:
            if not duel_week_confirmed:
                return {"valid": False, "error": "not_duel_week"}
            return {"valid": False, "error": "score_missing"}

        return {
            "valid": True,
            "player_name": name or None,
            "score_text": score_text,
            "score_int": score_int,
            "raw_score_ocr": raw_score,
            "duel_week_confirmed": duel_week_confirmed,
        }

    def _duel_read_text(
        self,
        image,
        roi: tuple[float, float, float, float],
        *,
        whitelist: str | None = None,
        use_easyocr: bool = False,
    ) -> str:
        crop = _crop_norm(image, roi)
        if use_easyocr and self._easyocr_reader:
            proc = self._preprocess_crop(crop)
            detections = self._easyocr_reader.readtext(proc)
            if detections:
                detections.sort(key=lambda item: item[2], reverse=True)
                return detections[0][1].strip()
        processed = _prep_duel_image(crop)
        candidates = []
        for psm in (7, 6):
            text = _ocr_duel_text(processed, psm=psm, whitelist=whitelist)
            if text:
                candidates.append(text.strip())
        if not candidates:
            return ""
        return max(candidates, key=lambda value: sum(ch.isdigit() for ch in value))

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
            temp_path = persisted_path or await self._stash_temp_image(image_bytes, filename)

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

                if not parsed and self.ocr_space_api_key:
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

        headers = {"apikey": self.ocr_space_api_key}
        data = {"language": "eng", "isOverlayRequired": False}
        files = {"file": (filename or "profile.png", image_bytes, "application/octet-stream")}

        try:
            resp = await self.bot.http.request(
                "ocr_space",
                "POST",
                OCR_SPACE_ENDPOINT,
                headers=headers,
                data=data,
                files=files,
                retries=0,
                safe=False,
                timeout=self.ocr_space_timeout,
            )
            resp.raise_for_status()
        except CircuitBreakerOpen as exc:  # pragma: no cover - network edge
            self.log.warning("OCR.space circuit breaker open: %s", exc)
            return "", "External OCR is temporarily unavailable."
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
                    img = img.convert("L")
                    img = ImageOps.autocontrast(img)
                    img = img.resize(
                        (int(img.width * 2), int(img.height * 2)),
                        resample=Image.BICUBIC,
                    )
                    img = img.filter(ImageFilter.MedianFilter())
                    return pytesseract.image_to_string(
                        img, config="--oem 3 --psm 6"
                    )
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

    async def _stash_temp_image(
        self, image_bytes: bytes, filename: str | None = None
    ) -> Path | None:
        """Persist an uploaded image for OCR routines that prefer file paths."""

        shots_dir = Path(__file__).resolve().parent.parent / "shots" / "temp"
        shots_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(filename).suffix if filename else ".png"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        temp_path = shots_dir / f"profile_{timestamp}{suffix}"

        try:
            await asyncio.to_thread(temp_path.write_bytes, image_bytes)
        except Exception:
            self.log.exception("Failed to stash profile image to %s", temp_path)
            return None

        return temp_path

    async def _persist_profile_image(
        self, guild_id: int, user_id: int, image_bytes: bytes, filename: str | None = None
    ) -> Path | None:
        """Save the raw upload so rescans avoid refetching from Discord CDN."""

        base = Path(__file__).resolve().parent.parent / "shots" / "profiles" / str(guild_id)
        base.mkdir(parents=True, exist_ok=True)

        suffix = Path(filename).suffix if filename else ".png"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        path = base / f"{user_id}_{timestamp}{suffix}"

        try:
            await asyncio.to_thread(path.write_bytes, image_bytes)
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
                    value = _extract_number(best_text)
                    if value is not None:
                        results[mapped] = value
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
        gray = cv2.bilateralFilter(gray, 7, 75, 75)
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return gray

    def _build_payload(
        self,
        member: discord.User | discord.Member,
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

    def _build_review_embed(
        self, payload: dict, ocr_note: str | None = None
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🛰️ Profile scan review",
            description=(
                "Confirm the scan or request a rescan. If you don't respond, "
                "Marcia will auto-accept this scan."
            ),
            color=0xf1c40f,
        )
        ingame = [
            f"🎖️ VIP: {_format_metric(payload.get('vip_level'))} | 👍 Likes: {_format_metric(payload.get('likes'))}",
            f"⚔️ CP: {_format_metric(payload.get('cp'))} | ☠️ Kills: {_format_metric(payload.get('kills'))}",
            f"🏰 Alliance: {payload.get('alliance') or '-'}",
            f"🌐 Server: {payload.get('server') or '-'}",
        ]
        if payload.get("ownership_verified") is not None:
            status = "✅ Self-view detected" if payload["ownership_verified"] else "⚠️ Ownership unverified"
            ingame.append(status)
        embed.add_field(name="Captured Stats", value="\n".join(ingame), inline=False)
        if not payload.get("raw_ocr"):
            footer = ocr_note or (
                "Profile scan unavailable. Install Tesseract + pytesseract or easyocr + opencv for"
                " auto-parsing."
            )
            embed.set_footer(text=footer)
        return embed

    def _build_confirmation_embed(
        self, payload: dict, ocr_note: str | None = None
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🛰️ Profile logged",
            description=(
                f"{random.choice(PROFILE_TAGLINES)}\n\n"
                "`/gyper profile` shows your dossier; `/gyper leaderboard` compares XP and scan stats side by side."
            ),
            color=0x3498db,
        )

        ingame = [
            f"🎖️ VIP: {_format_metric(payload.get('vip_level'))} | 👍 Likes: {_format_metric(payload.get('likes'))}",
            f"⚔️ CP: {_format_metric(payload.get('cp'))} | ☠️ Kills: {_format_metric(payload.get('kills'))}",
            f"🏰 Alliance: {payload.get('alliance') or '-'}",
            f"🌐 Server: {payload.get('server') or '-'}",
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

    def _build_duel_review_embed(self, payload: dict) -> discord.Embed:
        embed = discord.Embed(
            title="⚔️ Duel score scan",
            description="Review the result and accept, decline, or rescan.",
            color=0xE67E22,
        )
        embed.add_field(name="Player", value=payload.get("player_name") or "Unknown", inline=False)
        score_text = payload.get("score_text") or "-"
        score_int = payload.get("score_int")
        score_value = f"{score_text}"
        if score_int is not None:
            score_value = f"{score_text} ({score_int:,})"
        embed.add_field(name="Score", value=score_value, inline=False)
        embed.add_field(name="Week", value=payload.get("week_key") or "-", inline=False)
        if not payload.get("duel_week_confirmed", True):
            embed.add_field(
                name="Header check",
                value="⚠️ Duel Week header not confirmed. Make sure this is the off-day screen.",
                inline=False,
            )
        if payload.get("raw_score_ocr"):
            embed.set_footer(text=f"OCR raw: {payload['raw_score_ocr']}")
        return embed

    def _build_duel_confirmation_embed(self, payload: dict) -> discord.Embed:
        embed = discord.Embed(
            title="⚔️ Duel score logged",
            description="Score saved. Use `/gyper leaderboard` to compare duel results.",
            color=0xE67E22,
        )
        embed.add_field(name="Player", value=payload.get("player_name") or "Unknown", inline=False)
        score_text = payload.get("score_text") or "-"
        score_int = payload.get("score_int")
        score_value = f"{score_text}"
        if score_int is not None:
            score_value = f"{score_text} ({score_int:,})"
        embed.add_field(name="Score", value=score_value, inline=False)
        embed.add_field(name="Week", value=payload.get("week_key") or "-", inline=False)
        if payload.get("raw_score_ocr"):
            embed.set_footer(text=f"OCR raw: {payload['raw_score_ocr']}")
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


class ScanMenuView(discord.ui.View):
    def __init__(self, cog: ProfileScanner, author_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True

        await interaction.response.send_message(
            "This scan menu belongs to someone else.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Profile scan", style=discord.ButtonStyle.primary, emoji="🛰️")
    async def profile_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog._pending_scans[interaction.user.id] = PendingScan(
            scan_type="profile",
            guild_id=self.guild_id,
            requested_at=datetime.now(timezone.utc),
        )
        await interaction.response.send_message(
            "🛰️ Profile scan selected. Upload your profile screenshot here to continue.",
        )

    @discord.ui.button(label="Duel score scan", style=discord.ButtonStyle.secondary, emoji="⚔️")
    async def duel_score_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog._pending_scans[interaction.user.id] = PendingScan(
            scan_type="duel",
            guild_id=self.guild_id,
            requested_at=datetime.now(timezone.utc),
        )
        await interaction.response.send_message(
            "⚔️ Duel score scan selected. Upload the Duel Week off-day screenshot here to continue.",
        )


class ProfileScanReviewView(discord.ui.View):
    def __init__(
        self,
        cog: ProfileScanner,
        guild_id: int,
        user_id: int,
        payload: dict,
        ocr_note: str | None,
        *,
        timeout: int,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.payload = payload
        self.ocr_note = ocr_note
        self.message: discord.Message | None = None
        self._finalized = False

    def bind_message(self, message: discord.Message) -> None:
        self.message = message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "🔒 Only the uploader can approve or rescan this profile.",
            ephemeral=True,
        )
        return False

    async def _finalize(self, *, interaction: discord.Interaction | None = None, auto: bool = False) -> None:
        if self._finalized:
            return
        self._finalized = True
        await upsert_profile_snapshot(self.guild_id, self.user_id, **self.payload)

        embed = self.cog._build_confirmation_embed(self.payload, self.ocr_note)
        content = "✅ Scan confirmed and saved." if not auto else "⏱️ Auto-confirmed after timeout."

        try:
            if interaction:
                await interaction.response.edit_message(content=content, embed=embed, view=None)
            elif self.message:
                await self.message.edit(content=content, embed=embed, view=None)
        except Exception:  # pragma: no cover - Discord edge
            self.cog.log.exception("Failed to finalize profile scan review")

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finalize(interaction=interaction, auto=False)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def decline_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finalized:
            return
        self._finalized = True
        embed = discord.Embed(
            title="🗑️ Scan declined",
            description="Result discarded. Send a fresh screenshot if you want to try again.",
            color=0xe74c3c,
        )
        try:
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception:  # pragma: no cover - Discord edge
            self.cog.log.exception("Failed to decline profile scan")

    @discord.ui.button(label="Rescan", style=discord.ButtonStyle.secondary, emoji="🔁")
    async def rescan_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finalized:
            return
        self._finalized = True
        self.cog._pending_scans[self.user_id] = PendingScan(
            scan_type="profile",
            guild_id=self.guild_id,
            requested_at=datetime.now(timezone.utc),
        )
        embed = discord.Embed(
            title="🔁 Rescan requested",
            description=(
                "Upload a fresh profile screenshot here. This scan was not saved."
            ),
            color=0x95a5a6,
        )
        try:
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception:  # pragma: no cover - Discord edge
            self.cog.log.exception("Failed to update rescan message")

    async def on_timeout(self) -> None:
        await self._finalize(auto=True)


class DuelScanReviewView(discord.ui.View):
    def __init__(
        self,
        cog: ProfileScanner,
        guild_id: int,
        user_id: int,
        payload: dict,
        *,
        timeout: int,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.payload = payload
        self.message: discord.Message | None = None
        self._finalized = False

    def bind_message(self, message: discord.Message) -> None:
        self.message = message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "🔒 Only the uploader can approve or rescan this duel score.",
            ephemeral=True,
        )
        return False

    async def _finalize(self, *, interaction: discord.Interaction | None = None) -> None:
        if self._finalized:
            return
        self._finalized = True
        await add_duel_score(
            self.guild_id,
            self.user_id,
            week_key=self.payload.get("week_key"),
            player_name=self.payload.get("player_name"),
            score_text=self.payload.get("score_text"),
            score_int=self.payload.get("score_int"),
            raw_ocr=self.payload.get("raw_score_ocr"),
        )
        embed = self.cog._build_duel_confirmation_embed(self.payload)
        try:
            if interaction:
                await interaction.response.edit_message(content="✅ Duel score saved.", embed=embed, view=None)
            elif self.message:
                await self.message.edit(content="✅ Duel score saved.", embed=embed, view=None)
        except Exception:  # pragma: no cover - Discord edge
            self.cog.log.exception("Failed to finalize duel scan")

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finalize(interaction=interaction)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def decline_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finalized:
            return
        self._finalized = True
        embed = discord.Embed(
            title="🗑️ Duel score declined",
            description="Result discarded. Send a new screenshot if you want to try again.",
            color=0xe74c3c,
        )
        try:
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception:  # pragma: no cover - Discord edge
            self.cog.log.exception("Failed to decline duel scan")

    @discord.ui.button(label="Rescan", style=discord.ButtonStyle.secondary, emoji="🔁")
    async def rescan_scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._finalized:
            return
        self._finalized = True
        self.cog._pending_scans[self.user_id] = PendingScan(
            scan_type="duel",
            guild_id=self.guild_id,
            requested_at=datetime.now(timezone.utc),
        )
        embed = discord.Embed(
            title="🔁 Rescan requested",
            description="Upload a fresh duel screenshot here. This scan was not saved.",
            color=0x95a5a6,
        )
        try:
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception:  # pragma: no cover - Discord edge
            self.cog.log.exception("Failed to update duel rescan message")

    async def on_timeout(self) -> None:
        self._finalized = True


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
            details = f"{status} CP {row.get('cp') or '-'} • Kills {row.get('kills') or '-'}"
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
        embed.add_field(name="🏰 Alliance", value=snapshot.get("alliance") or "-", inline=True)
        embed.add_field(name="🌐 Server", value=snapshot.get("server") or "-", inline=True)
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
