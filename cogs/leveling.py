"""
FILE: cogs/leveling.py
USE: Multi-server RPG system (SQL Version).
FEATURES: Per-server XP, Scavenging with Rarity, and Prestige collectors.
"""
import discord
from discord import app_commands
from discord.errors import HTTPException
from discord.ext import commands
import io
import random
import time
import aiosqlite
from datetime import datetime, timezone
from utils.bug_logging import log_command_exception
from utils.assets import (
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
    add_to_inventory,
    get_duel_leaderboard,
    get_duel_scores_for_user,
    get_duel_weeks,
    get_inventory,
    get_latest_duel_score,
    get_latest_duel_week,
    get_profile_snapshot,
    get_settings,
    get_user_stats,
    increment_activity_metric,
    is_channel_ignored,
    log_inventory_transfer,
    top_global_profile_stat,
    top_global_xp,
    top_profile_stat,
    top_xp_leaderboard,
    update_scavenge_time,
    update_user_xp,
    transfer_inventory,
)

XP_PER_MESSAGE = 12
BASE_XP = 120
ROLE_STEP = 5
ROLE_PREFIX = "Uplink Tier"
ROLE_TITLES = [
    "Scrap Initiate",
    "Dustline Runner",
    "Signal Scout",
    "Relay Warden",
    "Grid Operative",
    "Outlands Ranger",
    "Salvage Marshal",
    "Blacksite Courier",
    "Echo Pathfinder",
    "Iron Vanguard",
    "Ghostline Tracker",
    "Rift Enforcer",
    "Nullwatch Captain",
    "Apex Cartographer",
    "Vaultbreaker",
    "Stormhand Commander",
    "Redline Sentinel",
    "Obsidian Overseer",
    "Skyfall Director",
    "Uplink Sovereign",
]

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
    "level": ("Profile Level", "⭐"),
}
LEADERBOARD_METRICS = {
    "xp": ("XP", "🏆"),
    **PROFILE_STAT_LABELS,
    "duel": ("Duel Score", "⚔️"),
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
        return f"{value:,}" if isinstance(value, int) else "-"

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
                content="❌ Missing required info. Check `/gyper commands` for the full syntax list.",
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
                old_tiers = [
                    r for r in member.roles
                    if r.name in ROLE_TITLES or r.name.startswith(f"{ROLE_PREFIX} ")
                ]
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

        ctx = await self.bot.get_context(message)
        if ctx.valid:
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

    def _tier_title_for_level(self, level: int) -> str:
        tier = max(ROLE_STEP, (level // ROLE_STEP) * ROLE_STEP)
        role_name = getattr(self, "_tier_role_name", None)
        if callable(role_name):
            return role_name(tier)
        return f"{ROLE_PREFIX} {tier:03d}"

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

        tier_title = self._tier_title_for_level(lvl)
        embed = discord.Embed(
            title=f"📇 Sector Dossier | {member.display_name}",
            description=(
                "Fast-glance ops card for progression, stash, and profile intel."
            ),
            color=0x3498db,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        progression = [
            f"**Level:** {lvl}",
            f"**Tier:** {tier_title}",
            f"**XP:** {xp:,} / {next_xp_req:,}",
            f"`{bar}` ({pct}%)",
        ]
        embed.add_field(
            name="Progress", value="\n".join(progression), inline=True
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
        if snapshot and snapshot.get("scan_valid", 1):
            ingame = [
                f"🪪 Name: {snapshot.get('player_name') or member.display_name}",
                f"🏰 Alliance: {snapshot.get('alliance') or '-'}",
                f"🌐 Server: {snapshot.get('server') or '-'}",
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
                value="No valid profile scan stats stored yet. Run `/gyper scan` to capture your card.",
                inline=False,
            )

        duel_latest = await get_latest_duel_score(ctx.guild.id, member.id)
        profile_view: discord.ui.View | None = None
        if duel_latest:
            score_text = duel_latest.get("score_text") or "-"
            score_int = duel_latest.get("score_int")
            score_value = f"{score_text}"
            if score_int is not None:
                score_value = f"{score_text} ({score_int:,})"
            embed.add_field(
                name="Duel Score (Latest)",
                value=f"Week {duel_latest.get('week_key')}: {score_value}",
                inline=False,
            )
            profile_view = DuelHistoryView(
                requester_id=ctx.author.id,
                guild_id=ctx.guild.id,
                user_id=member.id,
            )

        await increment_activity_metric(ctx.guild.id, "profile_views")
        if profile_view:
            await self._safe_send(ctx, embed=embed, view=profile_view)
        else:
            await self._safe_send(ctx, embed=embed)

    @commands.hybrid_command(
        name="profile",
        aliases=["p", "rank"],
        description="Show detailed Discord + in-game stats for you or another survivor.",
    )
    async def profile(self, ctx, member: discord.Member = None):
        """Displays user level, XP, inventory, and scanned stats."""
        await self._send_profile_overview(ctx, member)

    @commands.hybrid_command(description="Scavenge in the Discord mini game (1h cooldown).")
    async def scavenge(self, ctx):
        """Deploy a drone to find loot and XP. (1 Hour Cooldown)"""
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="🚁 Scavenging is only available inside servers.",
                ephemeral=True,
            )
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
                f"📍 Zone: **{zone['name']}** - {zone['tagline']}",
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
            embed.add_field(name="Status", value="Mission scrubbed - no salvage recovered.", inline=False)
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
            f"📍 Zone: **{zone['name']}** - {zone['tagline']}",
            f"🗂️ Contract: {contract}",
            field_report,
            random.choice(MARCIA_QUOTES),
        ]
        if recent_run:
            description_lines.insert(1, "⚡ Momentum maintained - drones pushed harder on this route.")
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

    @commands.hybrid_command(
        aliases=["inv", "stash"],
        description="Show scavenging inventory and send an item to another user.",
    )
    async def inventory(self, ctx):
        """Displays your current server-specific item stash."""
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="🎒 Inventory is only available inside servers.",
                ephemeral=True,
            )
        rows = await get_inventory(ctx.guild.id, ctx.author.id)

        if not rows:
            return await self._safe_send(
                ctx,
                content="🎒 Your stash is empty. Deploy a drone with `/gyper scavenge` to find gear!",
            )

        # Sort items by rarity (Mythics first)
        sorted_items = sorted(rows, key=lambda x: RARITY_ORDER.get(x['rarity'], 99))

        items_list = "\n".join([f"• **{item['item_id']}** x{item['quantity']} [{item['rarity']}]" for item in sorted_items])

        completion = len({item['item_id'] for item in rows})
        progress_line = f"Collection Progress: {completion}/{len(ALL_SCAVENGE_ITEMS)} unique"

        embed = discord.Embed(
            title=f"🎒 {ctx.author.display_name}'S STASH",
            description=f"{items_list}\n\n{progress_line}",
            color=0x5865F2
        )
        embed.set_footer(text="Items are local to this sector.")
        view = InventoryTransferView(ctx, sorted_items, embed)
        await self._safe_send(ctx, embed=embed, view=view)

    async def _build_leaderboard_embed(
        self,
        guild: discord.Guild | None,
        scope: str,
        metric: str,
        limit: int = 10,
        *,
        week_key: str | None = None,
    ) -> discord.Embed:
        """Generate a leaderboard embed for the requested data slice."""

        if not guild:
            return discord.Embed(
                title="🏅 Leaderboards",
                description="Leaderboards are scoped to servers. Run this inside a guild.",
                color=0x5865F2,
            )

        if metric == "xp" and scope != "global":
            rows = await top_xp_leaderboard(guild.id, limit)
            if not rows:
                return discord.Embed(
                    title="🏆 Sector XP",
                    description="No data yet. Talk, trade, and scavenge to generate rankings.",
                    color=0x5865F2,
                )

            embed = discord.Embed(
                title="🏆 Sector XP",
                description="XP rankings are isolated per sector. Bragging rights stay local.",
                color=0x5865F2,
            )
            lines = []
            for idx, row in enumerate(rows, start=1):
                member = guild.get_member(row["user_id"])
                name = member.display_name if member else f"Unknown {row['user_id']}"
                lines.append(
                    f"**{idx}. {name}** - Level {row['level']} | {row['xp']:,} XP"
                )
            embed.add_field(name="Ranks", value=self._fit_embed_lines(lines), inline=False)
            embed.set_footer(
                text=f"Showing top {len(rows)} survivors. Data is saved between restarts. Keep grinding."
            )
            return embed

        if metric == "xp" and scope == "global":
            rows = await top_global_xp(limit)
            if not rows:
                return discord.Embed(
                    title="🌐 Network Leaderboard",
                    description=(
                        "No global data yet. Start chatting and running `/gyper scavenge` to claim the top slots."
                    ),
                    color=0x5865F2,
                )

            embed = discord.Embed(
                title="🌐 Network Leaderboard",
                description=(
                    "Top performers across Marcia's entire network. Each survivor is tagged with their home sector."
                ),
                color=0x5865F2,
            )
            lines = []
            for idx, row in enumerate(rows, start=1):
                source_guild = self.bot.get_guild(row["guild_id"])
                guild_name = source_guild.name if source_guild else f"Guild {row['guild_id']}"
                user = self.bot.get_user(row["user_id"])
                user_display = user.mention if user else f"<@{row['user_id']}>"
                snapshot = await get_profile_snapshot(row["guild_id"], row["user_id"])
                server_info = (
                    f" | Server {snapshot['server']}"
                    if snapshot and snapshot.get("scan_valid", 1) and snapshot.get("server")
                    else ""
                )
                lines.append(
                    f"**{idx}. {user_display}** - Level {row['level']} | {row['xp']:,} XP ({guild_name}{server_info})"
                )
            embed.add_field(name="Ranks", value=self._fit_embed_lines(lines), inline=False)
            embed.set_footer(
                text=f"Showing top {len(rows)} survivors. Run your alliance like a war machine. /gyper scavenge and climb."
            )
            return embed

        if metric == "duel":
            if scope == "global":
                return discord.Embed(
                    title="⚔️ Duel Score Leaderboard",
                    description="Duel scores are tracked per sector only.",
                    color=0xE67E22,
                )

            resolved_week = week_key or await get_latest_duel_week(guild.id)
            if week_key is None:
                week_key = resolved_week
            if not week_key:
                return discord.Embed(
                    title="⚔️ Duel Score Leaderboard",
                    description="No duel score scans recorded yet. Use `/gyper scan` to capture scores.",
                    color=0xE67E22,
                )

            rows = await get_duel_leaderboard(guild.id, week_key, limit)
            if not rows:
                return discord.Embed(
                    title="⚔️ Duel Score Leaderboard",
                    description=f"No duel scores found for week {week_key}.",
                    color=0xE67E22,
                )

            embed = discord.Embed(
                title="⚔️ Duel Score Leaderboard",
                description=f"Week {week_key} (top {len(rows)})",
                color=0xE67E22,
            )
            lines = []
            for idx, row in enumerate(rows, start=1):
                member = guild.get_member(row["user_id"])
                name = row.get("player_name") or (member.display_name if member else f"User {row['user_id']}")
                score_int = row.get("score_int")
                score_text = row.get("score_text") or "-"
                score_value = f"{score_text}"
                if score_int is not None:
                    score_value = f"{score_text} ({score_int:,})"
                lines.append(f"**{idx}.** {name} - {score_value}")
            embed.add_field(name="Ranks", value=self._fit_embed_lines(lines), inline=False)
            embed.set_footer(
                text=f"Showing top {len(rows)} duel scores for week {week_key}."
            )
            return embed

        stat_label, emoji = PROFILE_STAT_LABELS.get(metric, (metric.title(), "📈"))
        if scope == "global":
            rows = await top_global_profile_stat(metric, limit)
            if not rows:
                return discord.Embed(
                    title=f"{emoji} {stat_label} Leaderboard",
                    description="No scanned profiles yet. Run `/gyper scan` and try again.",
                    color=0x5865F2,
                )

            embed = discord.Embed(
                title=f"{emoji} {stat_label} Leaderboard",
                description="Profile scan stats from across the entire network. Server numbers shown for each player.",
                color=0x5865F2,
            )
            lines = []
            for idx, row in enumerate(rows, start=1):
                source_guild = self.bot.get_guild(row["guild_id"])
                guild_name = source_guild.name if source_guild else f"Guild {row['guild_id']}"
                user = self.bot.get_user(row["user_id"])
                user_display = user.mention if user else f"<@{row['user_id']}>"
                name = row["player_name"] or user_display
                server_value = row["server"] if "server" in row.keys() else None
                server_info = f" | Server {server_value}" if server_value else ""
                lines.append(
                    f"**{idx}.** {name} - {self._format_metric(row['value'])} ({guild_name}{server_info})"
                )
            embed.add_field(name="Ranks", value=self._fit_embed_lines(lines), inline=False)
            embed.set_footer(
            text=f"Showing top {len(rows)} survivors. Scan profiles to keep network stats fresh."
            )
            return embed

        rows = await top_profile_stat(guild.id, metric, limit)
        if not rows:
            return discord.Embed(
                title=f"{emoji} {stat_label} Leaderboard",
                description="No scanned profiles yet. Run `/gyper scan` and try again.",
                color=0x5865F2,
            )

        embed = discord.Embed(
            title=f"{emoji} {stat_label} Leaderboard",
            description="Profile scan stats from the latest profile scans in this sector.",
            color=0x5865F2,
        )
        lines = []
        for idx, row in enumerate(rows, start=1):
            user = guild.get_member(row["user_id"])
            name = row["player_name"] or (user.display_name if user else f"User {row['user_id']}")
            lines.append(f"**{idx}.** {name} - {self._format_metric(row['value'])}")
        embed.add_field(name="Ranks", value=self._fit_embed_lines(lines), inline=False)
        embed.set_footer(
            text=f"Showing top {len(rows)} survivors. Use `/gyper scan` then `/gyper leaderboard` to surface fresh scans."
        )
        return embed

    @staticmethod
    def _fit_embed_lines(lines: list[str], max_len: int = 1024) -> str:
        rendered: list[str] = []
        total = 0
        for line in lines:
            candidate = line if not rendered else f"\n{line}"
            if total + len(candidate) > max_len:
                if not rendered:
                    return line[: max_len - 1] + "…"
                break
            rendered.append(line)
            total += len(candidate)
        return "\n".join(rendered) if rendered else "-"

    async def _export_leaderboard_data(
        self,
        guild: discord.Guild | None,
        scope: str,
        metric: str,
        limit: int,
        *,
        week_key: str | None = None,
    ) -> tuple[io.StringIO, str, str] | None:
        if not guild:
            return None

        rows: list[dict] = []
        headers: list[str]
        filename: str
        note: str

        if metric == "duel":
            if scope == "global":
                return None
            if not week_key:
                week_key = await get_latest_duel_week(guild.id)
            if not week_key:
                return None
            rows = await get_duel_leaderboard(guild.id, week_key, limit)
            if not rows:
                return None
            headers = ["Rank", "User", "Score", "Week"]
            filename = f"leaderboard_duel_{week_key}_{guild.id}.tsv"
            note = f"Duel score leaderboard for week {week_key} (top {len(rows)})."
            lines = ["\t".join(headers)]
            for idx, row in enumerate(rows, start=1):
                member = guild.get_member(row["user_id"])
                name = row.get("player_name") or (member.display_name if member else f"User {row['user_id']}")
                score_text = row.get("score_text") or "-"
                score_int = row.get("score_int")
                score_value = f"{score_text}"
                if score_int is not None:
                    score_value = f"{score_text} ({score_int:,})"
                lines.append("\t".join(map(str, [idx, name, score_value, week_key])))
        elif metric == "xp" and scope != "global":
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
        elif metric == "xp" and scope == "global":
            rows = await top_global_xp(limit)
            if not rows:
                return None
            headers = ["Rank", "User", "Level", "XP", "Guild", "Server"]
            filename = "leaderboard_global.tsv"
            note = f"Network XP leaderboard (top {len(rows)})."
            lines = ["\t".join(headers)]
            for idx, row in enumerate(rows, start=1):
                source_guild = self.bot.get_guild(row["guild_id"])
                guild_name = source_guild.name if source_guild else f"Guild {row['guild_id']}"
                user = self.bot.get_user(row["user_id"])
                user_display = user.name if user else f"User {row['user_id']}"
                snapshot = await get_profile_snapshot(row["guild_id"], row["user_id"])
                server_num = snapshot.get("server") if snapshot and snapshot.get("scan_valid", 1) else "-"
                lines.append(
                    "\t".join(
                        map(
                            str,
                            [idx, user_display, row["level"], row["xp"], guild_name, server_num],
                        )
                    )
                )
        elif scope == "global":
            stat_label, _ = PROFILE_STAT_LABELS.get(metric, (metric.title(), ""))
            rows = await top_global_profile_stat(metric, limit)
            if not rows:
                return None
            headers = ["Rank", "User", stat_label, "Server", "Guild"]
            filename = f"leaderboard_global_{metric}.tsv"
            note = f"Global {stat_label} leaderboard (top {len(rows)})."
            lines = ["\t".join(headers)]
            for idx, row in enumerate(rows, start=1):
                source_guild = self.bot.get_guild(row["guild_id"])
                guild_name = source_guild.name if source_guild else f"Guild {row['guild_id']}"
                user = self.bot.get_user(row["user_id"])
                user_display = user.name if user else f"User {row['user_id']}"
                name = row["player_name"] or user_display
                server_num = row.get("server") or "-"
                lines.append(
                    "\t".join(map(str, [idx, name, row["value"], server_num, guild_name]))
                )
        else:
            stat_label, _ = PROFILE_STAT_LABELS.get(metric, (metric.title(), ""))
            rows = await top_profile_stat(guild.id, metric, limit)
            if not rows:
                return None
            headers = ["Rank", "User", stat_label]
            filename = f"leaderboard_{metric}_{guild.id}.tsv"
            note = f"{stat_label} leaderboard (top {len(rows)})."
            lines = ["\t".join(headers)]
            for idx, row in enumerate(rows, start=1):
                member = guild.get_member(row["user_id"])
                name = row["player_name"] or (member.display_name if member else f"User {row['user_id']}")
                lines.append("\t".join(map(str, [idx, name, row["value"]])))

        buffer = io.StringIO("\n".join(lines))
        buffer.seek(0)
        return buffer, filename, note

    @commands.hybrid_command(
        description=(
            "Leaderboards menu with Sector/Network scope, XP/CP/Kills/Likes/VIP, plus Excel export."
        )
    )
    async def leaderboard(self, ctx):
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Leaderboards only work inside servers.",
                ephemeral=True,
            )

        view = LeaderboardView(
            self, ctx.guild, requester_id=ctx.author.id, scope="local", metric="xp"
        )
        embed = await self._build_leaderboard_embed(ctx.guild, "local", "xp", view.limit)
        message = await self._safe_send(ctx, embed=embed, view=view)
        if isinstance(message, discord.Message):
            view.bind_message(message)

    def _tier_role_name(self, tier: int) -> str:
        index = max(0, (tier // ROLE_STEP) - 1)
        if index < len(ROLE_TITLES):
            return ROLE_TITLES[index]
        return f"{ROLE_PREFIX} {tier:03d}"

    async def ensure_tier_role(self, guild: discord.Guild, level: int) -> discord.Role | None:
        tier = max(ROLE_STEP, (level // ROLE_STEP) * ROLE_STEP)
        color = discord.Color(TIER_COLORS[tier % len(TIER_COLORS)])
        role_name = self._tier_role_name(tier)
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


class DuelHistoryView(discord.ui.View):
    def __init__(self, requester_id: int, guild_id: int, user_id: int):
        super().__init__(timeout=120)
        self.requester_id = requester_id
        self.guild_id = guild_id
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True

        await interaction.response.send_message(
            "This duel history belongs to someone else.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Duel History", style=discord.ButtonStyle.secondary, emoji="📜")
    async def duel_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = await get_duel_scores_for_user(self.guild_id, self.user_id, limit=10)
        if not rows:
            await interaction.response.send_message(
                "No duel scores recorded yet.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="⚔️ Duel Score History",
            color=0xE67E22,
        )
        lines = []
        for row in rows:
            score_text = row.get("score_text") or "-"
            score_int = row.get("score_int")
            score_value = f"{score_text}"
            if score_int is not None:
                score_value = f"{score_text} ({score_int:,})"
            lines.append(f"Week {row.get('week_key')}: {score_value}")

        embed.add_field(name="Recent Weeks", value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class InventoryTransferView(discord.ui.View):
    def __init__(self, ctx: commands.Context, items: list[dict], embed: discord.Embed):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.items = items
        self.embed = embed
        self.add_item(InventoryTransferSelect(ctx, items, embed))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class InventoryTransferSelect(discord.ui.Select):
    def __init__(self, ctx: commands.Context, items: list[dict], embed: discord.Embed):
        options = []
        self.items = items
        self.embed = embed
        for item in items[:25]:
            label = item["item_id"]
            description = f"x{item['quantity']} • {item['rarity']}"
            options.append(
                discord.SelectOption(label=label, description=description, value=label)
            )
        super().__init__(
            placeholder="Send an item to a fellow survivor…",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(
                "Only the stash owner can send items.", ephemeral=True
            )
        item_name = self.values[0]
        matched = next((item for item in self.items if item["item_id"] == item_name), None)
        max_qty = matched["quantity"] if matched else 1
        view = InventorySendView(
            self.ctx,
            item_name,
            max_qty,
            self.items,
            self.embed,
        )
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class InventoryRecipientSelect(discord.ui.UserSelect):
    def __init__(self, parent_view: "InventorySendView"):
        super().__init__(placeholder="Select a recipient", min_values=1, max_values=1)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.recipient = self.values[0]
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)


class InventoryQuantitySelect(discord.ui.Select):
    def __init__(self, parent_view: "InventorySendView", max_qty: int):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label=str(i), value=str(i))
            for i in range(1, min(max_qty, 10) + 1)
        ]
        if max_qty > 10:
            options.append(discord.SelectOption(label=f"All ({max_qty})", value=str(max_qty)))
        super().__init__(placeholder="Pick a quantity", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.quantity = int(self.values[0])
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)


class InventorySendView(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        item_name: str,
        max_qty: int,
        items: list[dict],
        parent_embed: discord.Embed,
    ):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.item_name = item_name
        self.max_qty = max_qty
        self.items = items
        self.parent_embed = parent_embed
        self.recipient: discord.Member | None = None
        self.quantity: int | None = None
        self.add_item(InventoryRecipientSelect(self))
        self.add_item(InventoryQuantitySelect(self, max_qty))

    def build_embed(self) -> discord.Embed:
        recipient_label = self.recipient.mention if self.recipient else "Select a survivor"
        qty_label = str(self.quantity) if self.quantity else "Select a quantity"
        embed = discord.Embed(
            title="📤 Send Item",
            description=(
                f"**Item:** {self.item_name}\n"
                f"**Recipient:** {recipient_label}\n"
                f"**Quantity:** {qty_label}\n"
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Confirm to send or go back to your stash.")
        return embed

    @discord.ui.button(label="Confirm Send", style=discord.ButtonStyle.success, emoji="✅", row=1)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(
                "Only the stash owner can send items.", ephemeral=True
            )
        if not self.recipient or not self.quantity:
            return await interaction.response.send_message(
                "Select a recipient and quantity before confirming.",
                ephemeral=True,
            )
        if self.recipient.id == self.ctx.author.id:
            return await interaction.response.send_message(
                "❌ You cannot send items to yourself.",
                ephemeral=True,
            )

        success = await transfer_inventory(
            self.ctx.guild.id,
            self.ctx.author.id,
            self.recipient.id,
            self.item_name,
            self.quantity,
        )
        if not success:
            return await interaction.response.send_message(
                "❌ Not enough of that item to send.",
                ephemeral=True,
            )

        await log_inventory_transfer(
            self.ctx.guild.id,
            self.ctx.channel.id,
            self.ctx.author.id,
            self.recipient.id,
            self.item_name,
            self.quantity,
        )

        await interaction.response.edit_message(
            content=f"✅ Sent **{self.item_name}** x{self.quantity} to {self.recipient.mention}.",
            embed=None,
            view=None,
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class LeaderboardScopeSelect(discord.ui.Select):
    def __init__(self, parent_view: "LeaderboardView"):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label="Sector (Server)", description="Rankings inside this server", value="local", emoji="🏠"
            ),
            discord.SelectOption(
                label="Network (Global)",
                description="Rankings across linked servers",
                value="global",
                emoji="🌐",
            ),
        ]

        for option in options:
            option.default = option.value == parent_view.scope
        super().__init__(
            placeholder="Pick a scope",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.requester_id:
            return await interaction.response.send_message(
                "Only the original requester can change this menu.", ephemeral=True
            )

        self.parent_view.scope = self.values[0]
        for option in self.options:
            option.default = option.value == self.values[0]
        await self.parent_view.refresh(interaction)


class LeaderboardMetricSelect(discord.ui.Select):
    def __init__(self, parent_view: "LeaderboardView"):
        self.parent_view = parent_view
        options = []
        for metric, (label, emoji) in LEADERBOARD_METRICS.items():
            if metric == "xp":
                description = "Activity-based XP rankings"
            elif metric == "duel":
                description = "Weekly duel score rankings"
            else:
                description = f"Profile scans ranked by {label.lower()}"
            options.append(
                discord.SelectOption(
                    label=label,
                    description=description,
                    value=metric,
                    emoji=emoji,
                )
            )

        for option in options:
            option.default = option.value == parent_view.metric
        super().__init__(
            placeholder="Pick a stat",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.requester_id:
            return await interaction.response.send_message(
                "Only the original requester can change this menu.", ephemeral=True
            )

        self.parent_view.metric = self.values[0]
        if self.parent_view.metric == "duel":
            self.parent_view.duel_week = None
        for option in self.options:
            option.default = option.value == self.values[0]
        await self.parent_view.refresh(interaction)


class LeaderboardWeekSelect(discord.ui.Select):
    def __init__(self, parent_view: "LeaderboardView"):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label="No duel weeks yet",
                value="none",
                default=True,
            )
        ]
        super().__init__(
            placeholder="Pick a duel week",
            options=options,
            min_values=1,
            max_values=1,
            disabled=True,
        )

    def update_options(self, weeks: list[str], selected: str | None, enabled: bool) -> None:
        if not enabled:
            self.disabled = True
            self.options = [
                discord.SelectOption(
                    label="Switch to Duel to pick a week",
                    value="none",
                    default=True,
                )
            ]
            return

        if not weeks:
            self.disabled = True
            self.options = [
                discord.SelectOption(
                    label="No duel weeks yet",
                    value="none",
                    default=True,
                )
            ]
            return

        self.disabled = False
        self.placeholder = "Pick a duel week"
        self.options = [
            discord.SelectOption(
                label=f"Week {week}",
                value=week,
                default=week == selected,
            )
            for week in weeks
        ]

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.requester_id:
            return await interaction.response.send_message(
                "Only the original requester can change this menu.", ephemeral=True
            )

        if self.values[0] == "none":
            return await interaction.response.send_message(
                "No duel weeks are available yet.", ephemeral=True
            )

        self.parent_view.duel_week = self.values[0]
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
            self.parent_view.guild,
            self.parent_view.scope,
            self.parent_view.metric,
            self.parent_view.limit,
            week_key=self.parent_view.duel_week,
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
        scope: str,
        metric: str,
        limit: int = 10,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.requester_id = requester_id
        self.scope = scope
        self.metric = metric
        self.limit = limit if limit in LEADERBOARD_LIMITS else LEADERBOARD_LIMITS[0]
        self.duel_week: str | None = None
        self.message: discord.Message | None = None
        self.add_item(LeaderboardScopeSelect(self))
        self.add_item(LeaderboardMetricSelect(self))
        self.week_select = LeaderboardWeekSelect(self)
        self.add_item(self.week_select)
        self.add_item(LeaderboardLimitSelect(self))
        self.add_item(ExportLeaderboardButton(self))

    def bind_message(self, message: discord.Message) -> None:
        self.message = message

    async def refresh(self, interaction: discord.Interaction | None = None):
        if self.metric == "duel":
            weeks = await get_duel_weeks(self.guild.id)
            if weeks:
                if self.duel_week not in weeks:
                    self.duel_week = weeks[0]
            else:
                self.duel_week = None
            self.week_select.update_options(weeks, self.duel_week, enabled=True)
        else:
            self.week_select.update_options([], None, enabled=False)

        embed = await self.cog._build_leaderboard_embed(
            self.guild,
            self.scope,
            self.metric,
            self.limit,
            week_key=self.duel_week,
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
