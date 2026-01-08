"""
FILE: cogs/settings.py
USE: Configuration management for server admins.
FEATURES: SQL-backed setup, channel linking, auto-role, and clock sync.
"""
import asyncio
import random
import re
import discord
from discord.ext import commands
from assets import MARCIA_QUOTES
from database import (
    add_ignored_channel,
    get_ignored_channels,
    get_settings,
    remove_ignored_channel,
    update_setting,
)


def _marcia_line(prefix: str | None = None) -> str:
    """Injects a lore-friendly line to keep Marcia in character."""
    quote = random.choice(MARCIA_QUOTES)
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


def _channels_from_message(msg: discord.Message, guild: discord.Guild) -> list[discord.TextChannel]:
    channels = list(msg.channel_mentions)
    for match in re.findall(r"\d{15,20}", msg.content or ""):
        channel = guild.get_channel(int(match))
        if channel and channel not in channels:
            channels.append(channel)
    return channels


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
    def __init__(self, cog, setup_channel: discord.abc.Messageable | None):
        super().__init__(timeout=90)
        self.cog = cog
        self.setup_channel = setup_channel

    @discord.ui.button(label="Start Guided Setup", style=discord.ButtonStyle.primary, emoji="🛰️")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "📡 Spinning up Marcia's console here. Answer the prompts in this channel.",
            ephemeral=True,
        )
        await self.cog.run_setup_wizard(
            interaction.user,
            interaction.guild,
            self.setup_channel or interaction.channel,
        )

    @discord.ui.button(label="Sector Audit", style=discord.ButtonStyle.secondary, emoji="🛰️")
    async def audit(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog._build_audit_embed(interaction.guild)
        await self.cog._safe_interaction_reply(interaction, embed=embed, ephemeral=True)

    @discord.ui.button(label="Setup Help", style=discord.ButtonStyle.secondary, emoji="📘")
    async def help(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.cog._build_help_embed()
        await self.cog._safe_interaction_reply(interaction, embed=embed, ephemeral=True)

    @discord.ui.button(label="Ignore Channels", style=discord.ButtonStyle.secondary, emoji="🚫")
    async def ignore_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._prompt_ignore_channels(interaction)

    @discord.ui.button(label="Unignore Channels", style=discord.ButtonStyle.secondary, emoji="✅")
    async def unignore_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._prompt_unignore_channels(interaction)

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _safe_send(self, ctx, *, ephemeral: bool = False, **kwargs):
        interaction = getattr(ctx, "interaction", None)
        if interaction:
            return await self.bot._safe_interaction_reply(
                interaction, ephemeral=ephemeral, **kwargs
            )
        kwargs.pop("ephemeral", None)
        return await ctx.send(**kwargs)

    async def _safe_interaction_reply(
        self, interaction: discord.Interaction, **kwargs
    ):
        return await self.bot._safe_interaction_reply(interaction, **kwargs)

    # --- Internal helpers ---
    async def _prompt_ignore_channels(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.send_message(
            "🚫 Drop channel mentions or IDs here to ignore. Type `cancel` to abort.",
            ephemeral=True,
        )

        def check(msg: discord.Message):
            return msg.author.id == interaction.user.id and msg.channel == interaction.channel

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            return await self._safe_interaction_reply(
                interaction,
                content="⌛ Timed out. Try again from `/setup` when ready.",
                ephemeral=True,
            )

        if msg.content.lower().strip() == "cancel":
            return await msg.reply(_marcia_line("Abort confirmed."))

        channels = _channels_from_message(msg, interaction.guild)
        if not channels:
            return await msg.reply("❌ Couldn't read those channels. Try again.")

        for channel in channels:
            await add_ignored_channel(interaction.guild.id, channel.id)
        await msg.reply("✅ Added to the ignore list.")

    async def _prompt_unignore_channels(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        await interaction.response.send_message(
            "✅ Mention ignored channels to remove, or paste IDs. Type `cancel` to abort.",
            ephemeral=True,
        )

        def check(msg: discord.Message):
            return msg.author.id == interaction.user.id and msg.channel == interaction.channel

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            return await self._safe_interaction_reply(
                interaction,
                content="⌛ Timed out. Try again from `/setup` when ready.",
                ephemeral=True,
            )

        if msg.content.lower().strip() == "cancel":
            return await msg.reply(_marcia_line("Abort confirmed."))

        channels = _channels_from_message(msg, interaction.guild)
        if not channels:
            return await msg.reply("❌ Couldn't read those channels. Try again.")

        for channel in channels:
            await remove_ignored_channel(interaction.guild.id, channel.id)
        await msg.reply("✅ Removed from the ignore list.")

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

    @commands.hybrid_command(name="setup", description="Configure Marcia's channels, roles, and offset.")
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx):
        """Displays the current server configuration and setup status."""
        data = await get_settings(ctx.guild.id)
        ignored_channels = await get_ignored_channels(ctx.guild.id)

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
                "Use **Start Guided Setup** to configure channels and auto-role in this channel.\n"
                "Run **Sector Audit** to review links and permissions.\n"
                "Use **Ignore Channels** or **Unignore Channels** to manage event exclusions."
            ),
            inline=False
        )
        readable = []
        for cid in ignored_channels:
            channel = ctx.guild.get_channel(cid)
            readable.append(channel.mention if channel else f"`#deleted ({cid})`")
        ignored_value = ", ".join(readable) if readable else "_None configured_"
        embed.add_field(
            name="🚫 Ignored Channels",
            value=ignored_value,
            inline=False,
        )

        await self._safe_send(ctx, embed=embed, view=SetupWizardView(self, ctx.channel))

    async def run_setup_wizard(
        self,
        user: discord.User,
        guild: discord.Guild | None,
        setup_channel: discord.abc.Messageable | None,
    ):
        if not guild or not setup_channel:
            return

        def check(msg: discord.Message):
            return msg.author.id == user.id and msg.channel == setup_channel

        try:
            intro = (
                "🛰️ **Marcia OS // Guided Setup**\n"
                f"Sector: **{guild.name}**\n"
                "I'll tune your channels and auto-role. Answer in this channel or I'll time out."
            )
            await setup_channel.send(intro)
            await setup_channel.send(_marcia_line("While you think, remember:"))

            questions = [
                ("event_channel_id", "Which channel receives mission pings? Mention it or paste an ID."),
                ("chat_channel_id", "Where should level-up chatter go?"),
                ("welcome_channel_id", "Where do you want arrival logs?"),
                ("rules_channel_id", "Channel for your rules codex?"),
                ("verify_channel_id", "Verification checkpoint channel?"),
            ]

            for setting_key, prompt in questions:
                await setup_channel.send(f"💬 {prompt} (type `skip` to leave unchanged)")
                msg = await self.bot.wait_for("message", check=check, timeout=180)
                if msg.content.lower().strip() == "skip":
                    await setup_channel.send(_marcia_line("Skipping. Your call."))
                    continue
                found_channel = _channel_from_message(msg, guild)
                if found_channel:
                    await update_setting(guild.id, setting_key, found_channel.id, guild.name)
                    await msg.reply(f"✅ Linked **{found_channel.mention}**.")
                else:
                    await setup_channel.send("❌ Couldn't read that channel. Run `/setup` again when you're ready.")

            await setup_channel.send("🎚️ Mention the auto-role for new arrivals (or say `skip`).")
            role_msg = await self.bot.wait_for("message", check=check, timeout=120)
            if role_msg.content.lower().strip() != "skip":
                role = _role_from_message(role_msg, guild)
                if role:
                    await update_setting(guild.id, "auto_role_id", role.id, guild.name)
                    await role_msg.reply(f"✅ I'll tag newcomers with **{role.name}**.")
                else:
                    await setup_channel.send("❌ Couldn't find that role. Run `/setup` again when ready.")
            else:
                await setup_channel.send(_marcia_line("Leaving auto-role untouched."))

            await setup_channel.send(
                "🚫 Mention any channels Marcia should ignore (or type `skip`)."
            )
            ignore_msg = await self.bot.wait_for("message", check=check, timeout=120)
            if ignore_msg.content.lower().strip() != "skip":
                if ignore_msg.channel_mentions:
                    for mentioned in ignore_msg.channel_mentions:
                        await add_ignored_channel(guild.id, mentioned.id)
                    await ignore_msg.reply("✅ Ignoring those channels.")
                else:
                    await setup_channel.send(
                        "❌ Couldn't read those channels. Use `/setup` again if needed."
                    )

            await setup_channel.send(
                "🔊 Mention channels to unmute (or type `skip`)."
            )
            unignore_msg = await self.bot.wait_for("message", check=check, timeout=120)
            if unignore_msg.content.lower().strip() != "skip":
                if unignore_msg.channel_mentions:
                    for mentioned in unignore_msg.channel_mentions:
                        await remove_ignored_channel(guild.id, mentioned.id)
                    await unignore_msg.reply("✅ Channels removed from the ignore list.")
                else:
                    await setup_channel.send(
                        "❌ Couldn't read those channels. Use `/setup` again if needed."
                    )

            await update_setting(guild.id, "server_offset_hours", -2, guild.name)
            await setup_channel.send("🕒 Clock set to **UTC-2** (game time). I'll ignore local clocks.")

            await setup_channel.send(
                "🎉 Setup pass complete. Run `/setup` in the server to verify links."
            )
        except asyncio.TimeoutError:
            await setup_channel.send("⌛ Timeout. Ping me again with `/setup` when you're ready.")

    async def _build_audit_embed(self, guild: discord.Guild | None) -> discord.Embed:
        data = await get_settings(guild.id) if guild else {}

        embed = discord.Embed(
            title="🛰️ Marcia OS | Sector Audit",
            description="Reviewing comms, roles, and timers for Dark War Survival ops.",
            color=0x5865F2,
        )

        checks = {
            "Event": self._channel_status(guild, data.get("event_channel_id")),
            "Chat": self._channel_status(guild, data.get("chat_channel_id")),
            "Welcome": self._channel_status(guild, data.get("welcome_channel_id")),
            "Rules": self._channel_status(guild, data.get("rules_channel_id")),
            "Verify": self._channel_status(guild, data.get("verify_channel_id")),
            "Auto-Role": self._role_status(guild, data.get("auto_role_id")),
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
        return embed

    def _build_help_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🛠️ Marcia OS | Setup Intelligence",
            description="Follow these steps to ensure Marcia is fully operational in your server.",
            color=0x3498db,
        )
        embed.add_field(
            name="1️⃣ The Event Sector",
            value="Linking the **Events** channel is vital. This is where Marcia will announce new Missions and Trading updates.",
            inline=False,
        )
        embed.add_field(
            name="2️⃣ Auto-Role Logic",
            value="Make sure Marcia's role is **higher** than the role you are trying to assign in the Discord Role Hierarchy, or she won't be able to give it to members.",
            inline=False,
        )
        embed.add_field(
            name="3️⃣ Time Sync",
            value="All missions and reminders run on the game's **UTC-2** clock. No local offset needed.",
            inline=False,
        )
        return embed

async def setup(bot):
    bot.remove_command("setup")
    await bot.add_cog(Settings(bot))
