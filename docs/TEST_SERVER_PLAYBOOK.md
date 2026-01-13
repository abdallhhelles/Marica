# Marcia Server Playbook (Server ID: 1454704176662843525)

This playbook defines the **minimal** channel layout and auto-setup behavior for the Marcia Server. The bot auto-creates missing channels, applies permissions, and auto-links them in `/setup`.

## ✅ Auto-created channels (Marcia Server only)
Marcia checks for these channels and creates them if missing:

1. **#rules**
   - Created if missing.
   - Marcia posts the rules.
   - **Only Marcia can post.**
2. **#events**
   - Created if missing.
   - **Only Marcia can post.**
   - `/event` announcements land here.
3. **#feedback-suggestions**
   - Created if missing.
   - Community feedback + ideas live here.
4. **#global-analytics**
   - Created if missing.
   - **Only Marcia can post.**
   - Updates **hourly** with fun stats and bot activity.

## ✅ Minimal channel layout (keep it lean)
Only the essential setup channels + feedback + global analytics are required:

- `#rules`
- `#events`
- `#feedback-suggestions`
- `#global-analytics`

If you add optional channels (chat, welcome, verify, etc.), use `/setup` to link them manually. The Marcia Server should stay small by default.

## ✅ Auto-link behavior
For this server only, Marcia will:

- Auto-link **rules** and **events** channels in `/setup`.
- Auto-link **feedback** and **global analytics** channels in `/setup`.
- Preserve any admin edits you make later via `/setup`.

## ✅ Permission expectations
Marcia enforces read-only behavior for:

- `#rules`
- `#events`
- `#global-analytics`

She will set **@everyone → send_messages: false** and allow only her own role to post.

## ✅ Event reminders (Marcia Server rules)
- **T-60 minutes:** channel announcement in `#events` with `@everyone`.
- **All other reminders:** DM only to users who reacted with 🤝.

## ✅ Global analytics channel
- Updates every hour.
- Includes fun stats + what the bot is tracking.
- Designed to be read-only and low-noise.

## ✅ Quick verification checklist
- `#rules`, `#events`, `#feedback-suggestions`, `#global-analytics` exist.
- `#rules`, `#events`, `#global-analytics` are read-only to members.
- `/setup` shows those channels linked.
- `#global-analytics` updates hourly.

Keep it tight. This server is the showcase for clean ops and minimal clutter.
