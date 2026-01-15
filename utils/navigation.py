"""
FILE: navigation.py
USE: Shared navigation helpers for menu-based Discord UI flows.
"""
from __future__ import annotations

import discord


async def go_to_command_center(interaction: discord.Interaction) -> None:
    """Return the user to the /commands home view if available."""
    from cogs.utility import CommandCenterView

    utility = interaction.client.get_cog("Utility")
    if not utility:
        await interaction.response.send_message(
            "Open `/commands` to return to the Marcia Command Center.",
            ephemeral=True,
        )
        return

    guild_name = interaction.guild.name if interaction.guild else None
    embed = utility._build_command_center_embed("home", guild_name)
    view = CommandCenterView(utility, guild_name)
    await interaction.response.edit_message(embed=embed, view=view)
