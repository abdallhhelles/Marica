# Feature Ideas & Product Backlog

A practical backlog of next-step ideas based on the current command surface (`/event`, `/scan`, `/profile`, `/leaderboard`, `/setup_trade`, etc.).

## High-impact ideas (short term)

1. **Event attendance scorecards**
   - Track who reacted to Join Event and who actually checked in.
   - Add per-user attendance percentages and streaks.
   - Surface top attendees in `/leaderboard` as an optional metric.

2. **Trade reputation + cooldown controls**
   - Add optional trust score (completed trades vs cancels/ghosting).
   - Add admin-configurable cooldowns to reduce spam relisting.
   - Show reputation badge in trade UI.

3. **Scan quality coach in DMs**
   - Before OCR processing, run quick checks for blur, crop, and low contrast.
   - Return instant guidance ("retake with full header visible") instead of silent poor extraction.

4. **Reminder templates per role/team**
   - Let admins bind reminder templates to role presets (Raid, Defense, Duel).
   - One click in `/remind` to choose template + role target.

## Mid-term ideas

5. **Ops calendar export (ICS)**
   - Export upcoming events as `.ics` files for Google/Apple/Outlook calendars.
   - Auto-refresh file link in the events channel.

6. **Weekly alliance digest**
   - Scheduled summary with: XP movers, new scans, event participation, and top traders.
   - Post to analytics channel and optionally DM commanders.

7. **Profile change tracking**
   - Compare latest scan against previous scan.
   - Show deltas in `/profile` (e.g., CP +25k, Kills +310).

8. **Role-based onboarding presets**
   - `/setup` preset buttons for "small server", "competitive alliance", "event-heavy".
   - Auto-fill recommended channels/flags.

## Long-term ideas

9. **Cross-alliance federation mode (opt-in)**
   - Shared global rankings or trade discovery across trusted guild clusters.
   - Guild owners explicitly opt in with visibility controls.

10. **AI mission brief generator**
   - Draft event briefings from short inputs (goal, time, constraints).
   - Keep approval human-first: admin reviews before posting.

11. **A/B testing for reminder timing**
   - Compare reminder cadences by completion/attendance outcomes.
   - Recommend best schedule per guild.

12. **Mobile-first command UX pass**
   - Simplify embeds and button density for phone users.
   - Add compact mode toggles for heavy workflows.

## Nice-to-have polish

- Per-command permissions audit dashboard.
- "Why was I pinged?" explainers on reminder messages.
- Built-in backup/restore for templates and settings.
- Localized command copy packs (EN-first, extendable).

---

If you want, this list can be converted into a milestone-based roadmap (`Now / Next / Later`) and mapped to estimated effort.
