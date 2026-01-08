# Marcia OS Showcase

> "Freedom is expensive. Don't waste my time for free." — Marcia

A lore-driven, UTC-2–anchored command AI for **Dark War Survival** alliances. Marcia speaks in-character, runs your ops clock, manages trading, and keeps survivor data isolated per server.

## Lore Snapshot
- Former underground hacker who now guards scattered hubs with a drone fleet (Sparky, Vulture-7, Ghost-Link, and more).
- Protects refugees while hiding empathy behind sarcasm; rewards self-sufficient crews and mocks freeloaders.
- Drones patrol every linked sector; her voice and quotes keep broadcasts human, not robotic.
- Tracks scavenging streaks as war diaries and pushes crews to earn freedom with discipline, not shortcuts.

## Core Systems
### Owner Control & Analytics
- Private control panel (owner-only) shows XP leaders, global stats, rare drops, economy health, and per-server uptime/link status.
- Command usage telemetry keeps a running count of message + slash executions, surfaced in the server health view.
- Broadcast helpers let the owner DM guild leaders or target a channel with in-character announcements.

### Operations (UTC-2 clock)
- `/event` DM wizard asks for codename, instructions, UTC-2 start, optional location, and role ping.
- Reminder cadence: 60/30/15/3/0 minutes with Marcia’s quips, drone call-signs, and RSVP rollups (✅/❔/❌) baked into reminders.
- Members use `/event` to see upcoming ops; admins clean with `/event_remove`.

### Trading: Fish-Link
- Persistent button UI (`Add Spare`, `Find Fish`, `My Listings`, `Who Has My Wanted?`).
- Per-server isolation; re-anchors on restart without spamming the channel.
- Automatic donor DMs when matches appear.

### Progression & Scavenging
- Endless XP ladder with scaling milestones and auto-created Uplink Tier roles (colors and names adjust per tier).
- Hourly `/scavenge` for Common → Mythic loot, zone hazard pay, streak + overclock bonuses, milestone XP, and ultra-rare catalog items.
- Inventory tracking per guild; prestige **Vaultwalker** role when a member completes the loot catalog.
- `/leaderboard` shows XP plus CP/kills from profile scans with 10/25/50/100 row controls and a DM export.
- `/trade_item @user <item> <qty>` lets survivors barter scavenged goods.
- Profile scanner: `/setup_profile_channel`, `/scan_profile`, `/profile_stats`; caches uploads to avoid re-downloading screenshots.

### Welcomes, Departures, & Automation
- `/setup` (admins/mods) links event/chat/welcome/rules/verify channels and auto-role.
- Joins: chat-style welcomes with rule/verify reminders using Marcia’s voice.
- Leaves: 15 in-character farewell variants.
- Status helpers: `/status`, `/setup` (Sector Audit), `/analytics` for quick health and data snapshots.

## Command Directory (quick view)
- **Admin:** `/setup`, `/setup_trade`, `/refresh_commands`, `/event`, `/event_remove`, `/analytics`, `/status`
- **Members:** `/event` (upcoming ops), `/profile`, `/profile_stats`, `/leaderboard`, `/inventory`, `/scavenge`, `/manual`, `/features`, `/commands`
- **Profile scans:** `/setup_profile_channel`, `/scan_profile`; `/leaderboard` export sends TSV via DM
- **Utility:** `/intel <topic>`, `/poll`, `/remindme`, `/clear`, translation via flag reactions
- **Trading:** Fish-Link buttons + `/trade_item`

## How to Deploy
1. Invite the bot with message content/role perms enabled; place it above auto-role targets.
2. In each server, run `/setup` and follow the guided setup in-channel to link channels and auto-role (saved in SQLite for restart persistence).
3. Drop a trade terminal with `/setup_trade` and pin the message if desired.
4. Create operations via `/event`; let Marcia handle UTC-2 reminders and roster pings.
5. Encourage members to `/scavenge`, `/trade_item`, and climb ranks for prestige.

## Data & Safety
- All settings, events, leveling, telemetry, and trading data are stored per guild in `data/marcia_os.db`; no cross-server leakage.
- Allowed mentions are scoped to avoid unwanted @everyone pings; role pings are opt-in during event creation.
- Uses WAL-mode SQLite and startup migrations so data survives restarts, updates, and re-deploys.

## Tips for Server Admins
- Keep an events channel with minimal chatter to highlight reminders.
- Rotate Fish-Link to an appropriate channel; it auto-reanchors on reboot.
- Use `/setup` → **Sector Audit** after changing channel permissions to ensure Marcia can send messages.
- If voice pings are desired for ops, pick a role dedicated to live comms and select it during `/event`.

## Marcia’s Voice
Her replies and reminders pull from a large quote bank in `assets.py`, blending dry humor with tactical urgency. Every broadcast should feel like a human ally watching the grid, not a sterile scheduler.
