import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
import json
import os
import asyncio
import random
import logging
from googletrans import Translator
from dotenv import load_dotenv

# Import external dialogue assets from assets.py
from assets import DRONE_NAMES, WELCOME_VARIATIONS, MARICA_QUOTES

# ---------------- ALLIANCE LEADERSHIP DIRECTORY ----------------
LEADER_IDS = {
    "AMEER": 253838459133886465,
    "AKROT": 135894953027960833,
    "LUJAYN": 461483389866999809,
    "PANDA": 1404240829849014395,
    "MIGS_BOO": 461483389866999809,
    "PLUMBER": 1412425270631333919,
    "CHAOS": 798849874971590678,
    "REAPER": 329019585896644608,
    "BLOSSOM": 1409572913534730328,
    "AMATAE": 1389988384885178420
}

# ---------------- MARICA LORE ----------------
MARICA_LORE = """
Marcia is a cunning, mischievous hacker in her early twenties who transitioned from a high-stakes digital 
thief to a tactical survivalist in the post-apocalypse. Before the world fell, she used her 
skills to redistribute wealth for her own freedom and enjoyment, never caring about the rules. 
She is never seen without her two tiny drones, which she considers her only true friends.

In the ruins, she is known as a 'Shadow Weaver.' She can hack any defense system and has a dark sense 
of humor, often making zombies stumble like puppets for her amusement while she chuckles from the 
shadows. While she remains wild and untamed, she has developed a hidden spark of kindness 
and a quiet sense of responsibility for struggling survivors. Her drones gliding through 
the night sky have become a symbol of peace and safety, signaling that Marcia is watching over 
the Helles Hub, even if she denies being a hero.
"""

# ---------------- LOGGING & CONFIG ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger('MaricaBot')
load_dotenv()
TOKEN = os.getenv("TOKEN")
LEVEL_FILE = "levels.json"
MISSION_FILE = "missions.json"
FISH_FILE = "fish_data.json"

SERVER_OFFSET = timedelta(hours=-2) 
XP_PER_MESSAGE = 10
LEVEL_UP_BASE = 100

# --- ROUTING IDs ---
WELCOME_CHANNEL_ID = 1404215179419451554
VERIFY_CHANNEL_ID = 1411420121901301760
RULES_CHANNEL_ID = 1409268742340477069
TEST_CHANNEL_ID = 1428183359959470140    
EVENT_CHANNEL_IDS = [1429975118196510781] 
CHAT_CHANNEL_ID = 1404215179419451554 
FISH_TRADE_CHANNEL_ID = 1428183359959470140  
AUTO_ROLE_NAME = "🪶 Wanderers"

# --- ROLE REWARDS ---
ROLE_REWARDS = {5: "Scout", 10: "Veteran", 20: "Alliance Elite"}

FLAG_LANG = {
    "🇺🇸": "en", "🇬🇧": "en", "🇦🇺": "en", "🇨🇦": "en", "🇫🇷": "fr", "🇪🇸": "es", 
    "🇲🇽": "es", "🇩🇪": "de", "🇮🇹": "it", "🇵🇹": "pt", "🇧🇷": "pt", "🇳🇱": "nl",
    "🇷🇺": "ru", "🇺🇦": "uk", "🇵🇱": "pl", "🇬🇷": "el", "🇨🇳": "zh-cn", "🇭🇰": "zh-tw", 
    "🇹🇼": "zh-tw", "🇯🇵": "ja", "🇰🇷": "ko", "🇻🇳": "vi", "🇹🇭": "th", "🇸🇦": "ar", 
    "🇹🇷": "tr", "🇮🇱": "he", "🇸🇪": "sv", "🇳🇴": "no"
}

ON_MENTION_REPLIES = [
    "You looking for a handout? I only steal from people richer than you.",
    "Careful. Sparky says you're standing too close to the hardware.",
    "I'm busy making the local zombies dance. What do you want?",
    "Hacking this system is easier than talking to you. Don't test me.",
    "The drones are watching. They don't like people who ping too much.",
    "I'm not a hero. I'm just the one keeping this hub from collapsing.",
    "Freedom is expensive. Don't waste my time for free.",
    "My drones are my only friends, but I might make an exception if you're useful.",
    "Analyzing your bio-signals... yikes. You look like you need a stim-pack and a nap.",
    "You're lucky I have a 'tiny spark of kindness,' or I'd wipe your credits right now.",
    "I've got a satellite to fix, Wanderer. Don't clutter my frequency.",
    "Are you still here? The wasteland is that way.",
    "Signal received. Processing... Error: I'm currently ignoring you.",
    "I've seen better logic in a pre-war toaster.",
    "Just because I'm watching your back doesn't mean I want to hear your voice.",
    "Calculating the probability of that being a good point... It's zero.",
    "Wait, I need to adjust my attitude... Okay, still don't care.",
    "My logic circuits are overheating just trying to follow your train of thought.",
    "If I wanted to talk to something slow, I'd reboot a 20th-century laptop.",
    "End of transmission. Goodbye, Wanderer."
]

TIMED_REMINDERS = {
    60: [
        ("📡 **T-MINUS 60 MINUTES:**", "Operation `{name}` is an hour out. Check your mags and calibrate your scopes."),
        ("🚁 **ORBITAL UPDATE:**", "My drones are in position for `{name}`. You have 60 minutes to reach the drop-zone."),
        ("🛠️ **MARICA'S SHOP:**", "60 minutes until `{name}`. If your gear is broken, fix it now. I'm busy later."),
        ("🔋 **POWER CHECK:**", "Grid will divert power to `{name}` in one hour. Be ready."),
        ("☢️ **RAD-WATCH:**", "The storm clears in 60 minutes. `{name}` starts exactly then."),
        ("🛰️ **UPLINK PING:**", "One hour until `{name}` goes live. I’m warming up the satellite array."),
        ("🧟 **INTEL GATHERED:**", "Scouts report heavy activity for `{name}`. You've got 60 minutes to prep."),
        ("📻 **RADIO CHATTER:**", "Alliance commanders are discussing `{name}`. Operation starts in one hour."),
        ("🦾 **TECH READY:**", "I've finished the software patch for `{name}`. 60 minutes until deployment."),
        ("🏚️ **OUTPOST ALERT:**", "Gates for `{name}` open in 60 minutes. Don't be late.")
    ],
    30: [
        ("⏱️ **30 MINUTE WARNING:**", "Half an hour until `{name}`. Hope you’re not still in your bunks."),
        ("🚁 **DRONE STATUS:**", "**{drone}** is reporting clear skies for `{name}`. 30 minutes left."),
        ("🧨 **PREP LOG:**", "30 minutes until we breach for `{name}`. Double-check your stim-packs."),
        ("📟 **COMM-LINK:**", "Signal strength for `{name}` is at 80%. We go live in 30 minutes."),
        ("🪶 **WANDERER ALERT:**", "30 minutes until `{name}`. The wasteland doesn't wait for laggards."),
        ("⚙️ **SYSTEM SYNC:**", "30 minutes out from `{name}`. I’m locking in the coordinates."),
        ("🔥 **HEAT MAP:**", "Hostile signatures are grouping up for `{name}`. 30 minutes to go."),
        ("🧊 **CHILL FACTOR:**", "Calm before the storm. 30 minutes until `{name}` kicking off."),
        ("🔌 **BATTERY LOW:**", "30 minutes until `{name}`. My drones need to see some action soon."),
        ("🛡️ **DEFENSE MODE:**", "Perimeter turrets are switching to `{name}` protocols. 30 minutes left.")
    ],
    15: [
        ("🚨 **15 MINUTE ALERT:**", "Quarter hour until `{name}`. This is your final chance to gear up!"),
        ("🚁 **VULTURE SIGHTING:**", "I’ve got **{drone}** hovering over the `{name}` site. 15 minutes!"),
        ("⚡ **ENERGY SURGE:**", "15 minutes until `{name}`. I’m overclocking the sensors for you."),
        ("🏃 **GET MOVING:**", "If you aren't at your stations for `{name}` in 15 minutes, don't bother coming."),
        ("🛰️ **LOCKED ON:**", "Target acquired for `{name}`. 15 minutes to impact."),
        ("☣️ **BIO-ALERT:**", "Radiation is dropping. `{name}` is a go in 15 minutes."),
        ("🛠️ **LAST CALL:**", "Closing the workbench. 15 minutes until `{name}` starts. Good luck."),
        ("💥 **FUSE LIT:**", "The timer for `{name}` is down to 15 minutes. Prepare for noise."),
        ("🔭 **SCOPE CHECK:**", "Adjusting focus for `{name}`. 15 minutes until we engage."),
        ("🧩 **LOGIC BOARD:**", "Everything is falling into place. `{name}` starts in 15 minutes.")
    ],
    3: [
        ("⚠️ **3 MINUTES LEFT:**", "Lock and load! `{name}` is practically on top of us!"),
        ("🚁 **DRONE SWARM:**", "Deploying the full fleet for `{name}`! 3 minutes until contact!"),
        ("🧟 **I SEE THEM:**", "They're at the gates! 3 minutes until `{name}` is a bloodbath!"),
        ("📡 **SIGNAL PEAK:**", "Uplink is 100% stable. `{name}` starts in 3... 2... actually 3 minutes."),
        ("🏃 **RUN:**", "3 minutes to get to the `{name}` extraction point! Move it!"),
        ("🔥 **ENGINES HOT:**", "Engines are roaring. `{name}` is launching in 3 minutes!"),
        ("🧨 **CHARGE SET:**", "3 minutes until we blow the doors for `{name}`! Covers your ears!"),
        ("🌑 **DARK MODE:**", "Switching to combat HUD for `{name}`. 3 minutes remaining."),
        ("🦾 **NEURO-LINK:**", "Syncing all survivors to `{name}` frequency. 3 minutes to go!"),
        ("🎤 **MARICA'S MIC:**", "This is it. 3 minutes. `{name}`. Don't embarrass me.")
    ],
    0: [
        ("🔥 **MISSION START:**", "`{name}` IS LIVE! Go, go, go!"),
        ("🚁 **DRONES AWAY:**", "Deployment for `{name}` has begun! Eyes up, survivors!"),
        ("🧟 **CONTACT:**", "Engaging hostiles for `{name}`! Clearance granted!"),
        ("🛰️ **ORBITAL STRIKE:**", "Payload delivered for `{name}`! Move into the smoke!"),
        ("🔌 **GRID ACTIVE:**", "Full power to `{name}`! Show them what the Alliance can do!"),
        ("🛠️ **TOOLS DOWN:**", "No more talk. `{name}` is happening NOW."),
        ("🚨 **HORN BLAST:**", "The sirens are wailing! `{name}` has officially started!"),
        ("⚡ **VOLTAGE MAX:**", "Systems are red-lining! `{name}` is in progress!"),
        ("🔭 **TARGET NEUTRALIZING:**", "Commencing operation `{name}`. I'm watching your back."),
        ("🎬 **ACTION:**", "The cameras are rolling and the drones are flying. `{name}` is live!")
    ]
}

INTEL_DATABASE = {
    "verify": "Proceed to <#1411420121901301760> and complete your bio-scan to unlock the rest of the hub.",
    "rules": "Protocol is simple: Respect the crew, follow the chain of command, and don't touch my drones. Full list in <#1409268742340477069>.",
    "roles": "We have 3 main ranks: Scout (Lvl 5), Veteran (Lvl 10), and Alliance Elite (Lvl 20). Level up by contributing to the hub!",
    "drones": "My current fleet includes Sparky (Scout), Vulture-7 (Combat), and Orbital-Alpha (Intel). Don't try to hack them.",
    "marica": "Want to know about me? I'm a former hacker turned Hub guardian. My drones are my only friends, and I'm just here for the freedom."
}

SCAVENGE_OUTCOMES = [
    ("🥫 My drone Sparky found a stash of beans! (+20 XP)", 20, "Canned Beans"),
    ("🔫 'Vulture-7' spotted some 9mm casings in the dirt. (+10 XP)", 10, "9mm Casing"),
    ("💉 I've dropped a stim-pack at your coordinates. (+30 XP)", 30, "Stim-pack"),
    ("📻 I found a radio! I might be able to fix this. (+15 XP)", 15, "Broken Radio"),
    ("🧥 Look at this vest! It's better than those rags you're wearing. (+25 XP)", 25, "Tactical Vest"),
    ("🍫 Found a protein bar. It’s 2 years expired, but who cares? (+22 XP)", 22, "Protein Bar"),
    ("🔦 Found a flashlight. Batteries are at 4%, better move fast. (+12 XP)", 12, "Flashlight"),
    ("🛠️ Found a bag of loose bolts. Might be useful for drone repairs. (+15 XP)", 15, "Bag of Bolts"),
    ("🔋 An old laptop battery! I can definitely repurpose this. (+28 XP)", 28, "Old Battery"),
    ("💊 Found some dirty bandages. Better than nothing, I guess. (+10 XP)", 10, "Bandages")
]

MARICA_STATUSES = [
    "Recalibrating Drones...", "Checking Heat Maps...", "Fixing Vulture-3...", 
    "Watching your back.", "Hacking a terminal...", "Watching Helles Hub.", 
    "Debugging Neuro-Links.", "Monitoring Rad-Storms.", "Syncing Satellites.", "Cleaning Sparky's lenses."
]

FISH_CONFIG = {'N': 20, 'R': 20, 'SR': 15, 'SSR': 10}

# ---------------- DATA HANDLING ----------------
def load_json(filename, default):
    if not os.path.exists(filename): return default
    try:
        with open(filename, 'r', encoding='utf-8') as f: return json.load(f)
    except: return default

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

level_data = load_json(LEVEL_FILE, {})
mission_data = load_json(MISSION_FILE, {})
fish_data = load_json(FISH_FILE, {"extras": {}, "wanted": {}})

xp_cooldowns = {}
scavenge_cooldowns = {}
running_tasks = {}

# ---------------- FISH EXCHANGE COMPONENTS ----------------

async def re_anchor_menu(channel):
    """Ensures the trade menu is always at the very bottom."""
    # Search history for previous bot menu and delete it
    async for message in channel.history(limit=50):
        if message.author.id == bot.user.id and message.embeds:
            # FIX: Safely check for title to avoid TypeError: 'NoneType' is not iterable
            title = message.embeds[0].title
            if title and "Fish-Link Network" in title:
                try: 
                    await message.delete()
                except:
                    pass
    
    emb = discord.Embed(title="📡 Marcia’s Fish-Link Network", 
                        description="Coordinate your Arctic Ice Pit trades here.\n\n"
                                    "**📦 Add Extra:** Share duplicates you have.\n"
                                    "**🎣 Find Fish:** Search or log a request for fish you need.\n"
                                    "**⚙️ Manage:** Remove fish you gave away or finally received.", 
                        color=0x0099ff)
    await channel.send(embed=emb, view=FishControlView())

class FishSelect(discord.ui.Select):
    def __init__(self, rarity, mode):
        self.mode = mode
        self.rarity = rarity
        max_num = FISH_CONFIG[rarity]
        options = [discord.SelectOption(label=f"{rarity}-{i}", value=f"{rarity}-{i}") for i in range(1, max_num + 1)]
        super().__init__(placeholder=f"Pick a {rarity} fish...", options=options)

    async def callback(self, interaction: discord.Interaction):
        fish_id = self.values[0]
        uid = str(interaction.user.id)
        
        if self.mode == 'add':
            if fish_id not in fish_data["extras"]: fish_data["extras"][fish_id] = []
            if uid not in fish_data["extras"][fish_id]:
                fish_data["extras"][fish_id].append(uid)
                
                if fish_id in fish_data["wanted"]:
                    wanters = fish_data["wanted"][fish_id]
                    for wanter_id in wanters:
                        try:
                            w_user = await bot.fetch_user(int(wanter_id))
                            await w_user.send(f"📦 **FISH-LINK MATCH:** <@{uid}> just listed a spare **{fish_id}**!")
                        except: pass
                
                save_json(FISH_FILE, fish_data)
                emb = discord.Embed(color=0x2ecc71, description=f"📦 **Duplicate Alert:** <@{uid}> has a spare **{fish_id}**!")
                await interaction.channel.send(embed=emb)
                await interaction.response.edit_message(content=f"✅ Registered **{fish_id}**.", view=None)
            else:
                await interaction.response.edit_message(content=f"You already listed **{fish_id}**.", view=None)
        
        else: # Mode 'find'
            donors = fish_data["extras"].get(fish_id, [])
            if donors:
                mentions = ", ".join([f"<@{d}>" for d in donors])
                await interaction.response.edit_message(content=f"📡 **Signal Found:** {mentions} have it.", view=None)
            else:
                if fish_id not in fish_data["wanted"]: fish_data["wanted"][fish_id] = []
                if uid not in fish_data["wanted"][fish_id]:
                    fish_data["wanted"][fish_id].append(uid)
                    save_json(FISH_FILE, fish_data)
                
                await interaction.response.edit_message(content=f"❌ Request logged for **{fish_id}**.", view=None)
                await interaction.channel.send(f"🎣 <@{uid}> is looking for **{fish_id}**!")
        
        # KEY FIX: Force menu re-anchoring immediately after interaction completes
        await re_anchor_menu(interaction.channel)

class FishControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Add Extra", style=discord.ButtonStyle.green, custom_id="fish_add", emoji="📦")
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.prompt_rarity(interaction, 'add')

    @discord.ui.button(label="Find Fish", style=discord.ButtonStyle.primary, custom_id="fish_find", emoji="🎣")
    async def find_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.prompt_rarity(interaction, 'find')

    @discord.ui.button(label="Manage My Trades", style=discord.ButtonStyle.gray, custom_id="fish_manage", emoji="⚙️")
    async def manage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        my_extras = [fid for fid, users in fish_data["extras"].items() if uid in users]
        my_needs = [fid for fid, users in fish_data["wanted"].items() if uid in users]

        if not my_extras and not my_needs:
            return await interaction.response.send_message("No active fish listings.", ephemeral=True)

        options = []
        for f in my_extras:
            options.append(discord.SelectOption(label=f"Gave Away: {f}", value=f"rem_extra_{f}", emoji="🗑️"))
        for f in my_needs:
            options.append(discord.SelectOption(label=f"Received: {f}", value=f"rem_need_{f}", emoji="✅"))

        view = discord.ui.View()
        sel = discord.ui.Select(placeholder="Remove an entry...", options=options)

        async def sel_cb(it: discord.Interaction):
            val = sel.values[0]
            if val.startswith("rem_extra_"):
                fid = val.replace("rem_extra_", "")
                fish_data["extras"][fid].remove(str(it.user.id))
            else:
                fid = val.replace("rem_need_", "")
                fish_data["wanted"][fid].remove(str(it.user.id))
            
            save_json(FISH_FILE, fish_data)
            await it.response.edit_message(content="✅ Entry removed.", view=None)
            await re_anchor_menu(it.channel)

        sel.callback = sel_cb
        view.add_item(sel)
        await interaction.response.send_message("Management Terminal:", view=view, ephemeral=True)

    async def prompt_rarity(self, interaction, mode):
        view = discord.ui.View()
        sel = discord.ui.Select(placeholder="Select Rarity...", options=[discord.SelectOption(label=r, value=r) for r in FISH_CONFIG.keys()])
        async def sel_cb(it: discord.Interaction):
            v = discord.ui.View(); v.add_item(FishSelect(sel.values[0], mode))
            await it.response.edit_message(content=f"Select the **{sel.values[0]}**:", view=v)
        sel.callback = sel_cb
        view.add_item(sel)
        await interaction.response.send_message(f"Trade Phase 1", view=view, ephemeral=True)

# ---------------- CORE BOT CLASS ----------------
class MaricaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        intents.members = True          
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.translator = Translator()

bot = MaricaBot()

async def apply_role_rewards(member, stats):
    lvl = stats["level"]
    for rank_lvl, role_name in ROLE_REWARDS.items():
        if lvl >= rank_lvl:
            role = discord.utils.get(member.guild.roles, name=role_name)
            if role and role not in member.roles:
                try: await member.add_roles(role)
                except: pass

async def check_level_up(user, stats):
    next_level_xp = stats["level"] * LEVEL_UP_BASE
    if stats["xp"] >= next_level_xp:
        stats["level"] += 1
        stats["xp"] = 0 
        try:
            await user.send(f"Level up! You're now **Level {stats['level']}**.")
        except: pass
        if isinstance(user, discord.Member):
            await apply_role_rewards(user, stats)
    return stats

# ---------------- TASKS ----------------
@tasks.loop(minutes=30)
async def cycle_status():
    status = random.choice(MARICA_STATUSES)
    await bot.change_presence(activity=discord.Game(name=status))

@tasks.loop(hours=84)
async def random_broadcast():
    jitter = random.randint(1, 302400)
    await asyncio.sleep(jitter)
    channel = bot.get_channel(CHAT_CHANNEL_ID)
    if channel:
        await channel.send(random.choice(MARICA_QUOTES))

# ---------------- HELP & UTILITY ----------------
async def send_help_text(ctx):
    help_content = (
        "📂 **MARICA OS v3.0 - SYSTEM DIRECTORY**\n\n"
        "🛠️ **SURVIVOR:** `!profile`, `!top`, `!inventory`, `!scavenge`, `!intel <topic>`, `!bio` \n"
        "🛰️ **UTILITY:** `!talk`, `!ping` \n"
        "🚁 **COMMANDER:** `!event`, `!upcoming`, `!cancel_mission <name>`, `!clear <n>` \n"
        "🎣 **NETWORK:** `!setup_trade` \n\n"
        "Deleting in 30s..."
    )
    msg = await ctx.send(help_content)
    await asyncio.sleep(30)
    try: await msg.delete()
    except: pass

@bot.command()
async def ping(ctx):
    await ctx.reply(f"🏓 Signal: **{round(bot.latency * 1000)}ms**.")

@bot.command()
async def bio(ctx):
    msg = await ctx.send(f"📜 **LOG:**\n\n{MARICA_LORE}")
    await asyncio.sleep(60)
    try: await msg.delete()
    except: pass

@bot.command()
async def profile(ctx, member: discord.Member = None):
    member = member or ctx.author
    stats = level_data.get(str(member.id), {"xp": 0, "level": 1, "inventory": []})
    next_xp = stats["level"] * LEVEL_UP_BASE
    await ctx.send(f"👤 **{member.display_name}** | Level {stats['level']} | XP {stats['xp']}/{next_xp}")

@bot.command(name="help")
async def help_cmd(ctx): await send_help_text(ctx)

@bot.command(name="commands")
async def commands_cmd(ctx): await send_help_text(ctx)

# ---------------- SURVIVOR COMMANDS ----------------
@bot.command()
async def top(ctx):
    if not level_data: return await ctx.send("📡 No signals.")
    sorted_users = sorted(level_data.items(), key=lambda x: (x[1]['level'], x[1]['xp']), reverse=True)[:10]
    leaderboard = "🏆 **ELITE**\n\n"
    for i, (uid, data) in enumerate(sorted_users, 1):
        user = bot.get_user(int(uid))
        name = user.name if user else f"Ghost-{uid}"
        leaderboard += f"{i}. **{name}** - Lvl {data['level']}\n"
    msg = await ctx.send(leaderboard)
    await asyncio.sleep(20)
    try: await msg.delete()
    except: pass

@bot.command()
async def inventory(ctx):
    uid = str(ctx.author.id)
    inv = level_data.get(uid, {}).get("inventory", [])
    if not inv: 
        return await ctx.send("🎒 Stash empty.", delete_after=5)
    counts = {item: inv.count(item) for item in set(inv)}
    items_list = "\n".join([f"• {item} x{qty}" for item, qty in counts.items()])
    await ctx.send(f"🎒 **{ctx.author.name}'S STASH**\n\n{items_list}", delete_after=20)

@bot.command()
async def scavenge(ctx):
    uid = str(ctx.author.id)
    if datetime.now().timestamp() - scavenge_cooldowns.get(uid, 0) < 3600:
        return await ctx.reply("⏳ Drones recharging.", delete_after=5)
    flavor, xp, item = random.choice(SCAVENGE_OUTCOMES)
    scavenge_cooldowns[uid] = datetime.now().timestamp()
    stats = level_data.get(uid, {"xp": 0, "level": 1, "inventory": []})
    stats["xp"] += xp
    if "inventory" not in stats: stats["inventory"] = []
    stats["inventory"].append(item)
    stats = await check_level_up(ctx.author, stats)
    level_data[uid] = stats
    save_json(LEVEL_FILE, level_data)
    await ctx.reply(f"🚁 {flavor}")

@bot.command()
async def intel(ctx, topic: str = None):
    if topic is None:
        topics = ", ".join([f"`{t}`" for t in INTEL_DATABASE.keys()])
        return await ctx.reply(f"📡 Topics: {topics}", delete_after=10)
    info = INTEL_DATABASE.get(topic.lower())
    if info:
        await ctx.send(f"📥 **{topic.upper()}**\n\n{info}", delete_after=20)
    else:
        await ctx.reply("❌ Not found.", delete_after=5)

@bot.command()
async def talk(ctx): await ctx.reply(random.choice(MARICA_QUOTES))

@bot.command()
async def welcome_quote(ctx):
    if ctx.channel.id == WELCOME_CHANNEL_ID: await ctx.send(random.choice(MARICA_QUOTES))
    else: await ctx.reply("❌ Wrong channel.", delete_after=5)

@bot.command()
@commands.has_permissions(manage_guild=True)
async def setup_trade(ctx):
    try: await ctx.message.delete()
    except: pass
    await re_anchor_menu(ctx.channel)

# ---------------- COMMANDER PROTOCOLS ----------------
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Cleaned {amount} messages.", delete_after=3)

@bot.command()
async def upcoming(ctx):
    if not mission_data: return await ctx.send("📡 No missions.")
    upcoming_msg = "🚁 **LOG**\n\n"
    for name, info in mission_data.items():
        upcoming_msg += f"**{name}** - {info['time']}\n"
    await ctx.send(upcoming_msg)

@bot.command()
@commands.has_permissions(manage_guild=True)
async def cancel_mission(ctx, *, name: str):
    if name in mission_data:
        if name in running_tasks:
            running_tasks[name].cancel()
            del running_tasks[name]
        del mission_data[name]
        save_json(MISSION_FILE, mission_data)
        await ctx.send(f"✅ Aborted `{name}`.")
    else: await ctx.send("❌ Not found.")

@bot.command(name="test")
@commands.has_permissions(manage_guild=True)
async def test_suite(ctx):
    if ctx.channel.id != TEST_CHANNEL_ID: return
    menu = await ctx.send("🛠️ 1:Join, 2:Lvl, 3:XP")
    def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
    try:
        msg = await bot.wait_for('message', check=check, timeout=30)
        uid = str(ctx.author.id)
        if msg.content == "1": await on_member_join(ctx.author)
        elif msg.content == "2":
            stats = level_data.get(uid, {"xp": 0, "level": 1, "inventory": []})
            stats["xp"] = (stats["level"] * LEVEL_UP_BASE)
            await check_level_up(ctx.author, stats)
        elif msg.content == "3":
            stats = level_data.get(uid, {"xp": 0, "level": 1, "inventory": []})
            stats["xp"] += 100
            level_data[uid] = await check_level_up(ctx.author, stats)
            save_json(LEVEL_FILE, level_data)
            await ctx.send("⚡ XP Injected.")
        try: await msg.delete()
        except: pass
    except asyncio.TimeoutError: 
        try: await menu.delete()
        except: pass

@bot.command()
@commands.has_permissions(manage_guild=True)
async def event(ctx):
    try:
        await ctx.author.send("📡 Codename?")
        await ctx.message.add_reaction("🚁")
    except: return await ctx.send("❌ Open DMs.")
    def check(m): return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
    try:
        name = (await bot.wait_for('message', check=check, timeout=60)).content
        await ctx.author.send(f"Directives?")
        desc = (await bot.wait_for('message', check=check, timeout=60)).content
        await ctx.author.send(f"Time? `YYYY-MM-DD HH:MM`")
        t_str = (await bot.wait_for('message', check=check, timeout=60)).content
        target_dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
        utc_dt = target_dt.replace(tzinfo=timezone.utc) - SERVER_OFFSET
        mission_data[name] = {"desc": desc, "time": t_str, "utc": utc_dt.isoformat()}
        save_json(MISSION_FILE, mission_data)
        running_tasks[name] = bot.loop.create_task(manage_event_reminders(name, desc, utc_dt))
        await ctx.author.send("✅ Locked.")
    except Exception as e: await ctx.author.send(f"❌ Error: {e}")

async def manage_event_reminders(name, desc, utc_dt):
    for mins in [60, 30, 15, 3, 0]:
        trigger = utc_dt - timedelta(minutes=mins)
        wait = (trigger - datetime.now(timezone.utc)).total_seconds()
        if wait > 0:
            await asyncio.sleep(wait)
            h, b = random.choice(TIMED_REMINDERS[mins])
            notif = f"@everyone\n{h.format(name=name, drone='Sparky')}\n{b.format(name=name, drone='Sparky')}\n\n**Directives:** {desc}"
            for cid in EVENT_CHANNEL_IDS:
                chan = bot.get_channel(cid)
                if chan: await chan.send(notif)
    if name in mission_data:
        del mission_data[name]
        save_json(MISSION_FILE, mission_data)

# ---------------- CORE EVENTS ----------------
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return

    # BOTTOM ANCHOR LOGIC: Trigger when someone types
    if message.channel.id == FISH_TRADE_CHANNEL_ID:
        # FIX: Added title check here as well for consistency
        is_menu = (message.author.id == bot.user.id and 
                   message.embeds and 
                   message.embeds[0].title and 
                   "Fish-Link Network" in message.embeds[0].title)
        if not is_menu:
            await re_anchor_menu(message.channel)

    is_bot_mentioned = bot.user.mentioned_in(message) and not message.mention_everyone
    is_reply = message.reference and message.reference.resolved and message.reference.resolved.author.id == bot.user.id
    if is_bot_mentioned or is_reply: await message.reply(random.choice(ON_MENTION_REPLIES))
    
    if message.content.startswith("!") and message.channel.id != TEST_CHANNEL_ID:
        try: 
            await asyncio.sleep(3)
            await message.delete()
        except: pass

    uid = str(message.author.id)
    if datetime.now().timestamp() - xp_cooldowns.get(uid, 0) > 60:
        stats = level_data.get(uid, {"xp": 0, "level": 1, "inventory": []})
        stats["xp"] += XP_PER_MESSAGE
        level_data[uid] = await check_level_up(message.author, stats)
        xp_cooldowns[uid] = datetime.now().timestamp()
        save_json(LEVEL_FILE, level_data)
    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.emoji) in FLAG_LANG:
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        target = FLAG_LANG[str(payload.emoji)]
        translated = await asyncio.to_thread(bot.translator.translate, msg.content, dest=target)
        await msg.reply(f"📡 **DECODED [{target.upper()}]:**\n{translated.text}", mention_author=False)

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        welcome_msg = random.choice(WELCOME_VARIATIONS).format(
            mention=member.mention, verify=VERIFY_CHANNEL_ID, rules=RULES_CHANNEL_ID, 
            drone='Sparky', boss=f"<@{LEADER_IDS['AMEER']}>", tech_lead=f"<@{LEADER_IDS['PANDA']}>",
            troublemaker=f"<@{LEADER_IDS['AKROT']}>", engineer=f"<@{LEADER_IDS['MIGS_BOO']}>",
            archivist=f"<@{LEADER_IDS['LUJAYN']}>", plumber=f"<@{LEADER_IDS['PLUMBER']}>",
            chaos=f"<@{LEADER_IDS['CHAOS']}>", reaper=f"<@{LEADER_IDS['REAPER']}>",
            blossom=f"<@{LEADER_IDS['BLOSSOM']}>", amatae=f"<@{LEADER_IDS['AMATAE']}>"
        )
        await channel.send(welcome_msg)
    role = discord.utils.get(member.guild.roles, name=AUTO_ROLE_NAME)
    if role: 
        try: await member.add_roles(role)
        except: pass

@bot.event
async def on_ready():
    logger.info("MARICA v3.0 ONLINE")
    bot.add_view(FishControlView()) 
    if not cycle_status.is_running(): cycle_status.start()
    if not random_broadcast.is_running(): random_broadcast.start()
    for name, info in mission_data.items():
        if "utc" in info:
            utc_dt = datetime.fromisoformat(info["utc"])
            if utc_dt > datetime.now(timezone.utc):
                running_tasks[name] = bot.loop.create_task(manage_event_reminders(name, info["desc"], utc_dt))

bot.run(TOKEN)