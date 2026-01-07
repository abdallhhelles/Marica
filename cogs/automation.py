"""
FILE: cogs/automation.py
USE: Automated member management.
FEATURES: Auto-role assignment and Marcia-voiced welcome/exit chatter.
"""
import logging
import random

import discord
from discord.ext import commands

from assets import FAREWELL_VARIATIONS, WELCOME_VARIATIONS
from database import get_settings, is_channel_ignored


class Automation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger("MarciaOS.Automation")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Triggered when a new unit enters a server."""
        guild = member.guild
        settings = await get_settings(guild.id)

        if not settings:
            return

        # 1. Handle Auto-Role
        if settings['auto_role_id']:
            role = guild.get_role(settings['auto_role_id'])
            if role:
                try:
                    await member.add_roles(role)
                except discord.Forbidden:
                    self.log.warning("Missing permissions to add role in %s", guild.name)

        # 2. Handle Welcome Message (in-character, text-first)
        target_channel = None
        if settings['welcome_channel_id']:
            target_channel = self.bot.get_channel(settings['welcome_channel_id'])
        if not target_channel and settings.get('chat_channel_id'):
            target_channel = self.bot.get_channel(settings['chat_channel_id'])

        if target_channel and not await is_channel_ignored(guild.id, target_channel.id):
            verify_id = settings.get('verify_channel_id') or settings.get('welcome_channel_id') or target_channel.id
            rules_id = settings.get('rules_channel_id') or settings.get('chat_channel_id') or target_channel.id
            line = random.choice(WELCOME_VARIATIONS).format(
                mention=member.mention,
                verify=verify_id,
                rules=rules_id,
            )
            await target_channel.send(line)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Triggered when a signal is lost (member leaves)."""
        settings = await get_settings(member.guild.id)

        if not settings:
            return

        target_channel = None
        if settings['welcome_channel_id']:
            target_channel = self.bot.get_channel(settings['welcome_channel_id'])
        if not target_channel and settings.get('chat_channel_id'):
            target_channel = self.bot.get_channel(settings['chat_channel_id'])

        if target_channel and not await is_channel_ignored(member.guild.id, target_channel.id):
            farewell = random.choice(FAREWELL_VARIATIONS).format(name=member.display_name)
            await target_channel.send(farewell)


async def setup(bot):
    await bot.add_cog(Automation(bot))
