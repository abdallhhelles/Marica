"""
FILE: cogs/missions.py
USE: Cleans up expired missions that have reached their target time.
FEATURES: Persistent mission cleanup and auto-pruning.
"""
from discord.ext import commands, tasks
from datetime import datetime, timezone
import logging
from database import (
    delete_mission, get_all_active_missions,
)

logger = logging.getLogger('MarciaOS.Missions')

class Missions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mission_updater.start()

    def cog_unload(self):
        self.mission_updater.cancel()

    @tasks.loop(seconds=60)
    async def mission_updater(self):
        """Background task to check for expired missions."""
        missions = await get_all_active_missions()
        now = datetime.now(timezone.utc)

        for m in missions:
            try:
                target_utc = datetime.fromisoformat(m['target_utc']).astimezone(timezone.utc)
                if now >= target_utc:
                    await delete_mission(m['guild_id'], m['codename'])
                    logger.info(f"🗑️ Mission {m['codename']} expired in guild {m['guild_id']}")
            except Exception as e:
                logger.error(f"Error checking mission {m['codename']}: {e}")

async def setup(bot):
    await bot.add_cog(Missions(bot))
