"""
FILE: cogs/automation.py
USE: Automated member management.
FEATURES: Auto-role assignment and server-specific welcome messages.
"""
import discord
from discord.ext import commands
from database import get_settings

class Automation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
                    print(f"DEBUG: Missing permissions to add role in {guild.name}")

        # 2. Handle Welcome Message
        if settings['welcome_channel_id']:
            channel = self.bot.get_channel(settings['welcome_channel_id'])
            if channel:
                embed = discord.Embed(
                    title="📡 NEW SIGNAL DETECTED",
                    description=f"Welcome to the wasteland, {member.mention}.\nYour ID has been registered to **{guild.name}**.",
                    color=0x2ecc71
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Member Count: {guild.member_count}")
                await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Triggered when a signal is lost (member leaves)."""
        settings = await get_settings(member.guild.id)
        
        if settings and settings['welcome_channel_id']:
            channel = self.bot.get_channel(settings['welcome_channel_id'])
            if channel:
                await channel.send(f"⚠️ **SIGNAL LOST:** {member.display_name} has left the sector.")

async def setup(bot):
    await bot.add_cog(Automation(bot))