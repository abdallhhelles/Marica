# Marcia Server Playbook (Server ID: 1454704176662843525)

This playbook defines the **minimal** channel layout and auto-setup behavior for the Marcia Server. The bot auto-creates missing channels, applies permissions, and auto-links them in `/setup`.

## ✅ Auto-created channels (Marcia Server only)
Marcia checks for these channels and creates them if missing:

1. **#about**
   - Created if missing.
   - Marcia posts the purpose + onboarding brief.
   - **Only Marcia can post.**
2. **#rules**
   - Created if missing.
   - Marcia posts the rules.
   - **Only Marcia can post.**
3. **#commands**
   - Created if missing.
   - Marcia posts the command quick-start.
   - **Only Marcia can post.**
4. **#general**
   - Created if missing.
   - Welcome + community chat.
5. **#bugs**
   - Created if missing.
   - Bug reports and scan issues.
6. **#suggestions**
   - Created if missing.
   - Community feedback + ideas live here.
7. **#analytics**
   - Created if missing.
   - **Only Marcia can post.**
   - Updates **hourly** with fun stats and bot activity.
8. **#events**
   - Created if missing.
   - **Only Marcia can post.**
   - `/event` announcements land here.

## ✅ Minimal channel layout (keep it lean)
Only the essential channels are required:

- `#about`
- `#rules`
- `#commands`
- `#general`
- `#bugs`
- `#suggestions`
- `#analytics`
- `#events`

## ✅ Auto-link behavior
For this server only, Marcia will:

- Auto-link **rules**, **events**, **general** (chat + welcome), **suggestions**, and **analytics** in `/setup`.
- Preserve any admin edits you make later via `/setup`.

## ✅ Permission expectations
Marcia enforces read-only behavior for:

- `#about`
- `#rules`
- `#commands`
- `#analytics`
- `#events`

She will set **@everyone → send_messages: false** and allow only her own role to post.

## ✅ Event reminders (Marcia Server rules)
- **T-60 minutes:** channel announcement in `#events` with `@everyone`.
- **All other reminders:** DM only to users who reacted with 🤝.

## ✅ Analytics channel
- Updates every hour.
- Includes fun stats + what the bot is tracking.
- Designed to be read-only and low-noise.

## ✅ Quick verification checklist
- `#about`, `#rules`, `#commands`, `#general`, `#bugs`, `#suggestions`, `#analytics`, `#events` exist.
- `#about`, `#rules`, `#commands`, `#analytics`, `#events` are read-only to members.
- `/setup` shows those channels linked.
- `#analytics` updates hourly.

Keep it tight. This server is the showcase for clean ops and minimal clutter.
