"""
FILE: cogs/heroes.py
USE: Hero codex menu and detail views.
"""
from pathlib import Path

import discord
from discord.ext import commands


HEROES = {
    "marcia": {
        "name": "Marcia :marcia:",
        "type": ":stier::goldfragment:",
        "skills": [
            (
                "Cluster - Annihilation",
                "\n".join([
                    "Base: Deals damage equal to **600% attack** to enemies.",
                    "Star scaling:",
                    "⭐ +180%",
                    "⭐⭐ +360%",
                    "⭐⭐⭐ +540%",
                    "⭐⭐⭐⭐ +780%",
                    "⭐⭐⭐⭐⭐ +1200%",
                ]),
            ),
            (
                "Infusion - Penetration",
                "\n".join([
                    "Base: Deals damage equal to **140% attack** to enemies.",
                    "Star scaling:",
                    "⭐ +18%",
                    "⭐⭐ +36%",
                    "⭐⭐⭐ +54%",
                    "⭐⭐⭐⭐ +78%",
                    "⭐⭐⭐⭐⭐ +120%",
                ]),
            ),
            (
                "Shadow of Gale",
                "\n".join([
                    "Base: Increases Riders’ HP by **5%**.",
                    "Star scaling (Rider Battle Damage):",
                    "⭐ +5%",
                    "⭐⭐ +8%",
                    "⭐⭐⭐ +12%",
                    "⭐⭐⭐⭐ +18%",
                    "⭐⭐⭐⭐⭐ +25%",
                ]),
            ),
            (
                "High Morale",
                "\n".join([
                    "Attack +10%",
                    "Defense +10%",
                    "Troop capacity +5%",
                ]),
            ),
        ],
        "image": Path("data/heroes/marcia.webp"),
    }
}


def _build_hero_list_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🧬 Hero Codex",
        description="Select a hero to view their profile, skills, and scaling.",
        color=0x9b59b6,
    )
    hero_lines = [f"• **{data['name']}** — {data['type']}" for data in HEROES.values()]
    embed.add_field(name="Available Heroes", value="\n".join(hero_lines), inline=False)
    embed.set_footer(text="More heroes will be added as intel is verified.")
    return embed


def _build_hero_embed(hero_key: str) -> tuple[discord.Embed, discord.File | None]:
    hero = HEROES[hero_key]
    embed = discord.Embed(
        title=f"🛰️ {hero['name']}",
        description="Hero dossier and skill scaling.",
        color=0x5865F2,
    )
    embed.add_field(name="Hero Type", value=hero["type"], inline=False)
    for skill_name, skill_text in hero["skills"]:
        embed.add_field(name=f"✨ {skill_name}", value=skill_text, inline=False)

    image_file = None
    image_path = hero.get("image")
    if image_path and image_path.exists():
        image_file = discord.File(image_path, filename=image_path.name)
        embed.set_image(url=f"attachment://{image_path.name}")

    embed.set_footer(text="Stats are sourced from verified in-game data.")
    return embed, image_file


class HeroSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=data["name"].replace(" :marcia:", ""),
                description=data["type"],
                value=key,
                emoji="🧬",
            )
            for key, data in HEROES.items()
        ]
        super().__init__(
            placeholder="Choose a hero…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        hero_key = self.values[0]
        embed, image_file = _build_hero_embed(hero_key)
        attachments = [image_file] if image_file else []
        await interaction.response.edit_message(
            embed=embed,
            view=self.view,
            attachments=attachments,
        )


class HeroSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(HeroSelect())


class Heroes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(description="Browse the hero codex and view hero details.")
    async def heroes(self, ctx):
        embed = _build_hero_list_embed()
        view = HeroSelectView()
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Heroes(bot))
