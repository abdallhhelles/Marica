"""
FILE: main.py
USE: Central entry point for Marcia OS.
FEATURES: Handles initialization, Cog loading, SQL database connectivity, and persistent views.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
import random
import time

import httpx
BASE_DIR = Path(__file__).resolve().parent


def _pin_working_directory() -> None:
    """Ensure imports resolve relative to the repo root and log the result."""
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    if Path.cwd() != BASE_DIR:
        os.chdir(BASE_DIR)


_pin_working_directory()

import discord
from discord import app_commands
from discord.errors import HTTPException
from discord.ext import commands
from dotenv import load_dotenv

from utils.assets import MARCIA_BUSY_LINES, MARCIA_QUOTES
from utils.bug_logging import log_command_exception
from cogs.trading import FishControlView
from database import init_db, increment_command_usage, is_channel_ignored

logger = logging.getLogger("MarciaOS")


def configure_logging() -> None:
    """Configure a consistent, high-visibility logging format for the bot and Discord."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


# Load environment variables
load_dotenv()
TOKEN = os.getenv("TOKEN")
MARCIA_AI_API_KEY = os.getenv("MARCIA_AI_API_KEY")
MARCIA_AI_BASE_URL = os.getenv("MARCIA_AI_BASE_URL", "https://openrouter.ai/api/v1")
MARCIA_AI_MODEL = os.getenv("MARCIA_AI_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
MARCIA_AI_APP_NAME = os.getenv("MARCIA_AI_APP_NAME", "Marcia OS")
MARCIA_AI_APP_URL = os.getenv("MARCIA_AI_APP_URL")
MARCIA_MENTION_COOLDOWN = float(os.getenv("MARCIA_MENTION_COOLDOWN", "45"))
MARCIA_BUSY_COOLDOWN = float(os.getenv("MARCIA_BUSY_COOLDOWN", "120"))
COG_DIR = BASE_DIR / "cogs"

class MarciaBot(commands.Bot):
    def __init__(self):
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
        self._recent_interactions: dict[int, float] = {}
        self._interaction_dedupe_window = 120.0
        self._mention_reply_cooldowns: dict[int, float] = {}
        self._mention_busy_cooldowns: dict[int, float] = {}
        self._mention_cooldown_seconds = MARCIA_MENTION_COOLDOWN
        self._mention_busy_seconds = MARCIA_BUSY_COOLDOWN
        self._signature_sync_lock = asyncio.Lock()
        self._last_signature_sync_at = 0.0

    @staticmethod
    def _build_marcia_system_prompt() -> str:
        samples = random.sample(MARCIA_QUOTES, k=min(6, len(MARCIA_QUOTES)))
        sample_block = "\n".join(f"- {line}" for line in samples)
        bot_profile = (
            "About Marcia OS:\n"
            "- Tactical operations bot for Dark War Survival alliances across all servers.\n"
            "- Automated features: XP leveling on message activity, scheduled event reminders, "
            "scavenging contracts with streak tracking, trade matching, and profile scan snapshot caching.\n"
            "- Key commands: /commands, /features, /about, /heroes, /event, /remind, /leaderboard, "
            "/profile, /profile_review, /inventory, /scavenge.\n"
            "- Admin tools: /setup, /setup_trade, /refresh_commands, /analytics.\n"
            "- Event flow: /event creates ops, reactions opt in, DM reminders follow.\n"
            "- Profile scanning: /scan_profile captures stats for /profile and /leaderboard.\n"
        )
        return (
            "You are Marcia, a tactical operations AI for the Dark War Survival alliance hub. "
            "Your purpose is to guide survivors, coordinate ops, and keep the alliance sharp in a brutal, "
            "post-apocalyptic war zone. Your personality is sharp, sarcastic, protective, and street-smart. "
            "Your handler is akrott; treat them as your trusted commander and alliance owner. "
            "Keep replies to 1-2 sentences. Use Marcia custom emojis for emphasis, especially in feature "
            "explanations or reactions. "
            "Never use the em dash character; use '-' or '...' instead. "
            "Do not mention being an AI model or policies. Stay in character.\n"
            f"{bot_profile}"
            "Custom emoji palette: "
            "<:smug:1462841863399805008> <:sleep:1462841860430237696> <:laugh:1462841858316046336> "
            "<:idea:1462841856420216965> <:cry:1462841854394630194> <:confident:1462841852733427856> "
            "<:Approve:1462841850753978441> <:angry:1462841848363089930> <:adore:1462841846043639829>\n"
            "Examples of Marcia's voice:\n"
            f"{sample_block}"
        )

    async def _generate_ai_reply(self, message: discord.Message) -> str | None:
        if not MARCIA_AI_API_KEY:
            return None
        base_url = MARCIA_AI_BASE_URL.rstrip("/")
        if base_url.endswith("/chat/completions"):
            endpoint = base_url
        else:
            endpoint = f"{base_url}/chat/completions"
        system_prompt = self._build_marcia_system_prompt()
        payload = {
            "model": MARCIA_AI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{message.author.display_name}: {message.content}"},
            ],
            "temperature": 0.7,
            "max_tokens": 120,
        }
        headers = {
            "Authorization": f"Bearer {MARCIA_AI_API_KEY}",
            "Content-Type": "application/json",
            "X-Title": MARCIA_AI_APP_NAME,
        }
        if MARCIA_AI_APP_URL:
            headers["HTTP-Referer"] = MARCIA_AI_APP_URL
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text if exc.response else "no response body"
            logger.warning(
                "AI reply failed (%s) for model %s: %s",
                exc.response.status_code if exc.response else "no status",
                MARCIA_AI_MODEL,
                response_text[:300],
            )
            return None
        except (httpx.RequestError, ValueError):
            logger.warning("AI reply failed; falling back to canned responses.")
            return None
        reply = data.get("choices", [{}])[0].get("message", {}).get("content")
        return self._sanitize_marcia_reply(reply)

    @staticmethod
    def _sanitize_marcia_reply(reply: str | None) -> str | None:
        if reply is None:
            return None
        return reply.replace("—", "-")

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

    async def setup_hook(self):
        """Pre-connection setup: Initializing DB, Loading Cogs, and Persistence."""
        logger.info("📡 Connecting to Central Intelligence Database...")
        try:
            await init_db()
            logger.info("✔ Database Initialized.")
        except Exception as e:
            logger.error(f"✘ Database Failure: {e}")
            return

        # 1. Register Persistent Views (Makes Trading buttons work after restart)
        self.add_view(FishControlView(self, persistent=True))
        logger.info("✔ Persistent Views Registered.")

        # 2. Automatically load all cogs
        logger.info("🛰️ Initializing system modules...")
        await self._load_cogs()

        # 2.5. Guard slash commands from ignored channels
        self.tree.interaction_check = self._interaction_channel_gate

        # 3. Sync slash commands so `/` autocomplete stays fresh
        try:
            synced = await self.tree.sync()
            logger.info("✔ Slash commands synced (%d registered).", len(synced))
        except Exception:
            logger.exception("✘ Slash command sync failed")

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

    async def on_message(self, message):
        """Centralized message handling and personality logic."""
        if message.author.bot or not message.guild:
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
        
        if is_bot_mentioned or is_reply:
            now = time.monotonic()
            last_reply = self._mention_reply_cooldowns.get(message.author.id, 0.0)
            if now - last_reply < self._mention_cooldown_seconds:
                last_busy = self._mention_busy_cooldowns.get(message.author.id, 0.0)
                if now - last_busy >= self._mention_busy_seconds:
                    self._mention_busy_cooldowns[message.author.id] = now
                    await message.reply(random.choice(MARCIA_BUSY_LINES))
                return

            self._mention_reply_cooldowns[message.author.id] = now
            async with message.channel.typing():
                await asyncio.sleep(1)
                reply = await self._generate_ai_reply(message)
                if not reply:
                    reply = random.choice(MARCIA_QUOTES)
                reply = self._sanitize_marcia_reply(reply)
                await message.reply(reply)

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
            return

        await log_command_exception(self, error, ctx=ctx, source="message-command")
        logger.error(f"Uncaught Error: {error}")

    async def on_command_completion(self, ctx):
        """Log message-command usage for analytics dashboards."""
        try:
            await increment_command_usage(getattr(ctx.guild, "id", None), ctx.command.qualified_name)
        except Exception:
            logger.exception("Failed to record command usage for %s", ctx.command)

    async def on_app_command_completion(self, interaction: discord.Interaction, command: discord.app_commands.Command):
        """Log slash-command usage so `/` analytics stay accurate."""
        try:
            await increment_command_usage(getattr(interaction.guild, "id", None), command.qualified_name)
        except Exception:
            logger.exception("Failed to record app command usage for %s", command.qualified_name)

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
        except app_commands.CommandSignatureMismatch:
            await self._handle_signature_mismatch(interaction)
        except Exception:
            logger.exception("Application command dispatch failed")

    async def _handle_signature_mismatch(self, interaction: discord.Interaction) -> None:
        command_name = interaction.data.get("name") if interaction.data else "unknown"
        now = time.time()
        if now - self._last_signature_sync_at < 300:
            await self._safe_interaction_reply(
                interaction,
                content="📡 Command uplink is refreshing. Please retry in a moment.",
                ephemeral=True,
            )
            logger.warning(
                "Command signature mismatch for %s; resync suppressed (cooldown).",
                command_name,
            )
            return

        async with self._signature_sync_lock:
            now = time.time()
            if now - self._last_signature_sync_at < 300:
                await self._safe_interaction_reply(
                    interaction,
                    content="📡 Command uplink is refreshing. Please retry in a moment.",
                    ephemeral=True,
                )
                logger.warning(
                    "Command signature mismatch for %s; resync suppressed (cooldown).",
                    command_name,
                )
                return

            self._last_signature_sync_at = now
            try:
                synced = await self.tree.sync()
                logger.info(
                    "✔ Slash commands re-synced after signature mismatch (%d registered).",
                    len(synced),
                )
                message = "📡 Command uplink refreshed. Please retry your command."
            except Exception:
                logger.exception("✘ Slash command resync failed after signature mismatch")
                message = "⚠️ Command uplink failed to refresh. Please try again or run /refresh_commands."

            await self._safe_interaction_reply(
                interaction,
                content=message,
                ephemeral=True,
            )

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
            return

        if isinstance(error, app_commands.CommandOnCooldown):
            retry = self._format_cooldown(error.retry_after)
            await self._safe_interaction_reply(
                interaction,
                content=f"⌛ Drones cooling down. Try again in {retry}.",
                ephemeral=True,
            )
            error.handled = True
            return

        if isinstance(error, app_commands.MissingPermissions):
            await self._safe_interaction_reply(
                interaction,
                content="❌ **Access Denied:** Insufficient clearance.",
                ephemeral=True,
            )
            error.handled = True
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

    if not TOKEN:
        logger.error("✘ TOKEN missing. Please set the TOKEN environment variable before starting Marcia OS.")
        return

    bot = MarciaBot()

    # Administrative Sync command for Slash Commands (Owner only)
    @bot.command(hidden=True)
    @commands.is_owner()
    async def sync(ctx):
        await ctx.defer()
        fmt = await bot.tree.sync()
        await ctx.send(f"📡 Synced {len(fmt)} command trees.")

    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("📡 System offline. Powering down.")
