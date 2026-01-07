"""
FILE: cogs/leveling.py
USE: Multi-server RPG system (SQL Version).
FEATURES: Per-server XP, Scavenging with Rarity, Prestige collectors, and Automated Data Migration.
"""
import discord
from discord import app_commands
from discord.errors import HTTPException
from discord.ext import commands
import io
import json
import os
import random
import time
import aiosqlite
from datetime import datetime, timezone
from bug_logging import log_command_exception
from assets import (
    SCAVENGE_FIELD_REPORTS,
    SCAVENGE_ZONES,
    SCAVENGE_CONTRACTS,
    SCAVENGE_MISHAPS,
    SCAVENGE_OUTCOMES,
    DRONE_NAMES,
    MARCIA_QUOTES,
    PRESTIGE_ROLE,
)
from database import (
    DB_PATH,
    get_inventory,
    get_profile_snapshot,
    get_settings,
    get_user_stats,
    increment_activity_metric,
    is_channel_ignored,
    top_profile_stat,
    top_global_xp,
    top_xp_leaderboard,
    transfer_inventory,
    update_scavenge_time,
    update_user_xp,
    add_to_inventory,
)

XP_PER_MESSAGE = 12
BASE_XP = 120
ROLE_STEP = 5
ROLE_PREFIX = "Uplink Tier"

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
LEADERBOARD_LIMITS = (10, 25, 50, 100)
PROFILE_STAT_LABELS = {
    "cp": ("Combat Power", "⚔️"),
    "kills": ("Kills", "☠️"),
    "likes": ("Likes", "👍"),
    "vip_level": ("VIP Level", "🎖️"),
}

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _safe_send(self, ctx, *, ephemeral: bool = False, **kwargs):
        """Send a response for both message and slash contexts without double-acking."""

        mention_author = kwargs.pop("mention_author", None)
        if mention_author is False and "allowed_mentions" not in kwargs:
            kwargs["allowed_mentions"] = discord.AllowedMentions(replied_user=False)

        interaction = getattr(ctx, "interaction", None)
        if interaction:
            return await self.bot._safe_interaction_reply(
                interaction, ephemeral=ephemeral, **kwargs
            )

        kwargs.pop("ephemeral", None)
        return await ctx.send(**kwargs)

    @staticmethod
    def _format_metric(value: int | None) -> str:
        return f"{value:,}" if isinstance(value, int) else "—"

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

    def _get_scavenge_zone(self, level: int) -> dict:
        zone_index = min(len(SCAVENGE_ZONES) - 1, max(0, (level - 1) // 10))
        return SCAVENGE_ZONES[zone_index]

    def _roll_scavenge_outcome(self, rarity_boost: float) -> tuple[str, int, str, str]:
        rarity_weights = {
            "Common": 50,
            "Uncommon": 25,
            "Rare": 12,
            "Epic": 6,
            "Legendary": 3,
            "Artifact": 2,
            "Mythic": 1,
        }
        rarity_ranks = {
            "Common": 0,
            "Uncommon": 1,
            "Rare": 2,
            "Epic": 3,
            "Legendary": 4,
            "Artifact": 5,
            "Mythic": 6,
        }
        adjusted = {
            rarity: weight * (1 + rarity_boost * rarity_ranks[rarity])
            for rarity, weight in rarity_weights.items()
        }
        rarities = list(adjusted.keys())
        weights = list(adjusted.values())
        chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]
        rarity_outcomes = [o for o in SCAVENGE_OUTCOMES if o[3] == chosen_rarity]
        return random.choice(rarity_outcomes)

    async def apply_role_rewards(self, member, level):
        """Automatically assigns dynamic tier roles based on level reached."""
        tier_role = await self.ensure_tier_role(member.guild, level)
        if tier_role and tier_role not in member.roles:
            try:
                # Remove older tier roles to keep things tidy
                old_tiers = [r for r in member.roles if r.name.startswith(f"{ROLE_PREFIX} ")]
                if old_tiers:
                    await member.remove_roles(*old_tiers, reason="Upgrading tier role")
                await member.add_roles(tier_role, reason="Level up reward")
            except discord.Forbidden:
                pass

    async def _award_xp(self, guild_id: int, user_id: int, xp_gain: int) -> tuple[int, int, int]:
        """Apply XP gain and handle multi-level progression."""
        data = await get_user_stats(guild_id, user_id)
        current_level = data["level"] if data else 1
        current_xp = data["xp"] if data else 0

        total_xp = current_xp + xp_gain
        level = current_level

        while total_xp >= self.get_next_xp(level):
            total_xp -= self.get_next_xp(level)
            level += 1

        await update_user_xp(guild_id, user_id, total_xp, new_level=level)
        return level, total_xp, level - current_level

    @commands.Cog.listener()
    async def on_message(self, message):
        """Passive XP gain with a 60-second anti-spam cooldown."""
        if message.author.bot or not message.guild:
            return

        if message.type is not discord.MessageType.default:
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

            new_level, _, levels_gained = await self._award_xp(
                gid, uid, XP_PER_MESSAGE + random.randint(0, 6)
            )

            if levels_gained:
                # Level up Announcement
                embed = discord.Embed(
                    title="🎊 LEVEL SYNCHRONIZED",
                    description=(
                        f"{message.author.mention}, your bio-signature has evolved to **Level {new_level}**.\n"
                        f"{random.choice(MARCIA_QUOTES)}"
                    ),
                    color=0x2ecc71
                )
                
                # Direct announcement to the chat sector if configured
                settings = await get_settings(gid)
                target = message.channel
                if settings and settings['chat_channel_id']:
                    target = self.bot.get_channel(settings['chat_channel_id']) or message.channel

                try:
                    await target.send(embed=embed)
                except discord.Forbidden:
                    if target != message.channel:
                        try:
                            await message.channel.send(embed=embed)
                        except discord.Forbidden:
                            pass
                await self.apply_role_rewards(message.author, new_level)

    async def _send_profile_overview(self, ctx, member: discord.Member | None = None):
        """Send the combined profile view with XP and scanned stats."""
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="❌ Profiles are only available inside servers.",
                ephemeral=True,
            )

        member = member or ctx.author
        data = await get_user_stats(ctx.guild.id, member.id)

        lvl = data['level'] if data else 1
        xp = data['xp'] if data else 0
        next_xp_req = self.get_next_xp(lvl)

        # Calculate progress bar
        progress = int((xp / next_xp_req) * 10) if xp > 0 else 0
        progress = min(progress, 10)
        bar = "▰" * progress + "▱" * (10 - progress)
        pct = min(100, int((xp / next_xp_req) * 100)) if next_xp_req else 0

        embed = discord.Embed(
            title=f"📇 Sector dossier | {member.display_name}",
            description=(
                "Progression, stash, and profile scan vitals in one view. Keep this handy before "
                "you deploy or trade."
            ),
            color=0x3498db,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        progression = [
            f"Level **{lvl}**",
            f"XP: {xp:,} / {next_xp_req:,}",
            f"`{bar}` ({pct}%)",
        ]
        embed.add_field(
            name="Progress", value="\n".join(progression), inline=False
        )

        inv = await get_inventory(ctx.guild.id, member.id)
        item_count = sum(item['quantity'] for item in inv)
        unique_count = len({item['item_id'] for item in inv})
        stash_line = f"📦 {item_count} items | {unique_count}/{len(ALL_SCAVENGE_ITEMS)} unique"
        embed.add_field(name="Stash", value=stash_line, inline=True)

        last_scavenge_ts = data["last_scavenge_ts"] if data else 0
        scavenge_streak = data["scavenge_streak"] if data else 0
        zone = self._get_scavenge_zone(lvl)
        if last_scavenge_ts:
            cooldown_remaining = int(3600 - (time.time() - last_scavenge_ts))
            cooldown_label = self._format_cooldown(cooldown_remaining) if cooldown_remaining > 0 else "Ready"
        else:
            cooldown_label = "Ready"
        scavenge_status = [
            f"Zone: **{zone['name']}**",
            f"Cooldown: {cooldown_label}",
            f"Streak: {scavenge_streak} run(s)",
        ]
        embed.add_field(name="Scavenge Status", value="\n".join(scavenge_status), inline=True)

        snapshot = await get_profile_snapshot(ctx.guild.id, member.id)
        if snapshot:
            ingame = [
                f"🪪 Name: {snapshot.get('player_name') or member.display_name}",
                f"🏰 Alliance: {snapshot.get('alliance') or '—'}",
                f"🌐 Server: {snapshot.get('server') or '—'}",
                f"🎖️ VIP: {self._format_metric(snapshot.get('vip_level'))} | 👍 Likes: {self._format_metric(snapshot.get('likes'))}",
                f"⚔️ CP: {self._format_metric(snapshot.get('cp'))} | ☠️ Kills: {self._format_metric(snapshot.get('kills'))}",
            ]
            if snapshot.get("ownership_verified") is not None:
                status = "✅ Self-view detected" if snapshot["ownership_verified"] else "⚠️ Could not confirm this is your own profile"
                ingame.append(status)
            if snapshot.get("last_image_url"):
                ingame.append(f"🖼️ [Latest scan]({snapshot['last_image_url']})")
            embed.add_field(
                name="In-game Profile Scan", value="\n".join(ingame), inline=False
            )

            if snapshot.get("last_updated"):
                dt = datetime.fromtimestamp(snapshot["last_updated"], tz=timezone.utc)
                embed.set_footer(text=f"Last scanned {dt.strftime('%Y-%m-%d %H:%M UTC')}")
        else:
            embed.add_field(
                name="Profile Scan",
                value="No profile scan stats stored yet. Run `/scan_profile` to capture your card.",
                inline=False,
            )

        await increment_activity_metric(ctx.guild.id, "profile_views")
        await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(name="profile", aliases=["p", "rank"], description="Display your Marcia profile, level, and XP.")
    async def profile(self, ctx, member: discord.Member = None):
        """Displays user level, XP, inventory, and scanned stats."""
        await self._send_profile_overview(ctx, member)

    @commands.hybrid_command(description="Deploy a drone to find loot and XP (1h cooldown).")
    async def scavenge(self, ctx):
        """Deploy a drone to find loot and XP. (1 Hour Cooldown)"""
        drone_name = random.choice(DRONE_NAMES)

        # Momentum bonus if the survivor keeps scavenging within 90 minutes of the last run
        user_data = await get_user_stats(ctx.guild.id, ctx.author.id)
        last_scavenge_ts = user_data["last_scavenge_ts"] if user_data else 0
        current_level = user_data["level"] if user_data else 1
        current_streak = user_data["scavenge_streak"] if user_data else 0
        now_ts = time.time()
        if last_scavenge_ts:
            cooldown_remaining = int(3600 - (now_ts - last_scavenge_ts))
            if cooldown_remaining > 0:
                pretty_wait = self._format_cooldown(cooldown_remaining)
                await self._safe_send(
                    ctx,
                    content=f"⌛ Drones cooling down. Try again in {pretty_wait}.",
                    mention_author=False,
                )
                return

        await increment_activity_metric(ctx.guild.id, "scavenge_runs")
        recent_run = last_scavenge_ts and (now_ts - last_scavenge_ts) <= 5400
        streak_window = 10800
        streak = current_streak + 1 if last_scavenge_ts and (now_ts - last_scavenge_ts) <= streak_window else 1
        streak = min(streak, 10)
        momentum_xp = random.randint(15, 35) if recent_run else 0
        field_report = random.choice(SCAVENGE_FIELD_REPORTS)
        contract = random.choice(SCAVENGE_CONTRACTS)
        zone = self._get_scavenge_zone(current_level)
        rarity_boost = zone["rarity_bonus"] + min(0.12, streak * 0.02) + min(0.08, current_level / 250)
        mishap_chance = 0.14 + zone["mishap_bonus"] - min(0.03, streak * 0.01)
        overclock = streak // 3

        # Failure factor: sometimes the drones return empty-handed but with intel
        if random.random() < mishap_chance:
            mishap_reason, mishap_xp = random.choice(SCAVENGE_MISHAPS)
            mishap_reason = mishap_reason.format(drone=drone_name)
            streak_xp = max(0, (streak - 1) * 4)
            milestone_xp = 25 if streak in (5, 10) else 0
            zone_xp = zone["xp_bonus"] // 2
            total_xp = mishap_xp + momentum_xp + streak_xp + milestone_xp + zone_xp

            new_level, _, levels_gained = await self._award_xp(ctx.guild.id, ctx.author.id, total_xp)
            await update_scavenge_time(ctx.guild.id, ctx.author.id, streak=streak)

            description_lines = [
                f"_{mishap_reason}_",
                "",
                f"📍 Zone: **{zone['name']}** — {zone['tagline']}",
                f"🗂️ Contract: {contract}",
                "",
                field_report,
                "",
                random.choice(MARCIA_QUOTES),
            ]
            embed = discord.Embed(
                title=f"🚫 {drone_name.upper()} RETURNED EMPTY",
                description="\n".join(description_lines),
                color=0xe67e22,
            )
            embed.add_field(name="Status", value="Mission scrubbed — no salvage recovered.", inline=False)
            xp_lines = [f"Recon data: +{mishap_xp} XP"]
            if momentum_xp:
                xp_lines.append(f"Momentum chain: +{momentum_xp} XP")
            if zone_xp:
                xp_lines.append(f"Zone hazard pay: +{zone_xp} XP")
            if streak_xp:
                xp_lines.append(f"Streak discipline: +{streak_xp} XP")
            if milestone_xp:
                xp_lines.append(f"Streak milestone: +{milestone_xp} XP")
            xp_lines.append(f"Total: **+{total_xp} XP**")
            embed.add_field(name="Experience", value="\n".join(xp_lines), inline=False)
            embed.add_field(name="Streak", value=f"{streak} run(s) logged", inline=True)
            if levels_gained:
                embed.add_field(
                    name="Level Up",
                    value=f"{ROLE_PREFIX} elevated to **Level {new_level}**.",
                    inline=False,
                )
            embed.set_footer(text="Drone recalibrating. Ready for redeployment in 60 minutes.")

            await self._safe_send(ctx, embed=embed)
            if levels_gained:
                await self.apply_role_rewards(ctx.author, new_level)
            return

        outcome = self._roll_scavenge_outcome(rarity_boost)
        flavor, xp_gain, item_name, rarity = outcome

        # Surprise bonus cache with reduced XP but extra loot
        bonus_outcome = None
        bonus_cache_xp = 0
        bonus_cache_chance = 0.12 + (overclock * 0.04) + zone["rarity_bonus"]
        if random.random() < bonus_cache_chance:
            bonus_outcome = self._roll_scavenge_outcome(rarity_boost * 0.75)
            _, bonus_xp, bonus_item, bonus_rarity = bonus_outcome
            bonus_cache_xp = max(10, bonus_xp // 2)

        streak_xp = max(0, (streak - 1) * 6)
        overclock_xp = overclock * 12
        milestone_xp = 25 if streak in (5, 10) else 0
        zone_xp = zone["xp_bonus"]
        total_xp = xp_gain + momentum_xp + bonus_cache_xp + streak_xp + overclock_xp + milestone_xp + zone_xp

        # Update database
        new_level, _, levels_gained = await self._award_xp(ctx.guild.id, ctx.author.id, total_xp)
        await add_to_inventory(ctx.guild.id, ctx.author.id, item_name, 1, rarity)
        if bonus_outcome:
            await add_to_inventory(ctx.guild.id, ctx.author.id, bonus_item, 1, bonus_rarity)
        await update_scavenge_time(ctx.guild.id, ctx.author.id, streak=streak)

        # Build richer scavenge report
        color_choices = [RARITY_COLORS.get(rarity, 0x2b2d31)]
        description_lines = [
            f"_{flavor}_",
            "",
            f"📍 Zone: **{zone['name']}** — {zone['tagline']}",
            f"🗂️ Contract: {contract}",
            field_report,
            random.choice(MARCIA_QUOTES),
        ]
        if recent_run:
            description_lines.insert(1, "⚡ Momentum maintained — drones pushed harder on this route.")
        if bonus_outcome:
            description_lines.insert(2, f"🎁 Bonus cache: {bonus_item} [{bonus_rarity}] was tucked under the rubble.")
            color_choices.append(RARITY_COLORS.get(bonus_rarity, 0x2b2d31))

        embed = discord.Embed(
            title=f"🚁 {drone_name.upper()} RETURNING...",
            description="\n".join(description_lines),
            color=max(color_choices),
        )
        embed.add_field(name="Loot", value=f"**{item_name}** [`{rarity}`]", inline=True)

        xp_lines = [f"Base haul: +{xp_gain} XP"]
        if momentum_xp:
            xp_lines.append(f"Momentum chain: +{momentum_xp} XP")
        if zone_xp:
            xp_lines.append(f"Zone hazard pay: +{zone_xp} XP")
        if streak_xp:
            xp_lines.append(f"Streak discipline: +{streak_xp} XP")
        if overclock_xp:
            xp_lines.append(f"Overclock bonus: +{overclock_xp} XP")
        if milestone_xp:
            xp_lines.append(f"Streak milestone: +{milestone_xp} XP")
        if bonus_cache_xp:
            xp_lines.append(f"Salvage cache: +{bonus_cache_xp} XP")
        xp_lines.append(f"Total: **+{total_xp} XP**")
        embed.add_field(name="Experience", value="\n".join(xp_lines), inline=True)
        embed.add_field(name="Streak", value=f"{streak} run(s) logged", inline=True)
        if levels_gained:
            embed.add_field(
                name="Level Up",
                value=f"{ROLE_PREFIX} elevated to **Level {new_level}**.",
                inline=True,
            )

        if bonus_outcome:
            embed.add_field(
                name="Bonus Loot",
                value=f"**{bonus_item}** [`{bonus_rarity}`]",
                inline=True,
            )

        embed.set_footer(text="Drone recalibrating. Ready for redeployment in 60 minutes.")

        await self._safe_send(ctx, embed=embed)
        if levels_gained:
            await self.apply_role_rewards(ctx.author, new_level)
        await self.check_collector_prestige(ctx.author)

    @commands.hybrid_command(aliases=["inv", "stash"], description="Show your current sector stash.")
    async def inventory(self, ctx):
        """Displays your current server-specific item stash."""
        rows = await get_inventory(ctx.guild.id, ctx.author.id)

        if not rows:
            return await self._safe_send(
                ctx,
                content="🎒 Your stash is empty. Deploy a drone with `/scavenge` to find gear!",
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
        await self._safe_send(ctx, embed=embed)

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
                f"{random.choice(MARCIA_QUOTES)}"
            ),
            color=0x3498db,
        )
        await ctx.send(embed=embed)
        await self.check_collector_prestige(ctx.author)
        await self.check_collector_prestige(member)

    async def _build_leaderboard_embed(
        self, guild: discord.Guild | None, selection: str, limit: int = 10
    ) -> discord.Embed:
        """Generate a leaderboard embed for the requested data slice."""

        if not guild:
            return discord.Embed(
                title="🏅 Leaderboards",
                description="Leaderboards are scoped to servers. Run this inside a guild.",
                color=0xe67e22,
            )

        if selection == "local_xp":
            rows = await top_xp_leaderboard(guild.id, limit)
            if not rows:
                return discord.Embed(
                    title="🏆 Sector XP",
                    description="No data yet. Talk, trade, and scavenge to generate rankings.",
                    color=0xe67e22,
                )

            embed = discord.Embed(
                title="🏆 Sector XP",
                description="XP rankings are isolated per sector. Bragging rights stay local.",
                color=0xe67e22,
            )
            lines = []
            for idx, row in enumerate(rows, start=1):
                member = guild.get_member(row["user_id"])
                name = member.display_name if member else f"Unknown {row['user_id']}"
                lines.append(
                    f"**{idx}. {name}** — Level {row['level']} | {row['xp']:,} XP"
                )
            embed.add_field(name="Ranks", value="\n".join(lines), inline=False)
            embed.set_footer(
                text=f"Showing top {len(rows)} survivors. Data is saved between restarts. Keep grinding."
            )
            return embed

        if selection == "global_xp":
            rows = await top_global_xp(limit)
            if not rows:
                return discord.Embed(
                    title="🌐 Network Leaderboard",
                    description=(
                        "No global data yet. Start chatting and running `/scavenge` to claim the top slots."
                    ),
                    color=0x3498db,
                )

            embed = discord.Embed(
                title="🌐 Network Leaderboard",
                description=(
                    "Top performers across Marcia's entire network. Each survivor is tagged with their home sector."
                ),
                color=0x3498db,
            )
            lines = []
            for idx, row in enumerate(rows, start=1):
                source_guild = self.bot.get_guild(row["guild_id"])
                guild_name = source_guild.name if source_guild else f"Guild {row['guild_id']}"
                user = self.bot.get_user(row["user_id"])
                user_display = user.mention if user else f"<@{row['user_id']}>"
                lines.append(
                    f"**{idx}. {user_display}** — Level {row['level']} | {row['xp']:,} XP ({guild_name})"
                )
            embed.add_field(name="Ranks", value="\n".join(lines), inline=False)
            embed.set_footer(
                text=f"Showing top {len(rows)} survivors. Run your alliance like a war machine. /scavenge and climb."
            )
            return embed

        stat_label, emoji = PROFILE_STAT_LABELS.get(selection, (selection.title(), "📈"))
        rows = await top_profile_stat(guild.id, selection, limit)
        if not rows:
            return discord.Embed(
                title=f"{emoji} {stat_label} Leaderboard",
                description="No scanned profiles yet. Run `/scan_profile` and try again.",
                color=0xf1c40f,
            )

        embed = discord.Embed(
            title=f"{emoji} {stat_label} Leaderboard",
            description="Profile scan stats from the latest profile scans in this sector.",
            color=0xf1c40f,
        )
        lines = []
        for idx, row in enumerate(rows, start=1):
            user = guild.get_member(row["user_id"])
            name = row["player_name"] or (user.display_name if user else f"User {row['user_id']}")
            lines.append(f"**{idx}.** {name} — {self._format_metric(row['value'])}")
        embed.add_field(name="Ranks", value="\n".join(lines), inline=False)
        embed.set_footer(
            text=f"Showing top {len(rows)} survivors. Use `/scan_profile` then `/leaderboard` to surface fresh scans."
        )
        return embed

    async def _export_leaderboard_data(
        self, guild: discord.Guild | None, selection: str, limit: int
    ) -> tuple[io.StringIO, str, str] | None:
        if not guild:
            return None

        rows: list[dict] = []
        headers: list[str]
        filename: str
        note: str

        if selection == "local_xp":
            rows = await top_xp_leaderboard(guild.id, limit)
            if not rows:
                return None
            headers = ["Rank", "User", "Level", "XP"]
            filename = f"leaderboard_sector_{guild.id}.tsv"
            note = f"Sector XP leaderboard (top {len(rows)})."
            lines = ["\t".join(headers)]
            for idx, row in enumerate(rows, start=1):
                member = guild.get_member(row["user_id"])
                name = member.display_name if member else f"User {row['user_id']}"
                lines.append("\t".join(map(str, [idx, name, row["level"], row["xp"]])))
        elif selection == "global_xp":
            rows = await top_global_xp(limit)
            if not rows:
                return None
            headers = ["Rank", "User", "Level", "XP", "Guild"]
            filename = "leaderboard_global.tsv"
            note = f"Network XP leaderboard (top {len(rows)})."
            lines = ["\t".join(headers)]
            for idx, row in enumerate(rows, start=1):
                source_guild = self.bot.get_guild(row["guild_id"])
                guild_name = source_guild.name if source_guild else f"Guild {row['guild_id']}"
                user = self.bot.get_user(row["user_id"])
                user_display = user.name if user else f"User {row['user_id']}"
                lines.append(
                    "\t".join(
                        map(
                            str,
                            [idx, user_display, row["level"], row["xp"], guild_name],
                        )
                    )
                )
        else:
            stat_label, _ = PROFILE_STAT_LABELS.get(selection, (selection.title(), ""))
            rows = await top_profile_stat(guild.id, selection, limit)
            if not rows:
                return None
            headers = ["Rank", "User", stat_label]
            filename = f"leaderboard_{selection}_{guild.id}.tsv"
            note = f"{stat_label} leaderboard (top {len(rows)})."
            lines = ["\t".join(headers)]
            for idx, row in enumerate(rows, start=1):
                member = guild.get_member(row["user_id"])
                name = row["player_name"] or (member.display_name if member else f"User {row['user_id']}")
                lines.append("\t".join(map(str, [idx, name, row["value"]])))

        buffer = io.StringIO("\n".join(lines))
        buffer.seek(0)
        return buffer, filename, note

    @commands.hybrid_command(description="Browse XP and profile scan leaderboards from one menu.")
    async def leaderboard(self, ctx):
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Leaderboards only work inside servers.",
                ephemeral=True,
            )

        view = LeaderboardView(
            self, ctx.guild, requester_id=ctx.author.id, selection="local_xp"
        )
        embed = await self._build_leaderboard_embed(ctx.guild, "local_xp", view.limit)
        message = await self._safe_send(ctx, embed=embed, view=view)
        if isinstance(message, discord.Message):
            view.bind_message(message)

    @commands.hybrid_command(name="global_leaderboard", description="See the top survivors across every linked server.")
    async def global_leaderboard(self, ctx):
        view = LeaderboardView(
            self, ctx.guild, requester_id=ctx.author.id, selection="global_xp"
        )
        embed = await self._build_leaderboard_embed(ctx.guild, "global_xp", view.limit)
        message = await self._safe_send(ctx, embed=embed, view=view)
        if isinstance(message, discord.Message):
            view.bind_message(message)

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
        role_name = f"{ROLE_PREFIX} {tier:03d}"
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

class LeaderboardSelect(discord.ui.Select):
    def __init__(self, parent_view: "LeaderboardView"):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label="Sector XP", description="Top survivors in this server", value="local_xp", emoji="🏆"
            ),
            discord.SelectOption(
                label="Network XP", description="Top survivors across linked servers", value="global_xp", emoji="🌐"
            ),
        ]

        for stat, (label, emoji) in PROFILE_STAT_LABELS.items():
            options.append(
                discord.SelectOption(
                    label=f"{label} (Profile Scan)",
                    description=f"Profile scans ranked by {label.lower()}",
                    value=stat,
                    emoji=emoji,
                )
            )

        for option in options:
            option.default = option.value == parent_view.selection
        super().__init__(
            placeholder="Pick a leaderboard to view",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.requester_id:
            return await interaction.response.send_message(
                "Only the original requester can change this menu.", ephemeral=True
            )

        self.parent_view.selection = self.values[0]
        for option in self.options:
            option.default = option.value == self.values[0]
        await self.parent_view.refresh(interaction)


class LeaderboardLimitSelect(discord.ui.Select):
    def __init__(self, parent_view: "LeaderboardView"):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label=str(limit), value=str(limit), default=limit == parent_view.limit)
            for limit in LEADERBOARD_LIMITS
        ]
        super().__init__(
            placeholder="Rows to display", options=options, min_values=1, max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.requester_id:
            return await interaction.response.send_message(
                "Only the original requester can change this menu.", ephemeral=True
            )

        self.parent_view.limit = int(self.values[0])
        for option in self.options:
            option.default = option.value == self.values[0]
        await self.parent_view.refresh(interaction)


class ExportLeaderboardButton(discord.ui.Button):
    def __init__(self, parent_view: "LeaderboardView"):
        super().__init__(label="Export (Excel)", emoji="📤", style=discord.ButtonStyle.secondary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.requester_id:
            return await interaction.response.send_message(
                "Only the original requester can export this leaderboard.", ephemeral=True
            )

        export = await self.parent_view.cog._export_leaderboard_data(
            self.parent_view.guild, self.parent_view.selection, self.parent_view.limit
        )
        if not export:
            return await interaction.response.send_message(
                "No leaderboard data available to export yet.", ephemeral=True
            )

        buffer, filename, note = export
        file = discord.File(buffer, filename=filename)

        try:
            await interaction.user.send(content=note, file=file)
        except discord.Forbidden:
            return await interaction.response.send_message(
                "I couldn't DM you. Please enable DMs from server members and try again.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"📤 Sent you **{filename}** with the current leaderboard.", ephemeral=True
        )


class LeaderboardView(discord.ui.View):
    def __init__(
        self,
        cog: Leveling,
        guild: discord.Guild,
        requester_id: int,
        *,
        selection: str,
        limit: int = 10,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.requester_id = requester_id
        self.selection = selection
        self.limit = limit if limit in LEADERBOARD_LIMITS else LEADERBOARD_LIMITS[0]
        self.message: discord.Message | None = None
        self.add_item(LeaderboardSelect(self))
        self.add_item(LeaderboardLimitSelect(self))
        self.add_item(ExportLeaderboardButton(self))

    def bind_message(self, message: discord.Message) -> None:
        self.message = message

    async def refresh(self, interaction: discord.Interaction | None = None):
        embed = await self.cog._build_leaderboard_embed(
            self.guild, self.selection, self.limit
        )
        if interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.message:
            await self.message.edit(embed=embed, view=self)

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

async def setup(bot):
    await bot.add_cog(Leveling(bot))
