# Marica command primer

Concise guidance for the commands operators use most. Times use the in-game clock (UTC-2) unless noted.

## Event & mission control
- **Launch the wizard:** `/event`
- **Create a new event:** select **Custom Event** and answer the DM prompts.
  - **Ping target:** type `everyone` to @everyone, mention a role, or type `none` for silent alerts (the selection is shown on the preview card).
  - **Time format:** `YYYY-MM-DD HH:MM` in game time (UTC-2). Marica converts to UTC for scheduling.
- **Use a saved template:** choose **Use Template** when running `/event`.
- **Remove an event:** `/event_remove <codename>`
- **List upcoming events:** `/events`
- **DM opt-ins:** at the 60-minute alert, members can react with 📬 to receive later reminders by DM.

### Event safeguards
- Alerts only ping when a channel is configured in settings and not in the ignore list.
- `@everyone` pings use explicit allowed mentions to avoid accidental server-wide alerts.

## Scavenge & progression
- **Run a scavenge:** `/scavenge` (1-hour cooldown per user).
- **Momentum bonus:** running again within 90 minutes grants bonus XP.
- **Cooldown messaging:** Marica reports remaining time in minutes/seconds when you need to wait.
- **View profile:** `/profile [@member]` for level/xp, cooldown state, and stash summary.
- **Trade loot:** `/trade_item @member <quantity> <item name>` moves scavenged items between survivors.

## Profile screenshot scanner
- **Set the intake channel:** `/setup_profile_channel #channel` scopes where Marica watches for profile screenshots.
- **Auto-capture stats:** screenshots in that channel log CP, kills, server, and alliance to the uploader.
- **Review scans:** `/profile_stats [@member]` shows the last parsed snapshot for you or another survivor with VIP, likes, and a self-view check.
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
- **Leaderboards:** `/leaderboard` opens a selector for local XP, global XP, and scanned profile stats. You can choose 10/25/50/100 rows and tap **Export (Excel)** to receive a TSV in your DMs. `/global_leaderboard` is kept for quick access to network XP.
- Level-based tier roles are applied automatically when `Sector Rank` roles exist and permissions allow role edits.

## Channels & automation
- Duel directives post at game-day reset when an event channel is configured.
- Ignored channels (set via the admin tools) will never receive event broadcasts or duel reminders.
