# 📂 MARICA OS v3.0 | Helles Hub Tactical Bot

![Status](https://img.shields.io/badge/Status-Online-brightgreen)
![Library](https://img.shields.io/badge/Library-Discord.py-blue)
![License](https://img.shields.io/badge/License-Private-red)

> *"Freedom is expensive. Don't waste my time for free."* — **Marcia**

**Marcia** is a custom tactical bot built for the **Helles Hub Alliance**. She is a cunning hacker turned hub guardian who manages survivor ranks, wasteland scavenging, and the "Fish-Link" trade network.

### Bot Profile Blurb (≤400 chars)
Dark War Survival liaison. Marcia tracks UTC-2 ops, pings squads with lorey drone chatter, manages Fish-Link trades, endless leveling, mythic scavenging, intel, translations, reminders, and analytics across alliances. Built to keep survivors organized, supplied, and hyped.

---

## 🛠️ System Features

### 1. 🎣 Fish-Link Network
A dynamic, auto-anchored trading interface for the Arctic Ice Pit.
* **Matchmaking:** Marcia automatically DMs users when a duplicate fish matches their "Wanted" list.
* **UI Anchoring:** The trade menu automatically stays at the bottom of the channel, even during heavy chat.
* **Management:** Users can easily add extras, find needs, and clear their listings.

### 2. 🧟 Survivor Progression
* **Endless XP Tiers:** Survivors earn dynamic XP per message (60s cooldown) and unlock auto-created "Sector Rank" roles every 5 levels.
* **Prestige Collections:** Hourly scavenging now drops Common → Mythic loot; completing the catalog grants the prestige role **Vaultwalker**.
* **Loot Economy:** Trade scavenged items with `/trade_item` to help squadmates finish their sets.

### 3. 🚁 Commander Protocols
* **Event Management:** Set up missions with automated reminders at T-minus 60, 30, 15, 3, and 0 minutes.
* **Intel Database:** Quick-access information regarding hub rules, roles, and lore.
* **Translations:** React with a flag emoji to have Marcia decode messages into any language using Google Translate.

### 4. 🛰️ Event Creator (UTC-2)
* **Guided flow:** `/event` opens a DM interview where Marcia asks for the codename, tag (raid/siege/rally/briefing), instructions, and the exact game-time start (`YYYY-MM-DD HH:MM` in UTC-2). She can also capture a location/voice-channel link and which role to ping.
* **Broadcast cadence:** Reminders post at 60/30/15/3/0 minutes with lore-flavored drone signatures, keeping every guild on the Dark War Survival clock.
* **Member visibility:** `/events` lists the next scheduled operations for the current server, including tags, locations, and UTC-2 timestamps so squads can self-check the roster.
* **Admin cleanup:** `/event_remove <codename>` scrubs an operation instantly. Templates can be archived and reused from the same menu for repeat ops.

---

## 🚀 Installation & Setup

### 1. Requirements
* Python 3.8+
* `discord.py`
* `googletrans==4.0.0rc1`
* `python-dotenv`
* `aiosqlite`

### 2. Local Setup
1. Clone this repository to your private server.
2. Create a `.env` file in the root directory:
```env
TOKEN=your_discord_bot_token_here
```

*Data persistence:* All per-server links (event/chat/welcome/verify/rules/auto-role) and progression data live in `data/marcia_os.db` by default. The bot creates this folder automatically and reuses it across restarts and git pulls. Override with `MARCIA_DB_PATH` if your host prefers a custom data mount.

### 3. Troubleshooting
* **`ModuleNotFoundError: cogs`** — The bot forces its working directory to this repository root at startup. If you still see this error on hosts like Pterodactyl, double-check that `main.py` and the `cogs/` folder stay together and that your start command runs from this folder.
