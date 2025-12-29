"""
FILE: cogs/reminders.py
USE: Reminder broadcasting with template management.
FEATURES: Guild-scoped template archive, default starter prompts, and ignore-list compliance.
"""

import random

import discord
from discord.ext import commands

from assets import MARICA_QUOTES
from database import (
    add_reminder_template,
    delete_reminder_template,
    get_reminder_templates,
    is_channel_ignored,
)


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild and await is_channel_ignored(ctx.guild.id, ctx.channel.id):
            notice = "🚫 Marcia is muted in this channel. Try another sector."
            if ctx.interaction:
                if not ctx.interaction.response.is_done():
                    await ctx.interaction.response.send_message(notice, ephemeral=True)
            else:
                try:
                    await ctx.author.send(notice)
                except Exception:
                    pass
            return False
        return True

    @commands.hybrid_group(
        name="remind",
        invoke_without_command=True,
        description="Send a reminder from a saved template or manage the archive.",
    )
    async def remind(self, ctx: commands.Context, *, template: str | None = None):
        if not ctx.guild:
            return await ctx.send("❌ Reminders can only be managed inside a server.")
        if template:
            return await self._send_template(ctx, template)

        templates = await get_reminder_templates(ctx.guild.id)
        if not templates:
            return await ctx.send("📂 No reminder templates saved yet.")

        embed = discord.Embed(
            title="🛰️ Reminder Templates",
            description="Pick a template name to broadcast with `/remind send <name>`.",
            color=0x2b2d31,
        )
        for entry in templates:
            embed.add_field(
                name=f"🔹 {entry['template_name']}",
                value=entry['body'],
                inline=False,
            )
        await ctx.send(embed=embed)

    async def _send_template(self, ctx: commands.Context, template: str):
        templates = await get_reminder_templates(ctx.guild.id)
        match = next((t for t in templates if t['template_name'].lower() == template.lower()), None)
        if not match:
            names = ", ".join(t['template_name'] for t in templates) or "none"
            return await ctx.send(f"❌ Template not found. Available: {names}")

        quote = random.choice(MARICA_QUOTES)
        await ctx.send(f"📡 **Reminder:** {match['template_name']}\n{match['body']}\n\n{quote}")

    @remind.command(name="send", description="Broadcast a saved reminder template.")
    async def remind_send(self, ctx: commands.Context, *, template: str):
        await self._send_template(ctx, template)

    @remind.command(name="add", description="Archive a new reminder template.")
    @commands.has_permissions(manage_guild=True)
    async def remind_add(self, ctx: commands.Context, name: str, *, body: str):
        await add_reminder_template(ctx.guild.id, name, body)
        await ctx.send(f"✅ Template `{name}` saved to the archive.")

    @remind.command(name="remove", description="Delete a saved reminder template.")
    @commands.has_permissions(manage_guild=True)
    async def remind_remove(self, ctx: commands.Context, *, name: str):
        await delete_reminder_template(ctx.guild.id, name)
        await ctx.send(f"🗑️ Template `{name}` deleted.")


async def setup(bot):
    await bot.add_cog(Reminders(bot))
