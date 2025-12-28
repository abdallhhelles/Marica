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

BASE_DIR = Path(__file__).resolve().parent


def _pin_working_directory() -> None:
    """Ensure imports resolve relative to the repo root and log the result."""
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    if Path.cwd() != BASE_DIR:
        os.chdir(BASE_DIR)


_pin_working_directory()

import discord
from discord.ext import commands
from dotenv import load_dotenv

from assets import MARICA_QUOTES
from cogs.trading import FishControlView
from database import init_db

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
            command_prefix="!",
            intents=intents,
            help_command=None,
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
        )

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

    async def on_ready(self):
        """Final system check once online."""
        logger.info("-" * 30)
        logger.info("MARCIA OS ONLINE")
        logger.info(f"User: {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} sectors.")
        logger.info("-" * 30)
        
        await self.change_presence(
            activity=discord.Game(name="Dark War: Survival | !manual"),
        )

    async def on_message(self, message):
        """Centralized message handling and personality logic."""
        if message.author.bot or not message.guild:
            return

        # 1. Personality Logic: Replies to mentions or direct replies
        is_bot_mentioned = self.user.mentioned_in(message) and not message.mention_everyone
        is_reply = (message.reference and 
                    message.reference.resolved and 
                    message.reference.resolved.author.id == self.user.id)
        
        if is_bot_mentioned or is_reply:
            async with message.channel.typing():
                await asyncio.sleep(1)
                await message.reply(random.choice(MARICA_QUOTES))

        # 2. Process Commands
        await self.process_commands(message)

        # 3. Command Cleanup
        if message.content.startswith("!"):
            await asyncio.sleep(2)
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

    async def on_command_error(self, ctx, error):
        """Handles common command errors gracefully."""
        if isinstance(error, commands.CommandNotFound): 
            return 
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ **Access Denied:** Insufficient clearance.", delete_after=5)
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`.")
            return
        if isinstance(error, commands.CommandOnCooldown):
            retry = int(error.retry_after)
            await ctx.send(f"⏳ Cooldown active. Try again in {retry}s.")
            return

        logger.error(f"Uncaught Error: {error}")

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
