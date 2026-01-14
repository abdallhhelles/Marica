"""
FILE: cogs/heroes.py
USE: Hero codex menu and detail views.
"""
from pathlib import Path

import discord
from discord.ext import commands


# --------------------
# Emoji references
# --------------------
# NOTE: Use the provided custom emoji IDs so the hero cards match in-game assets.
GOLDFRAGMENT_EMOJI = "<:goldfragment:1460417880922521816>"
BLUEFRAGMENT_EMOJI = "<:bluefragment:1460802947981115552>"
PURPLEFRAGMENT_EMOJI = "<:purplefragment:1460802954411114546>"
STIER_EMOJI = "<:stier:1460422183838027886>"
ATIER_EMOJI = "<:atier:1460802951672234090>"
BTIER_EMOJI = "<:btier:1460802949965025362>"
STAR_EMOJI = "<:star:1460417899708809257>"
MARCIA_EMOJI = "<:marcia:1460422296425468046>"
RIDER_EMBLEM = "<:rideremblem:1460802943744999424>"
FIGHTER_EMBLEM = "<:fighteremblem:1460802946085425315>"
SHOOTER_EMBLEM = "<:shooteremblem:1460802966926659684>"
SEASON1_EMOJI = "<:season1:1460802958651297792>"
SEASON2_EMOJI = "<:season2:1460802961679716586>"
SEASON3_EMOJI = "<:season3:1460802956172460053>"
SEASON4_EMOJI = "<:season4:1460802964095766528>"

# --------------------
# Hero data model
# --------------------
# Add new heroes by following this template so Discord embeds look consistent:
# 1) Provide metadata (name, faction, season, tier, fragment, emblem, portrait).
# 2) Add lore as a list of story paragraphs (ordered).
# 3) Add skills as (name, description) tuples.
# 4) Add exclusive weapon data with flavor lines + star upgrades.
# 5) Optional image should live in data/heroes/<hero>.webp.
# Keep copy concise to fit embed field limits (1024 chars per field).
HEROES: dict[str, dict] = {
    "marcia": {
        "name": "Marcia",
        "faction": "Riders",
        "season": "Season 2",
        "tier_label": "S",
        "tier_emoji": STIER_EMOJI,
        "fragment_emoji": GOLDFRAGMENT_EMOJI,
        "emblem_emoji": RIDER_EMBLEM,
        "season_emoji": SEASON2_EMOJI,
        "portrait_emoji": MARCIA_EMOJI,
        "lore": [
            "Marcia was in her early twenties, always wearing a mischievous grin with a sharp edge behind it. "
            "Before the apocalypse, she was a hacker who could break into any system and turn someone else’s "
            "wealth into her own. Two tiny drones were always buzzing around her, not just tools, but her only "
            "real friends.",
            "When the zombies broke loose, Marcia’s life turned into a real survival game. No more hiding "
            "behind screens. She hacked defense systems, messed with zombies’ senses, and guided hordes away "
            "from survivors. Sometimes she pushed it further, making zombies stumble like puppets while she "
            "laughed from the shadows, carving out safe ground for herself and the few she trusted.",
            "Survivors started to notice her. Some feared her playful unpredictability, others wanted her tech "
            "to boost their odds. Marcia stayed wild and untamed, using drones and hacking to get what she "
            "wanted. She hated rules, but deep down there was still a spark of kindness. At night, when drone "
            "lights flickered through the ruins, her laughter echoed like a strange melody in a dead world.",
            "Her love for mischief never disappeared, but responsibility slowly crept in. She didn’t want to "
            "be a hero, yet she quietly protected struggling souls in a broken world. Whenever her drones lit "
            "up the night sky, people knew peace followed. In this endless end-of-the-world game, Marcia kept "
            "surviving with her brains, her tricks, and her loyal drone buddies.",
        ],
        "skills": [
            (
                "Cluster - Annihilation",
                "\n".join([
                    "Base: Deals damage equal to **600% attack** to enemies.",
                    "Star scaling:",
                    f"{STAR_EMOJI} +180%",
                    f"{STAR_EMOJI * 2} +360%",
                    f"{STAR_EMOJI * 3} +540%",
                    f"{STAR_EMOJI * 4} +780%",
                    f"{STAR_EMOJI * 5} +1200%",
                ]),
            ),
            (
                "Infusion - Penetration",
                "\n".join([
                    "Base: Deals damage equal to **140% attack** to enemies.",
                    "Star scaling:",
                    f"{STAR_EMOJI} +18%",
                    f"{STAR_EMOJI * 2} +36%",
                    f"{STAR_EMOJI * 3} +54%",
                    f"{STAR_EMOJI * 4} +78%",
                    f"{STAR_EMOJI * 5} +120%",
                ]),
            ),
            (
                "Shadow of Gale",
                "\n".join([
                    "Base: Increases Riders’ HP by **5%**.",
                    "Star scaling (Rider Battle Damage):",
                    f"{STAR_EMOJI} +5%",
                    f"{STAR_EMOJI * 2} +8%",
                    f"{STAR_EMOJI * 3} +12%",
                    f"{STAR_EMOJI * 4} +18%",
                    f"{STAR_EMOJI * 5} +25%",
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
        "exclusive_weapon": {
            "name": "Winged Vengeance-C2",
            "exclusivity": "Marcia Exclusive",
            "skill_name": "Divine Favor",
            "description": (
                "When Marcia unleashes **[Cluster – Annihilation]**, boosts troop’s normal attack crit rate by "
                "50%. On crit, that normal attack deals an additional 100% damage, lasting for 3 turns.\n"
                "During adventure, only the following effects apply: Marcia’s ATK, DEF, and HP increase by 25%."
            ),
            "flavor": [
                "“Perseus system synced”",
                "“These aren’t machines—they’re divine retribution!”",
            ],
            "upgrades": [
                (f"{STAR_EMOJI}", "+15% normal attack crit rate"),
                (f"{STAR_EMOJI * 2}", "+22% normal attack crit rate"),
                (f"{STAR_EMOJI * 3}", "+35% normal attack crit rate"),
                (f"{STAR_EMOJI * 4}", "+50% normal attack crit rate"),
                (f"{STAR_EMOJI * 5}", "+75% normal attack crit rate (5★ required)"),
            ],
        },
        "image": Path("data/heroes/marcia.webp"),
    },
    "tristan": {
        "name": "Tristan",
        "faction": "Fighters",
        "season": "Season 1",
        "tier_label": "S",
        "tier_emoji": STIER_EMOJI,
        "fragment_emoji": BLUEFRAGMENT_EMOJI,
        "emblem_emoji": FIGHTER_EMBLEM,
        "season_emoji": SEASON1_EMOJI,
        "portrait_emoji": "",
        "lore": [
            "Tristan’s legend began at the familiar dawn of the apocalypse. Clad in a black leather cloak and "
            "wielding golden dual pistols, this zombie hunter stepped into the realm of survival with a deep "
            "understanding of zombie weaknesses. Once a nobody, Tristan quickly adapted to the chaos of the "
            "outbreak and set out on his heroic journey.",
            "As time passed, Tristan evolved from a fledgling warrior into a legendary figure. With every "
            "challenge, he sharpened his skills and gathered valuable intelligence about zombies. By "
            "continually upgrading his weapons and refining his combat strategies, he became a ray of hope in "
            "the darkness.",
            "Tristan’s fame continued to spread, but he no longer fought alone. He was soon joined by "
            "like-minded companions who stood beside him in battles against zombies and in defense of human "
            "territories. Inspired by Tristan’s wisdom and bravery, they began reclaiming lands that had been "
            "overrun by the walking dead.",
            "Tristan and his people faced the ultimate test of the apocalypse head-on. Through countless "
            "life-and-death battles, his precise strikes against zombie weaknesses led his team to repeated "
            "victories. These triumphs were not just acts of revenge against the undead, but a stand for "
            "humanity itself, preserving hope in a broken world.",
        ],
        "skills": [
            (
                "Rain Fire",
                "\n".join([
                    "Rapidly shoots marked enemies causing damage equal to **1719% attack**.",
                    "Star scaling:",
                    f"{STAR_EMOJI} Deals an additional 180% damage",
                    f"{STAR_EMOJI * 2} Additional damage increases to 360%",
                    f"{STAR_EMOJI * 3} Additional damage increases to 540%",
                    f"{STAR_EMOJI * 4} Additional damage increases to 780%",
                    f"{STAR_EMOJI * 5} Additional damage increases to 1200%",
                ]),
            ),
            (
                "Rapid Fire",
                "\n".join([
                    "Fires purifying silver bullets causing damage equal to **252% attack** to enemies.",
                    "Star scaling:",
                    f"{STAR_EMOJI} Deals an additional 18% damage",
                    f"{STAR_EMOJI * 2} Additional damage increases to 36%",
                    f"{STAR_EMOJI * 3} Additional damage increases to 54%",
                    f"{STAR_EMOJI * 4} Additional damage increases to 78%",
                    f"{STAR_EMOJI * 5} Additional damage increases to 120%",
                ]),
            ),
            (
                "Training Expert: Assaulter",
                "\n".join([
                    "Tristan excels in improving defense skills, boosting Fighters' DEF by 19%.",
                    "Star scaling (Fighter ATK):",
                    f"{STAR_EMOJI} +5%",
                    f"{STAR_EMOJI * 2} +10%",
                    f"{STAR_EMOJI * 3} +15%",
                    f"{STAR_EMOJI * 4} +35%",
                    f"{STAR_EMOJI * 5} Increases all Fighters' battle damage by 10% "
                    "whether the hero is deployed or not.",
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
        "exclusive_weapon": {
            "name": "Endgame Echoes",
            "exclusivity": "Tristan Exclusive",
            "skill_name": "Twin Ballistics",
            "description": (
                "When Tristan releases skill **[Rain Fire]**, it triggers 2 straight strikes, with each strike "
                "dealing 55% damage.\n"
                "During adventure, only the following effects apply: Tristan’s ATK, DEF, and HP increase by 5%."
            ),
            "flavor": [
                "“As the first bullet tears through space, the second seals the loop of fate.”",
                "“Death is not the end of life; forgetfulness is.”",
            ],
            "upgrades": [
                (f"{STAR_EMOJI}", "Each strike causes 60% damage of skill [Rain Fire] (1★ required)"),
                (f"{STAR_EMOJI * 2}", "Each strike causes 65% damage of skill [Rain Fire] (2★ required)"),
                (f"{STAR_EMOJI * 3}", "Each strike causes 75% damage of skill [Rain Fire] (3★ required)"),
                (f"{STAR_EMOJI * 4}", "Each strike causes 85% damage of skill [Rain Fire] (4★ required)"),
                (f"{STAR_EMOJI * 5}", "Each strike causes 100% damage of skill [Rain Fire] (5★ required)"),
            ],
        },
        "image": Path("data/heroes/tristan.webp"),
    },
}


FACTIONS = ("Fighters", "Shooters", "Riders")


def _hero_type_line(hero: dict) -> str:
    return (
        f"{hero['tier_emoji']} {hero['tier_label']}-Tier {hero['fragment_emoji']} "
        f"{hero['emblem_emoji']} {hero['faction']} • {hero['season_emoji']} {hero['season']}"
    )


def _build_hero_home_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🧬 Hero Codex",
        description=(
            "A living dossier of verified heroes, their lore, skills, and signature weapons.\n"
            "Choose a faction below, then select a hero from the dropdown to view their full profile."
        ),
        color=0x9b59b6,
    )
    embed.add_field(
        name="Factions",
        value="\n".join([f"• {faction}" for faction in FACTIONS]),
        inline=False,
    )
    embed.set_footer(text="Tap a faction button to begin. Use Home to return to this menu.")
    return embed


def _build_faction_embed(faction: str) -> discord.Embed:
    heroes = [hero for hero in HEROES.values() if hero["faction"] == faction]
    embed = discord.Embed(
        title=f"🧬 {faction} Codex",
        description="Select a hero from the dropdown to view lore, skills, and exclusive weapon details.",
        color=0x9b59b6,
    )
    lines = [f"• **{hero['name']}** — {_hero_type_line(hero)}" for hero in heroes]
    embed.add_field(name="Available Heroes", value="\n".join(lines) if lines else "—", inline=False)
    embed.set_footer(text="Home resets the codex menu.")
    return embed


def _add_lore_fields(embed: discord.Embed, lore: list[str]) -> None:
    """
    Add lore chunks without exceeding Discord embed field limits.
    Fix: if lore spans multiple fields, label subsequent ones as "Lore (continued)"
    so it doesn't look like the section restarted.
    """
    chunk: list[str] = []
    current_len = 0
    story_index = 1
    part = 1

    for story in lore:
        entry = f"**Story {story_index}:** {story}"
        story_index += 1
        entry_len = len(entry) + (2 if chunk else 0)

        if current_len + entry_len > 1000:
            field_name = "Lore" if part == 1 else "Lore (continued)"
            embed.add_field(name=field_name, value="\n\n".join(chunk), inline=False)
            part += 1
            chunk = [entry]
            current_len = len(entry)
        else:
            chunk.append(entry)
            current_len += entry_len

    if chunk:
        field_name = "Lore" if part == 1 else "Lore (continued)"
        embed.add_field(name=field_name, value="\n\n".join(chunk), inline=False)


def _add_chunked_field(embed: discord.Embed, title: str, lines: list[str]) -> None:
    """
    Add chunked fields for long sections.
    Fix: when the content overflows and needs multiple fields, we label subsequent ones as "(continued)"
    so it doesn't look like the section restarted.
    """
    chunk: list[str] = []
    current_len = 0
    part = 1

    for line in lines:
        entry_len = len(line) + (1 if chunk else 0)
        if current_len + entry_len > 1000:
            field_name = title if part == 1 else f"{title} (continued)"
            embed.add_field(name=field_name, value="\n".join(chunk), inline=False)
            part += 1
            chunk = [line]
            current_len = len(line)
        else:
            chunk.append(line)
            current_len += entry_len

    if chunk:
        field_name = title if part == 1 else f"{title} (continued)"
        embed.add_field(name=field_name, value="\n".join(chunk), inline=False)


def _hero_header(hero: dict) -> str:
    return f"{hero['portrait_emoji']} **{hero['name']}**" if hero.get("portrait_emoji") else hero["name"]


def _attach_hero_image(embed: discord.Embed, hero: dict) -> discord.File | None:
    image_path = hero.get("image")
    if image_path and image_path.exists():
        image_file = discord.File(image_path, filename=image_path.name)
        embed.set_image(url=f"attachment://{image_path.name}")
        return image_file
    return None


def _hero_embed_base(hero: dict, description: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"🛰️ {hero['name']}",
        description=description,
        color=0x5865F2,
    )
    embed.add_field(
        name="Hero Type",
        value=f"{_hero_header(hero)}\n{_hero_type_line(hero)}",
        inline=False,
    )
    embed.set_footer(text="Stats are sourced from verified in-game data.")
    return embed


def _build_hero_lore_embed(hero_key: str) -> tuple[discord.Embed, discord.File | None]:
    hero = HEROES[hero_key]
    embed = _hero_embed_base(hero, "Character dossier. Tap the buttons below to switch panels.")
    _add_lore_fields(embed, hero["lore"])
    image_file = _attach_hero_image(embed, hero)
    return embed, image_file


def _build_hero_skills_embed(hero_key: str) -> tuple[discord.Embed, discord.File | None]:
    hero = HEROES[hero_key]
    embed = _hero_embed_base(hero, "Skill breakdown and scaling.")
    for skill_name, skill_text in hero["skills"]:
        embed.add_field(name=f"✨ {skill_name}", value=skill_text, inline=False)
    image_file = _attach_hero_image(embed, hero)
    return embed, image_file


def _build_hero_weapon_embed(hero_key: str) -> tuple[discord.Embed, discord.File | None]:
    hero = HEROES[hero_key]
    embed = _hero_embed_base(hero, "Signature armament intel.")
    weapon = hero.get("exclusive_weapon")

    if weapon:
        # Split weapon section into purpose-built fields for cleaner UX
        meta_lines = [
            f"**Weapon Name:** {weapon['name']}",
            f"**Exclusivity:** {weapon['exclusivity']}",
            f"**Skill Name:** {weapon['skill_name']}",
            f"**Skill Description:** {weapon['description']}",
        ]
        embed.add_field(name="Exclusive Weapon", value="\n".join(meta_lines), inline=False)

        if weapon.get("flavor"):
            flavor_lines = "\n".join([f"• {line}" for line in weapon["flavor"]])
            embed.add_field(name="Flavor Lines", value=flavor_lines, inline=False)

        if weapon.get("upgrades"):
            upgrade_lines = [f"{stars} {text}" for stars, text in weapon["upgrades"]]
            _add_chunked_field(embed, "Upgrade Levels", upgrade_lines)

    else:
        embed.add_field(name="Exclusive Weapon", value="No exclusive weapon data logged yet.", inline=False)

    image_file = _attach_hero_image(embed, hero)
    return embed, image_file


class HeroSelect(discord.ui.Select):
    def __init__(self, faction: str):
        heroes = [(key, data) for key, data in HEROES.items() if data["faction"] == faction]
        options = [
            discord.SelectOption(
                label=data["name"],
                description=f"{data['faction']} • {data['season']} • {data['tier_label']}-Tier",
                value=key,
                emoji="🧬",
            )
            for key, data in heroes
        ]
        super().__init__(
            placeholder=f"Choose a {faction} hero…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        hero_key = self.values[0]
        embed, image_file = _build_hero_lore_embed(hero_key)
        attachments = [image_file] if image_file else []
        await interaction.response.edit_message(
            embed=embed,
            view=HeroDetailView(hero_key),
            attachments=attachments,
        )


class FactionButton(discord.ui.Button):
    def __init__(self, faction: str):
        style = discord.ButtonStyle.primary if faction == "Riders" else discord.ButtonStyle.secondary
        emoji = "🧬" if faction == "Riders" else "⚔️" if faction == "Fighters" else "🎯"
        super().__init__(label=faction, style=style, emoji=emoji)
        self.faction = faction

    async def callback(self, interaction: discord.Interaction):
        view: HeroesView = self.view
        view.set_faction(self.faction)
        embed = _build_faction_embed(self.faction)
        await interaction.response.edit_message(embed=embed, view=view)


class HomeButton(discord.ui.Button):
    def __init__(self, disabled: bool):
        super().__init__(label="Home", style=discord.ButtonStyle.secondary, emoji="🏠", disabled=disabled)

    async def callback(self, interaction: discord.Interaction):
        view: HeroesView = self.view
        view.set_faction(None)
        embed = _build_hero_home_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class HeroesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.faction: str | None = None
        self._refresh_items()

    def set_faction(self, faction: str | None):
        self.faction = faction
        self._refresh_items()

    def _refresh_items(self):
        self.clear_items()
        self.add_item(HomeButton(disabled=self.faction is None))
        for faction in FACTIONS:
            self.add_item(FactionButton(faction))
        if self.faction and any(hero["faction"] == self.faction for hero in HEROES.values()):
            self.add_item(HeroSelect(self.faction))


class HeroDetailView(discord.ui.View):
    def __init__(self, hero_key: str):
        super().__init__(timeout=180)
        self.hero_key = hero_key

    async def _switch(self, interaction: discord.Interaction, builder):
        embed, image_file = builder(self.hero_key)
        attachments = [image_file] if image_file else []
        await interaction.response.edit_message(
            embed=embed,
            view=self,
            attachments=attachments,
        )

    @discord.ui.button(label="Home", style=discord.ButtonStyle.secondary, emoji="🏠")
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_hero_home_embed()
        await interaction.response.edit_message(embed=embed, view=HeroesView(), attachments=[])

    @discord.ui.button(label="Lore", style=discord.ButtonStyle.primary, emoji="📖")
    async def lore(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, _build_hero_lore_embed)

    @discord.ui.button(label="Skills", style=discord.ButtonStyle.secondary, emoji="✨")
    async def skills(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, _build_hero_skills_embed)

    @discord.ui.button(label="Weapon", style=discord.ButtonStyle.secondary, emoji="🗡️")
    async def weapon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch(interaction, _build_hero_weapon_embed)


class Heroes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(description="Browse the hero codex and view hero details.")
    async def heroes(self, ctx):
        embed = _build_hero_home_embed()
        view = HeroesView()
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Heroes(bot))
