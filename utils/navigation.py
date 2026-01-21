"""
FILE: navigation.py
USE: Shared helpers for lightweight Discord navigation messaging.
"""
from __future__ import annotations

import discord


async def go_to_command_center(interaction: discord.Interaction) -> None:
    """Share the /gyper commands directory without interactive menus."""
    utility = interaction.client.get_cog("Utility")
    if not utility:
        await interaction.response.send_message(
            "Open `/gyper commands` to see the command directory.",
            ephemeral=True,
        )
        return

    guild_name = interaction.guild.name if interaction.guild else None
    embed = utility._build_command_directory(guild_name)
    await interaction.response.edit_message(embed=embed, view=None)
