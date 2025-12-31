"""
FILE: cogs/akrott.py
PURPOSE: Owner-only control panel for cross-server analytics and broadcast utilities.
"""
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite

from database import DB_PATH, command_usage_totals

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


async def _owner_only(interaction: discord.Interaction) -> bool:
    """Dynamic owner check that respects the configured application owner."""
    try:
        if await interaction.client.is_owner(interaction.user):
            return True
    except Exception:
        # Fallback for legacy hosts where owner_id is not hydrated
        pass

    owner_id = getattr(interaction.client, "owner_id", None)
    return owner_id is not None and interaction.user.id == owner_id


class _OwnerLockedView(discord.ui.View):
    """Base view that denies any interaction from non-owners."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await _owner_only(interaction):
            return True

        await interaction.response.send_message(
            "❌ Access denied. This console is locked to the bot owner.", ephemeral=True
        )
        return False


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
        embed = await self.cog.build_detail_embed(index)
        await interaction.response.edit_message(
            embed=embed,
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

        if selection_index == 6:
            self.add_item(BroadcastDMButton(cog))
        elif selection_index == 7:
            self.add_item(AnnouncementButton(cog))

    @discord.ui.button(label="⬅️ Back to menu", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog.build_menu_embed(), view=ControlPanelMenu(self.cog)
        )


class BroadcastDMButton(discord.ui.Button):
    def __init__(self, cog: "AkrottControl"):
        super().__init__(label="Send update DM", style=discord.ButtonStyle.primary, emoji="✉️")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BroadcastDMModal(self.cog))


class AnnouncementButton(discord.ui.Button):
    def __init__(self, cog: "AkrottControl"):
        super().__init__(label="Send channel announcement", style=discord.ButtonStyle.primary, emoji="📣")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AnnouncementModal(self.cog))


class BroadcastDMModal(discord.ui.Modal, title="Owner update DM"):
    def __init__(self, cog: "AkrottControl"):
        super().__init__()
        self.cog = cog
        self.message = discord.ui.TextInput(
            label="Message body",
            placeholder="Short status update for every guild owner",
            style=discord.TextStyle.long,
            max_length=500,
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        sent, failed = await self.cog.broadcast_owner_dm(str(self.message.value))
        await interaction.followup.send(
            f"✅ Sent to {sent} owners. {'⚠️ ' + str(failed) + ' failed.' if failed else ''}",
            ephemeral=True,
        )


class AnnouncementModal(discord.ui.Modal, title="Channel announcement"):
    def __init__(self, cog: "AkrottControl"):
        super().__init__()
        self.cog = cog
        self.channel_id = discord.ui.TextInput(
            label="Channel ID",
            placeholder="123456789012345678",
            max_length=25,
        )
        self.message = discord.ui.TextInput(
            label="Announcement text",
            style=discord.TextStyle.long,
            max_length=1000,
        )
        self.add_item(self.channel_id)
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cid = int(str(self.channel_id.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Invalid channel ID.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        success = await self.cog.send_channel_announcement(cid, str(self.message.value))
        if success:
            await interaction.followup.send("📣 Announcement dispatched.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Failed to send announcement.", ephemeral=True)


class AkrottControl(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    akrott = app_commands.Group(
        name="akrott",
        description="Owner control panel and administrative overview.",
        default_permissions=None,
    )

    def build_menu_embed(self) -> discord.Embed:
        description_lines = [f"{NUMBER_EMOJIS[i]} {label}" for i, (label, _) in enumerate(MENU_OPTIONS)]
        embed = discord.Embed(
            title="🛰️ Owner Control Panel",
            description="\n".join(description_lines),
            color=0x2b2d31,
        )
        embed.set_footer(text="Ephemeral session | Only akrott can operate this console.")
        return embed

    async def build_detail_embed(self, selection_index: int) -> discord.Embed:
        builders = {
            0: self._build_xp_leaderboard,
            1: self._build_global_stats,
            2: self._build_scavenge_summary,
            3: self._build_rare_feed,
            4: self._build_economy_stats,
            5: self._build_server_health,
            6: self._build_dm_helper,
            7: self._build_announcement_helper,
        }

        builder = builders.get(selection_index)
        if builder:
            return await builder()

        title, hint = MENU_OPTIONS[selection_index]
        embed = discord.Embed(title=f"{NUMBER_EMOJIS[selection_index]} {title}", color=0x5865F2)
        embed.description = hint
        embed.set_footer(text="Tap Back to reopen the control panel menu.")
        return embed

    async def _build_xp_leaderboard(self) -> discord.Embed:
        embed = discord.Embed(title=f"{NUMBER_EMOJIS[0]} XP Leaderboard", color=0x5865F2)
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT guild_id, user_id, xp, level
                FROM user_stats
                ORDER BY xp DESC
                LIMIT 5
                """
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            embed.description = "No XP data recorded yet."
            return embed

        lines = []
        for idx, row in enumerate(rows, start=1):
            guild = self.bot.get_guild(row["guild_id"])
            guild_name = guild.name if guild else f"Guild {row['guild_id']}"
            user = self.bot.get_user(row["user_id"])
            user_display = user.mention if user else f"<@{row['user_id']}>"
            lines.append(
                f"{idx}. {user_display} — {row['xp']} XP | L{row['level']} ({guild_name})"
            )

        embed.description = "\n".join(lines)
        embed.set_footer(text="Across all connected servers")
        return embed

    async def _build_global_stats(self) -> discord.Embed:
        embed = discord.Embed(title=f"{NUMBER_EMOJIS[1]} Global Stats Dashboard", color=0x3498db)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM settings") as cursor:
                guilds = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*), COALESCE(SUM(xp), 0) FROM user_stats") as cursor:
                users, total_xp = await cursor.fetchone()
            async with db.execute("SELECT COUNT(*) FROM server_missions") as cursor:
                missions = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM trade_pool") as cursor:
                trades = (await cursor.fetchone())[0]

        embed.add_field(name="Configured Servers", value=f"{guilds}", inline=True)
        embed.add_field(name="Tracked Survivors", value=f"{users}", inline=True)
        embed.add_field(name="XP Recorded", value=f"{total_xp}", inline=True)
        embed.add_field(name="Active Missions", value=f"{missions}", inline=True)
        embed.add_field(name="Trade Listings", value=f"{trades}", inline=True)
        embed.set_footer(text="Live snapshot from Marcia's database")
        return embed

    async def _build_scavenge_summary(self) -> discord.Embed:
        embed = discord.Embed(title=f"{NUMBER_EMOJIS[2]} Scavenged Items Summary", color=0x2ecc71)
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT rarity, SUM(quantity) AS qty FROM user_inventory GROUP BY rarity ORDER BY qty DESC"
            ) as cursor:
                rows = await cursor.fetchall()
            async with db.execute("SELECT COUNT(DISTINCT item_id) FROM user_inventory") as cursor:
                unique_items = (await cursor.fetchone())[0]

        if not rows:
            embed.description = "No scavenged loot logged yet."
            return embed

        breakdown = [f"**{row['rarity']}**: {row['qty']}" for row in rows]
        embed.description = "\n".join(breakdown)
        embed.add_field(name="Unique Items Logged", value=str(unique_items), inline=False)
        embed.set_footer(text="Inventory totals across all sectors")
        return embed

    async def _build_rare_feed(self) -> discord.Embed:
        embed = discord.Embed(title=f"{NUMBER_EMOJIS[3]} Rare Drops Feed", color=0x9b59b6)
        rarity_order = {"Mythic": 0, "Artifact": 1, "Legendary": 2, "Epic": 3}

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT guild_id, user_id, item_id, quantity, rarity
                FROM user_inventory
                WHERE rarity IN ('Mythic', 'Artifact', 'Legendary', 'Epic')
                ORDER BY
                    CASE rarity
                        WHEN 'Mythic' THEN 0
                        WHEN 'Artifact' THEN 1
                        WHEN 'Legendary' THEN 2
                        ELSE 3
                    END,
                    quantity DESC
                LIMIT 8
                """
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            embed.description = "No epic-tier drops recorded yet."
            return embed

        lines = []
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            guild_name = guild.name if guild else f"Guild {row['guild_id']}"
            user = self.bot.get_user(row["user_id"])
            user_display = user.mention if user else f"<@{row['user_id']}>"
            lines.append(
                f"{row['rarity']} — {row['item_id']} x{row['quantity']} | {user_display} ({guild_name})"
            )

        embed.description = "\n".join(lines)
        embed.set_footer(text="Highest-tier inventory holders")
        return embed

    async def _build_economy_stats(self) -> discord.Embed:
        embed = discord.Embed(title=f"{NUMBER_EMOJIS[4]} Economy Stats", color=0xe67e22)
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT type, COUNT(*) AS total FROM trade_pool GROUP BY type"
            ) as cursor:
                trade_rows = await cursor.fetchall()
            async with db.execute(
                "SELECT fish_rarity, COUNT(*) AS total FROM trade_pool GROUP BY fish_rarity ORDER BY total DESC"
            ) as cursor:
                rarity_rows = await cursor.fetchall()

        trade_lines = [f"{row['type'].title()}: {row['total']}" for row in trade_rows] or ["No active listings"]
        rarity_lines = [f"{row['fish_rarity']}: {row['total']}" for row in rarity_rows] or ["No trades by rarity"]

        embed.add_field(name="Listings by type", value="\n".join(trade_lines), inline=True)
        embed.add_field(name="Listings by rarity", value="\n".join(rarity_lines), inline=True)
        embed.set_footer(text="Marketplace volume across the network")
        return embed

    async def _build_server_health(self) -> discord.Embed:
        embed = discord.Embed(title=f"{NUMBER_EMOJIS[5]} Server List, Health, Activity", color=0x2b2d31)
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM settings ORDER BY server_name ASC") as cursor:
                rows = await cursor.fetchall()
            async with db.execute("SELECT COUNT(DISTINCT user_id) FROM user_stats") as cursor:
                total_users = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM user_inventory") as cursor:
                inventory_rows = (await cursor.fetchone())[0]

        if not rows:
            embed.description = "No servers configured yet. Run /setup to link sectors."
            return embed

        command_total, top_command, top_uses = await command_usage_totals()

        embed.add_field(name="Connected Servers", value=str(len(rows)), inline=True)
        embed.add_field(name="Tracked Survivors", value=str(total_users), inline=True)
        embed.add_field(name="Commands Used", value=str(command_total), inline=True)
        if top_command:
            embed.add_field(
                name="Top Command",
                value=f"{top_command} ({top_uses} uses)",
                inline=True,
            )
        embed.add_field(name="Inventory Rows", value=str(inventory_rows), inline=True)

        lines = []
        for row in rows:
            configured_links = sum(
                1
                for key in (
                    "event_channel_id",
                    "chat_channel_id",
                    "welcome_channel_id",
                    "rules_channel_id",
                    "verify_channel_id",
                )
                if row[key]
            )
            status = "✅ Stable" if configured_links >= 4 else "⚠️ Needs links"
            name = row["server_name"] or f"Guild {row['guild_id']}"
            lines.append(f"{name} — {status} ({configured_links}/5 channels linked)")

        embed.description = "\n".join(lines[:15])
        if len(lines) > 15:
            embed.set_footer(text=f"+{len(lines) - 15} more servers tracked")
        return embed

    async def _build_dm_helper(self) -> discord.Embed:
        embed = discord.Embed(title=f"{NUMBER_EMOJIS[6]} Send Update DM to all server owners", color=0x5865F2)
        embed.description = (
            "Prepare a short update and press **Send update DM** to broadcast it to every guild owner "
            "Marcia is connected to."
        )
        return embed

    async def _build_announcement_helper(self) -> discord.Embed:
        embed = discord.Embed(title=f"{NUMBER_EMOJIS[7]} Send Announcement to channel by channel_id", color=0x5865F2)
        embed.description = (
            "Paste a channel ID and a message to push an announcement without changing servers. "
            "Use Discord's Copy ID on the target channel first."
        )
        return embed

    async def broadcast_owner_dm(self, content: str) -> tuple[int, int]:
        sent = 0
        failed = 0
        for guild in self.bot.guilds:
            owner = guild.owner or guild.get_member(guild.owner_id)
            if owner is None:
                try:
                    owner = await guild.fetch_member(guild.owner_id)
                except Exception:
                    failed += 1
                    continue

            try:
                await owner.send(f"📡 Marcia OS Update for **{guild.name}**\n\n{content}")
                sent += 1
            except Exception:
                failed += 1

        return sent, failed

    async def send_channel_announcement(self, channel_id: int, content: str) -> bool:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                return False

        try:
            await channel.send(content)
            return True
        except Exception:
            return False

    @akrott.command(name="panel", description="Owner-only control panel for cross-server analytics.")
    @app_commands.check(_owner_only)
    async def akrott_panel(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=self.build_menu_embed(), view=ControlPanelMenu(self), ephemeral=True
        )

    @akrott_panel.error
    async def akrott_panel_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Access denied. This console is reserved for akrott.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⚠️ An unexpected error occurred while opening the console.", ephemeral=True
            )

    @akrott.command(name="overview", description="Administrator-only network server overview.")
    @app_commands.guild_only()
    async def akrott_overview(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        lines = []
        for guild in sorted(self.bot.guilds, key=lambda g: g.name.lower()):
            owner = guild.owner or guild.get_member(guild.owner_id)
            if owner is None:
                try:
                    owner = await guild.fetch_member(guild.owner_id)
                except Exception:
                    owner = None

            owner_username = str(owner) if owner else "Unknown"
            owner_display = owner.display_name if owner else "Unknown"
            lines.append(
                "\n".join(
                    [
                        f"**{guild.name}**",
                        f"ID: `{guild.id}`",
                        f"Members: {guild.member_count}",
                        f"Owner: {owner_username}",
                        f"Display: {owner_display}",
                    ]
                )
            )

        embed = discord.Embed(
            title="🛰️ Network Server Overview",
            description="\n\n".join(lines) if lines else "No servers connected.",
            color=0x2b2d31,
        )
        embed.set_footer(text="Administrator access | Read-only overview")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    cog = AkrottControl(bot)
    await bot.add_cog(cog)
    existing = bot.tree.get_command("akrott")
    if existing:
        bot.tree.remove_command(existing.name, type=existing.type)
    bot.tree.add_command(cog.akrott)
