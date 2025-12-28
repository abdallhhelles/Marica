"""
FILE: cogs/trading.py
USE: The Fish-Link Trading Network (SQL Version).
FEATURES: Server-isolated matching, automatic menu re-anchoring on restart.
"""
import discord
from discord.ext import commands
import aiosqlite
import logging
import asyncio
from assets import FISH_NAMES
from database import DB_PATH

logger = logging.getLogger('MarciaOS.Trading')

FISH_CONFIG = {r: len(names) for r, names in FISH_NAMES.items()}

# --- DATABASE HELPERS ---

async def db_get_trade_data(guild_id):
    data = {"extras": {}, "wanted": {}}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, fish_rarity, fish_index, type FROM trade_pool WHERE guild_id = ?", 
            (guild_id,)
        ) as cursor:
            async for row in cursor:
                uid, rarity, idx, cat = str(row[0]), row[1], row[2], row[3]
                fid = f"{rarity}-{idx}"
                key = "extras" if cat == "spare" else "wanted"
                data[key].setdefault(fid, [])
                data[key][fid].append(uid)
    return data

async def db_add_listing(guild_id, user_id, rarity, index, trade_type):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM trade_pool WHERE guild_id=? AND user_id=? AND fish_rarity=? AND fish_index=? AND type=?",
            (guild_id, user_id, rarity, index, trade_type)
        ) as cursor:
            if await cursor.fetchone(): return False
        await db.execute(
            "INSERT INTO trade_pool (guild_id, user_id, fish_rarity, fish_index, type) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, rarity, index, trade_type)
        )
        await db.commit()
        return True

async def db_remove_listing(guild_id, user_id, rarity, index, trade_type):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM trade_pool WHERE guild_id = ? AND user_id = ? AND fish_rarity = ? AND fish_index = ? AND type = ?",
            (guild_id, user_id, rarity, index, trade_type)
        )
        await db.commit()

# --- DISPLAY HELPERS ---

def _summarize_listings(fid_list):
    labels = [format_fish_label(fid) for fid in fid_list]
    if not labels:
        return "—"
    if len(labels) > 8:
        visible = ", ".join(labels[:8])
        return f"{visible}, +{len(labels) - 8} more"
    return ", ".join(labels)


def rarity_block(fish_data, rarity: str) -> str:
    extras = [fid for fid in fish_data["extras"] if fid.startswith(rarity + "-")]
    wanted = [fid for fid in fish_data["wanted"] if fid.startswith(rarity + "-")]
    extras.sort(key=lambda x: int(x.split('-')[1]))
    wanted.sort(key=lambda x: int(x.split('-')[1]))
    return (
        f"✅ Extras: {_summarize_listings(extras)}\n"
        f"🎣 Wanted: {_summarize_listings(wanted)}"
    )


def stock_summary(fish_data) -> str:
    chunks = []
    for rarity in FISH_CONFIG.keys():
        extra_count = sum(1 for fid in fish_data["extras"] if fid.startswith(rarity))
        want_count = sum(1 for fid in fish_data["wanted"] if fid.startswith(rarity))
        if extra_count or want_count:
            chunks.append(f"{rarity}: {extra_count} extras · {want_count} wanted")
    return " | ".join(chunks) if chunks else "Network is quiet. Start listing fish!"

def sort_by_rarity(fish_list):
    categorized = {r: [] for r in FISH_CONFIG.keys()}
    for fid in fish_list:
        try:
            r = fid.split('-')[0]
            if r in categorized: categorized[r].append(fid)
        except: continue
    output = []
    for r, items in categorized.items():
        if items:
            items.sort(key=lambda x: int(x.split('-')[1]))
            output.append(f"**{r}**: {', '.join(format_fish_label(i) for i in items)}")
    return "\n".join(output) if output else "None"


def format_fish_label(fid: str) -> str:
    try:
        rarity, idx_s = fid.split('-')
        idx = int(idx_s)
        name = FISH_NAMES.get(rarity, [None])[idx - 1]
        return f"{rarity}-{idx} {name}" if name else fid
    except Exception:
        return fid

# --- VIEWS ---

class ManageListingsView(discord.ui.View):
    def __init__(self, cog, guild_id, user_id, category, fish_data):
        super().__init__(timeout=60)
        self.cog, self.gid, self.uid, self.cat = cog, guild_id, user_id, category
        my_fish = [fid for fid, users in fish_data[category].items() if str(user_id) in users]
        if not my_fish:
            self.add_item(discord.ui.Button(label="No active listings", disabled=True))
            return
        options = [
            discord.SelectOption(label=f"Remove {format_fish_label(fid)}", value=fid, emoji="🗑️")
            for fid in my_fish[:25]
        ]
        select = discord.ui.Select(placeholder=f"Remove from {category}...", options=options)
        select.callback = self.remove_callback
        self.add_item(select)

    async def remove_callback(self, it: discord.Interaction):
        fid = it.data['values'][0]
        rarity, idx = fid.split('-')
        db_type = "spare" if self.cat == "extras" else "find"
        await db_remove_listing(self.gid, self.uid, rarity, int(idx), db_type)
        await it.response.send_message(f"✅ Removed **{fid}**.", ephemeral=True)
        await self.cog.re_anchor_menu(it.channel)

class FishSelect(discord.ui.Select):
    def __init__(self, rarity, mode, cog):
        self.mode, self.cog, self.rarity = mode, cog, rarity
        options = [
            discord.SelectOption(
                label=format_fish_label(f"{rarity}-{i}"),
                value=str(i),
                emoji="🐟",
            )
            for i in range(1, FISH_CONFIG[rarity] + 1)
        ]
        super().__init__(placeholder=f"Select {rarity} index...", options=options)

    async def callback(self, it: discord.Interaction):
        idx, uid, gid = int(self.values[0]), it.user.id, it.guild.id
        db_type = "spare" if self.mode == 'add' else "find"
        success = await db_add_listing(gid, uid, self.rarity, idx, db_type)
        if not success: 
            return await it.response.send_message("Already listed.", ephemeral=True)
        fid = f"{self.rarity}-{idx}"
        label = format_fish_label(fid)
        await it.channel.send(f"{'📦' if self.mode == 'add' else '🎣'} <@{uid}> listed **{label}**!", delete_after=10)
        data = await db_get_trade_data(gid)
        target_cat = "wanted" if self.mode == 'add' else "extras"
        if fid in data[target_cat]:
            for target_id in data[target_cat][fid]:
                if int(target_id) == uid: continue 
                try:
                    m = it.guild.get_member(int(target_id))
                    if m: await m.send(f"🚨 **FISH-LINK:** Match for **{label}** in **{it.guild.name}**!")
                except: pass 
        await it.response.defer()
        await self.cog.re_anchor_menu(it.channel)

class FishControlView(discord.ui.View):
    def __init__(self, owner, persistent=False):
        super().__init__(timeout=None if persistent else 60)
        self.owner = owner

    def _get_cog(self, interaction: discord.Interaction):
        if isinstance(self.owner, commands.Bot):
            return interaction.client.get_cog("Trading")
        return self.owner

    @discord.ui.button(label="Add Spare", style=discord.ButtonStyle.success, custom_id="f_add", emoji="📦")
    async def add_btn(self, it, btn): await self.prompt_rarity(it, 'add')

    @discord.ui.button(label="Find Fish", style=discord.ButtonStyle.primary, custom_id="f_find", emoji="🔍")
    async def find_btn(self, it, btn): await self.prompt_rarity(it, 'find')

    @discord.ui.button(label="Who Has My Wanted?", style=discord.ButtonStyle.success, custom_id="f_donor", emoji="🤝")
    async def donor_btn(self, it, btn):
        data = await db_get_trade_data(it.guild.id)
        uid_s = str(it.user.id)
        wanted_items = [f for f, u in data["wanted"].items() if uid_s in u]
        matches = []
        for fid in wanted_items:
            donors = [d for d in data["extras"].get(fid, []) if d != uid_s]
            if donors:
                mentions = ", ".join([f"<@{d}>" for d in donors])
                matches.append(f"• **{format_fish_label(fid)}**: Held by {mentions}")
        report = "\n".join(matches) if matches else "No matches found."
        await it.response.send_message(embed=discord.Embed(title="🤝 Matches", description=report, color=0x2ecc71), ephemeral=True)

    @discord.ui.button(label="My Listings", style=discord.ButtonStyle.secondary, custom_id="f_mine", emoji="📜")
    async def mine_btn(self, it, btn):
        data = await db_get_trade_data(it.guild.id)
        uid_s = str(it.user.id)
        extra_list = [f for f, u in data["extras"].items() if uid_s in u]
        wanted_list = [f for f, u in data["wanted"].items() if uid_s in u]
        embed = discord.Embed(title="📜 Your Listings", color=0x5865f2)
        embed.add_field(name="✅ SPARES", value=sort_by_rarity(extra_list), inline=False)
        embed.add_field(name="🎣 REQUESTS", value=sort_by_rarity(wanted_list), inline=False)
        view = discord.ui.View()
        b1, b2 = discord.ui.Button(label="Remove Spares", style=discord.ButtonStyle.danger), discord.ui.Button(label="Remove Wanted", style=discord.ButtonStyle.danger)
        cog = self._get_cog(it)
        if not cog:
            return await it.response.send_message("📡 Trading module is still booting. Try again in a moment.", ephemeral=True)
        b1.callback = lambda i: i.response.send_message("Select spare:", view=ManageListingsView(cog, it.guild.id, it.user.id, "extras", data), ephemeral=True)
        b2.callback = lambda i: i.response.send_message("Select request:", view=ManageListingsView(cog, it.guild.id, it.user.id, "wanted", data), ephemeral=True)
        view.add_item(b1); view.add_item(b2)
        await it.response.send_message(embed=embed, view=view, ephemeral=True)

    async def prompt_rarity(self, it, mode):
        view = discord.ui.View()
        select = discord.ui.Select(placeholder="Select Rarity...", options=[discord.SelectOption(label=t, value=t) for t in FISH_CONFIG.keys()])
        async def cb(i):
            cog = self._get_cog(i)
            if not cog:
                return await i.response.send_message("📡 Trading module is still booting. Try again in a moment.", ephemeral=True)
            v2 = discord.ui.View(); v2.add_item(FishSelect(select.values[0], mode, cog))
            await i.response.edit_message(content=f"📡 Filtering {select.values[0]}...", view=v2)
        select.callback = cb
        view.add_item(select)
        await it.response.send_message("Select rarity:", view=view, ephemeral=True)

# --- COG MAIN ---

class Trading(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Wait for database initialization before re-anchoring."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(2) # Give main.py time to finish init_db()
        
        logger.info("📡 Re-anchoring Trade Terminals...")
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Add table check here just in case
                await db.execute("CREATE TABLE IF NOT EXISTS settings (guild_id INTEGER PRIMARY KEY, trade_channel_id INTEGER)")
                async with db.execute("SELECT guild_id, trade_channel_id FROM settings WHERE trade_channel_id IS NOT NULL") as cursor:
                    async for guild_id, channel_id in cursor:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await self.re_anchor_menu(channel)
        except Exception as e:
            logger.error(f"Error in Trading on_ready: {e}")

    async def re_anchor_menu(self, channel):
        """Refresh the trading terminal without spamming the channel."""
        target_msg = None
        duplicates = []
        try:
            async for m in channel.history(limit=50):
                if m.author.id == self.bot.user.id and m.embeds and "Fish-Link" in (m.embeds[0].title or ""):
                    if target_msg is None:
                        target_msg = m
                    else:
                        duplicates.append(m)
        except Exception:
            target_msg = None

        data = await db_get_trade_data(channel.guild.id)
        embed = discord.Embed(
            title="📡 Fish-Link Trading Terminal",
            description=(
                "Server-isolated trading. Use the buttons to add spares or hunts.\n"
                f"**Stock pulse:** {stock_summary(data)}"
            ),
            color=0x2b2d31,
        )

        for rarity in FISH_CONFIG.keys():
            embed.add_field(
                name=f"{rarity} Tier", value=rarity_block(data, rarity), inline=False
            )

        embed.set_footer(text=f"Sector: {channel.guild.name} | Marcia OS")
        view = FishControlView(self.bot, persistent=True)

        if target_msg:
            try:
                await target_msg.edit(embed=embed, view=view)
            except Exception:
                target_msg = None

        if not target_msg:
            await channel.send(embed=embed, view=view)

        for msg in duplicates:
            try:
                await msg.delete()
            except Exception:
                pass

    @commands.command(name="setup_trade")
    @commands.has_permissions(manage_guild=True)
    async def setup_trade(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO settings (guild_id) VALUES (?)", (ctx.guild.id,))
            await db.execute("UPDATE settings SET trade_channel_id = ? WHERE guild_id = ?", (ctx.channel.id, ctx.guild.id))
            await db.commit()
        try: await ctx.message.delete()
        except: pass
        await self.re_anchor_menu(ctx.channel)

async def setup(bot):
    await bot.add_cog(Trading(bot))