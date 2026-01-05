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

## Profile Screenshot Scanner
- **Set the intake channel:** `/setup_profile_channel #channel` tells Marcia where to watch for in-game profile screenshots.
- **Auto-capture stats:** dropping a profile screenshot in that channel logs CP, kills, likes, VIP, level, server, and alliance to the uploader.
- **Review your scan:** `/profile_stats [@member]` shows the last parsed snapshot for you or another survivor.
- **Compare stats:** `/profile_leaderboard <stat>` lists the top CP/kills/likes/VIP/level from scanned profiles.
- **OCR dependencies:** Tesseract+pytesseract are enough for basic scans. For higher accuracy, install `requirements-ocr.txt` (easyocr, opencv, numpy), but skip them on low-memory hosts.

### Quick testing routine
1. **Dependencies:** Ensure `tesseract` is installed on the host and Python dependencies are synced (`pip install -r requirements.txt`).
2. **Configure channel:** Run `/setup_profile_channel #channel` in a test server and note the confirmation embed.
3. **Happy path:** Post a known-good profile screenshot in the configured channel. Expect a reply embed summarizing parsed CP/kills/likes/vip/level/alliance/server.
4. **Profile view:** Run `/profile_stats` for yourself and confirm it matches the prior reply and shows `Last scanned` timestamp.
5. **Leaderboard:** Run `/profile_leaderboard cp` (and other stats if populated). Verify ordering matches expected values and that users without values are skipped.
6. **OCR-off fallback:** Temporarily uninstall or disable `tesseract` and post another screenshot. Confirm the bot replies with `OCR unavailable` in the footer and still records the upload with your display name.
7. **Channel guard:** Post a screenshot in a different channel and confirm the bot ignores it (no DB write/response).
8. **Audit storage:** Inspect the SQLite DB (`data/marcia_os.db`, `profile_snapshots` table) to confirm `player_name`, metrics, `last_image_url`, and `raw_ocr` are populated for the test guild/user.

## Leaderboard & Roles
- **Local leaderboard:** `/leaderboard` to see the top survivors in your server.
- **Global leaderboard:** `/global_leaderboard` compares across servers.
- Level-based tier roles are applied automatically when `Sector Rank` roles exist and permissions allow role edits.

## Channels & Automation
- Duel directives post at game-day reset when an event channel is configured.
- Ignored channels (set via the admin tools) will never receive event broadcasts or duel reminders.
