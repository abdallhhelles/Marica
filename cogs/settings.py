"""
FILE: cogs/settings.py
USE: Configuration management for server admins.
FEATURES: SQL-backed setup, channel linking, auto-role, and clock sync.
"""
import discord
from discord.ext import commands
from database import update_setting, get_settings

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="setup", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx):
        """Displays the current server configuration and setup status."""
        data = await get_settings(ctx.guild.id)
        
        embed = discord.Embed(
            title="📡 MARCIA OS | System Diagnostics",
            description=(
                "Checking sector infrastructure... All links must be active for "
                "optimal drone deployment and mission synchronization."
            ),
            color=0x2b2d31
        )

        def get_status(cid):
            if not cid:
                return "❌ **LINK MISSING**"
            channel = self.bot.get_channel(cid)
            if not channel:
                return "⚠️ **CHANNEL DELETED**"
            
            perms = channel.permissions_for(ctx.guild.me)
            if not perms.send_messages:
                return f"{channel.mention} (🚫 **NO PERMS**)"
            return f"{channel.mention} (✅ **ACTIVE**)"

        def get_role_status(rid):
            if not rid:
                return "❌ **LINK MISSING**"
            role = ctx.guild.get_role(rid)
            if not role:
                return "⚠️ **ROLE DELETED**"
            return f"{role.mention} (✅ **ACTIVE**)"

        if data:
            embed.add_field(name="🛰️ Event Sector", value=get_status(data['event_channel_id']), inline=True)
            embed.add_field(name="💬 Chat Sector", value=get_status(data['chat_channel_id']), inline=True)
            embed.add_field(name="👋 Welcome Sector", value=get_status(data['welcome_channel_id']), inline=True)
            embed.add_field(name="📜 Rules Sector", value=get_status(data['rules_channel_id']), inline=True)
            embed.add_field(name="🛂 Verify Sector", value=get_status(data['verify_channel_id']), inline=True)
            embed.add_field(name="🔏 Auto-Role", value=get_role_status(data['auto_role_id']), inline=True)
            
            offset_str = f"UTC {data['server_offset_hours']:+}h"
            embed.set_footer(text=f"System Clock: {offset_str} | Protocol: Multi-Sector Stable")
        else:
            embed.description = "⚠️ **CRITICAL ERROR:** No configuration found in databank. Initialize sectors immediately."

        embed.add_field(
            name="🛠️ Maintenance Commands", 
            value=(
                "`!setup events #channel` - Mission/Event broadcasts\n"
                "`!setup chat #channel` - Main interaction zone\n"
                "`!setup role @role` - Auto-role for arrivals\n"
                "`!setup help` - View detailed setup guide"
            ), 
            inline=False
        )
        
        await ctx.send(embed=embed)

    @setup.command(name="help")
    async def setup_help(self, ctx):
        """Tips and Information for Server Setup."""
        embed = discord.Embed(
            title="🛠️ Marcia OS | Setup Intelligence",
            description="Follow these steps to ensure Marcia is fully operational in your server.",
            color=0x3498db
        )
        embed.add_field(
            name="1️⃣ The Event Sector",
            value="Linking the **Events** channel is vital. This is where Marcia will announce new Missions and Trading updates.",
            inline=False
        )
        embed.add_field(
            name="2️⃣ Auto-Role Logic",
            value="Make sure Marcia's role is **higher** than the role you are trying to assign in the Discord Role Hierarchy, or she won't be able to give it to members.",
            inline=False
        )
        embed.add_field(
            name="3️⃣ Time Sync",
            value="Use `!setup offset [number]` to match your server's local time. For example, if you are US Eastern (UTC-5), use `!setup offset -5`.",
            inline=False
        )
        await ctx.send(embed=embed)

    @setup.command(name="events")
    @commands.has_permissions(manage_guild=True)
    async def setup_events(self, ctx, channel: discord.TextChannel):
        await update_setting(ctx.guild.id, "event_channel_id", channel.id, ctx.guild.name)
        await ctx.send(f"✅ **Event Sector** linked to {channel.mention}.")

    @setup.command(name="chat")
    @commands.has_permissions(manage_guild=True)
    async def setup_chat(self, ctx, channel: discord.TextChannel):
        await update_setting(ctx.guild.id, "chat_channel_id", channel.id, ctx.guild.name)
        await ctx.send(f"✅ **Chat Sector** linked to {channel.mention}.")

    @setup.command(name="welcome")
    @commands.has_permissions(manage_guild=True)
    async def setup_welcome(self, ctx, channel: discord.TextChannel):
        await update_setting(ctx.guild.id, "welcome_channel_id", channel.id, ctx.guild.name)
        await ctx.send(f"✅ **Welcome Sector** linked to {channel.mention}.")

    @setup.command(name="rules")
    @commands.has_permissions(manage_guild=True)
    async def setup_rules(self, ctx, channel: discord.TextChannel):
        await update_setting(ctx.guild.id, "rules_channel_id", channel.id, ctx.guild.name)
        await ctx.send(f"✅ **Rules Sector** linked to {channel.mention}.")

    @setup.command(name="verify")
    @commands.has_permissions(manage_guild=True)
    async def setup_verify(self, ctx, channel: discord.TextChannel):
        await update_setting(ctx.guild.id, "verify_channel_id", channel.id, ctx.guild.name)
        await ctx.send(f"✅ **Verification Sector** linked to {channel.mention}.")

    @setup.command(name="role")
    @commands.has_permissions(manage_guild=True)
    async def setup_role(self, ctx, role: discord.Role):
        await update_setting(ctx.guild.id, "auto_role_id", role.id, ctx.guild.name)
        await ctx.send(f"✅ **Auto-Role** synchronized to **{role.name}**.")

    @setup.command(name="offset")
    @commands.has_permissions(manage_guild=True)
    async def setup_offset(self, ctx, hours: int):
        if not -12 <= hours <= 14:
            return await ctx.send("❌ **Error:** Offset must be between -12 and +14.")
        await update_setting(ctx.guild.id, "server_offset_hours", hours, ctx.guild.name)
        await ctx.send(f"✅ **Internal Clock** offset by {hours:+} hours relative to UTC.")

async def setup(bot):
    await bot.add_cog(Settings(bot))