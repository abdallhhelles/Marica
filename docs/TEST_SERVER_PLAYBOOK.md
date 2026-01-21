# Marcia Server Playbook (Server ID: 1454704176662843525)

This playbook defines the **minimum** channel layout and auto-setup behavior for the Marcia Server. The bot keeps the footprint small, creates what is missing, and links the essentials in `/setup`.

## ✅ Auto-created channels (Marcia Server only)
Marcia checks for these channels and creates them if missing:

1. **#about**
   - Created if missing.
   - Marcia posts the short onboarding brief.
   - **Only Marcia can post.**
2. **#rules**
   - Created if missing.
   - Marcia posts the rules.
   - **Only Marcia can post.**
3. **#events**
   - Created if missing.
   - **Only Marcia can post.**
   - `/event` announcements land here.

## ✅ Minimal channel layout (bare minimum)
Only the essentials are required for clean navigation:

- `#about`
- `#rules`
- `#events`

Anything else (chat, feedback, analytics) is optional and should be added only if the community needs it.

## ✅ Auto-link behavior
For this server only, Marcia will:

- Auto-link **rules** and **events** in `/setup`.
- Preserve any admin edits you make later via `/setup`.

## ✅ Permission expectations
Marcia enforces read-only behavior for:

- `#about`
- `#rules`
- `#events`

She will set **@everyone → send_messages: false** and allow only her own role to post.

## ✅ Event reminders (Marcia Server rules)
- **T-60 minutes:** channel announcement in `#events` with `@everyone`.
- **All other reminders:** DM-only to users who reacted with 🤝.

## ✅ Quick verification checklist
- `#about`, `#rules`, `#events` exist.
- `#about`, `#rules`, `#events` are read-only to members.
- `/setup` shows the rules and events channels linked.

Keep it tight. This server is the showcase for clean ops and minimal clutter.
