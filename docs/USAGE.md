# Marica Command Primer

A quick guide for running Marica's most-used tools inside your server. Times use the in-game clock (UTC-2) unless noted.

## Event / Mission Control
- **Open console:** `/event`
- **Create an event:** choose **Custom Event** and answer the DM prompts.
  - **Ping who?** Type `everyone` to @everyone, mention a role, or type `none` for silent alerts. The ping choice appears on the preview card.
  - **Time format:** `YYYY-MM-DD HH:MM` in game time (UTC-2). Marica converts to UTC for scheduling.
- **Use saved templates:** choose **Use Template** when running `/event` and pick from the menu.
- **Remove an event:** `/event_remove <codename>`
- **See upcoming events:** `/events`
- **DM opt-ins:** At the 60-minute alert, members can react with 📬 to get later reminders by DM.

### Event safety notes
- Alerts only ping when a channel is configured in settings and not in the ignore list.
- `@everyone` pings use explicit allowed mentions so silent runs stay silent.

## Scavenge / Progression
- **Run a scavenge:** `/scavenge` (1-hour cooldown per user).
- **Momentum bonus:** running again within 90 minutes grants bonus XP.
- **Cooldown message:** Marica reports remaining time in minutes/seconds when you need to wait.
- **View profile:** `/profile [@member]` for level/xp, cooldown state, and stash summary.
- **Trade loot:** `/trade_item @member <quantity> <item name>` moves scavenged items between survivors.

## Leaderboard & Roles
- **Local leaderboard:** `/leaderboard` to see the top survivors in your server.
- **Global leaderboard:** `/global_leaderboard` compares across servers.
- Level-based tier roles are applied automatically when `Sector Rank` roles exist and permissions allow role edits.

## Channels & Automation
- Duel directives post at game-day reset when an event channel is configured.
- Ignored channels (set via the admin tools) will never receive event broadcasts or duel reminders.
