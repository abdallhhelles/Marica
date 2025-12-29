"""
FILE: cogs/akrott.py
PURPOSE: Owner-only control panel for cross-server analytics and broadcast utilities.
"""
import discord
from discord import app_commands
from discord.ext import commands

OWNER_ID = 135894953027960833

MENU_OPTIONS = [
    ("XP Leaderboard", "Live ranking across all linked servers."),
    ("Global Stats Dashboard", "Pulse check on XP, loot, and mission totals."),
    ("Scavenged Items Summary", "Hourly scavenging output, rarity mix, and bottlenecks."),
    ("Rare Drops Feed", "Recent Epic/Mythic drops and the servers they landed in."),
    ("Economy Stats", "Marketplace volume, trade velocity, and sink/source balance."),
    ("Server List, Health, Activity", "Connected sectors, heartbeat status, and presence."),
    ("Send Update DM to all server owners", "Broadcast a short status update via DM."),
    ("Send Announcement to channel by channel_id", "Targeted announcement with a channel override."),
]

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]


def _owner_only(interaction: discord.Interaction) -> bool:
    return interaction.user.id == OWNER_ID


class _OwnerLockedView(discord.ui.View):
    """Base view that denies any interaction from non-owners."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "❌ Access denied. This console is locked to the bot owner.", ephemeral=True
            )
            return False
        return True


class ControlPanelSelect(discord.ui.Select):
    def __init__(self, cog: "AkrottControl"):
        options = [
            discord.SelectOption(
                label=f"{NUMBER_EMOJIS[i]} {label}",
                description=hint[:95],
                value=str(i),
            )
            for i, (label, hint) in enumerate(MENU_OPTIONS)
        ]
        super().__init__(
            placeholder="Choose an action to execute",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        await interaction.response.edit_message(
            embed=self.cog.build_detail_embed(index),
            view=ControlPanelDetail(self.cog, index),
        )


class ControlPanelMenu(_OwnerLockedView):
    def __init__(self, cog: "AkrottControl"):
        super().__init__(timeout=300)
        self.cog = cog
        self.add_item(ControlPanelSelect(cog))


class ControlPanelDetail(_OwnerLockedView):
    def __init__(self, cog: "AkrottControl", selection_index: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.selection_index = selection_index

    @discord.ui.button(label="⬅️ Back to menu", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog.build_menu_embed(), view=ControlPanelMenu(self.cog)
        )


class AkrottControl(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def build_menu_embed(self) -> discord.Embed:
        description_lines = [f"{NUMBER_EMOJIS[i]} {label}" for i, (label, _) in enumerate(MENU_OPTIONS)]
        embed = discord.Embed(
            title="🛰️ Owner Control Panel",
            description="\n".join(description_lines),
            color=0x2b2d31,
        )
        embed.set_footer(text="Ephemeral session | Only akrott can operate this console.")
        return embed

    def build_detail_embed(self, selection_index: int) -> discord.Embed:
        title, hint = MENU_OPTIONS[selection_index]
        embed = discord.Embed(title=f"{NUMBER_EMOJIS[selection_index]} {title}", color=0x5865F2)
        embed.description = (
            f"📡 **Action Triggered:** {title}\n\n"
            f"🔒 This intel stream stays ephemeral to akrott only.\n"
            f"🧭 Next step: {hint}"
        )
        embed.set_footer(text="Tap Back to reopen the control panel menu.")
        return embed

    @app_commands.command(name="akrott", description="Owner-only control panel for cross-server analytics.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.check(_owner_only)
    async def akrott(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=self.build_menu_embed(), view=ControlPanelMenu(self), ephemeral=True
        )

    @akrott.error
    async def akrott_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Access denied. This console is reserved for akrott.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⚠️ An unexpected error occurred while opening the console.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AkrottControl(bot))
