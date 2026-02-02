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
from utils.assets import MARCIA_QUOTES
from database import (
    add_ignored_channel,
    get_ignored_channels,
    get_scanner_config,
    get_settings,
    remove_ignored_channel,
    SCANNER_CONFIG_KEYS,
    upsert_scanner_config,
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


class SetupFeatureSelect(discord.ui.Select):
    def __init__(self, cog):
        options = [
            discord.SelectOption(
                label="Events channel",
                description="Where mission announcements post",
                value="event_channel_id",
                emoji="📡",
            ),
            discord.SelectOption(
                label="Chat channel",
                description="Where level-up chatter lands",
                value="chat_channel_id",
                emoji="💬",
            ),
            discord.SelectOption(
                label="Welcome channel",
                description="Join/leave messages live here",
                value="welcome_channel_id",
                emoji="👋",
            ),
            discord.SelectOption(
                label="Rules channel",
                description="Rules + onboarding posts",
                value="rules_channel_id",
                emoji="📜",
            ),
            discord.SelectOption(
                label="Verify channel",
                description="Verification checkpoint",
                value="verify_channel_id",
                emoji="🛂",
            ),
            discord.SelectOption(
                label="Auto-role",
                description="Role granted to new members",
                value="auto_role_id",
                emoji="🔏",
            ),
            discord.SelectOption(
                label="AI mention replies",
                description="Toggle auto-replies to mentions",
                value="ai_replies_enabled",
                emoji="🤖",
            ),
        ]
        if cog.is_marcia_server:
            options.extend([
                discord.SelectOption(
                    label="Feedback & suggestions",
                    description="Where community ideas go",
                    value="feedback_channel_id",
                    emoji="💡",
                ),
                discord.SelectOption(
                    label="Global analytics",
                    description="Hourly fun stats channel",
                    value="analytics_channel_id",
                    emoji="📊",
                ),
            ])
        super().__init__(
            placeholder="Select a feature to edit…",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await self.cog._prompt_feature_update(interaction, self.values[0])


class SetupWizardView(discord.ui.View):
    def __init__(self, cog, setup_channel: discord.abc.Messageable | None):
        super().__init__(timeout=90)
        self.cog = cog
        self.setup_channel = setup_channel
        self.add_item(SetupFeatureSelect(cog))

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
        self.is_marcia_server = False

    async def _ensure_scanner_config(self, guild_id: int) -> tuple[dict | None, list[str]]:
        config = await get_scanner_config(guild_id)
        missing = [
            key
            for key in SCANNER_CONFIG_KEYS
            if not config or key not in config or config.get(key) is None
        ]
        if missing:
            config = await upsert_scanner_config(
                guild_id,
                profile_scan_enabled=1,
                duel_scan_enabled=1,
            )
            missing = [
                key
                for key in SCANNER_CONFIG_KEYS
                if not config or key not in config or config.get(key) is None
            ]
        return config, missing

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

    async def _prompt_feature_update(self, interaction: discord.Interaction, feature_key: str) -> None:
        if not interaction.guild:
            return

        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "🔒 You need Manage Server permissions to update setup.",
                ephemeral=True,
            )

        feature_labels = {
            "event_channel_id": "Events channel",
            "chat_channel_id": "Chat channel",
            "welcome_channel_id": "Welcome channel",
            "rules_channel_id": "Rules channel",
            "verify_channel_id": "Verify channel",
            "feedback_channel_id": "Feedback & suggestions channel",
            "analytics_channel_id": "Global analytics channel",
            "auto_role_id": "Auto-role",
            "ai_replies_enabled": "AI mention replies",
        }
        label = feature_labels.get(feature_key, "Feature")

        if feature_key == "ai_replies_enabled":
            await interaction.response.send_message(
                f"🤖 **{label}** - type `on` or `off` to toggle mention replies.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"📡 **{label}** - mention it here, paste an ID, or type `clear` to unset.",
                ephemeral=True,
            )

        def check(msg: discord.Message):
            return msg.author.id == interaction.user.id and msg.channel == interaction.channel

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            return await self._safe_interaction_reply(
                interaction,
                content="⌛ Timed out. Open `/setup` again when ready.",
                ephemeral=True,
            )

        content = msg.content.strip().lower()
        if content == "cancel":
            return await msg.reply(_marcia_line("Abort confirmed."))

        if feature_key == "ai_replies_enabled":
            if content in {"on", "enable", "enabled", "yes", "y"}:
                await update_setting(interaction.guild.id, "ai_replies_enabled", 1, interaction.guild.name)
                return await msg.reply("✅ AI mention replies enabled.")
            if content in {"off", "disable", "disabled", "no", "n"}:
                await update_setting(interaction.guild.id, "ai_replies_enabled", 0, interaction.guild.name)
                return await msg.reply("✅ AI mention replies disabled.")
            return await msg.reply("❌ I need `on` or `off` to update AI mention replies.")

        if feature_key == "auto_role_id":
            if content == "clear":
                await update_setting(interaction.guild.id, "auto_role_id", None, interaction.guild.name)
                return await msg.reply("✅ Auto-role cleared.")
            role = _role_from_message(msg, interaction.guild)
            if not role:
                return await msg.reply("❌ Couldn't find that role. Try `/setup` again.")
            await update_setting(interaction.guild.id, "auto_role_id", role.id, interaction.guild.name)
            return await msg.reply(f"✅ Auto-role set to **{role.name}**.")

        if content == "clear":
            await update_setting(interaction.guild.id, feature_key, None, interaction.guild.name)
            return await msg.reply(f"✅ {label} cleared.")

        channel = _channel_from_message(msg, interaction.guild)
        if not channel:
            return await msg.reply("❌ Couldn't read that channel. Try again.")
        await update_setting(interaction.guild.id, feature_key, channel.id, interaction.guild.name)
        await msg.reply(f"✅ {label} linked to {channel.mention}.")

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
        scan_config, scan_missing = await self._ensure_scanner_config(ctx.guild.id)
        is_marcia_server = ctx.guild.id == 1454704176662843525
        self.is_marcia_server = is_marcia_server

        embed = discord.Embed(
            title="📡 MARCIA OS | System Diagnostics",
            description=(
                "Pick a feature from the dropdown to edit one channel at a time. "
                "All links should be active for clean ops and reminders."
            ),
            color=0x2b2d31
        )

        if data:
            embed.add_field(name="🛰️ Event Sector", value=self._channel_status(ctx.guild, data['event_channel_id'])[0], inline=True)
            embed.add_field(name="💬 Chat Sector", value=self._channel_status(ctx.guild, data['chat_channel_id'])[0], inline=True)
            embed.add_field(name="👋 Welcome Sector", value=self._channel_status(ctx.guild, data['welcome_channel_id'])[0], inline=True)
            embed.add_field(name="📜 Rules Sector", value=self._channel_status(ctx.guild, data['rules_channel_id'])[0], inline=True)
            embed.add_field(name="🛂 Verify Sector", value=self._channel_status(ctx.guild, data['verify_channel_id'])[0], inline=True)
            if is_marcia_server:
                embed.add_field(
                    name="💡 Feedback Sector",
                    value=self._channel_status(ctx.guild, data.get('feedback_channel_id'))[0],
                    inline=True,
                )
                embed.add_field(
                    name="📊 Analytics Sector",
                    value=self._channel_status(ctx.guild, data.get('analytics_channel_id'))[0],
                    inline=True,
                )
            embed.add_field(name="🔏 Auto-Role", value=self._role_status(ctx.guild, data['auto_role_id'])[0], inline=True)
            ai_enabled = data.get("ai_replies_enabled", 1)
            ai_status = "✅ Enabled" if ai_enabled else "⏸️ Disabled"
            embed.add_field(name="🤖 AI Replies", value=ai_status, inline=True)

            embed.set_footer(text="System Clock: UTC-2 (Dark War Survival global time)")
        else:
            embed.description = "⚠️ **CRITICAL ERROR:** No configuration found in databank. Initialize sectors immediately."

        embed.add_field(
            name="🛠️ Maintenance Commands",
            value=(
                "Use the **feature dropdown** to update a single channel or role.\n"
                "Use **Setup Help** for definitions and notes.\n"
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
        if scan_config:
            enabled = {
                "profile_scan_enabled": "✅ Enabled" if scan_config.get("profile_scan_enabled") else "⏸️ Disabled",
                "duel_scan_enabled": "✅ Enabled" if scan_config.get("duel_scan_enabled") else "⏸️ Disabled",
            }
            scan_lines = [f"**{key}**: {value}" for key, value in enabled.items()]
        else:
            scan_lines = ["⚠️ Missing scan configuration."]
        if scan_missing:
            scan_lines.append(f"Missing keys: {', '.join(scan_missing)}")
        embed.add_field(
            name="🧪 Scan Configuration",
            value="\n".join(scan_lines),
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
                "🛰️ **Marcia // Guided Setup**\n"
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
            title="🛰️ Marcia | Sector Audit",
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
        if guild and guild.id == 1454704176662843525:
            checks["Feedback"] = self._channel_status(guild, data.get("feedback_channel_id"))
            checks["Analytics"] = self._channel_status(guild, data.get("analytics_channel_id"))

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
            title="🛠️ Marcia | Setup Intelligence",
            description="Each feature below can be configured from the `/setup` dropdown.",
            color=0x3498db,
        )
        embed.add_field(
            name="📡 Events channel",
            value="Where mission announcements and scheduled ops are posted.",
            inline=False,
        )
        embed.add_field(
            name="💬 Chat channel",
            value="Optional stream for level-up chatter and daily noise.",
            inline=False,
        )
        embed.add_field(
            name="👋 Welcome channel",
            value="Join/leave messages and arrival guidance.",
            inline=False,
        )
        embed.add_field(
            name="📜 Rules channel",
            value="Your rules codex. Marcia can post here during setup for the Marcia Server.",
            inline=False,
        )
        embed.add_field(
            name="🛂 Verify channel",
            value="Checkpoint for verification instructions.",
            inline=False,
        )
        if self.is_marcia_server:
            embed.add_field(
                name="💡 Feedback & suggestions",
                value="Community ideas live here. Marcia still DMs akrott privately.",
                inline=False,
            )
            embed.add_field(
                name="📊 Global analytics",
                value="Hourly fun stats channel (auto-created in the Marcia Server).",
                inline=False,
            )
        embed.add_field(
            name="🔏 Auto-role",
            value="Role granted to new arrivals. Keep Marcia’s role **above** it.",
            inline=False,
        )
        embed.add_field(
            name="🤖 AI mention replies",
            value="Toggle whether Marcia responds to mentions and direct replies.",
            inline=False,
        )
        embed.add_field(
            name="🎣 Trading terminal",
            value="Run `/setup_trade` in the channel you want the Fish-Link menu pinned.",
            inline=False,
        )
        return embed

async def setup(bot):
    bot.remove_command("setup")
    await bot.add_cog(Settings(bot))
