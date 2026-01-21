# Patch Notes

## Added
- `/heroes` command with the new hero codex menu and Marcia hero profile (image, skills, scaling).
- Marcia Server automation (server ID `1454704176662843525`): auto-creates **about**, **rules**, and **events** channels; auto-links them in `/setup`.
- Setup dropdown flow so admins can configure one feature at a time.

## Changed
- Event reminders: channel announcement only at T-60 with `@everyone`; all other reminders are DM-only to opt-in members.
- Event removal is now handled inside `/event` with a dropdown + confirm flow.
- `/analytics` expanded with fun server stats (XP, CP, kills) and opened to all users.
- `/setup` now includes profile scan intake, feedback, and analytics channels; help text refreshed.
- About page rewritten as a sales pitch in Marcia’s voice (owner: `akrott`).
- Trading is now accessed via Fish-Link buttons and the trade button inside `/profile` and `/inventory`.
- Documentation reorganized under `docs/` for a cleaner root directory.

## Removed
- `/event_remove` (use `/event` → Remove Event).
- `/menu` (command center lives in `/commands`).
- `/manual` (guidance lives in `/commands` and `/setup` help).
- `/intel`.
- `/trade_item` (trading now via UI buttons).
- `/setup_profile_channel` (use `/setup` → Profile scan intake).
- `/profile_stats` (use `/profile`).
- Legacy mission and configuration text commands.

## Migrations / Breaking Changes
- New settings columns: `feedback_channel_id` and `analytics_channel_id`.
- Legacy text commands for missions/config were removed.
- Trading by direct item handoff (`/trade_item`) is no longer supported.

## Marcia Server Notes (ID: 1454704176662843525)
- Marcia will auto-create missing channels: `#about`, `#rules`, and `#events`.
- `#about`, `#rules`, and `#events` are enforced as read-only for members.
- `/setup` is auto-linked with the required channels; manual edits are still respected.
