# Marcia Usage Guide

Hey, I’m **Marcia**. I keep your server coordinated, loot flowing, and schedules clean. Here’s the fast, direct guide for owners and admins.

> **Private-use notice:** This guide is for owner-operated instances only.
> **Clock standard:** Times use in-game time (UTC-2) unless noted.

## Owner launch checklist
1. **/setup** → link only the channels you need (start with **rules** + **events**).
2. **/setup_trade** in your trade channel to anchor the Fish-Link terminal.
3. **/refresh_commands** if slash commands ever desync.

## What I do (high level)
- **Operations control:** Full event scheduling with opt-in reminders and DM countdowns.
- **Scavenge loop:** Hourly loot + XP with streaks, hazard pay, and bonus caches.
- **Profiles & OCR:** I read profile screenshots, track stats, and power leaderboards.
- **Economy:** Fish-Link matches spares ↔ wants and pings players on hits.
- **Automation:** Duel directives, role tiering, and guardrails that respect muted channels.

## Core commands (owners/admins)
- **/setup** — configure channels and status.
- **/setup_trade** — place the Fish-Link UI in your trade channel.
- **/event** — mission console (create, reuse templates, list upcoming, remove).
- **/analytics** — usage + inventory stats.
- **/refresh_commands** — sync slash commands.

## Member commands (share with your crew)
- **/scavenge** — hourly run with streak bonuses and hazard pay.
- **/profile [@member]** — XP, stash, cooldown, and last scan.
- **/leaderboard** — XP + scan stats (local/global) + export.
- **/inventory** — items, sets, and bonuses.
- **/remind** — personal or channel reminders with templates.
- **/commands**, **/features**, **/heroes** — onboarding menus.

## Event & mission control
- **Launch:** `/event`
- **Create:** **New Event** → fill the quick form in-channel.
  - **Ping target:** `everyone`, a role mention, or `none`.
  - **Time format:** `YYYY-MM-DD HH:MM` (game time). I convert to UTC.
- **Reuse:** **Use Template** to schedule from a saved briefing.
- **Remove:** **Remove Event** to delete a scheduled op.
- **Upcoming:** **Upcoming Events** to list the queue.
- **Share:** **Share Upcoming** posts the queue in your events channel.

### Event flow (what I automate)
1. I post a preview card to the events channel.
2. **60-minute broadcast:** I ping `@everyone` and add **Join Event (🤝)**.
3. Members who react get **DM reminders** at **30/15/3 minutes** and kickoff.
4. Event completes and clears from the active list.

### Event safeguards
- I only ping in configured channels and never in ignored ones.
- `@everyone` pings use explicit allowed mentions to avoid accidental blasts.
- Natural @ mentions (e.g., “Dear @everyone”) read smoothly in context.

## Reminders system
- **/remind** opens the menu.
- **Send to channel:** choose channel + message + optional schedule.
- **Send to events channel:** quick post to your configured events channel.
- **Templates:**
  - **/remind add <name> <body>**
  - **Manage Templates** to delete old ones.
- **Scheduling:** leave time blank for **send now** or set `YYYY-MM-DD HH:MM`.

## Scavenge & progression
- **Cooldown:** 1 hour per user.
- **Momentum bonus:** run again within 90 minutes.
- **Streak chain:** run within 3 hours to stack up to 10.
- **Overclock:** every 3rd streak tier boosts XP + cache odds.
- **Milestones:** streak 5 and 10 grant XP spikes (even on failures).
- **Zone hazard pay:** your level raises XP and rare drop odds.
- **Cooldown UX:** I report exact remaining time.

## Profiles & OCR scanning
- **Run a scan:** `/scan` in a server, then upload the screenshot in DMs.
- **Auto-capture:** CP, kills, likes, VIP, level, server, alliance.
- **Review scans:** `/profile_review` (admin-only moderation queue).
- **Config health:** `/scan_status` (admin-only scanner config check).
- **Leaderboard stats:** `/leaderboard` (XP + profile metrics in one flow).
- **OCR stack:**
  - Base: **Tesseract + pytesseract**.
  - Full install: `requirements.txt` already includes OCR dependencies.
  - Low memory: use `requirements-lite.txt` (scanning disabled) and add OCR later with `requirements-ocr.txt` if needed.
  - Reference: [Low-memory installation](LOW_MEMORY_INSTALL.md).

## Leaderboards & roles
- **/leaderboard** lets you pick:
  - **Scope:** Sector (server) or Network (global)
  - **Metric:** XP, Combat Power, Kills, Likes, VIP Level, Profile Level
  - **Rows:** 10/25/50/100
  - **Export:** TSV to DM
- **Tier roles:** I apply **Uplink Tier** roles every 5 levels when permissions allow.

## Automation & guardrails
- **Event reminders:** 60-minute broadcast with @everyone, then DM-only opt-in.
- **Duel directives:** daily at midnight (game time) with priorities + SP slots.
- **Kill Event shields:** reminders Friday evening + Saturday.
- **Safety:** ignored channels never receive automations or pings.

---

If you want me lean and quiet, keep only the channels you use. If you want full ops control, wire up events and trades—and I’ll do the rest.

## Feature ideas
- For roadmap suggestions, see [FEATURE_IDEAS.md](FEATURE_IDEAS.md).
