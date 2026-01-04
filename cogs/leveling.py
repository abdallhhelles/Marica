"""
FILE: cogs/leveling.py
USE: Multi-server RPG system (SQL Version).
FEATURES: Per-server XP, Scavenging with Rarity, Prestige collectors, and Automated Data Migration.
"""
import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import random
import time
import aiosqlite
from datetime import datetime
from bug_logging import log_command_exception
from assets import SCAVENGE_OUTCOMES, DRONE_NAMES, MARICA_QUOTES, PRESTIGE_ROLE
from database import (
    DB_PATH,
    get_settings,
    get_user_stats,
    update_user_xp,
    add_to_inventory,
    get_inventory,
    update_scavenge_time,
    transfer_inventory,
    top_xp_leaderboard,
    top_global_xp,
    is_channel_ignored,
)

XP_PER_MESSAGE = 12
BASE_XP = 120
ROLE_STEP = 5

RARITY_COLORS = {
    "Common": 0x95a5a6,
    "Uncommon": 0x2ecc71,
    "Rare": 0x3498db,
    "Epic": 0x9b59b6,
    "Legendary": 0xe67e22,
    "Artifact": 0xf1c40f,
    "Mythic": 0xe91e63,
}

RARITY_ORDER = {"Mythic": 0, "Artifact": 1, "Legendary": 2, "Epic": 3, "Rare": 4, "Uncommon": 5, "Common": 6}
ALL_SCAVENGE_ITEMS = {entry[2] for entry in SCAVENGE_OUTCOMES}
TIER_COLORS = [0x3498db, 0x2ecc71, 0x9b59b6, 0xe67e22, 0xf1c40f, 0xe91e63, 0x1abc9c]

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _safe_send(self, ctx, *, ephemeral: bool = False, **kwargs):
        """Send a response for both message and slash contexts without double-acking."""

        interaction = getattr(ctx, "interaction", None)
        if interaction:
            if interaction.response.is_done():
                return await interaction.followup.send(**kwargs, ephemeral=ephemeral)
            return await interaction.response.send_message(**kwargs, ephemeral=ephemeral)

        kwargs.pop("ephemeral", None)
        return await ctx.send(**kwargs)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = int(error.retry_after)
            mins, secs = divmod(retry, 60)
            await self._safe_send(ctx, content=f"⌛ Drones cooling down. Try again in {mins}m {secs}s.")
            error.handled = True
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await self._safe_send(
                ctx,
                content="❌ Usage: `/trade_item @member <quantity> <item name>`.",
                ephemeral=True,
            )
            error.handled = True
            return

        await log_command_exception(self.bot, error, ctx=ctx)
        raise error

    def get_next_xp(self, level):
        """Escalating RPG leveling curve for endless progression."""
        return int(BASE_XP * (level ** 1.25))

    def _format_cooldown(self, seconds: int) -> str:
        """Human-friendly cooldown string like `10m 05s` or `45s`."""
        total = max(0, int(seconds))
        mins, secs = divmod(total, 60)
        if mins:
            return f"{mins}m {secs:02d}s"
        return f"{secs}s"

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        base_error = getattr(error, "original", error)
        if isinstance(base_error, app_commands.CommandOnCooldown):
            retry = int(base_error.retry_after)
            mins, secs = divmod(retry, 60)
            content = f"⌛ Drones cooling down. Try again in {mins}m {secs}s."
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)
            return
        raise error

    async def apply_role_rewards(self, member, level):
        """Automatically assigns dynamic tier roles based on level reached."""
        tier_role = await self.ensure_tier_role(member.guild, level)
        if tier_role and tier_role not in member.roles:
            try:
                # Remove older tier roles to keep things tidy
                old_tiers = [r for r in member.roles if r.name.startswith("Sector Rank ")]
                if old_tiers:
                    await member.remove_roles(*old_tiers, reason="Upgrading tier role")
                await member.add_roles(tier_role, reason="Level up reward")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Passive XP gain with a 60-second anti-spam cooldown."""
        if message.author.bot or not message.guild:
            return

        gid, uid = message.guild.id, message.author.id
        if await is_channel_ignored(gid, message.channel.id):
            return
        user_data = await get_user_stats(gid, uid)
        
        current_ts = time.time()
        # 60 second XP cooldown to prevent spamming
        if not user_data or (current_ts - user_data['last_msg_ts'] > 60):
            # Record message timestamp in database
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE user_stats SET last_msg_ts = ? WHERE guild_id = ? AND user_id = ?",
                                 (current_ts, gid, uid))
                await db.commit()

            await update_user_xp(gid, uid, XP_PER_MESSAGE + random.randint(0, 6))
            
            # Re-fetch to check for level up
            updated = await get_user_stats(gid, uid)
            next_xp_req = self.get_next_xp(updated['level'])
            
            if updated['xp'] >= next_xp_req:
                new_lvl = updated['level'] + 1
                # Level up logic: Reset XP to carry over remainder
                remaining_xp = updated['xp'] - next_xp_req
                await update_user_xp(gid, uid, remaining_xp, new_level=new_lvl)
                
                # Level up Announcement
                embed = discord.Embed(
                    title="🎊 LEVEL SYNCHRONIZED",
                    description=(
                        f"{message.author.mention}, your bio-signature has evolved to **Level {new_lvl}**.\n"
                        f"{random.choice(MARICA_QUOTES)}"
                    ),
                    color=0x2ecc71
                )
                
                # Direct announcement to the chat sector if configured
                settings = await get_settings(gid)
                target = message.channel
                if settings and settings['chat_channel_id']:
                    target = self.bot.get_channel(settings['chat_channel_id']) or message.channel
                
                await target.send(embed=embed)
                await self.apply_role_rewards(message.author, new_lvl)

    @commands.hybrid_command(name="profile", aliases=["p", "rank"], description="Display your Marcia profile, level, and XP.")
    async def profile(self, ctx, member: discord.Member = None):
        """Displays user level, XP, and inventory stats."""
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="❌ Profiles are only available inside servers.",
                ephemeral=True,
            )

        member = member or ctx.author
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.defer()
            except Exception:
                pass

        data = await get_user_stats(ctx.guild.id, member.id)

        lvl = data['level'] if data else 1
        xp = data['xp'] if data else 0
        next_xp_req = self.get_next_xp(lvl)

        # Calculate progress bar
        progress = int((xp / next_xp_req) * 10) if xp > 0 else 0
        progress = min(progress, 10)
        bar = "▰" * progress + "▱" * (10 - progress)

        embed = discord.Embed(title=f"📡 DISPATCH: {member.display_name}", color=0x3498db)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=f"**{lvl}**", inline=True)
        embed.add_field(name="XP", value=f"{xp} / {next_xp_req}", inline=True)
        embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
        
        # Fetch inventory count for profile summary
        inv = await get_inventory(ctx.guild.id, member.id)
        item_count = sum(item['quantity'] for item in inv)
        unique_count = len({item['item_id'] for item in inv})
        embed.add_field(name="Inventory", value=f"📦 {item_count} items | {unique_count}/{len(ALL_SCAVENGE_ITEMS)} unique", inline=True)
        
        await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(description="Deploy a drone to find loot and XP (1h cooldown).")
    async def scavenge(self, ctx):
        """Deploy a drone to find loot and XP. (1 Hour Cooldown)"""
        drone_name = random.choice(DRONE_NAMES)
        outcome = random.choice(SCAVENGE_OUTCOMES)
        flavor, xp_gain, item_name, rarity = outcome

        # Momentum bonus if the survivor keeps scavenging within 90 minutes of the last run
        user_data = await get_user_stats(ctx.guild.id, ctx.author.id)
        last_scavenge_ts = user_data["last_scavenge_ts"] if user_data else 0
        now_ts = time.time()
        if last_scavenge_ts:
            cooldown_remaining = int(3600 - (now_ts - last_scavenge_ts))
            if cooldown_remaining > 0:
                pretty_wait = self._format_cooldown(cooldown_remaining)
                await ctx.reply(
                    f"⌛ Drones cooling down. Try again in {pretty_wait}.",
                    mention_author=False,
                )
                return
        recent_run = last_scavenge_ts and (now_ts - last_scavenge_ts) <= 5400
        momentum_xp = random.randint(15, 35) if recent_run else 0

        # Surprise bonus cache with reduced XP but extra loot
        bonus_outcome = None
        bonus_cache_xp = 0
        if random.random() < 0.18:
            bonus_outcome = random.choice(SCAVENGE_OUTCOMES)
            _, bonus_xp, bonus_item, bonus_rarity = bonus_outcome
            bonus_cache_xp = max(10, bonus_xp // 2)

        total_xp = xp_gain + momentum_xp + bonus_cache_xp

        # Update database
        await update_user_xp(ctx.guild.id, ctx.author.id, total_xp)
        await add_to_inventory(ctx.guild.id, ctx.author.id, item_name, 1, rarity)
        if bonus_outcome:
            await add_to_inventory(ctx.guild.id, ctx.author.id, bonus_item, 1, bonus_rarity)
        await update_scavenge_time(ctx.guild.id, ctx.author.id)

        # Build richer scavenge report
        color_choices = [RARITY_COLORS.get(rarity, 0x2b2d31)]
        description_lines = [f"_{flavor}_"]
        if recent_run:
            description_lines.append("⚡ Momentum maintained — drones pushed harder on this route.")
        if bonus_outcome:
            description_lines.append(f"🎁 Bonus cache: {bonus_item} [{bonus_rarity}] was tucked under the rubble.")
            color_choices.append(RARITY_COLORS.get(bonus_rarity, 0x2b2d31))
        description_lines.append("")
        description_lines.append(random.choice(MARICA_QUOTES))

        embed = discord.Embed(
            title=f"🚁 {drone_name.upper()} RETURNING...",
            description="\n".join(description_lines),
            color=max(color_choices),
        )
        embed.add_field(name="Loot Found", value=f"**{item_name}**", inline=True)
        embed.add_field(name="Rarity", value=f"`{rarity}`", inline=True)

        xp_lines = [f"Base haul: +{xp_gain} XP"]
        if momentum_xp:
            xp_lines.append(f"Momentum chain: +{momentum_xp} XP")
        if bonus_cache_xp:
            xp_lines.append(f"Salvage cache: +{bonus_cache_xp} XP")
        xp_lines.append(f"Total: **+{total_xp} XP**")
        embed.add_field(name="Experience", value="\n".join(xp_lines), inline=True)

        if bonus_outcome:
            embed.add_field(
                name="Bonus Loot",
                value=f"**{bonus_item}** [`{bonus_rarity}`]",
                inline=True,
            )

        embed.set_footer(text="Drone recalibrating. Ready for redeployment in 60 minutes.")

        await ctx.reply(embed=embed)
        await self.check_collector_prestige(ctx.author)

    @commands.hybrid_command(aliases=["inv", "stash"], description="Show your current sector stash.")
    async def inventory(self, ctx):
        """Displays your current server-specific item stash."""
        rows = await get_inventory(ctx.guild.id, ctx.author.id)

        if not rows:
            return await ctx.send(
                "🎒 Your stash is empty. Deploy a drone with `/scavenge` to find gear!"
            )

        # Sort items by rarity (Mythics first)
        sorted_items = sorted(rows, key=lambda x: RARITY_ORDER.get(x['rarity'], 99))

        items_list = "\n".join([f"• **{item['item_id']}** x{item['quantity']} [{item['rarity']}]" for item in sorted_items])

        completion = len({item['item_id'] for item in rows})
        progress_line = f"Collection Progress: {completion}/{len(ALL_SCAVENGE_ITEMS)} unique"

        embed = discord.Embed(
            title=f"🎒 {ctx.author.display_name}'S STASH",
            description=f"{items_list}\n\n{progress_line}",
            color=0x95a5a6
        )
        embed.set_footer(text="Items are local to this sector.")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="trade_item", description="Trade scavenged loot to another survivor.")
    async def trade_item(self, ctx, member: discord.Member, quantity: int, *, item_name: str):
        """Trade scavenged loot to another survivor."""
        if member.bot:
            return await ctx.send("❌ Bots don't need loot.")
        if member.id == ctx.author.id:
            return await ctx.send("❌ Trading with yourself? Even I won't sign that invoice.")
        if quantity <= 0:
            return await ctx.send("❌ Quantity must be positive.")

        item_name = item_name.strip()
        success = await transfer_inventory(ctx.guild.id, ctx.author.id, member.id, item_name, quantity)
        if not success:
            return await ctx.send(f"❌ You don't have {quantity}x **{item_name}** to trade.")

        embed = discord.Embed(
            title="🤝 Trade Logged",
            description=(
                f"{ctx.author.mention} sent **{quantity}x {item_name}** to {member.mention}.\n"
                f"{random.choice(MARICA_QUOTES)}"
            ),
            color=0x3498db,
        )
        await ctx.send(embed=embed)
        await self.check_collector_prestige(ctx.author)
        await self.check_collector_prestige(member)

    @commands.hybrid_command(description="See the top survivors in this sector.")
    async def leaderboard(self, ctx):
        rows = await top_xp_leaderboard(ctx.guild.id)
        if not rows:
            return await ctx.send("📡 No data yet. Tell your crew to talk, trade, and scavenge.")

        embed = discord.Embed(
            title="🏆 Sector Leaderboard",
            description="XP rankings are isolated per sector. Bragging rights stay local.",
            color=0xe67e22,
        )

        lines = []
        for idx, row in enumerate(rows, start=1):
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name if member else f"Unknown {row['user_id']}"
            lines.append(f"**{idx}. {name}** — Level {row['level']} | {row['xp']} XP")

        embed.add_field(name="Ranks", value="\n".join(lines), inline=False)
        embed.set_footer(text="Data is saved between restarts. Keep grinding.")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="global_leaderboard", description="See the top survivors across every linked server.")
    async def global_leaderboard(self, ctx):
        rows = await top_global_xp(10)
        if not rows:
            return await ctx.send(
                "📡 No global data yet. Start chatting and running `/scavenge` to claim the top slots."
            )

        embed = discord.Embed(
            title="🌐 Network Leaderboard",
            description=(
                "Top performers across Marcia's entire network. Each survivor is tagged with their home sector"
                " so bragging rights stay clear."
            ),
            color=0x3498db,
        )

        lines = []
        for idx, row in enumerate(rows, start=1):
            guild = self.bot.get_guild(row["guild_id"])
            guild_name = guild.name if guild else f"Guild {row['guild_id']}"
            user = self.bot.get_user(row["user_id"])
            user_display = user.mention if user else f"<@{row['user_id']}>"
            lines.append(
                f"**{idx}. {user_display}** — Level {row['level']} | {row['xp']} XP ({guild_name})"
            )

        embed.add_field(name="Ranks", value="\n".join(lines), inline=False)
        embed.set_footer(text="Run your alliance like a war machine. /scavenge and climb.")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def import_old_levels(self, ctx):
        """Critical migration tool: Transfers legacy JSON data to the SQL database."""
        if not os.path.exists("levels.json"):
            return await ctx.send("❌ `levels.json` not found in root directory.")
        
        try:
            with open("levels.json", "r") as f:
                old_data = json.load(f)
            
            async with aiosqlite.connect(DB_PATH) as db:
                for uid, stats in old_data.items():
                    # Import Stats with safety check for types
                    user_id = int(uid)
                    xp = stats.get('xp', 0)
                    lvl = stats.get('level', 1)
                    
                    await db.execute('''
                        INSERT OR REPLACE INTO user_stats (guild_id, user_id, xp, level)
                        VALUES (?, ?, ?, ?)
                    ''', (ctx.guild.id, user_id, xp, lvl))
                    
                    # Import Inventory items (handles both string and dict formats)
                    for item in stats.get('inventory', []):
                        name = item['name'] if isinstance(item, dict) else item
                        # Assign default 'Common' rarity for legacy items
                        await db.execute('''
                            INSERT INTO user_inventory (guild_id, user_id, item_id, quantity, rarity)
                            VALUES (?, ?, ?, 1, 'Common')
                            ON CONFLICT(guild_id, user_id, item_id) DO UPDATE SET quantity = quantity + 1
                        ''', (ctx.guild.id, user_id, name))
                await db.commit()
            
            await ctx.send(f"✅ **Sector Data Restored.** Migrated {len(old_data)} user profiles to database.")
        except Exception as e:
            await ctx.send(f"❌ **System Breach during migration:** `{e}`")

    async def ensure_tier_role(self, guild: discord.Guild, level: int) -> discord.Role | None:
        tier = max(ROLE_STEP, (level // ROLE_STEP) * ROLE_STEP)
        color = discord.Color(TIER_COLORS[tier % len(TIER_COLORS)])
        role_name = f"Sector Rank {tier:03d}"
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            return role
        try:
            role = await guild.create_role(name=role_name, color=color, reason="Marcia rank auto-creation")
        except discord.Forbidden:
            return None
        return role

    async def check_collector_prestige(self, member: discord.Member):
        rows = await get_inventory(member.guild.id, member.id)
        owned = {item['item_id'] for item in rows}
        if len(owned) < len(ALL_SCAVENGE_ITEMS):
            return

        prestige = discord.utils.get(member.guild.roles, name=PRESTIGE_ROLE)
        if not prestige:
            try:
                prestige = await member.guild.create_role(
                    name=PRESTIGE_ROLE,
                    color=discord.Color.gold(),
                    reason="Marcia prestige collector unlock",
                )
            except discord.Forbidden:
                return
        if prestige not in member.roles:
            try:
                await member.add_roles(prestige, reason="Completed scavenger catalog")
                await member.send(
                    f"🏅 You secured every artifact in this sector. Prestige role `{PRESTIGE_ROLE}` granted."
                )
            except discord.Forbidden:
                pass

async def setup(bot):
    await bot.add_cog(Leveling(bot))
