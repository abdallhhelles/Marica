"""
FILE: cogs/settings.py
USE: Configuration management for server admins.
FEATURES: SQL-backed setup, channel linking, auto-role, and clock sync.
"""
import asyncio
import random
import discord
from discord.ext import commands
from assets import MARICA_QUOTES
from database import update_setting, get_settings


def _marica_line(prefix: str | None = None) -> str:
    """Injects a lore-friendly line to keep Marica in character."""
    quote = random.choice(MARICA_QUOTES)
    return f"{prefix + ' ' if prefix else ''}{quote}"


def _channel_from_message(msg: discord.Message, guild: discord.Guild) -> discord.TextChannel | None:
    if msg.channel_mentions:
        return msg.channel_mentions[0]
    try:
        cid = int(msg.content.strip())
        return guild.get_channel(cid)
    except (ValueError, AttributeError):
        pass
    lowered = msg.content.strip().lstrip('#').lower()
    return discord.utils.get(guild.text_channels, name=lowered)


def _role_from_message(msg: discord.Message, guild: discord.Guild) -> discord.Role | None:
    if msg.role_mentions:
        return msg.role_mentions[0]
    try:
        rid = int(msg.content.strip())
        return guild.get_role(rid)
    except (ValueError, AttributeError):
        pass
    lowered = msg.content.strip().lstrip('@').lower()
    return discord.utils.get(guild.roles, name=lowered)


class SetupWizardView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=90)
        self.cog = cog

    @discord.ui.button(label="Start Guided Setup", style=discord.ButtonStyle.primary, emoji="🛰️")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📡 Spinning up Marcia's console. Check your DMs!", ephemeral=True)
        await self.cog.run_setup_wizard(interaction.user, interaction.guild)

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- Internal helpers ---

    def _channel_status(self, guild: discord.Guild, channel_id: int | None) -> tuple[str, str]:
        """Return a human-friendly status string plus a short warning slug."""
        if not channel_id:
            return "❌ **LINK MISSING**", "missing"

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return "⚠️ **CHANNEL DELETED**", "missing"

        perms = channel.permissions_for(guild.me)
        if not perms.send_messages:
            return f"{channel.mention} (🚫 **NO PERMS**)", "perms"
        return f"{channel.mention} (✅ **ACTIVE**)", "ok"

    def _role_status(self, guild: discord.Guild, role_id: int | None) -> tuple[str, str]:
        if not role_id:
            return "❌ **LINK MISSING**", "missing"

        role = guild.get_role(role_id)
        if not role:
            return "⚠️ **ROLE DELETED**", "missing"
        if guild.me.top_role <= role:
            return f"{role.mention} (🚫 **MOVE ME ABOVE**)", "perms"
        return f"{role.mention} (✅ **ACTIVE**)", "ok"

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

        if data:
            embed.add_field(name="🛰️ Event Sector", value=self._channel_status(ctx.guild, data['event_channel_id'])[0], inline=True)
            embed.add_field(name="💬 Chat Sector", value=self._channel_status(ctx.guild, data['chat_channel_id'])[0], inline=True)
            embed.add_field(name="👋 Welcome Sector", value=self._channel_status(ctx.guild, data['welcome_channel_id'])[0], inline=True)
            embed.add_field(name="📜 Rules Sector", value=self._channel_status(ctx.guild, data['rules_channel_id'])[0], inline=True)
            embed.add_field(name="🛂 Verify Sector", value=self._channel_status(ctx.guild, data['verify_channel_id'])[0], inline=True)
            embed.add_field(name="🔏 Auto-Role", value=self._role_status(ctx.guild, data['auto_role_id'])[0], inline=True)
            
            embed.set_footer(text="System Clock: UTC-2 (Dark War Survival global time)")
        else:
            embed.description = "⚠️ **CRITICAL ERROR:** No configuration found in databank. Initialize sectors immediately."

        embed.add_field(
            name="🛠️ Maintenance Commands",
            value=(
                "`!setup events #channel` - Mission/Event broadcasts\n"
                "`!setup chat #channel` - Main interaction zone\n"
                "`!setup role @role` - Auto-role for arrivals\n"
                "`!setup help` - View detailed setup guide\n"
                "Tap the button below for a guided DM setup with Marcia."
            ),
            inline=False
        )

        await ctx.send(embed=embed, view=SetupWizardView(self))

    @setup.command(name="audit")
    @commands.has_permissions(manage_guild=True)
    async def setup_audit(self, ctx):
        """Runs a quick health check of channels, permissions, and the server clock."""
        data = await get_settings(ctx.guild.id) or {}

        embed = discord.Embed(
            title="🛰️ Marcia OS | Sector Audit",
            description="Reviewing comms, roles, and timers for Dark War Survival ops.",
            color=0x5865F2,
        )

        # Channel/role validations
        checks = {
            "Event": self._channel_status(ctx.guild, data.get("event_channel_id")),
            "Chat": self._channel_status(ctx.guild, data.get("chat_channel_id")),
            "Welcome": self._channel_status(ctx.guild, data.get("welcome_channel_id")),
            "Rules": self._channel_status(ctx.guild, data.get("rules_channel_id")),
            "Verify": self._channel_status(ctx.guild, data.get("verify_channel_id")),
            "Auto-Role": self._role_status(ctx.guild, data.get("auto_role_id")),
        }

        warnings = [name for name, (_, flag) in checks.items() if flag != "ok"]
        status_lines = [f"**{name}:** {value}" for name, (value, _) in checks.items()]
        embed.add_field(name="Links", value="\n".join(status_lines), inline=False)

        embed.add_field(
            name="⏱️ Server Clock",
            value="UTC-2 (Dark War Survival global clock)",
            inline=False,
        )

        suggestion = "✅ All green. Drones are mission-ready." if not warnings else (
            "⚠️ Fix these before battle: " + ", ".join(warnings)
        )
        embed.set_footer(text=suggestion)

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
            value="All missions and reminders run on the game's **UTC-2** clock. No local offset needed.",
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
    async def setup_offset(self, ctx, hours: int = -2):
        await update_setting(ctx.guild.id, "server_offset_hours", -2, ctx.guild.name)
        await ctx.send("🕒 Clock is locked to **UTC-2** for Dark War Survival. Local time is ignored.")

    async def run_setup_wizard(self, user: discord.User, guild: discord.Guild | None):
        if not guild:
            return

        def check(msg: discord.Message):
            return msg.author.id == user.id and isinstance(msg.channel, discord.DMChannel)

        current = await get_settings(guild.id) or {}

        try:
            intro = (
                "🛰️ **Marcia OS // Guided Setup**\n"
                f"Sector: **{guild.name}**\n"
                "I'll tune your channels and auto-role. Answer quickly or I'll time out."
            )
            await user.send(intro)
            await user.send(_marica_line("While you think, remember:"))

            questions = [
                ("event_channel_id", "Which channel receives mission pings? Mention it or paste an ID."),
                ("chat_channel_id", "Where should level-up chatter go?"),
                ("welcome_channel_id", "Where do you want arrival logs?"),
                ("rules_channel_id", "Channel for your rules codex?"),
                ("verify_channel_id", "Verification checkpoint channel?"),
            ]

            for setting_key, prompt in questions:
                await user.send(f"💬 {prompt} (type `skip` to leave unchanged)")
                msg = await self.bot.wait_for("message", check=check, timeout=180)
                if msg.content.lower().strip() == "skip":
                    await user.send(_marica_line("Skipping. Your call."))
                    continue
                channel = _channel_from_message(msg, guild)
                if channel:
                    await update_setting(guild.id, setting_key, channel.id, guild.name)
                    await user.send(f"✅ Linked **{channel.mention}**.")
                else:
                    await user.send("❌ Couldn't read that channel. Try `!setup events #channel` later.")

            await user.send("🎚️ Mention the auto-role for new arrivals (or say `skip`).")
            role_msg = await self.bot.wait_for("message", check=check, timeout=120)
            if role_msg.content.lower().strip() != "skip":
                role = _role_from_message(role_msg, guild)
                if role:
                    await update_setting(guild.id, "auto_role_id", role.id, guild.name)
                    await user.send(f"✅ I'll tag newcomers with **{role.name}**.")
                else:
                    await user.send("❌ Couldn't find that role. Use `!setup role @role` later.")
            else:
                await user.send(_marica_line("Leaving auto-role untouched."))

            await update_setting(guild.id, "server_offset_hours", -2, guild.name)
            await user.send("🕒 Clock set to **UTC-2** (game time). I'll ignore local clocks.")

            await user.send(
                "🎉 Setup pass complete. Run `!setup` in the server to verify links."
            )
        except asyncio.TimeoutError:
            await user.send("⌛ Timeout. Ping me again with `!setup` when you're ready.")

async def setup(bot):
    await bot.add_cog(Settings(bot))