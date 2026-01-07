"""
FILE: cogs/events.py
USE: Automations, Duel Reminders, and Mission Control (SQL Version).
FEATURES: Server-time synced resets, persistent mission recovery, and broadcast logic.
"""
import discord
from discord.ext import commands, tasks
import asyncio
import random
import logging
from datetime import datetime, timezone, timedelta
from assets import TIMED_REMINDERS, DRONE_NAMES, MARCIA_STATUSES, MARCIA_QUOTES
from time_utils import now_game, game_to_utc, format_game, utc_to_game
from database import (
    add_mission,
    add_mission_opt_in,
    add_template,
    can_run_daily_task,
    clear_mission_opt_ins,
    delete_mission,
    get_all_active_missions,
    get_mission_opt_ins,
    get_settings,
    get_templates,
    get_upcoming_missions,
    increment_activity_metric,
    is_channel_ignored,
    lookup_dm_prompt,
    mark_task_complete,
    upsert_dm_prompt,
)

logger = logging.getLogger('MarciaOS.Events')
DM_OPT_IN_EMOJI = "📬"

DUEL_DATA = {
    0: "**MONDAY – Day 1: Research / Building / Gathering**\n\n✅ **DO:**\n• Send gatherers before reset.\n• Duel points count on Return.\n• Use gathering heroes: Musashimaru, Bob, Joe.\n📊 **SP SLOTS:** Shelter → Hero → Unit → Science → Arms.",
    1: "**TUESDAY – Day 2: Radar / Recruitment / Heroes**\n\n✅ **DO:**\n• Claim radar missions. Use Prime tickets.\n• Spend hero fragments.\n📊 **SP SLOTS:** Hero → Unit → Science → Arms → Shelter → Hero.",
    2: "**WEDNESDAY – Day 3: Trucks / Orange / Training**\n\n✅ **DO:**\n• Run 4 S-Trucks & 8-9 Orange missions.\n• Use Power Cores. Train units passively.\n📊 **SP SLOTS:** Unit → Science → Arms → Shelter → Hero → Unit.",
    3: "**THURSDAY – Day 4: Radar / Vehicles / Monsters**\n\n✅ **DO:**\n• Burn stamina on Lv20+ mummies.\n• Use vehicle gears and blueprints.\n📊 **SP SLOTS:** Science → Arms → Shelter → Hero → Unit → Science.",
    4: "**FRIDAY – Day 5: Vehicles / Fragments / Wisdom**\n\n✅ **DO:**\n• Collect Zombie Siege rewards.\n• Use Wisdom Medals.\n📊 **SP SLOTS:** Arms → Shelter → Hero → Unit → Science → Arms.",
    5: "**SATURDAY – Day 6: Enemy Buster**\n\n✅ **DO:**\n• KE and RSS hunting. Focus on easy 40K slots.\n📊 **SP SLOTS:** Shelter → Hero → Unit → Science → Arms → Shelter.",
    6: "**SUNDAY – Day 7: Preparation**\n\nDirectives: Prepare gatherers for Monday reset. Restock speedups."
}


def _marcia_quip():
    return random.choice(MARCIA_QUOTES)

# --- UI COMPONENTS ---

class TemplateSelect(discord.ui.Select):
    def __init__(self, templates, callback_func, ctx, placeholder="Select a template...", mode="use"):
        options = [
            discord.SelectOption(
                label=t["template_name"],
                emoji="📋" if mode == "use" else "🗑️",
            )
            for t in templates[:24]
        ]
        options.append(discord.SelectOption(label="Cancel", emoji="❌"))
        super().__init__(placeholder=placeholder, options=options)
        self.callback_func = callback_func
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "Cancel":
            return await interaction.response.edit_message(content="📡 Directive cancelled.", view=None, embed=None)
        await self.callback_func(interaction, self.values[0], self.ctx)

class EventMenuView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=60)
        self.cog, self.ctx = cog, ctx

    def _can_manage_events(self, interaction: discord.Interaction) -> bool:
        return bool(
            interaction.guild
            and interaction.user
            and interaction.user.guild_permissions.manage_guild
        )

    async def _require_manage_events(self, interaction: discord.Interaction) -> bool:
        if self._can_manage_events(interaction):
            return True
        await interaction.response.send_message(
            "🔒 You need Manage Server permissions to schedule or archive events.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Custom Event", style=discord.ButtonStyle.primary, emoji="✍️")
    async def custom_event(self, it, btn):
        if not await self._require_manage_events(it):
            return
        await it.response.send_message("📡 Setup signal sent to DMs.", ephemeral=True)
        await self.cog.create_mission_flow(self.ctx)

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.success, emoji="📋")
    async def template_event(self, it, btn):
        if not await self._require_manage_events(it):
            return
        tps = await get_templates(it.guild.id)
        if not tps: return await it.response.send_message("❌ Archive is empty.", ephemeral=True)
        view = discord.ui.View()
        view.add_item(TemplateSelect(tps, self.cog.use_template_callback, self.ctx))
        await it.response.edit_message(content="**Select a mission preset:**", view=view, embed=None)

    @discord.ui.button(label="Archive Template", style=discord.ButtonStyle.secondary, emoji="💾")
    async def create_template_btn(self, it, btn):
        if not await self._require_manage_events(it):
            return
        await it.response.send_message("💾 Archiving Module Active. Check DMs.", ephemeral=True)
        await self.cog.create_template_flow(self.ctx)

    @discord.ui.button(label="Upcoming Events", style=discord.ButtonStyle.secondary, emoji="📆")
    async def upcoming_events(self, it, btn):
        missions = await get_upcoming_missions(it.guild.id, limit=10)
        if not missions:
            return await it.response.send_message(
                "📡 *No upcoming events logged for this sector.*",
                ephemeral=True,
            )
        embed = self.cog._build_upcoming_events_embed(it.guild, missions)
        await it.response.send_message(embed=embed, ephemeral=True)

# --- COG MAIN ---

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.running_tasks = {}
        self.cycle_status.start()
        self.check_duel_reset.start()
        self.bot.loop.create_task(self.recover_missions())

    def cog_unload(self):
        self.cycle_status.cancel()
        self.check_duel_reset.cancel()
        for task in self.running_tasks.values(): task.cancel()

    async def _safe_send(self, ctx, *, ephemeral: bool = False, **kwargs):
        interaction = getattr(ctx, "interaction", None)
        if interaction:
            return await self.bot._safe_interaction_reply(
                interaction, ephemeral=ephemeral, **kwargs
            )
        kwargs.pop("ephemeral", None)
        return await ctx.send(**kwargs)

    async def recover_missions(self):
        """Reloads active missions from SQL on startup."""
        await self.bot.wait_until_ready()
        all_missions = await get_all_active_missions()
        for m in all_missions:
            try:
                utc_dt = datetime.fromisoformat(m['target_utc']).astimezone(timezone.utc)
                if utc_dt > datetime.now(timezone.utc):
                    task_key = f"{m['guild_id']}_{m['codename']}"
                    self.running_tasks[task_key] = self.bot.loop.create_task(
                        self.manage_reminders(
                            m['codename'],
                            m['description'],
                            utc_dt,
                            m['guild_id'],
                            location=m.get('location'),
                            ping_role_id=m.get('ping_role_id'),
                        )
                    )
                else:
                    await delete_mission(m['guild_id'], m['codename'])
            except: pass

    @tasks.loop(minutes=5)
    async def check_duel_reset(self):
        """Sends daily Duel info at Midnight Server Time."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            settings = await get_settings(guild.id)
            if not settings or not settings['event_channel_id']: continue

            now_server = now_game()

            if now_server.hour == 0:
                date_key = now_server.strftime("%Y-%m-%d")
                task_id = f"duel_{guild.id}"
                
                if await can_run_daily_task(task_id, date_str=date_key):
                    chan = guild.get_channel(settings['event_channel_id'])
                    if chan and not await is_channel_ignored(guild.id, chan.id):
                        info = DUEL_DATA.get(now_server.weekday(), "No data.")
                        await chan.send(
                            f"@everyone\n📡 **MARCIA OS | DUEL DIRECTIVE**\n\n{info}",
                            allowed_mentions=discord.AllowedMentions(everyone=True),
                        )
                        await mark_task_complete(task_id, date_str=date_key)

    @tasks.loop(minutes=30)
    async def cycle_status(self):
        try: await self.bot.change_presence(activity=discord.Game(name=random.choice(MARCIA_STATUSES)))
        except: pass

    @commands.hybrid_command(name="event", description="Open Marcia's mission control console.")
    async def event_cmd(self, ctx):
        """Opens the Mission Control menu."""
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Events can only be managed inside servers.",
                ephemeral=True,
            )
        embed = discord.Embed(
            title="📡 Mission Control // Marcia",
            description=(
                "Pick how you want me to broadcast your operation.\n"
                "`Custom Event` opens a DM interview, `Use Template` pulls from your archive.\n"
                "`Upcoming Events` previews the next ops list for this sector.\n"
                "I track everything in UTC-2 (Dark War Survival)."
            ),
            color=0x2b2d31
        )
        embed.set_footer(text="Marcia drones on standby. Keep it sharp.")
        await self._safe_send(ctx, embed=embed, view=EventMenuView(self, ctx))

    @commands.hybrid_command(name="event_remove", description="Delete a scheduled operation.")
    @commands.has_permissions(manage_guild=True)
    async def event_remove(self, ctx, *, codename: str):
        """Remove a scheduled event."""
        if not ctx.guild:
            return await self._safe_send(
                ctx,
                content="Events can only be removed inside servers.",
                ephemeral=True,
            )
        await delete_mission(ctx.guild.id, codename)
        await self._safe_send(ctx, content=f"🗑️ Event **{codename}** scrubbed from the docket.")

    async def create_template_flow(self, ctx):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send("💾 **Template Title?** (what do we call this op?)")
            title = (await self.bot.wait_for('message', check=check, timeout=120)).content
            await ctx.author.send("📝 **Directives?** Drop the briefing text.")
            desc = (await self.bot.wait_for('message', check=check, timeout=300)).content
            await add_template(ctx.guild.id, title, desc)
            await ctx.author.send(f"✅ Protocol `{title}` archived. {_marcia_quip()}")
        except: await ctx.author.send("❌ Timeout.")

    async def create_mission_flow(self, ctx):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send(
                "📡 **Mission Codename?** (keep it short; I'll broadcast it)"
            )
            name_msg = await self.bot.wait_for('message', check=check, timeout=120)
            name = name_msg.content

            await ctx.author.send("📝 **Instructions?** Tell the squad what to do.")
            desc_msg = await self.bot.wait_for('message', check=check, timeout=300)
            desc = desc_msg.content

            await ctx.author.send("📍 **Location or voice channel?** Reply with coords/link or type `skip`.")
            location_msg = await self.bot.wait_for('message', check=check, timeout=180)
            location = None if location_msg.content.lower().strip() == "skip" else location_msg.content

            await ctx.author.send(
                "👥 **Ping who?** Mention a role, type `everyone`, or `none` to stay quiet."
            )
            ping_msg = await self.bot.wait_for('message', check=check, timeout=120)
            ping_target = await self._resolve_ping(ctx, ping_msg.content)

            await ctx.author.send(
                f"⏰ **Target Time?** `YYYY-MM-DD HH:MM` using the game clock (UTC-2)."
            )
            t_msg = await self.bot.wait_for('message', check=check, timeout=180)
            await self.finalize_mission(ctx, name, desc, t_msg.content, location, ping_target)
        except asyncio.TimeoutError:
            await ctx.author.send("⌛ Timed out. Ping me again with `/event` when you're ready.")

    async def create_template_mission_flow(self, ctx, template_name, template_desc):
        def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            await ctx.author.send(
                f"📋 **Template Loaded:** `{template_name}`\n{template_desc}\n\n"
                "Reply with a new codename or type `skip` to keep this name."
            )
            name_msg = await self.bot.wait_for('message', check=check, timeout=120)
            name = template_name if name_msg.content.lower().strip() == "skip" else name_msg.content

            await ctx.author.send("📍 **Location or voice channel?** Reply with coords/link or type `skip`.")
            location_msg = await self.bot.wait_for('message', check=check, timeout=180)
            location = None if location_msg.content.lower().strip() == "skip" else location_msg.content

            await ctx.author.send(
                "👥 **Ping who?** Mention a role, type `everyone`, or `none` to stay quiet."
            )
            ping_msg = await self.bot.wait_for('message', check=check, timeout=120)
            ping_target = await self._resolve_ping(ctx, ping_msg.content)

            await ctx.author.send(
                "⏰ **Target Time?** `YYYY-MM-DD HH:MM` using the game clock (UTC-2)."
            )
            t_msg = await self.bot.wait_for('message', check=check, timeout=180)
            await self.finalize_mission(ctx, name, template_desc, t_msg.content, location, ping_target)
        except asyncio.TimeoutError:
            await ctx.author.send("⌛ Timed out. Ping me again with `/event` when you're ready.")

    async def use_template_callback(self, interaction, template_name, ctx):
        templates = await get_templates(ctx.guild.id)
        selected = next(
            (template for template in templates if template["template_name"] == template_name),
            None,
        )
        if not selected:
            return await self.bot._safe_interaction_reply(
                interaction,
                content="❌ Template not found. Try again from `/event`.",
                ephemeral=True,
            )

        await self.bot._safe_interaction_reply(
            interaction,
            content="📡 Template loaded. Check your DMs to schedule the time.",
            ephemeral=True,
        )
        await self.create_template_mission_flow(
            ctx,
            selected["template_name"],
            selected["description"],
        )

    def _build_upcoming_events_embed(self, guild, missions):
        embed = discord.Embed(
            title="🛰️ Upcoming Operations (UTC-2)",
            color=0x3498db,
            description="I'll ping this channel when it's go-time.",
        )
        for m in missions:
            start_game = format_game(datetime.fromisoformat(m['target_utc']).astimezone(timezone.utc))
            details = [f"📝 {m['description']}"]
            if m['location']:
                details.append(f"📍 {m['location']}")
            embed.add_field(
                name=f"🔹 {m['codename']}",
                value="\n".join(details + [f"⏰ `{start_game}`"]),
                inline=False,
            )
        embed.set_footer(text=f"Sector: {guild.name} | Clock: UTC-2")
        return embed

    async def finalize_mission(self, ctx, name, desc, t_str, location, ping_target):
        try:
            target_dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
            utc_dt = game_to_utc(target_dt)
            if utc_dt < datetime.now(timezone.utc):
                return await ctx.author.send("❌ Past time.")

            ping_role_id = ping_target.id if isinstance(ping_target, discord.Role) else ping_target
            await add_mission(
                ctx.guild.id,
                name,
                desc,
                t_str,
                utc_dt.isoformat(),
                location=location,
                ping_role_id=ping_role_id,
                tag=None,
                notes=None,
            )
            await increment_activity_metric(ctx.guild.id, "events_scheduled")
            self.running_tasks[f"{ctx.guild.id}_{name}"] = self.bot.loop.create_task(
                self.manage_reminders(name, desc, utc_dt, ctx.guild.id, location, ping_role_id)
            )

            preview = self._build_event_embed(ctx.guild, name, desc, utc_dt, location, ping_role_id)
            await ctx.author.send(f"✅ Mission `{name}` locked. {_marcia_quip()}", embed=preview)

            settings = await get_settings(ctx.guild.id)
            if settings and settings['event_channel_id']:
                chan = ctx.guild.get_channel(settings['event_channel_id'])
                if chan and not await is_channel_ignored(ctx.guild.id, chan.id):
                    await chan.send("🛰️ **New Operation Logged**", embed=preview)
        except Exception:
            await ctx.author.send("❌ Use: `YYYY-MM-DD HH:MM`.")

    async def manage_reminders(self, name, desc, utc_dt, guild_id, location=None, ping_role_id=None):
        for mins in [60, 30, 15, 3, 0]:
            wait = (utc_dt - timedelta(minutes=mins) - datetime.now(timezone.utc)).total_seconds()
            if wait > 0:
                await asyncio.sleep(wait)

            # Final check if mission still exists in DB
            missions = await get_all_active_missions()
            if not any(m['guild_id'] == guild_id and m['codename'] == name for m in missions):
                return

            settings = await get_settings(guild_id)
            if not (settings and settings['event_channel_id']):
                continue

            chan = self.bot.get_channel(settings['event_channel_id'])
            if not chan or await is_channel_ignored(guild_id, chan.id):
                continue

            drone = random.choice(DRONE_NAMES)
            guild = chan.guild
            role = guild.get_role(ping_role_id) if isinstance(ping_role_id, int) and ping_role_id >= 0 else None
            mention = ""
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=False)
            if mins == 60:
                mention = "@everyone"
                allowed_mentions = discord.AllowedMentions(everyone=True, roles=False)
            elif ping_role_id == -1:
                mention = "@everyone"
                allowed_mentions = discord.AllowedMentions(everyone=True, roles=False)
            elif role:
                mention = role.mention
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=True)
            location_line = f"\n📍 {location}" if location else ""
            title, body = random.choice(TIMED_REMINDERS.get(mins, [("📡 **ALERT:**", "`{name}` is coming up.")]))
            body = body.format(name=name, drone=drone)
            quote = random.choice(MARCIA_QUOTES)

            if mins == 60:
                msg = (
                    f"{title} {quote}\n"
                    f"{body}\n\n"
                    f"{desc}{location_line}\n\n"
                    f"React with {DM_OPT_IN_EMOJI} to get DM pings for the next alerts."
                    f"\n\n*Drone: {drone}*"
                )
                if mention:
                    msg = f"{mention}\n" + msg
                sent = await chan.send(
                    msg,
                    allowed_mentions=allowed_mentions,
                )

                try:
                    await sent.add_reaction(DM_OPT_IN_EMOJI)
                except Exception:
                    logger.warning("Could not add DM opt-in reaction for %s", name)
                await upsert_dm_prompt(guild_id, name, sent.id)
            else:
                await self._notify_dm_opt_ins(guild_id, name, mins, desc, location)

        await delete_mission(guild_id, name)
        await clear_mission_opt_ins(guild_id, name)

    def _build_event_embed(self, guild, name, desc, utc_dt, location=None, ping_role_id=None):
        embed = discord.Embed(
            title=f"📡 {name}",
            description=desc,
            color=0x5865f2,
        )
        embed.add_field(name="⏰ Game Time", value=format_game(utc_dt), inline=False)
        if location:
            embed.add_field(name="📍 Location", value=location, inline=True)
        if ping_role_id is not None:
            if ping_role_id == -1:
                ping_display = "@everyone"
            else:
                role = guild.get_role(ping_role_id)
                ping_display = role.mention if role else "🔇 None"
            embed.add_field(name="👥 Ping", value=ping_display, inline=True)
        embed.set_footer(text=f"Sector: {guild.name} | Clock: UTC-2")
        return embed

    async def _notify_dm_opt_ins(self, guild_id: int, codename: str, mins: int, desc: str, location: str | None) -> None:
        subscribers = await get_mission_opt_ins(guild_id, codename)
        if not subscribers:
            return

        guild = self.bot.get_guild(guild_id)
        location_line = f"\n📍 {location}" if location else ""
        countdown = "now" if mins == 0 else f"in {mins} minutes"

        for uid in subscribers:
            member = guild.get_member(uid) if guild else None
            user = member or self.bot.get_user(uid)
            if not user or getattr(user, "bot", False):
                continue

            try:
                await user.send(
                    f"📡 `{codename}` hits {countdown}.\n{desc}{location_line}\n\n"
                    "You raised your hand for DM alerts. I'll keep them coming for this op."
                )
            except Exception:
                logger.debug("Failed to DM opt-in user %s for %s", uid, codename)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != DM_OPT_IN_EMOJI:
            return

        if payload.user_id == getattr(self.bot.user, "id", None):
            return

        prompt = await lookup_dm_prompt(payload.message_id)
        if not prompt:
            return

        guild_id, codename = prompt
        if payload.guild_id and payload.guild_id != guild_id:
            return

        guild = self.bot.get_guild(guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        if member is None and guild:
            try:
                member = await guild.fetch_member(payload.user_id)
            except Exception:
                member = None

        user = member or self.bot.get_user(payload.user_id)
        if not user or getattr(user, "bot", False):
            return

        await add_mission_opt_in(guild_id, codename, user.id)
        try:
            await user.send(
                f"📡 Locked in. I'll DM you the next `{codename}` reminders for **{guild.name if guild else 'this sector'}**."
            )
        except Exception:
            logger.debug("Could not DM opt-in confirmation to %s", user.id)

    async def _resolve_ping(self, ctx, msg_content):
        text = msg_content.strip().lower()
        if text == "none":
            return None
        if text == "everyone":
            return -1
        # Try mention syntax
        if msg_content.startswith("<@&") and msg_content.endswith(">"):
            role_id = int(msg_content[3:-1])
            return ctx.guild.get_role(role_id)

        return discord.utils.get(ctx.guild.roles, name=msg_content)

async def setup(bot):
    await bot.add_cog(Events(bot))
