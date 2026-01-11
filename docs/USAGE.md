# Marcia command primer

**Private-use notice:** This guide documents the owner-operated instance and is not intended for public distribution or third-party hosting.

Concise guidance for the commands operators use most. Times use the in-game clock (UTC-2) unless noted.

## Server owner quick guide
### 1) Core setup (admins/mods)
- **Run setup:** `/setup` and follow the in-channel wizard to link event, chat, welcome, rules, verify, and auto-role channels.
- **Audit links:** In `/setup`, tap **Sector Audit** to confirm permissions and channel links are green.
- **Profile scan intake:** `/setup_profile_channel #channel` to pick where profile screenshots are ingested.
- **Trading terminal:** `/setup_trade` in the trade channel to anchor the Fish-Link UI.

### 2) Essential commands (owners + admins)
- **Mission control:** `/event` opens the mission console, **Custom Event** schedules ops, **Use Template** reuses presets, and **Upcoming Events** lists the schedule.
- **Remove events:** `/event_remove <codename>` deletes an operation.
- **Health checks:** `/status` for latency and wiring; `/analytics` for per-server usage and inventory stats.
- **Command refresh:** `/refresh_commands` if slash commands go out of sync.

### 3) Member-facing commands (share with your crew)
- **Scavenge loop:** `/scavenge` for hourly loot/XP with zone hazard pay and streak bonuses.
- **Profiles:** `/profile` for XP + stash + scan summary; `/profile_stats` for scan details.
- **Leaderboards:** `/leaderboard` for unified XP + scan stats (local and global), with server numbers and export.
- **Reminders:** `/remind` for flexible reminders with templates, channel selection, and scheduling.
- **Inventory:** `/inventory` to review collected items and set bonuses.
- **Manual:** `/manual` and `/features` for onboarding.

### 4) Automation & passive features
- **Event reminders:** Scheduled alerts fire at 60/30/15/3/0 minutes with natural @ mentions, a clear Join Event reaction (🤝), and automatic DM reminders for participants. All messages follow Marcia's personality: clear, calm, firm, and encouraging.
- **Duel directives:** Daily duel instructions posted at midnight (game time) with detailed priorities, strategies, and SP slot rotations. Kill Event shield reminders send throughout Friday evening and Saturday.
- **XP leveling:** Message-based XP with cooldowns, auto-created **Uplink Tier** roles every 5 levels, and prestige unlocks when collections are complete.
- **Trading intelligence:** Fish-Link matches spares to wants and DMs players when matches appear.
- **Safety guardrails:** Channel ignore rules prevent reminders and automation from posting in muted rooms.

## Event & mission control
- **Launch the wizard:** `/event`
- **Create a new event:** select **Custom Event** and answer the DM prompts.
  - **Ping target:** type `everyone` to @everyone, mention a role, or type `none` for silent alerts (the selection is shown on the preview card).
  - **Time format:** `YYYY-MM-DD HH:MM` in game time (UTC-2). Marcia converts to UTC for scheduling.
- **Use a saved template:** choose **Use Template** when running `/event`.
- **Remove an event:** `/event_remove <codename>`
- **List upcoming events:** open `/event` and tap **Upcoming Events**
- **Join Event tracking:** at the 60-minute notification, members can react with 🤝 to join; reminders include the participant count.
- **Automatic DMs:** members who react with 🤝 receive DM reminders at 30/15/3 minutes and at kickoff.

### Event safeguards
- Alerts only ping when a channel is configured in settings and not in the ignore list.
- Natural @ mentions (e.g., "Dear @everyone", "Hello @everyone") blend into messages smoothly.
- `@everyone` pings use explicit allowed mentions to avoid accidental server-wide alerts.

### Event lifecycle (creation to completion)
1. **Create an event:** `/event` → **Custom Event** (or **Use Template**) captures codename, briefing, time, location, and ping target.
2. **Scheduled confirmation:** the event is logged and a preview card is posted to the events channel.
3. **60-minute broadcast:** the first notification always fires at the 60-minute mark and pings `@everyone`. The message includes a **Join Event (🤝)** reaction.
4. **Participation tracking:** members who react with 🤝 are marked as participants and counted in reminder updates.
5. **DM reminders:** participants receive direct messages at 30/15/3 minutes and at kickoff.
6. **Completion:** once the event starts, reminders finish and the event is cleared from the active list.

### Future enhancements (suggested)
- **Auto-summary reports:** post a brief after-action summary with participation counts and outcomes.
- **Role-based readiness:** allow optional role pings for specific squads while still keeping @everyone on the 60-minute broadcast.
- **Calendar exports:** generate an iCal feed for alliance planners.
- **Attendance streaks:** reward consistent participation with a badge or weekly shoutout.

## Reminders system
- **Launch reminder menu:** `/remind` opens the reminder control panel with multiple options.
- **Send to any channel:** Select **Send to Channel** and specify:
  - Target channel (#channel mention, channel ID, or channel name)
  - Reminder message text
  - Optional schedule time in game time (YYYY-MM-DD HH:MM) or leave blank to send immediately
- **Send to events channel:** Quick option to send to your configured events channel.
- **Use templates:** Select **From Template** to choose from saved reminder templates.
- **Manage templates:** Create with `/remind add <name> <body>` or delete old ones via **Manage Templates**.
- **Scheduling:** All reminder options support:
  - **Send now** — leave the time field blank
  - **Schedule for later** — enter date/time in game time format (UTC-2)

## Scavenge & progression
- **Run a scavenge:** `/scavenge` (1-hour cooldown per user).
- **Momentum bonus:** running again within 90 minutes grants bonus XP.
- **Streak chain:** running again within 3 hours keeps a streak and adds XP; streaks scale up to 10 runs.
- **Overclock bonus:** every 3rd streak tier adds extra XP and improves bonus cache odds.
- **Milestone XP:** hit streak 5 or 10 for an extra XP spike (even on failed runs).
- **Zone hazard pay:** your level determines the zone, boosting XP and rare drop odds.
- **Cooldown messaging:** Marcia reports remaining time in minutes/seconds when you need to wait.
- **View profile:** `/profile [@member]` for level/xp, cooldown state, and stash summary.
- **Trade loot:** `/trade_item @member <quantity> <item name>` moves scavenged items between survivors.

## Profile screenshot scanner
- **Set the intake channel:** `/setup_profile_channel #channel` scopes where Marcia watches for profile screenshots.
- **Auto-capture stats:** screenshots in that channel log CP, kills, server, and alliance to the uploader.
- **Extended More tab:** scans from the in-game **More** profile tab are supported via full-text OCR parsing.
- **Review scans:** `/profile_stats [@member]` shows the last parsed snapshot for you or another survivor with VIP, likes, and a self-view check.
- **Admin review:** `/profile_review` opens a management view to invalidate or delete scans when needed.
- **Compare stats:** `/leaderboard` opens a menu for XP plus CP/kills/likes/VIP from scanned profiles, with row counts (10/25/50/100) and an export-to-DM option for spreadsheet copy/paste.
- **OCR dependencies:** Tesseract+pytesseract cover basic scans. For higher accuracy, install the OCR extras bundled in `requirements.txt` (easyocr, opencv, numpy) unless memory is constrained; on tiny hosts you can skip them with `requirements-lite.txt` (scanning stays disabled).

### Quick testing routine (profile scanning)
1. **Dependencies:** Ensure `tesseract` is installed and Python deps are synced (`pip install -r requirements.txt`).
2. **Configure channel:** Run `/setup_profile_channel #channel` in a test server and confirm the setup embed.
3. **Happy path:** Post a known-good profile screenshot there. Expect a reply embed summarizing CP/kills/likes/VIP plus alliance/server and a self-view check.
4. **Profile view:** Run `/profile_stats` and confirm it matches the prior reply, including the `Last scanned` timestamp and verification status.
5. **Leaderboard:** Run `/leaderboard` and pick **Combat Power** (or **Kills** if populated). Verify ordering matches expectations and users without values are skipped.
6. **OCR-off fallback:** Temporarily uninstall or disable `tesseract` and post another screenshot. The bot should reply with `OCR unavailable` in the footer and still record the upload with your display name.
7. **Channel guard:** Post a screenshot in a different channel and confirm the bot ignores it (no DB write/response).
8. **Audit storage:** Inspect the SQLite DB (`data/marcia_os.db`, `profile_snapshots` table) to confirm `player_name`, metrics (including likes/VIP), `ownership_verified`, `last_image_url`, `local_image_path`, and `raw_ocr` are populated for the test guild/user. Profile uploads are cached under `shots/profiles/<guild_id>/` to avoid re-downloading images during rescans.

## Leaderboard & roles
- **Unified leaderboard:** `/leaderboard` opens a comprehensive menu with:
  - **Scope selector:** Toggle between Sector (server-only) and Network (global) rankings
  - **Metric selector:** Choose from XP, Combat Power, Kills, Likes, VIP Level, or Profile Level
  - **Row count:** Display 10, 25, 50, or 100 entries
  - **Export:** Tap **Export (Excel)** to receive a TSV file in your DMs
- **Global rankings:** Network leaderboards show server numbers next to each player for easy identification.
- **Tier roles:** Level-based tier roles are applied automatically when `Uplink Tier` roles exist and permissions allow role edits.

## Channels & automation
- Duel directives post at game-day reset when an event channel is configured.
- Ignored channels (set via the admin tools) will never receive event broadcasts or duel reminders.
