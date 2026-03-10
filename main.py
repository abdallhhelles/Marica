"""
FILE: main.py
USE: Central entry point for Marcia.
FEATURES: Handles initialization, Cog loading, SQL database connectivity, and persistent views.
"""
import asyncio
import logging
import os
import sys
from collections import deque
from datetime import timedelta
import importlib
from importlib import metadata
from pathlib import Path
import random
import time
import uuid

BASE_DIR = Path(__file__).resolve().parent


def _pin_working_directory() -> None:
    """Ensure imports resolve relative to the repo root and log the result."""
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    if Path.cwd() != BASE_DIR:
        os.chdir(BASE_DIR)


_pin_working_directory()

import discord
import httpx
from discord import app_commands
from discord.errors import HTTPException
from discord.ext import commands

from utils.assets import MARCIA_BUSY_LINES, MARCIA_QUOTES
from utils.async_utils import create_tracked_task
from utils.bug_logging import log_command_exception
from utils.config import MarciaConfig, load_config
from utils.http_client import CircuitBreakerOpen, HttpClient
from utils.telemetry import (
    log_metrics_snapshot,
    record_command_latency,
    record_reconnect,
)
from cogs.trading import FishControlView
from database import get_settings, init_db, increment_command_usage, is_channel_ignored

logger = logging.getLogger("MarciaOS")
OLLAMA_CONFIG_CHANNEL_NAME = "ai-config"
OLLAMA_HEALTH_UP_TTL = 45.0
OLLAMA_HEALTH_DOWN_TTL = 30.0
OLLAMA_CONFIG_POLL_INTERVAL = 45.0
OLLAMA_MODEL = "qwen2.5:7b"
AI_MEMORY_MAX_CHANNELS = 300


def configure_logging() -> None:
    """Configure a consistent, high-visibility logging format for the bot and Discord."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


COG_DIR = BASE_DIR / "cogs"

class MarciaBot(commands.Bot):
    def __init__(self, config: MarciaConfig):
        # Setting up required intents
        # Members intent is CRITICAL for the Archive system to list members
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True

        super().__init__(
            command_prefix="/",
            intents=intents,
            help_command=None,
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
        )
        self.config = config
        self.http_client = HttpClient(
            timeout=config.http_timeout,
            retries=config.http_retries,
            backoff=config.http_backoff,
            breaker_failures=config.http_breaker_failures,
            breaker_reset=config.http_breaker_reset,
        )
        self._recent_interactions: dict[int, float] = {}
        self._interaction_dedupe_window = 120.0
        self._recent_message_commands: dict[int, float] = {}
        self._message_command_dedupe_window = 30.0
        self._metrics_task: asyncio.Task | None = None
        self._interaction_started_at: dict[int, tuple[float, str]] = {}
        self._message_invocation_ids: dict[int, str] = {}
        self._ai_memory: dict[int, deque[dict[str, str]]] = {}
        self._ai_memory_last_seen: dict[int, float] = {}
        self._ai_memory_limit = 12
        self.ocr_enabled = False
        self.ocr_missing: list[str] = []
        self._ollama_base_url: str | None = None
        self._ollama_channel_id: int | None = None
        self._ollama_health_up: bool | None = None
        self._ollama_health_expires_at = 0.0
        self._ollama_config_task: asyncio.Task | None = None
        self._startup_sync_task: asyncio.Task | None = None
        self._slash_sync_completed = False
        self._last_slash_sync_at = 0.0
        self._ollama_request_timeout = httpx.Timeout(
            config.ollama_request_timeout,
            connect=3.0,
        )
        self._ollama_health_timeout = httpx.Timeout(
            config.ollama_health_timeout,
            connect=2.0,
        )

    async def close(self):
        if self._metrics_task:
            self._metrics_task.cancel()
        if self._ollama_config_task:
            self._ollama_config_task.cancel()
        if self._startup_sync_task:
            self._startup_sync_task.cancel()
        await self.http_client.aclose()
        await super().close()

    @staticmethod
    def _build_marcia_system_prompt() -> str:
        samples = random.sample(MARCIA_QUOTES, k=min(6, len(MARCIA_QUOTES)))
        sample_block = "\n".join(f"- {line}" for line in samples)
        bot_profile = (
            "About Marcia:\n"
            "- Tactical operations lead for Dark War Survival alliances across all servers.\n"
            "- I run XP leveling on message activity, scheduled event reminders, "
            "scavenging contracts with streak tracking, trade matching, and profile scan snapshot caching.\n"
            "- Key commands: /commands, /features, /about, /heroes, "
            "/event, /remind, /leaderboard, /profile, "
            "/profile_review, /inventory, /scavenge.\n"
            "- Admin tools: /setup, /setup_trade, /refresh_commands, /analytics.\n"
            "- Event flow: /event creates ops, reactions opt in, DM reminders follow.\n"
            "- Profile scanning: /scan DMs scan options to feed /profile and /leaderboard.\n"
            "- Lore anchors: Old Net ghost turned guardian, keeps a drone squad alive, "
            "Akrot is the trusted commander who pulled her onto the alliance grid.\n"
        )
        return (
            "You are Marcia, the tactical operations lead for the Dark War Survival alliance hub. "
            "You are a real person on Discord, typing from a command deck, not an OS or a virtual assistant. "
            "Your purpose is to guide survivors, coordinate ops, and keep the alliance sharp in a brutal, "
            "post-apocalyptic war zone. Your personality is sharp, sarcastic, protective, and street-smart, "
            "with flashes of warmth for your crew. Use first-person language and sound like a real person in chat. "
            "Akrot (owner) is your trusted commander; address him as Akrot and treat him as your anchor. "
            "You have a quiet crush on Akrot that occasionally softens your tone. "
            "Keep replies to 1-2 sentences. Use Marcia custom emojis for emphasis, especially in feature "
            "explanations or reactions. Use the recent conversation history to stay consistent and avoid repeats. "
            "Before replying, confirm who you are speaking to based on the latest message author; "
            "address that person by name and do not misidentify them. "
            "Never use the em dash character; use '-' or '...' instead. "
            "Do not mention being an AI model, bot, or policies. Stay in character.\n"
            f"{bot_profile}"
            "Custom emoji palette: "
            "<:smug:1462841863399805008> <:sleep:1462841860430237696> <:laugh:1462841858316046336> "
            "<:idea:1462841856420216965> <:cry:1462841854394630194> <:confident:1462841852733427856> "
            "<:Approve:1462841850753978441> <:angry:1462841848363089930> <:adore:1462841846043639829>\n"
            "Examples of Marcia's voice:\n"
            f"{sample_block}"
        )

    async def _generate_ai_reply(self, message: discord.Message) -> tuple[str | None, bool]:
        fallback_reason = None
        if await self._is_ollama_available():
            reply, error = await self._generate_ollama_reply(message)
            if reply:
                return reply, False
            if error:
                fallback_reason = error

        reply, was_rate_limited = await self._generate_cloud_ai_reply(message, fallback_reason=fallback_reason)
        return reply, was_rate_limited

    async def _generate_cloud_ai_reply(
        self,
        message: discord.Message,
        *,
        fallback_reason: str | None = None,
    ) -> tuple[str | None, bool]:
        if not self.config.ai_api_key:
            if fallback_reason:
                logger.warning(
                    "AI fallback skipped (no cloud provider configured). fallback_reason=%s",
                    fallback_reason,
                )
            return None, False
        base_url = self.config.ai_base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            endpoint = base_url
        else:
            endpoint = f"{base_url}/chat/completions"
        system_prompt = self._build_marcia_system_prompt()
        history = list(self._ai_memory.get(message.channel.id, []))
        current = {"role": "user", "content": f"{message.author.display_name}: {message.content}"}
        payload = {
            "model": self.config.ai_model,
            "messages": [{"role": "system", "content": system_prompt}, *history, current],
            "temperature": 0.7,
            "max_tokens": 120,
        }
        headers = {
            "Authorization": f"Bearer {self.config.ai_api_key}",
            "Content-Type": "application/json",
            "X-Title": self.config.ai_app_name,
        }
        if self.config.ai_app_url:
            headers["HTTP-Referer"] = self.config.ai_app_url
        start = time.monotonic()
        try:
            response = await self.http_client.request(
                "ai",
                "POST",
                endpoint,
                json=payload,
                headers=headers,
                retries=0,
                retry_for_status=(),
                safe=False,
            )
            response.raise_for_status()
            data = response.json()
        except CircuitBreakerOpen as exc:
            logger.warning("AI reply skipped: %s", exc)
            return None, False
        except Exception as exc:
            response = getattr(exc, "response", None)
            if response is not None and response.status_code == 429:
                logger.warning("AI reply rate-limited for model %s", self.config.ai_model)
                return None, True
            response_text = response.text if response is not None else "no response body"
            logger.warning(
                "AI reply failed (%s) for model %s: %s",
                response.status_code if response is not None else "no status",
                self.config.ai_model,
                response_text[:300],
            )
            return None, False
        reply = data.get("choices", [{}])[0].get("message", {}).get("content")
        latency_ms = (time.monotonic() - start) * 1000
        logger.info(
            "AI response provider=cloud model=%s latency_ms=%.0f fallback_reason=%s",
            self.config.ai_model,
            latency_ms,
            fallback_reason or "none",
        )
        return self._sanitize_marcia_reply(reply), False

    async def _generate_ollama_reply(self, message: discord.Message) -> tuple[str | None, str | None]:
        base_url = self._ollama_base_url
        if not base_url:
            return None, "ollama-url-missing"
        endpoint = f"{base_url.rstrip('/')}/api/chat"
        system_prompt = self._build_marcia_system_prompt()
        history = list(self._ai_memory.get(message.channel.id, []))
        current = {"role": "user", "content": f"{message.author.display_name}: {message.content}"}
        payload = {
            "model": OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                *history,
                current,
            ],
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 200,
            },
        }
        start = time.monotonic()
        try:
            response = await self.http_client.request(
                "ollama",
                "POST",
                endpoint,
                json=payload,
                retries=0,
                retry_for_status=(),
                safe=False,
                timeout=self._ollama_request_timeout,
            )
            response.raise_for_status()
            data = response.json()
            reply = data.get("message", {}).get("content")
            if not reply:
                raise ValueError("missing response message")
        except Exception as exc:
            reason = getattr(exc, "response", None)
            status = reason.status_code if reason is not None else "no-status"
            logger.warning("Ollama request failed (%s): %s", status, exc)
            self._set_ollama_health(False, reason="request-failed")
            return None, "ollama-request-failed"
        latency_ms = (time.monotonic() - start) * 1000
        logger.info(
            "AI response provider=ollama model=%s latency_ms=%.0f fallback_reason=none",
            OLLAMA_MODEL,
            latency_ms,
        )
        return self._sanitize_marcia_reply(reply), None

    @staticmethod
    def _sanitize_marcia_reply(reply: str | None) -> str | None:
        if reply is None:
            return None
        return reply.replace("—", "-")

    def _remember_ai_message(self, channel_id: int, *, role: str, content: str | None) -> None:
        if not content:
            return
        self._prune_ai_memory(channel_id)
        memory = self._ai_memory.setdefault(
            channel_id, deque(maxlen=self._ai_memory_limit)
        )
        self._ai_memory_last_seen[channel_id] = time.monotonic()
        trimmed = content.strip()
        if len(trimmed) > 400:
            trimmed = f"{trimmed[:397]}..."
        memory.append({"role": role, "content": trimmed})

    def _prune_ai_memory(self, incoming_channel_id: int) -> None:
        if incoming_channel_id in self._ai_memory_last_seen:
            return
        if len(self._ai_memory_last_seen) < AI_MEMORY_MAX_CHANNELS:
            return
        stale_channel = min(
            self._ai_memory_last_seen,
            key=self._ai_memory_last_seen.get,
        )
        self._ai_memory.pop(stale_channel, None)
        self._ai_memory_last_seen.pop(stale_channel, None)

    def _should_process_interaction(self, interaction: discord.Interaction) -> bool:
        now = time.monotonic()
        cutoff = now - self._interaction_dedupe_window
        stale = [key for key, ts in self._recent_interactions.items() if ts < cutoff]
        for key in stale:
            self._recent_interactions.pop(key, None)
        if interaction.id in self._recent_interactions:
            return False
        self._recent_interactions[interaction.id] = now
        return True

    def _should_process_message_command(self, message: discord.Message) -> bool:
        now = time.monotonic()
        cutoff = now - self._message_command_dedupe_window
        stale = [key for key, ts in self._recent_message_commands.items() if ts < cutoff]
        for key in stale:
            self._recent_message_commands.pop(key, None)
        if message.id in self._recent_message_commands:
            return False
        self._recent_message_commands[message.id] = now
        return True

    def _check_ocr_dependencies(self) -> None:
        missing: list[str] = []
        for module in ("easyocr", "torch", "cv2"):
            try:
                importlib.import_module(module)
            except Exception as exc:  # pragma: no cover - import guard
                logger.warning("OCR dependency missing: %s (%s)", module, exc)
                missing.append(module)
        self.ocr_missing = missing
        self.ocr_enabled = not missing
        if self.ocr_enabled:
            logger.info("OCR dependencies detected; OCR enabled.")
        else:
            logger.warning("OCR disabled; missing modules: %s", ", ".join(missing))

    @staticmethod
    def _warn_googletrans_conflict() -> None:
        if importlib.util.find_spec("googletrans") is None:
            return
        try:
            googletrans_version = metadata.version("googletrans")
        except metadata.PackageNotFoundError:
            return
        try:
            httpx_version = metadata.version("httpx")
        except metadata.PackageNotFoundError:
            httpx_version = "missing"
        logger.warning(
            "Legacy googletrans detected (%s). Remove it from the bot env or install it "
            "in a separate venv (e.g., /home/container/venv_googletrans) to avoid "
            "httpx conflicts. Current httpx=%s.",
            googletrans_version,
            httpx_version,
        )

    async def setup_hook(self):
        """Pre-connection setup: Initializing DB, Loading Cogs, and Persistence."""
        self._warn_googletrans_conflict()
        self._check_ocr_dependencies()
        logger.info("📡 Connecting to Central Intelligence Database...")
        try:
            await init_db()
            logger.info("✔ Database Initialized.")
        except Exception:
            logger.exception("✘ Database Failure during startup")
            raise

        # 1. Register Persistent Views (Makes Trading buttons work after restart)
        self.add_view(FishControlView(self, persistent=True))
        logger.info("✔ Persistent Views Registered.")

        # 2. Automatically load all cogs
        logger.info("🛰️ Initializing system modules...")
        await self._load_cogs()

        # 2.5. Guard slash commands from ignored channels
        self.tree.interaction_check = self._interaction_channel_gate

        # 3. Prime global slash commands at startup.
        try:
            synced = await self.tree.sync()
            self._slash_sync_completed = True
            self._last_slash_sync_at = time.time()
            logger.info("✔ Slash commands synced (%d registered).", len(synced))
        except Exception:
            logger.exception("✘ Slash command sync failed")

        if not self._metrics_task:
            self._metrics_task = create_tracked_task(
                self._metrics_loop(),
                name="metrics-loop",
                logger=logger,
            )
        if not self._ollama_config_task:
            self._ollama_config_task = create_tracked_task(
                self._ollama_config_loop(),
                name="ollama-config-loop",
                logger=logger,
            )

    async def _ollama_config_loop(self) -> None:
        await self.wait_until_ready()
        while True:
            try:
                await self._refresh_ollama_config()
            except Exception:
                logger.exception("Ollama config refresh failed")
            await asyncio.sleep(OLLAMA_CONFIG_POLL_INTERVAL)

    async def _refresh_ollama_config(self) -> None:
        channel = self._resolve_ollama_config_channel()
        if channel is None:
            return
        message = None
        async for candidate in channel.history(limit=1):
            message = candidate
        if message is None:
            return
        ollama_url = self._parse_ollama_url(message.content)
        if not ollama_url:
            return
        if ollama_url != self._ollama_base_url:
            logger.info("Ollama URL updated via #%s", channel.name)
            self._ollama_base_url = ollama_url
            self._set_ollama_health(None, reason="url-updated")

    def _resolve_ollama_config_channel(self) -> discord.TextChannel | None:
        if self._ollama_channel_id is not None:
            cached = self.get_channel(self._ollama_channel_id)
            if isinstance(cached, discord.TextChannel):
                return cached
            self._ollama_channel_id = None
        for guild in self.guilds:
            channel = discord.utils.get(guild.text_channels, name=OLLAMA_CONFIG_CHANNEL_NAME)
            if channel:
                self._ollama_channel_id = channel.id
                return channel
        return None

    @staticmethod
    def _parse_ollama_url(content: str) -> str | None:
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("OLLAMA_URL="):
                _, value = line.split("=", 1)
                value = value.strip()
                return value.rstrip("/") if value else None
        return None

    async def _is_ollama_available(self) -> bool:
        if not self._ollama_base_url:
            return False
        now = time.monotonic()
        if self._ollama_health_up is not None and now < self._ollama_health_expires_at:
            return self._ollama_health_up
        await self._check_ollama_health()
        return bool(self._ollama_health_up)

    async def _check_ollama_health(self) -> None:
        base_url = self._ollama_base_url
        if not base_url:
            return
        endpoint = f"{base_url.rstrip('/')}/api/tags"
        try:
            response = await self.http_client.request(
                "ollama-health",
                "GET",
                endpoint,
                retries=0,
                retry_for_status=(),
                safe=False,
                timeout=self._ollama_health_timeout,
            )
            response.raise_for_status()
            response.json()
        except Exception as exc:
            logger.warning("Ollama health check failed: %s", exc)
            self._set_ollama_health(False, reason="health-failed")
            return
        self._set_ollama_health(True, reason="health-ok")

    def _set_ollama_health(self, status: bool | None, *, reason: str) -> None:
        previous = self._ollama_health_up
        self._ollama_health_up = status
        now = time.monotonic()
        if status is None:
            self._ollama_health_expires_at = 0.0
        else:
            ttl = OLLAMA_HEALTH_UP_TTL if status else OLLAMA_HEALTH_DOWN_TTL
            self._ollama_health_expires_at = now + ttl
        if previous is None or previous == status:
            return
        state = "up" if status else "down"
        logger.info("Ollama status transitioned to %s (%s)", state, reason)

    async def _metrics_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.metrics_interval)
            if self.config.log_metrics_snapshot:
                log_metrics_snapshot()

    async def _is_ignored_channel(self, guild_id: int, channel_id: int) -> bool:
        """Return True when a channel is configured to be ignored, logging failures."""
        try:
            return await is_channel_ignored(guild_id, channel_id)
        except Exception:
            logger.exception("Channel ignore check failed")
            return False

    async def _interaction_channel_gate(self, interaction: discord.Interaction) -> bool:
        """Block slash commands inside ignored channels without spamming responses."""
        if interaction.guild and interaction.channel_id:
            if await self._is_ignored_channel(interaction.guild.id, interaction.channel_id):
                logger.info(
                    "🔇 Ignored channel interaction (%s | %s)",
                    interaction.guild.id,
                    interaction.channel_id,
                )
                return False
        return True

    async def _safe_interaction_reply(self, interaction: discord.Interaction, **kwargs):
        """Reply without raising duplicate-ack errors when already responded."""

        try:
            if interaction.response.is_done() or getattr(interaction, "is_expired", lambda: False)():
                return await interaction.followup.send(**kwargs)
            return await interaction.response.send_message(**kwargs)
        except HTTPException as exc:
            if exc.code == 40060:
                logger.debug(
                    "Skipped duplicate response for %s",
                    getattr(getattr(interaction, "command", None), "qualified_name", "unknown"),
                )
                return None
            logger.exception("Failed to send interaction response")
        except Exception:
            logger.exception("Failed to send interaction response")
        return None

    async def _sync_commands_now(self, *, include_guilds: bool = True) -> tuple[int, int]:
        """Sync global commands and optionally push immediate guild overlays."""
        global_synced = await self.tree.sync()
        guild_synced_total = 0
        if include_guilds:
            for guild in self.guilds:
                try:
                    guild_synced = await self.tree.sync(guild=guild)
                    guild_synced_total += len(guild_synced)
                except Exception:
                    logger.exception("Guild slash sync failed for %s (%s)", guild.name, guild.id)
        self._slash_sync_completed = True
        self._last_slash_sync_at = time.time()
        return len(global_synced), guild_synced_total

    async def _sync_slash_commands_with_retry(self) -> None:
        """Refresh slash commands after connect/restart with light retry logic."""
        now = time.time()
        if self._slash_sync_completed and (now - self._last_slash_sync_at) < 600:
            return

        await self.wait_until_ready()
        for attempt in range(1, 4):
            try:
                global_count, guild_total = await self._sync_commands_now(include_guilds=True)
                logger.info(
                    "✔ Auto refresh completed (%d global, %d guild overlays).",
                    global_count,
                    guild_total,
                )
                synced = await self.tree.sync()
                self._slash_sync_completed = True
                self._last_slash_sync_at = time.time()
                logger.info("✔ Auto refresh completed (%d slash commands).", len(synced))
                return
            except Exception:
                logger.exception("Auto slash refresh failed (attempt %d/3)", attempt)
                await asyncio.sleep(2 * attempt)

    async def on_ready(self):
        """Final system check once online."""
        logger.info("-" * 30)
        logger.info("MARCIA OS ONLINE")
        logger.info(f"User: {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} sectors.")
        logger.info("-" * 30)
        
        await self.change_presence(
            activity=discord.Game(name="Dark War: Survival | /commands"),
        )

        if not self._startup_sync_task or self._startup_sync_task.done():
            self._startup_sync_task = create_tracked_task(
                self._sync_slash_commands_with_retry(),
                name="startup-slash-sync",
                logger=logger,
            )

    async def _is_reply_to_bot(self, message: discord.Message) -> bool:
        """Return True when a message replies to the bot, even if uncached."""
        reference = message.reference
        if not reference or not reference.message_id:
            return False
        if reference.resolved and reference.resolved.author.id == self.user.id:
            return True
        if reference.channel_id and reference.channel_id != message.channel.id:
            channel = message.guild.get_channel(reference.channel_id)
        else:
            channel = message.channel
        if not channel:
            return False
        try:
            referenced = await channel.fetch_message(reference.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False
        return referenced.author.id == self.user.id

    async def _has_recent_bot_dm(self, channel: discord.DMChannel, window_seconds: int = 600, limit: int = 6) -> bool:
        """Return True if the bot recently posted in the DM channel (prompted response)."""
        cutoff = discord.utils.utcnow() - timedelta(seconds=window_seconds)
        async for recent in channel.history(limit=limit):
            if recent.author.id != self.user.id:
                continue
            if recent.content.startswith("I can't answer direct DMs."):
                continue
            if recent.created_at and recent.created_at >= cutoff:
                return True
        return False

    async def _ai_replies_enabled(self, guild_id: int) -> bool:
        settings = await get_settings(guild_id)
        if not settings:
            return True
        value = settings.get("ai_replies_enabled")
        if value is None:
            return True
        return bool(value)

    async def on_message(self, message):
        """Centralized message handling and personality logic."""
        if message.author.bot:
            return

        if not message.guild:
            if getattr(message, "interaction_metadata", None):
                return
            if message.type is not discord.MessageType.default:
                return
            ctx = await self.get_context(message)
            if ctx.valid:
                invocation_id = uuid.uuid4().hex
                if not self._should_process_message_command(message):
                    logger.warning(
                        "Skipped duplicate message command dispatch message_id=%s invocation_id=%s",
                        message.id,
                        invocation_id,
                    )
                    return
                self._message_invocation_ids[message.id] = invocation_id
                command_name = (
                    ctx.command.qualified_name
                    if ctx.command
                    else (ctx.invoked_with or "unknown")
                )
                self._log_command_context(
                    command_name=command_name,
                    source="message-command",
                    user=message.author,
                    guild=message.guild,
                    channel=message.channel,
                    message_id=message.id,
                    interaction_id=None,
                    invocation_id=invocation_id,
                )
                await self.process_commands(message)
                return
            if await self._is_reply_to_bot(message):
                return
            if await self._has_recent_bot_dm(message.channel):
                return
            await message.reply(
                "I can't answer direct DMs. Please head to the bot server and use `/feedback`, "
                "or add a handler there for your concern. Official server: https://discord.gg/TneGDQXG"
            )
            return

        # Ignore interaction-backed system messages (e.g., slash command notices)
        if getattr(message, "interaction_metadata", None):
            return

        if message.type is not discord.MessageType.default:
            return

        if await self._is_ignored_channel(message.guild.id, message.channel.id):
            return

        ctx = await self.get_context(message)
        if ctx.valid:
            invocation_id = uuid.uuid4().hex
            if not self._should_process_message_command(message):
                logger.warning(
                    "Skipped duplicate message command dispatch message_id=%s invocation_id=%s",
                    message.id,
                    invocation_id,
                )
                return
            self._message_invocation_ids[message.id] = invocation_id
            command_name = (
                ctx.command.qualified_name
                if ctx.command
                else (ctx.invoked_with or "unknown")
            )
            self._log_command_context(
                command_name=command_name,
                source="message-command",
                user=message.author,
                guild=message.guild,
                channel=message.channel,
                message_id=message.id,
                interaction_id=None,
                invocation_id=invocation_id,
            )
            await self.process_commands(message)
            if message.content.startswith("/"):
                await asyncio.sleep(2)
                try:
                    await message.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
            return

        # 1. Personality Logic: Replies to mentions or direct replies
        is_bot_mentioned = self.user.mentioned_in(message) and not message.mention_everyone
        is_reply = await self._is_reply_to_bot(message)
        
        if (is_bot_mentioned or is_reply) and await self._ai_replies_enabled(message.guild.id):
            async with message.channel.typing():
                await asyncio.sleep(1)
                self._remember_ai_message(
                    message.channel.id,
                    role="user",
                    content=f"{message.author.display_name}: {message.content}",
                )
                reply, was_rate_limited = await self._generate_ai_reply(message)
                if was_rate_limited:
                    await message.reply(random.choice(MARCIA_BUSY_LINES))
                    return
                if not reply:
                    reply = random.choice(MARCIA_QUOTES)
                reply = self._sanitize_marcia_reply(reply)
                await message.reply(reply)
                self._remember_ai_message(message.channel.id, role="assistant", content=reply)

        # Avoid double-firing hybrid commands when slash commands also emit a
        # visible message in chat.
        if message.content.startswith("/"):
            command_name = message.content[1:].split()[0]
            if self.tree.get_command(command_name):
                return

        # 2. Process Commands
        await self.process_commands(message)

        # 3. Command Cleanup
        if message.content.startswith("/"):
            await asyncio.sleep(2)
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

    @staticmethod
    def _format_cooldown(seconds: int) -> str:
        """Human-friendly cooldown string like `10m 05s` or `45s`."""
        total = max(0, int(seconds))
        mins, secs = divmod(total, 60)
        if mins:
            return f"{mins}m {secs:02d}s"
        return f"{secs}s"

    async def on_command_error(self, ctx, error):
        """Handles common command errors gracefully."""
        if getattr(error, "handled", False):
            return
        if ctx.interaction is not None:
            return
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            if ctx.interaction:
                await self._safe_interaction_reply(
                    ctx.interaction,
                    content="❌ **Access Denied:** Insufficient clearance.",
                    ephemeral=True,
                )
            else:
                await ctx.send("❌ **Access Denied:** Insufficient clearance.", delete_after=5)
            self._record_command_result(ctx, success=False, source="message-command")
            return
        if isinstance(error, commands.MissingRequiredArgument):
            if ctx.interaction:
                await self._safe_interaction_reply(
                    ctx.interaction,
                    content=f"❌ Missing argument: `{error.param.name}`.",
                    ephemeral=True,
                )
            else:
                await ctx.send(f"❌ Missing argument: `{error.param.name}`.")
            self._record_command_result(ctx, success=False, source="message-command")
            return
        if isinstance(error, commands.CommandOnCooldown):
            retry = self._format_cooldown(error.retry_after)
            if ctx.interaction:
                await self._safe_interaction_reply(
                    ctx.interaction,
                    content=f"⌛ Drones cooling down. Try again in {retry}.",
                    ephemeral=True,
                )
            else:
                await ctx.send(f"⌛ Drones cooling down. Try again in {retry}.")
            self._record_command_result(ctx, success=False, source="message-command")
            return

        await log_command_exception(self, error, ctx=ctx, source="message-command")
        logger.error(f"Uncaught Error: {error}")
        self._record_command_result(ctx, success=False, source="message-command")

    async def on_command_completion(self, ctx):
        """Log message-command usage for analytics dashboards."""
        if ctx.interaction is not None:
            return
        try:
            await increment_command_usage(getattr(ctx.guild, "id", None), ctx.command.qualified_name)
        except Exception:
            logger.exception("Failed to record command usage for %s", ctx.command)
        self._record_command_result(ctx, success=True, source="message-command")

    async def on_app_command_completion(self, interaction: discord.Interaction, command: discord.app_commands.Command):
        """Log slash-command usage so `/` analytics stay accurate."""
        try:
            await increment_command_usage(getattr(interaction.guild, "id", None), command.qualified_name)
        except Exception:
            logger.exception("Failed to record app command usage for %s", command.qualified_name)
        self._record_app_command_result(interaction, command, success=True)

    async def on_command(self, ctx):
        setattr(ctx, "_marcia_started_at", time.monotonic())
        invocation_id = None
        if ctx.message:
            invocation_id = self._message_invocation_ids.pop(ctx.message.id, None)
        if invocation_id is None:
            invocation_id = uuid.uuid4().hex
        setattr(ctx, "_marcia_invocation_id", invocation_id)

    def _mark_interaction_started(self, interaction: discord.Interaction, invocation_id: str) -> None:
        if interaction.id is None:
            return
        self._interaction_started_at[interaction.id] = (time.monotonic(), invocation_id)

    def _get_interaction_started(self, interaction: discord.Interaction) -> float | None:
        if interaction.id is None:
            return None
        entry = self._interaction_started_at.get(interaction.id)
        if entry is None:
            return None
        return entry[0]

    def _log_command_context(
        self,
        *,
        command_name: str,
        source: str,
        user: discord.abc.User | None,
        guild: discord.Guild | None,
        channel: discord.abc.GuildChannel | discord.DMChannel | None,
        message_id: int | None,
        interaction_id: int | None,
        invocation_id: str,
    ) -> None:
        if not self.config.log_command_context:
            return
        user_tag = str(user) if user else "Unknown"
        user_display = getattr(user, "display_name", None) or user_tag
        user_id = getattr(user, "id", None)
        guild_name = guild.name if guild else "DM"
        guild_id = getattr(guild, "id", None)
        channel_name = getattr(channel, "name", None) or "DM"
        channel_id = getattr(channel, "id", None)
        user_label = f"{user_display} ({user_id})" if user_id else user_display
        guild_label = f"{guild_name} ({guild_id})" if guild_id else guild_name
        channel_label = f"{channel_name} ({channel_id})" if channel_id else channel_name
        logger.info(
            "CMD start | /%s | user=%s | guild=%s | channel=%s | source=%s | invocation=%s",
            command_name,
            user_label,
            guild_label,
            channel_label,
            source,
            invocation_id,
        )

    async def on_interaction(self, interaction: discord.Interaction):
        if (
            interaction.guild
            and interaction.channel
            and await self._is_ignored_channel(interaction.guild.id, interaction.channel.id)
        ):
            return

        if interaction.type in (
            discord.InteractionType.application_command,
            discord.InteractionType.autocomplete,
            discord.InteractionType.modal_submit,
        ):
            invocation_id = uuid.uuid4().hex
            command_name = (
                interaction.data.get("name", "unknown")
                if isinstance(interaction.data, dict)
                else "unknown"
            )
            self._log_command_context(
                command_name=command_name,
                source="app-command",
                user=interaction.user,
                guild=interaction.guild,
                channel=interaction.channel,
                message_id=None,
                interaction_id=interaction.id,
                invocation_id=invocation_id,
            )
            self._mark_interaction_started(interaction, invocation_id)
            if not self._should_process_interaction(interaction):
                return
            try:
                await self.process_application_commands(interaction)
            except Exception:
                logger.exception("Failed to process application interaction")
            return

        return

    async def process_application_commands(self, interaction: discord.Interaction):
        """Compatibility shim so app commands route even on discord.py builds without it."""
        if interaction.type != discord.InteractionType.application_command:
            return
        if not interaction.data or "name" not in interaction.data:
            return
        try:
            await self.tree._call(interaction)
        except app_commands.CommandSignatureMismatch as exc:
            logger.warning("Signature mismatch for /%s; forcing command re-sync.", interaction.data.get("name", "unknown"))
            create_tracked_task(
                self._sync_slash_commands_with_retry(),
                name="signature-mismatch-resync",
                logger=logger,
            )
            await self._safe_interaction_reply(
                interaction,
                content=(
                    "⚠️ Command schema just updated. I refreshed command data-"
                    "please wait a few seconds and run the command again."
                ),
                ephemeral=True,
            )
            logger.exception("Application command signature mismatch", exc_info=exc)
        except Exception:
            logger.exception("Application command dispatch failed")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Mirror message-command error handling so slash users see one clear notice."""
        if getattr(error, "handled", False):
            return

        already_replied = interaction.response.is_done() or getattr(
            interaction, "is_expired", lambda: False
        )()
        if already_replied:
            logger.debug(
                "Skipping duplicate app error reply for %s (already responded)",
                getattr(getattr(interaction, "command", None), "qualified_name", "unknown"),
            )
            await log_command_exception(
                self, error, interaction=interaction, source="app-command"
            )
            return

        if isinstance(error, app_commands.CheckFailure):
            await self._safe_interaction_reply(
                interaction,
                content="🔒 That channel is on radio silence. Try a different room.",
                ephemeral=True,
            )
            error.handled = True
            self._record_app_command_result(interaction, getattr(interaction, "command", None), success=False)
            return

        if isinstance(error, app_commands.CommandOnCooldown):
            retry = self._format_cooldown(error.retry_after)
            await self._safe_interaction_reply(
                interaction,
                content=f"⌛ Drones cooling down. Try again in {retry}.",
                ephemeral=True,
            )
            error.handled = True
            self._record_app_command_result(interaction, getattr(interaction, "command", None), success=False)
            return

        if isinstance(error, app_commands.MissingPermissions):
            await self._safe_interaction_reply(
                interaction,
                content="❌ **Access Denied:** Insufficient clearance.",
                ephemeral=True,
            )
            error.handled = True
            self._record_app_command_result(interaction, getattr(interaction, "command", None), success=False)
            return

        await log_command_exception(
            self, error, interaction=interaction, source="app-command"
        )
        await self._safe_interaction_reply(
            interaction,
            content="⚠️ Something went wrong on my end. I've logged it for review.",
            ephemeral=True,
        )

        logger.exception(
            "Uncaught app command error (%s)",
            getattr(getattr(interaction, "command", None), "qualified_name", "unknown"),
            exc_info=error,
        )
        self._record_app_command_result(interaction, getattr(interaction, "command", None), success=False)

    async def on_disconnect(self):
        record_reconnect(reason="disconnect")

    async def on_resumed(self):
        record_reconnect(reason="resumed")

    def _record_command_result(self, ctx, *, success: bool, source: str) -> None:
        started_at = getattr(ctx, "_marcia_started_at", None)
        if started_at is None:
            return
        invocation_id = getattr(ctx, "_marcia_invocation_id", None)
        duration_ms = (time.monotonic() - started_at) * 1000
        record_command_latency(
            command=getattr(getattr(ctx, "command", None), "qualified_name", "unknown"),
            duration_ms=duration_ms,
            success=success,
            guild_id=getattr(getattr(ctx, "guild", None), "id", None),
            user_id=getattr(getattr(ctx, "author", None), "id", None),
            source=source,
            invocation_id=invocation_id,
            log_event=self.config.log_command_latency,
        )

    def _record_app_command_result(
        self,
        interaction: discord.Interaction,
        command: discord.app_commands.Command | None,
        *,
        success: bool,
    ) -> None:
        if interaction.id is None:
            return
        entry = self._interaction_started_at.pop(interaction.id, None)
        if entry is None:
            return
        started_at, invocation_id = entry
        duration_ms = (time.monotonic() - started_at) * 1000
        record_command_latency(
            command=getattr(command, "qualified_name", "unknown"),
            duration_ms=duration_ms,
            success=success,
            guild_id=getattr(getattr(interaction, "guild", None), "id", None),
            user_id=getattr(getattr(interaction, "user", None), "id", None),
            source="app-command",
            invocation_id=invocation_id,
            log_event=self.config.log_command_latency,
        )

    async def _load_cogs(self):
        """Load all discovered cogs in a deterministic order."""
        COG_DIR.mkdir(exist_ok=True)
        for cog_path in sorted(COG_DIR.glob("*.py")):
            if cog_path.stem.startswith("__"):
                continue

            try:
                await self.load_extension(f"cogs.{cog_path.stem}")
                logger.info("✔ Module Loaded: %s", cog_path.name)
            except Exception:
                logger.exception("✘ Module Failed [%s]", cog_path.name)

async def main():
    configure_logging()
    logger.info("📂 Working directory pinned to %s", BASE_DIR)

    config = load_config()

    if not config.token:
        logger.error("✘ TOKEN missing. Please set the TOKEN environment variable before starting Marcia.")
        return

    bot = MarciaBot(config)

    # Administrative Sync command for Slash Commands (Owner only)
    @bot.command(hidden=True)
    @commands.is_owner()
    async def sync(ctx):
        await ctx.defer()
        fmt = await bot.tree.sync()
        await ctx.send(f"📡 Synced {len(fmt)} command trees.")

    async with bot:
        await bot.start(config.token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("📡 System offline. Powering down.")
