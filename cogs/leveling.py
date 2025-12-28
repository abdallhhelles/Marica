"""
FILE: cogs/leveling.py
USE: Multi-server RPG system (SQL Version).
FEATURES: Per-server XP, Scavenging with Rarity, and Automated Data Migration.
"""
import discord
from discord.ext import commands
import json
import os
import random
import time
import aiosqlite
from datetime import datetime
from assets import SCAVENGE_OUTCOMES, DRONE_NAMES
from database import DB_PATH, get_settings, get_user_stats, update_user_xp, add_to_inventory, get_inventory, update_scavenge_time

XP_PER_MESSAGE = 10
BASE_XP = 100
# Define roles that exist in your server to be auto-assigned
ROLE_REWARDS = {5: "Scout", 10: "Veteran", 20: "Alliance Elite"}

RARITY_COLORS = {
    "Common": 0x95a5a6, 
    "Uncommon": 0x2ecc71, 
    "Rare": 0x3498db,
    "Epic": 0x9b59b6, 
    "Artifact": 0xf1c40f
}

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_next_xp(self, level):
        """Standard RPG leveling curve."""
        return level * BASE_XP

    async def apply_role_rewards(self, member, level):
        """Automatically assigns roles based on level reached."""
        for rank_lvl, role_name in ROLE_REWARDS.items():
            if level >= rank_lvl:
                role = discord.utils.get(member.guild.roles, name=role_name)
                if role and role not in member.roles:
                    try: 
                        await member.add_roles(role)
                    except discord.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Passive XP gain with a 60-second anti-spam cooldown."""
        if message.author.bot or not message.guild:
            return
        
        gid, uid = message.guild.id, message.author.id
        user_data = await get_user_stats(gid, uid)
        
        current_ts = time.time()
        # 60 second XP cooldown to prevent spamming
        if not user_data or (current_ts - user_data['last_msg_ts'] > 60):
            # Record message timestamp in database
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE user_stats SET last_msg_ts = ? WHERE guild_id = ? AND user_id = ?", 
                                 (current_ts, gid, uid))
                await db.commit()

            await update_user_xp(gid, uid, XP_PER_MESSAGE)
            
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
                    description=f"{message.author.mention}, your bio-signature has evolved to **Level {new_lvl}**.",
                    color=0x2ecc71
                )
                
                # Direct announcement to the chat sector if configured
                settings = await get_settings(gid)
                target = message.channel
                if settings and settings['chat_channel_id']:
                    target = self.bot.get_channel(settings['chat_channel_id']) or message.channel
                
                await target.send(embed=embed)
                await self.apply_role_rewards(message.author, new_lvl)

    @commands.command(name="profile", aliases=["p", "rank"])
    async def profile(self, ctx, member: discord.Member = None):
        """Displays user level, XP, and inventory stats."""
        member = member or ctx.author
        data = await get_user_stats(ctx.guild.id, member.id)
        
        lvl = data['level'] if data else 1
        xp = data['xp'] if data else 0
        next_xp_req = self.get_next_xp(lvl)
        
        # Calculate progress bar
        progress = int((xp / next_xp_req) * 10) if xp > 0 else 0
        bar = "▰" * progress + "▱" * (10 - progress)

        embed = discord.Embed(title=f"📡 DISPATCH: {member.display_name}", color=0x3498db)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=f"**{lvl}**", inline=True)
        embed.add_field(name="XP", value=f"{xp} / {next_xp_req}", inline=True)
        embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
        
        # Fetch inventory count for profile summary
        inv = await get_inventory(ctx.guild.id, member.id)
        item_count = sum(item['quantity'] for item in inv)
        embed.add_field(name="Inventory", value=f"📦 {item_count} items in stash", inline=True)
        
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def scavenge(self, ctx):
        """Deploy a drone to find loot and XP. (1 Hour Cooldown)"""
        drone_name = random.choice(DRONE_NAMES)
        outcome = random.choice(SCAVENGE_OUTCOMES)
        flavor, xp_gain, item_name, rarity = outcome
        
        # Update database
        await update_user_xp(ctx.guild.id, ctx.author.id, xp_gain)
        await add_to_inventory(ctx.guild.id, ctx.author.id, item_name, 1, rarity)
        await update_scavenge_time(ctx.guild.id, ctx.author.id)

        embed = discord.Embed(
            title=f"🚁 {drone_name.upper()} RETURNING...",
            description=f"_{flavor}_",
            color=RARITY_COLORS.get(rarity, 0x2b2d31)
        )
        embed.add_field(name="Loot Found", value=f"**{item_name}**", inline=True)
        embed.add_field(name="Rarity", value=f"`{rarity}`", inline=True)
        embed.add_field(name="Experience", value=f"+{xp_gain} XP", inline=True)
        embed.set_footer(text="Drone recalibrating. Ready for redeployment in 60 minutes.")
        
        await ctx.reply(embed=embed)

    @commands.command(aliases=["inv", "stash"])
    async def inventory(self, ctx):
        """Displays your current server-specific item stash."""
        rows = await get_inventory(ctx.guild.id, ctx.author.id)

        if not rows:
            return await ctx.send("🎒 Your stash is empty. Deploy a drone with `!scavenge` to find gear!")

        # Sort items by rarity (Artifacts first)
        rarity_order = {"Artifact": 0, "Epic": 1, "Rare": 2, "Uncommon": 3, "Common": 4}
        sorted_items = sorted(rows, key=lambda x: rarity_order.get(x['rarity'], 5))

        items_list = "\n".join([f"• **{item['item_id']}** x{item['quantity']} [{item['rarity']}]" for item in sorted_items])
        
        embed = discord.Embed(
            title=f"🎒 {ctx.author.display_name}'S STASH",
            description=items_list,
            color=0x95a5a6
        )
        embed.set_footer(text="Items are local to this sector.")
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

async def setup(bot):
    await bot.add_cog(Leveling(bot))