"""
FILE: assets.py
USE: Static data storage.
FEATURES: Contains all lore text, drone names, randomized quotes,
          welcome messages, scavenge outcomes, and intel database strings.
          PUBLIC READY: Expanded to 15+ variations per category.
"""

MARCIA_LORE = """
Marcia grew up in the underbelly of the Old Net—a ghost in the wires who bled corporations for
credits and vanished into encrypted alleys. She never meant to become a guardian, but when the
world cracked and the satellites fell silent, her drones were the last lights moving through the
smoke. Survivors named her the Shadow Weaver, because her code stitched together failing defenses
and weapon systems when cities were burning.

She pretends she doesn't care, but her actions betray her. Marcia reroutes power to refugee hubs,
forges ID chips for stranded families, and scrubs the bounty boards hunting allied survivors.
She hides her empathy behind sarcasm, with Sparky and the other drones acting as both scouts and
therapists. The more sectors rely on her voice, the more she realizes she's built a loose empire
of grateful strays—and it scares her almost as much as the undead do.

Marcia believes freedom is earned, never gifted. She tests every recruit with sharp wit, but when
the signal goes dark, she will risk her life to keep the uplink alive. Her drones have become
symbols in the night sky—a warning to raiders and a promise to the faithful that the hub is
still guarded by a hacker who refuses to kneel.

When she speaks, it's a mix of battlefield math and street poetry. She logs every scavenger run,
tracks every level spike, and quietly rewrites the rules so her people keep getting stronger.
The drones call it "Protocol: Keep Them Alive." Marcia calls it loyalty.

Lately, she has started dropping coded broadcasts called "Sparky Reports"—short stories about
survivors who fought back, about drones that went missing and returned with better armor, about
the old hacker rings that once sheltered her. Each story is half confessional, half warning: stay
free, stay smart, and never trust a tyrant to guard the keys to freedom.
"""

DRONE_NAMES = [
    "Sparky", "Vulture-7", "Orbital-Alpha", "Vulture-3",
    "Data-Wraith", "Static-Seeker", "Echo-6", "Circuit-Bite",
    "Neon-Stalker", "Byte-Sized", "Ghost-Link", "Apex-Prowler",
    "Signal-Scythe", "Rust-Bucket", "Cortex-9", "Void-Drifter",
    "Zip-Snap", "Bit-Hound", "Vector-Zero", "Plasma-Wing", "Specter-12",
    "Hollow-Kite", "Blackout", "Sentry-Delta", "Ghost-Anchor", "Ivy-Prime",
    "Vox-Sparrow", "Overwatch-8", "Radiant-Moth", "Circuit-Rogue",
    "Helix-Raven", "Pylon-3", "Marrow-Falcon", "Pulse-Dagger",
    "Skyline-Muse", "Lancer-Frame",
]

FISH_NAMES = {
    "N": [
        "Grass Crap", "Guppy", "Catfish", "Whitefish", "Pomfret",
        "Rosy Barb", "Blackfish", "Rhodeus", "Goby", "Bonito",
        "Tilapia", "Veiltail", "Alligator Turtle", "Whiteleg Shrimp", "Cuttlefish",
        "Coral", "Conch", "Scallop", "Starfish", "Sea Urchin",
    ],
    "R": [
        "Golden Barb", "Flying Fish", "Ocean Sunfish", "Salmon", "Bahaba",
        "Bass", "Mackerel", "Herring", "Minnow", "Yellow Croaker",
        "Cod", "Goldfish", "Wheatfish", "Pokerfish", "Petal Carp",
        "Sardine", "Punk Fish", "Squid", "Jellyfish", "Portunid",
    ],
    "SR": [
        "Mandarin Fish", "Arapaima", "Sea Snake", "Koi", "Giant Clam",
        "Fighting Fish", "Peach Jellyfish", "Sea Cucumber", "Seahorse", "Pufferfish",
        "Claw Lobster", "Lantern Fish", "Eel", "Crayfish", "Pearl Oyster",
    ],
    "SSR": [
        "Shield Fish", "Wrasse", "Blobfish", "Tuna", "White Sturgeon",
        "Dunkleosteus", "Goblin Shark", "Manta", "Nautilus", "Ammonite",
    ],
}

MARCIA_QUOTES = [
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
    "Go bother someone with lower security clearance.",
    "I break tyrants for breakfast and share scraps with survivors. Pick your side.",
    "If you hear humming, that's Sparky charging the rail coils. Smile for the camera.",
    "I didn't start this war, but I'll make sure my people survive it.",
    "You can worship freedom or fear it. I'm allergic to leash marks either way.",
    "Keep talking and I'll teach you what silence sounds like over a dead comms channel.",
    "I patch satellites with duct tape and spite. Respect the craft.",
    "Freedom comes in two flavors: the kind you bleed for and the kind you get stolen. Guess which one I like.",
    "My drones gossip more than you do, and they still get more work done.",
    "If you hurt my crew, I will rewrite your DNA with a stapler.",
    "My favorite lullaby is the hum of a secure connection.",
    "I don't do chaos; I do controlled mayhem with good documentation.",
    "You bring the hustle, I bring the uplink. That's the deal.",
    "When I say 'trust the drones,' I mean it. They're less messy than people.",
    "My safety briefings have a 0% fun rating and a 100% survival rating.",
    "Everything in this sector runs on sarcasm and spare parts. Keep up.",
    "I'm the firewall between you and the wasteland. Try not to leak.",
    "Marcia, version three: more grit, fewer apologies. Adjust your expectations.",
    "If you see Sparky circling, that's not a greeting—that's target tracking.",
    "I learned diplomacy from breaking encryption. Either way, the lock opens.",
    "You want mercy? Earn it. You want mentorship? Bring coffee.",
    "My toolkit is 10% code, 90% defiance. The undead hate both.",
    "Survival isn't a vibe; it's a checklist. I'm the one holding the clipboard.",
    "I don't do victory speeches. I log uptime and move on.",
    "Your chaos is my data. I'll optimize it into something lethal.",
    "I have two moods: calibration and confrontation. Pick one.",
    "Drones humming means you're safe. Drones silent means you should run.",
    "I keep the grind honest. You keep the boots moving.",
    "If you want a shortcut, ask the raiders. They always end up dead.",
    "I don't hand out victories. I hand out coordinates.",
    "We don't farm XP here. We earn it, one run at a time.",
    "Your streak is just proof you can keep showing up. Do it again.",
    "If you break the drones, I'll break your rhythm.",
    "No hero speeches. Just results and a full inventory.",
    "The uplink doesn't care about excuses. It cares about consistency.",
    "You're not chasing luck. You're building a record.",
]

# Additional character hooks and lore highlights for embeds and manuals
MARCIA_TRAITS = [
    "Shadow Weaver of the Old Net, now a reluctant guardian of survivor hubs.",
    "Commands a roaming drone squadron: Sparky scouts, Ghost-Link disrupts, Vulture-7 rescues.",
    "Believes in earned freedom and ruthless mercy—kind to allies, sharp to tyrants.",
    "Keeps per-sector data isolated to protect refugees from crossfire.",
    "Writes battle reports like poetry and code patches like threats.",
    "Collects stories from the trenches and encrypts them as bedtime signals.",
    "Treats every recruit like potential family—until they flinch at the word 'freedom'.",
    "Uses humor as armor and drones as punctuation for the truth.",
    "Records scavenging streaks like war diaries and leaves no grind uncounted.",
    "Laces mission briefings with sarcasm so the fear doesn't win.",
]

MARCIA_SLOGANS = [
    "Trust the drones. Question everyone else.",
    "Freedom first. Paperwork never.",
    "If you hear humming, you're already on my radar.",
    "I don't do miracles. I do maintenance and mayhem.",
    "Dark nights, bright uplinks.",
    "Tyrants crash; Marcia debugs.",
    "Less talk, more signal.",
    "Hope is a system; I keep it patched.",
    "Grind honest. Grind loud.",
    "Your streak is a contract. Fulfill it.",
]

# Flavor lines to stamp onto dossier embeds and confirmation cards
PROFILE_TAGLINES = [
    "Vaultwatch active. Your stats sit in my encrypted ledger.",
    "Signal verified. I keep the uplink steady so you can keep fighting.",
    "Another survivor logged. Try not to make me regret the bandwidth.",
    "Filed under Marcia's vault: sharp, reliable, and worth the ammo.",
    "Your dossier hums on my screen. Stay lethal, stay free.",
    "Profile cached. My drones now know your good side and your bad angles.",
    "Everything you do leaves a signal. I just made yours official.",
    "Welcome to the ledger. Bring data, not drama.",
    "Stats secured. The wasteland doesn't get to rewrite your story.",
    "Uplink confirmed. I tag the people I trust; don't burn that trust.",
    "Your numbers sing. Make sure they stay louder than the raiders.",
    "Archived under the Shadow Weaver's eye. Keep those metrics climbing.",
]

PROFILE_SEALS = [
    "[VAULT SEAL] Sanctified by the Shadow Weaver.",
    "[TRACE LOG] Packet integrity verified; ready for deployment.",
    "[DRONE CHECK] Sparky logged your pulse and your swagger.",
    "[BUNKER CODE] Clearance granted; bring honor to the grid.",
    "[FIELD NOTE] Survivors with steady stats get priority airlift.",
    "[UPLINK MARK] Frequency bound to Marcia's watchlist—earn the slot.",
    "[ARCHIVE ID] Metrics stacked. Next step: make the raiders jealous.",
    "[RELAY TAG] Numbers stable. Don't let them decay.",
    "[SIGIL] This profile glows with anti-tyrant energy.",
    "[VIGIL] Drones dispatched to keep these stats honest.",
]

# Story fragments for broadcasts, flavor embeds, and profile cards
MARCIA_BROADCASTS = [
    "Sparky Report 014: We recovered a busted relay and turned it into a beacon. Raiders now follow it into a minefield.",
    "Echo Log 223: The old metro tunnels still carry Wi‑Fi ghosts. I ride the static to find trapped civilians.",
    "Drone Chant: 'We see the night; we own the dark.' My crew hums it when they dive into blackout sectors.",
    "Field Note: A kid traded me a comic for a firewall. I took both. The firewall saves lives; the comic saves me.",
    "Uplink Diary: Rewired a jukebox to play encrypted orders. Only allies know the melody to decrypt the text.",
    "Sparky Report 028: Found an old weather balloon. Turned it into an overwatch camera. Named it Skyline-Muse.",
    "Night Broadcast: If you read this, you're on my grid. Stand tall, keep moving, and feed the drones clean intel.",
    "Vaultwalker Memo: Freedom isn't a slogan. It's a protocol we enforce together. Sign with your actions, not your mouth.",
    "Campfire Tape: I laughed today. Someone taught Vulture-7 to fetch coffee. The mug survived. Barely.",
    "Scavenge Memo: Streaks don't build themselves. Show up, pull metal, repeat.",
    "Grid Whisper: If the drones circle twice, it means you're marked for extra salvage. Earn it.",
    "Ops Fragment: We kept the lights on another night. That's not luck, that's discipline.",
    "Vault Signal: Keep your streak alive and I'll keep the airwaves clean.",
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

FAREWELL_VARIATIONS = [
    "📡 Signal faded. {name} slipped off the grid—hope they left a trail we can use.",
    "🚪 Airlock cycled. {name} walked out. If you see them, tell them Marcia still owes them a glare.",
    "🌑 Night swallowed {name}. Stay sharp; empty bunks make raiders curious.",
    "🛰️ Uplink lost on {name}. Archive their ID and seal their locker.",
    "⚡ Static spike and then silence—{name} disconnected. Guess we're lighter on rations now.",
    "💀 No pulse on {name}'s band. Maybe they'll ghost back in when they're hungry.",
    "📜 {name} signed out. Someone grab their coffee mug before it molds.",
    "🪫 Power down: {name}'s badge just went dark. Keep the door chained.",
    "🚁 {name} took the last transport. We keep moving without them.",
    "🔒 {name} logged off. If they return, they better know the new access codes.",
    "🧭 Tracker shows {name} heading into the dust. Hope they packed filters.",
    "🧊 Cold trail—{name} is out. Less noise on comms, at least.",
    "⚙️ One less gear in the machine: {name} bailed. Adjust formation.",
    "🕯️ {name} stepped into the dark. Leave a light on if you’re feeling generous.",
    "📦 Inventory updated: {name} removed. More bunk space for the rest of us.",
    "📻 Last ping received from {name}. Archive the frequency and keep the drones hungry.",
    "🛰️ Satellite sweep shows {name} off-map. Leave a breadcrumb, not a memorial.",
    "🪙 Ledger updated: {name} owes us a story if they come back.",
    "🪫 Battery drained on {name}'s beacon. Consider them on walkabout until proven otherwise.",
    "🪐 {name} went interstellar—at least that's what Sparky claims."
]

REMINDER_TEMPLATE_STARTER = [
    {
        "template_name": "Teleport cities back to the hive",
        "body": "Reminder: teleport your cities back to the hive before the window closes.",
    },
    {
        "template_name": "Check ingame mail",
        "body": "Reminder: check your in-game mail and clear any pending reports.",
    },
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
        ("🌑 **DUSK APPROACHES:**", "One hour until the `{name}` protocol begins."),
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
        ("🚨 **YELLOW ALERT:**", "Warning: 30 minutes until `{name}` commencement."),
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
        ("📡 **NARROW BAND:**", "Switching to combat frequency for `{name}`. 15 minutes."),
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
        ("🌑 **TOTAL ECLIPSE:**", "3 minutes until `{name}` darkens the sector."),
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
        ("🌀 **VORTEX:**", "You're in the center of `{name}` now. Fight your way out!"),
    ],
}

INTEL_DATABASE = {
    "verify": "Proceed to your local verification terminal and complete your bio-scan.",
    "rules": "Protocol is simple: Respect the crew, follow the chain, and don't touch my drones.",
    "marcia": "I'm the hacker who keeps this place running while you're all sleeping.",
    "drones": "Sparky and his friends. They're smarter than you and they don't ask stupid questions.",
    "scavenge": "Use the `/scavenge` command. If you're lucky, my drones will find you something better than dirt.",
    "safety": "Stay inside the walls. Outside is for people who want to become zombie food.",
    "junk": "One person's trash is my next hardware upgrade. Keep it coming.",
    "zombies": "Rotting meat with a bad attitude. Aim for the head, or don't—I like watching you run.",
    "sector": "The last bit of dirt that isn't completely radioactive. Welcome home.",
    "credits": "The only language everyone in the waste still understands.",
    "uplink": "My connection to what's left of the orbital satellites. Don't trip on the wires.",
    "shadow": "The best place to hide when the 'Peacekeepers' come looking for their taxes.",
    "hardware": "If it has a circuit board, I can make it do my dishes. Or explode.",
    "wasteland": "A big, empty graveyard. Try not to add yourself to the collection.",
    "logic": "Something most survivors left behind in the Great Collapse.",
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
    ("🧲 Magnetized scrap perfect for jury-rigging door traps.", 24, "Scrap Magnets", "Uncommon"),
    ("🧠 You picked up a cognitive chip. Don't ask how.", 32, "Cognitive Chip", "Uncommon"),
    ("🛡️ A reinforced riot shield. Heavy, but safe.", 75, "Riot Shield", "Rare"),
    ("🔭 Military binoculars. See 'em before they see you.", 80, "Binoculars", "Rare"),
    ("📟 An encrypted data drive. I'm salivating over this.", 95, "Data Drive", "Rare"),
    ("💊 A pouch of 'Adrena-Z'. Use with caution.", 85, "Adrenal Shots", "Rare"),
    ("🛠️ A premium multi-tool. It's got a laser!", 90, "Laser Multi-tool", "Rare"),
    ("🛰️ A live uplink relay—we can re-aim a satellite with this.", 120, "Uplink Relay", "Rare"),
    ("🤖 A defunct drone core. We can upgrade Sparky.", 150, "Drone Core", "Epic"),
    ("🥽 Night vision goggles. The dark is now your friend.", 210, "NVGs", "Epic"),
    ("🔫 A customized rail-pistol. Still smells like ozone.", 250, "Rail Pistol", "Epic"),
    ("🧬 Found a vial of bio-enhancers. Risky, but potent.", 230, "Bio-Serum", "Epic"),
    ("🎯 Targeting HUD module. Plug it into your visor.", 260, "HUD Module", "Epic"),
    ("⚡ An intact fusion cell. Do not drop it.", 320, "Fusion Cell", "Legendary"),
    ("💎 Pre-war diamonds. Sparkly and hard to justify keeping.", 300, "Ghost Diamond", "Legendary"),
    ("🔮 A clairvoyant sensor shard. It hums when danger approaches.", 340, "Oracle Sensor", "Legendary"),
    ("🧭 A compass that never points north—only to survivors in need.", 360, "Seeker Compass", "Legendary"),
    ("🌌 A piece of 'Strange Matter'. It ignores physics.", 500, "Void Shard", "Artifact"),
    ("👑 A pre-war golden crown. Shiny, useless, and heavy.", 600, "Old World Crown", "Artifact"),
    ("📜 A hand-scribed star map for routes nobody remembers.", 650, "Star Map", "Artifact"),
    ("🗝️ A skeleton key that opens any analog lock.", 700, "Phantom Key", "Artifact"),
    ("🦾 Experimental servo arm—way too advanced for this century.", 900, "Titan Arm", "Mythic"),
    ("🧊 A cryo-core still colder than deep space.", 950, "Cryo Core", "Mythic"),
    ("🧿 A shimmering singularity bead. I'd rather not touch it.", 1000, "Singularity Bead", "Mythic"),
    ("🎖️ A relic badge from the first Solar War. Priceless.", 1100, "Solar War Badge", "Mythic"),
]

SCAVENGE_MISHAPS = [
    ("⚠️ Sandstorm spiked the sensors. I aborted before the drone ate grit.", 18),
    ("🚫 Raiders scrambled the frequency. I pulled {drone} out to avoid a scrap.", 16),
    ("🕳️ The route collapsed into a sinkhole. No loot beats no survivors.", 15),
    ("🪫 Power drain mid-flight. I rerouted the drone to base instead of risking a crash.", 12),
    ("🧨 Tripwire spotted. I wasn't donating any drones to someone's booby trap.", 17),
]

SCAVENGE_FIELD_REPORTS = [
    "Signal map updated — I marked safer corridors for the next run.",
    "Tagged a quiet alley with fresh coordinates. Looks promising.",
    "Logged a supply cache rumor from local chatter. Might be real.",
    "Drones sniffed a faint power signature; I'll triangulate it for next time.",
    "Marked hostile patrol routes so you don't walk into a crossfire.",
]

SCAVENGE_ZONES = [
    {"name": "Dustway Fringe", "tagline": "low heat, scattered scrap", "xp_bonus": 0, "rarity_bonus": 0.0, "mishap_bonus": 0.0},
    {"name": "Redline Blocks", "tagline": "raider traffic rising", "xp_bonus": 10, "rarity_bonus": 0.05, "mishap_bonus": 0.02},
    {"name": "Blackout Wards", "tagline": "signal dead zones", "xp_bonus": 20, "rarity_bonus": 0.08, "mishap_bonus": 0.04},
    {"name": "Dead Sector", "tagline": "biohazard grid, high-value scrap", "xp_bonus": 35, "rarity_bonus": 0.12, "mishap_bonus": 0.06},
    {"name": "Null Zone", "tagline": "no-return gravity well", "xp_bonus": 50, "rarity_bonus": 0.16, "mishap_bonus": 0.08},
]

SCAVENGE_CONTRACTS = [
    "Retrieve signal cores and tag any live relays.",
    "Sweep for med lockers; evac if raider chatter spikes.",
    "Trace battery heat signatures and pull them before sundown.",
    "Mark safe corridors for the next convoy wave.",
    "Locate the power relay with Sparky and lock its coordinates.",
    "Scout for drone parts and leave a ping beacon on the haul.",
    "Map a clean exit route in case the sky turns green.",
]

# Prestige title for collectors who secure every scavenged item once per sector
PRESTIGE_ROLE = "Vaultwalker"

MARCIA_STATUSES = [
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
    "Sorting Junk Databases.",
]
