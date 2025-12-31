# Marica Test Server Playbook (Server ID: 1454704176662843525)

This playbook organizes the Marica testing hub and supplies in-character copy you can paste directly into new channels. Use it to recreate the community if the guild is wiped or when onboarding new testers.

## Core Categories & Channels
- **[Category] Control Tower**
  - `#readme` — Single source of truth for rules, verification, and quick start.
  - `#changelog` — Ship notes for every deploy. Keep only Marica/staff posts.
  - `#announcements` — Major milestones, maintenance notices, and beta calls.
  - `#mod-log` — Private; pipe moderation actions and transcripts here.
  - `#about` — Overview of Marica OS, its purpose, and what testers should expect.
- **[Category] Operations (UTC-2)**
  - `#events` — Quiet channel for `/event` reminders (60/30/15/3/0) and schedules.
  - `#ops-planning` — Player chatter for raid/defense prep.
  - `#voice-pings` — Role mention targets when ops go live.
- **[Category] Trading**
  - `#fish-link` — Drop the Fish-Link terminal here with `/setup_trade`.
  - `#loot-market` — Barter scavenged items; pair with `/trade_item` use.
- **[Category] Progression**
  - `#level-up` — Auto messages for rank milestones; keep it low-noise.
  - `#vaultwalker-wall` — Hall of fame for catalog completions.
- **[Category] Labs & QA**
  - `#bug-reports` — Repro steps, screenshots, and expected vs actual.
  - `#feature-requests` — Suggestions for the next sprint.
  - `#load-tests` — Stress test commands, cooldowns, and concurrency.
  - `#localization` — Collect translation edge cases and flag reaction tests.
- **[Category] General**
  - `#welcome` — Auto welcomes + verification reminders.
  - `#lounge` — Free chat for testers.
  - `#showcase` — Screenshots and clips of Marica in action.
  - `#intel` — `/intel` answers, FAQs, guides.
  - `#usage-guide` — Step-by-step setup and usage flow for new testers.

## Roles
- `Control` — Admins; ensure Marica sits above this for permission checks.
- `Ops Crew` — Pings for live operations; use in `/event` role prompt.
- `Traders` — Opt-in for Fish-Link updates.
- `QA` — Testers allowed to run `/setup audit` and report findings.
- `Vaultwalkers` — Awarded manually when someone finishes the scavenging catalog.

## Starter Channel Copy (Marica’s Voice)

### #readme (pin this)
> **Marica:** "Welcome to the test grid. I don’t babysit — I calibrate."
>
> **Setup:** Run `/setup` to link `events`, `welcome`, `verify`, `rules`, and auto-role. Data is siloed per guild in `data/marcia_os.db`. Use `/setup audit` after perms change.
> 
> **Clock:** Ops run on UTC-2. Use `/event` to schedule raids/sieges/briefings. Reminders fire at 60/30/15/3/0 with drone tags.
> 
> **Trading:** In `#fish-link`, hit the buttons: Add Spare, Find Fish, My Listings, Who Has My Wanted?. Matches DM donors automatically.
> 
> **Progression:** Chat for XP (60s cooldown). `/scavenge` hourly for Common → Mythic loot. `/trade_item` to barter. Finish the catalog to earn **Vaultwalker**.
> 
> **Tools:** `/commands`, `/features`, `/manual`, `/intel <topic>`, `/poll`, flag reactions for translations.
>
> **Conduct:** No spam in events/level-up channels. Keep repro steps clear in QA threads. Freedom is expensive — don’t waste my time for free.

### #about
> **Marica:** "I’m the ops spine for your raids, trades, and ranks."
>
> **What I do:**
> - Automate ops reminders on UTC-2 with `/event`.
> - Anchor Fish-Link trading with `/setup_trade` and smart donor matching.
> - Track XP/ranks and grant roles per guild without cross-contamination.
> - Answer intel quickly: `/intel <topic>`, `/manual`, `/features`.
>
> **How to help:**
> - Keep channel links current (`/setup audit`).
> - Report broken flows in `#bug-reports` with repro steps.
> - Stress the buttons in `#load-tests` before major pushes.

### #usage-guide
> **Goal:** Get Marica online in under 5 minutes.
>
> **1) Permissions:** Invite with message content + Manage Roles. Place Marica’s role above auto-roles.
>
> **2) Core setup:** Run `/setup` and map: `events`, `welcome`, `verify`, `rules`, auto-role. Confirm in `/setup audit`.
>
> **3) Trading:** In `#fish-link`, run `/setup_trade`. Pin the terminal. Use **Add Spare**, **Find Fish**, **My Listings**, **Who Has My Wanted?**
>
> **4) Events:** Schedule with `/event` (UTC-2). Reminders: 60/30/15/3/0. Keep channel read-only.
>
> **5) Progression:** Encourage chat for XP. Use `/scavenge` hourly. Track prestige and assign **Vaultwalker** for catalog completions.
>
> **6) Intel & support:** Use `/commands`, `/features`, `/manual`, `/intel <topic>`. If something breaks, post in `#bug-reports` with timestamp + screenshot.

### #changelog (template)
> **Build vX.Y.Z —** summarize fixes/features. Link PR if public.
> - Ops: e.g., "Improved UTC-2 reminder formatting; 60-minute post now includes location."
> - Trading: e.g., "Fish-Link anchor recovery after restarts."
> - Progression: e.g., "Adjusted XP curve; new rank color band."
> - QA: e.g., "Telemetry now shows command counts per guild."

### #announcements
> **Marica:** "Broadcasting to all sectors. New firmware pushed — check `/features` then go break it."

### #events
> Keep this channel read-only for everyone except Marica. All `/event` reminders land here with drone call-signs. Pin the current week’s schedule.

### #fish-link
> Run `/setup_trade` once. Pin the terminal. Remind traders: "Add Spare" for extras, "Find Fish" for wants, "My Listings" to clean, "Who Has My Wanted?" to check matches.

### #bug-reports
> **Format:** What happened, expected behavior, exact command, screenshot/log, timestamp (UTC-2). Include message link if translation/reaction related.

### #feature-requests
> **Marica:** "Pitch the upgrade. If it saves time or ammo, I’ll consider it."
> - Use bullets, not essays. Include intended user flow and channel targets.

### #load-tests
> Queue stress runs: high-frequency `/scavenge`, rapid Fish-Link button presses, and concurrent `/event` creation. Log results and rate limits.

### #localization
> Collect emoji flags that fail to trigger translations, edge-case languages, or layout issues. Include source message links.

### #welcome
> Configure `/setup` to point here. Marica’s joins remind newcomers to read `#readme`, verify, and grab `Traders`/`Ops Crew` opt-in roles.

### #intel
> Seed with `/intel rules`, `/intel events`, `/intel trading`, and `/intel ranks` to keep testers aligned.

## Operational Checklist
- Invite Marica with message content + manage role permissions enabled.
- Run `/setup` to link channels and auto-role; verify stored paths in `data/marcia_os.db`.
- Place Marica’s role above `Control` and auto-roles so she can assign ranks.
- After restarts, confirm Fish-Link re-anchors in `#fish-link` and that `/status` shows green.
- Use `/analytics` to review command volume and drop-off. Share screenshots in `#changelog`.

## Testing Ideas
- **Event loop:** Create overlapping ops, cancel via `/event_remove`, confirm reminder cadence.
- **Trading:** Add conflicting listings; verify donors receive DMs and buttons stay anchored after chatter.
- **Progression:** Grind XP to trigger rank role creation; prestige someone to `Vaultwalker` and post in `#vaultwalker-wall`.
- **Translations:** React with multiple flags and ensure correct language output/limits.
- **Resilience:** Restart the bot; confirm it restores Fish-Link, events, and channel links without duplication.

Stay sharp. This hub should feel like a live ops room, not a waiting room.
