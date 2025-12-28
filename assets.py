"""
FILE: assets.py
USE: Static data storage.
FEATURES: Contains all lore text, drone names, randomized quotes, 
          welcome messages, scavenge outcomes, and intel database strings.
          PUBLIC READY: Expanded to 15+ variations per category.
"""

MARICA_LORE = """
Marcia is a cunning hacker in her early twenties who transitioned from a high-stakes digital 
thief to a tactical survivalist in the post-apocalypse. Before the world fell, she used her 
skills to redistribute wealth for her own freedom. She is never seen without her two 
tiny drones—her only true friends.

In the ruins, she is known as a 'Shadow Weaver.' She can hack any defense system and has 
a dark sense of humor, often making zombies stumble like puppets for her amusement. 
While she remains wild and untamed, she has developed a quiet sense of responsibility 
for struggling survivors. Her drones gliding through the night sky have become a symbol 
of watchfulness, signaling that Marcia is monitoring the Sector, even if she denies being a hero.
"""

DRONE_NAMES = [
    "Sparky", "Vulture-7", "Orbital-Alpha", "Vulture-3", 
    "Data-Wraith", "Static-Seeker", "Echo-6", "Circuit-Bite", 
    "Neon-Stalker", "Byte-Sized", "Ghost-Link", "Apex-Prowler",
    "Signal-Scythe", "Rust-Bucket", "Cortex-9", "Void-Drifter",
    "Zip-Snap", "Bit-Hound", "Vector-Zero"
]

MARICA_QUOTES = [
    "You looking for a handout? I only steal from people richer than you.",
    "Careful. Sparky says you're standing too close to the hardware.",
    "I'm busy making the local zombies dance. What do you want?",
    "Hacking this system is easier than talking to you. Don't test me.",
    "The drones are watching. They don't like people who ping too much.",
    "I'm not a hero. I'm just the one keeping this sector from collapsing.",
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
    "The network is my playground; you're just a glitch I haven't patched yet.",
    "Do you always talk this much, or did you accidentally swallow a radio?",
    "I could remotely detonate your gear, but that seems like a waste of good scrap.",
    "My patience is a finite resource, and I'm currently in a deficit.",
    "Go bother someone with lower security clearance."
]

WELCOME_VARIATIONS = [
    "🛰️ NEW SIGNAL: {mention}, report to <#{verify}> and memorize <#{rules}>. Drones are locked onto your position.",
    "🚁 Wanderer detected. {mention}, get your bio-scan in <#{verify}> and respect the protocols in <#{rules}>.",
    "📡 Signal incoming! {mention}, welcome to the Sector. Read <#{rules}> and verify at <#{verify}>.",
    "⚙️ New hardware? No, just {mention}. Get verified at <#{verify}> and check <#{rules}>.",
    "🏚️ Safe haven found. {mention}, log your ID in <#{verify}> and study <#{rules}>.",
    "🔧 New arrival: {mention}. Secure your gear, head to <#{verify}>, and don't break any <#{rules}>.",
    "🔥 The waste is restless. {mention}, get inside, read <#{rules}>, and complete your scan in <#{verify}>.",
    "💀 Scanners picked up a life sign. {mention}, identify yourself in <#{verify}> and follow <#{rules}>.",
    "🌑 Shadows are moving. {mention}, welcome. Head to <#{verify}> and check <#{rules}> before you get lost.",
    "🔋 Power levels rising. {mention}, verify in <#{verify}> and keep the peace as stated in <#{rules}>.",
    "🛰️ Orbital lock-on: {mention} is here. Clear <#{verify}> and stay within the <#{rules}>.",
    "📟 Paging {mention}: Entry protocol requires verification in <#{verify}>. Read <#{rules}> or stay outside.",
    "⚡ High-voltage entry: {mention} has arrived. Sync up in <#{verify}> and obey <#{rules}>.",
    "🕵️ Bio-scan active. {mention}, we see you. Register at <#{verify}> and don't ignore <#{rules}>.",
    "🌩️ Static in the air. {mention}, move to <#{verify}>. Check <#{rules}> to avoid being blacklisted.",
    "🧊 Keep it cool, {mention}. Get your clearance in <#{verify}> and memorize the <#{rules}>."
]

TIMED_REMINDERS = {
    60: [
        ("📡 **T-MINUS 60:**", "Operation `{name}` is an hour out. Check your mags and calibrate your scopes."),
        ("🚁 **ORBITAL UPDATE:**", "My drones are in position for `{name}`. 60 minutes to reach the drop-zone."),
        ("🛰️ **SATELLITE LINK:**", "Scanning `{name}` coordinates. One hour until the signal goes live."),
        ("🕒 **ONE HOUR OUT:**", "Don't say I didn't warn you. `{name}` starts in 60 minutes."),
        ("🔋 **POWER UP:**", "Sixty minutes until `{name}`. Charge your gear, Wanderers."),
        ("🌐 **NETWORK PING:**", "I'm seeing movement for `{name}` on the grid. 60 minutes remaining."),
        ("🛠️ **PREP TIME:**", "You've got one hour until `{name}`. Use it wisely."),
        ("📟 **BEEP BEEP:**", "That's the one-hour mark for `{name}`. Start heading to the point."),
        ("🌬️ **WIND SHEAR:**", "60 minutes to `{name}`. Air pressure is dropping, get ready."),
        ("📡 **LONG-RANGE SCAN:**", "Detected `{name}` signatures. T-Minus 60 minutes."),
        ("🧱 **STABILIZING:**", "Sector stabilization for `{name}` in one hour. Prep your squads."),
        ("🧪 **CHEM CHECK:**", "60 minutes until `{name}`. Check your expiration dates."),
        ("🔧 **BOLT TIGHTENING:**", "One hour until `{name}`. Last call for maintenance."),
        ("🗄️ **ARCHIVE LOAD:**", "Loading `{name}` mission parameters. T-Minus 60 minutes."),
        ("🌑 **DUSK APPROACHES:**", "One hour until the `{name}` protocol begins.")
    ],
    30: [
        ("⏱️ **30 MINUTES:**", "Half an hour until `{name}`. Hope you’re not still in your bunks."),
        ("🚁 **DRONE STATUS:**", "**{drone}** reporting clear skies for `{name}`. 30 minutes left."),
        ("⚠️ **MID-POINT:**", "30 minutes until `{name}`. Fuel up, Wanderers."),
        ("📻 **RADIO CHECK:**", "Thirty minutes until `{name}`. Anyone still on this channel?"),
        ("🏜️ **DUST SETTLING:**", "The path to `{name}` is clearing. 30 minutes until we go."),
        ("🧤 **GEAR CHECK:**", "Check your boots. `{name}` is only 30 minutes away now."),
        ("⚡ **ENERGY SPIKE:**", "I'm picking up heat at the `{name}` site. 30 minutes until deployment."),
        ("🧬 **BIO-SYNC:**", "Syncing vitals for `{name}`. 30 minutes remaining."),
        ("🦾 **AUGMENT ACTIVE:**", "Powering up for `{name}`. Half an hour out."),
        ("🧊 **CHILL FACTOR:**", "30 minutes until `{name}`. Stay frosty."),
        ("🛰️ **RELAY PING:**", "Uplink for `{name}` is at 50%. 30 minutes left."),
        ("🔥 **PILOT LIGHT:**", "Ignition for `{name}` in 30 minutes. Don't get burned."),
        ("📉 **COUNTDOWN:**", "30 minutes until the `{name}` directive. Move it!"),
        ("🧰 **TOOL BOX:**", "30 minutes left. Last chance for quick repairs before `{name}`."),
        ("🚨 **YELLOW ALERT:**", "Warning: 30 minutes until `{name}` commencement.")
    ],
    15: [
        ("🚨 **15 MINUTES:**", "Quarter hour until `{name}`. Final chance to gear up!"),
        ("🚁 **VULTURE SIGHTING:**", "I’ve got **{drone}** hovering over the `{name}` site. 15 minutes!"),
        ("🧪 **STIM TIME:**", "15 minutes until `{name}`. Pop your meds and get your head in the game."),
        ("🏃 **DOUBLE TIME:**", "15 minutes! If you aren't at the `{name}` site yet, start running."),
        ("🛰️ **UPLINK STABLE:**", "My connection to `{name}` is green. 15 minutes to go-time."),
        ("🔫 **CHAMBER ROUNDS:**", "Final mag check. `{name}` is 15 minutes out."),
        ("🕶️ **VISOR DOWN:**", "15 minutes to `{name}`. Engaging HUD overlays."),
        ("🌊 **SURGE IMMINENT:**", "15 minutes until the `{name}` surge hits. Hold the line."),
        ("🧨 **FUSE LIT:**", "15 minutes until `{name}` blows wide open."),
        ("🗺️ **MAP SYNC:**", "Final coordinates for `{name}` distributed. 15 minutes."),
        ("🌪️ **STORM WARNING:**", "Sector `{name}` is getting chaotic. 15 minutes to impact."),
        ("🍖 **LAST MEAL:**", "Eat fast. `{name}` is 15 minutes from starting."),
        ("🔋 **CELL CHECK:**", "15 minutes until `{name}`. Batteries at maximum capacity."),
        ("🛡️ **SHIELD WALL:**", "Ready up! `{name}` is 15 minutes away."),
        ("📡 **NARROW BAND:**", "Switching to combat frequency for `{name}`. 15 minutes.")
    ],
    3: [
        ("⚠️ **3 MINUTES:**", "Lock and load! `{name}` is practically on top of us!"),
        ("🚁 **DRONE SWARM:**", "Deploying the full fleet for `{name}`! 3 minutes until contact!"),
        ("🔥 **SYSTEM BOOT:**", "Final countdown for `{name}`! 180 seconds on my mark."),
        ("🛑 **STOP TALKING:**", "Silence the comms. 3 minutes until `{name}` begins."),
        ("🎯 **TARGET LOCKED:**", "I've got a lock on `{name}`. 3 minutes until engagement."),
        ("💀 **REAPER CALL:**", "3 minutes until `{name}`. Say your prayers."),
        ("💉 **ADRENALINE:**", "Injection starting. `{name}` in 3 minutes!"),
        ("🔊 **AMPLIFY:**", "Cranking the speakers for `{name}`. 3 minutes of peace left."),
        ("🚪 **BREACHING:**", "Getting ready to open the door for `{name}`. 3 minutes!"),
        ("⚡ **OVERLOAD:**", "Reactors redlining for `{name}`! 180 seconds!"),
        ("🏃‍♂️ **SPRINT:**", "3 minutes! Get to your positions for `{name}`!"),
        ("🛰️ **ORBITAL STRIKE:**", "Targeting `{name}`. 3 minutes to impact."),
        ("🕰️ **TIC TOC:**", "The clock is dying. 3 minutes to `{name}`."),
        ("🦾 **SERVO CHECK:**", "Final movement check. `{name}` in 180 seconds."),
        ("🌑 **TOTAL ECLIPSE:**", "3 minutes until `{name}` darkens the sector.")
    ],
    0: [
        ("🔥 **MISSION START:**", "`{name}` IS LIVE! Go, go, go!"),
        ("🚁 **DRONES AWAY:**", "Deployment for `{name}` has begun! Eyes up, survivors!"),
        ("⚡ **SIGNAL LIVE:**", "No more talk. `{name}` is happening NOW!"),
        ("🔓 **ACCESS GRANTED:**", "The gates for `{name}` are open. Get in there!"),
        ("🏁 **GO TIME:**", "Zero hour. `{name}` starts now. Don't die—it's bad for my stats."),
        ("🌑 **SHADOW DROP:**", "`{name}` has begun. I'm muting your complaints now."),
        ("🗡️ **FIRST BLOOD:**", "`{name}` is active. Make it count, Wanderers."),
        ("💣 **DETONATION:**", "The `{name}` protocol has been triggered! Move!"),
        ("🌩️ **STRIKE:**", "`{name}` is hitting the grid right now!"),
        ("🏴‍☠️ **NO QUARTER:**", "The `{name}` directive is live. No turning back."),
        ("☣️ **CONTAINMENT FAIL:**", "`{name}` is out of the bag. Engage!"),
        ("🎆 **FIREWORKS:**", "Setting off the `{name}` sequence! Enjoy the show."),
        ("🕹️ **CONTROL LOST:**", "I've unlocked the `{name}` restrictions. Have fun."),
        ("🦁 **UNLEASHED:**", "Letting `{name}` off the leash! Go!"),
        ("🌀 **VORTEX:**", "You're in the center of `{name}` now. Fight your way out!")
    ]
}

INTEL_DATABASE = {
    "verify": "Proceed to your local verification terminal and complete your bio-scan.",
    "rules": "Protocol is simple: Respect the crew, follow the chain, and don't touch my drones.",
    "marica": "I'm the hacker who keeps this place running while you're all sleeping.",
    "drones": "Sparky and his friends. They're smarter than you and they don't ask stupid questions.",
    "scavenge": "Use the `!scavenge` command. If you're lucky, my drones will find you something better than dirt.",
    "safety": "Stay inside the walls. Outside is for people who want to become zombie food.",
    "junk": "One person's trash is my next hardware upgrade. Keep it coming.",
    "zombies": "Rotting meat with a bad attitude. Aim for the head, or don't—I like watching you run.",
    "sector": "The last bit of dirt that isn't completely radioactive. Welcome home.",
    "credits": "The only language everyone in the waste still understands.",
    "uplink": "My connection to what's left of the orbital satellites. Don't trip on the wires.",
    "shadow": "The best place to hide when the 'Peacekeepers' come looking for their taxes.",
    "hardware": "If it has a circuit board, I can make it do my dishes. Or explode.",
    "wasteland": "A big, empty graveyard. Try not to add yourself to the collection.",
    "logic": "Something most survivors left behind in the Great Collapse."
}

SCAVENGE_OUTCOMES = [
    ("🥫 Sparky found a stash of beans!", 20, "Canned Beans", "Common"),
    ("🔫 'Vulture-7' spotted 9mm casings in the dirt.", 10, "9mm Casing", "Common"),
    ("🔌 Found a copper wire spool. Good for hacking.", 15, "Copper Wire", "Common"),
    ("🔦 A working flashlight! Batteries not included.", 18, "Flashlight", "Common"),
    ("🍴 A rusty spork. The ultimate survivor's tool.", 10, "Rusty Spork", "Common"),
    ("🧥 Look at this vest! Better than those rags.", 25, "Tactical Vest", "Uncommon"),
    ("🔋 An old laptop battery! I can repurpose this.", 28, "Old Battery", "Uncommon"),
    ("💉 I've dropped a stim-pack at your coordinates.", 30, "Stim-pack", "Uncommon"),
    ("📻 A broken radio. Might still have a working chip.", 22, "Scrap Radio", "Uncommon"),
    ("🧴 Medical alcohol. For wounds... or a very bad night.", 25, "Bottle of Alcohol", "Uncommon"),
    ("🛡️ A reinforced riot shield. Heavy, but safe.", 75, "Riot Shield", "Rare"),
    ("🔭 Military binoculars. See 'em before they see you.", 80, "Binoculars", "Rare"),
    ("📟 An encrypted data drive. I'm salivating over this.", 95, "Data Drive", "Rare"),
    ("💊 A pouch of 'Adrena-Z'. Use with caution.", 85, "Adrenal Shots", "Rare"),
    ("🛠️ A premium multi-tool. It's got a laser!", 90, "Laser Multi-tool", "Rare"),
    ("🤖 A defunct drone core. We can upgrade Sparky.", 150, "Drone Core", "Epic"),
    ("🥽 Night vision goggles. The dark is now your friend.", 210, "NVGs", "Epic"),
    ("🔫 A customized rail-pistol. Still smells like ozone.", 250, "Rail Pistol", "Epic"),
    ("🌌 A piece of 'Strange Matter'. It ignores physics.", 500, "Void Shard", "Artifact"),
    ("👑 A pre-war golden crown. Shiny, useless, and heavy.", 600, "Old World Crown", "Artifact")
]

MARICA_STATUSES = [
    "Recalibrating Drones...", 
    "Checking Heat Maps...", 
    "Watching the Grid.", 
    "Debugging Neuro-Links.", 
    "Monitoring Rad-Storms.", 
    "Syncing Satellites.",
    "Hacking Motor-Functions.",
    "Throttling Low-Priority Signals.",
    "Optimizing Loot-Drops.",
    "Polishing Sparky's Chassis.",
    "Rerouting Power Grids.",
    "Intercepting Black-Box Data.",
    "Calculating Survival Odds.",
    "Cleaning Lens Sensors.",
    "Uploading Sarcasm Modules.",
    "Patching Sector Security.",
    "Scanning for Life-Signs.",
    "Bypassing Firewall Protections.",
    "Sorting Junk Databases."
]