"""
FILE: cogs/config.py
USE: Multi-server configuration management.
FEATURES: Interactive setup for server-specific channels and roles.
"""
import discord
from discord.ext import commands
from database import update_setting, get_settings

class Configuration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx):
        """Interactive setup for server settings."""
        embed = discord.Embed(
            title="⚙️ Marcia OS: Server Initialization",
            description=(
                "Please use the following commands to configure this unit for your server:\n\n"
                "`!set_chat #channel` - Where level-up alerts go.\n"
                "`!set_welcome #channel` - Where new member logs go.\n"
                "`!set_verify #channel` - Where the verification system lives.\n"
                "`!set_role @role` - The role given to new/verified members.\n"
                "`!view_config` - Check current server settings."
            ),
            color=0x3498db
        )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def set_chat(self, ctx, channel: discord.TextChannel):
        await update_setting(ctx.guild.id, "chat_channel_id", channel.id, ctx.guild.name)
        await ctx.send(f"✅ Level-up transmissions routed to {channel.mention}.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def set_welcome(self, ctx, channel: discord.TextChannel):
        await update_setting(ctx.guild.id, "welcome_channel_id", channel.id, ctx.guild.name)
        await ctx.send(f"✅ Welcome logs routed to {channel.mention}.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def set_role(self, ctx, role: discord.Role):
        await update_setting(ctx.guild.id, "auto_role_id", role.id, ctx.guild.name)
        await ctx.send(f"✅ Auto-role set to **{role.name}**.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def view_config(self, ctx):
        s = await get_settings(ctx.guild.id)
        if not s:
            return await ctx.send("❌ This server has not been configured yet. Use `!setup`.")

        embed = discord.Embed(title=f"📡 System Configuration: {ctx.guild.name}", color=0x2ecc71)
        embed.add_field(name="Chat Channel", value=f"<#{s['chat_channel_id']}>" if s['chat_channel_id'] else "Not Set")
        embed.add_field(name="Welcome Channel", value=f"<#{s['welcome_channel_id']}>" if s['welcome_channel_id'] else "Not Set")
        embed.add_field(name="Auto-Role", value=f"<@&{s['auto_role_id']}>" if s['auto_role_id'] else "Not Set")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Configuration(bot))