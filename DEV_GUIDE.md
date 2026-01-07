# Marcia Developer Guide

This document covers how the bot is organized, how to run it locally, and how automation keeps the DevHub/test guilds and patch notes in sync. Use it as the single place to onboard new contributors.

## Quickstart
1. Create a virtual environment with Python 3.11+ and install dependencies: `pip install -r requirements.txt`.
2. Copy your Discord token into the environment (`export DISCORD_TOKEN=...`).
3. Run the bot locally with `python main.py`. The `DevServerManager` cog will self-start and maintain guild layout plus info boards.
4. Run a cheap sanity check before pushing: `python -m compileall .`.

## Repository layout
- `main.py`: entrypoint that loads all cogs.
- `cogs/`: feature cogs. Key ones:
  - `devhub.py`: server housekeeping, patch note broadcast, test guild layout.
  - `assets.py`: embeds, views, and reusable Discord UI components.
  - `database.py`: database helpers (e.g., `command_usage_totals`).
  - `time_utils.py`: shared datetime helpers for reminders and schedule formatting.
  - `patch_notes.py`: persistence + formatting helpers for release notes.
- `data/`: JSON backing data (patch notes queue, templates, configs).
- `TEST_SERVER_PLAYBOOK.md`: canonical channel/category layout for the testing guild.

## Patch notes workflow
- Pending notes live in `data/patch_notes.json` as a list of objects: `{ "note": "message", "author": "optional", "added_at": "ISO timestamp" }`.
- `PatchNotesStore` (in `patch_notes.py`) provides `add`, `format_bullets`, and `clear` helpers for cogs and scripts.
- `DevServerManager` reads queued notes on startup and posts them to `#marcia-patch-notes` with the current git hash tag. After a successful broadcast the queue is cleared automatically so the same notes do not repost.
- Add or edit notes before deploying to control what ships in the next announcement. Keep changes small and scoped to the current release.

## Test guild layout automation (ID: 1454704176662843525)
- Categories/channels from `TEST_SERVER_PLAYBOOK.md` are created if missing and moved into the right category when the playbook changes.
- Channels with onboarding text (`#readme`, `#usage-guide`, `#changelog`, etc.) are seeded once per marker so the bot will not spam duplicates. Each seeded message ends with a marker like ``seed:readme:v1`` so you can bump the marker to force a reseed.
- Update the strings in `cogs/devhub.py` under `TEST_LAYOUT` when the playbook changes; bump the related marker to reseed.

## Info panel refresh
- The `#marcia-info` board refreshes every 30 minutes with live server/member/channel counts and command usage pulled from `command_usage_totals`.
- If the embed looks stale, restart the bot or inspect the `info_updater` task in `DevServerManager`.

## Coding conventions
- Avoid hard-coded patch notes inside cogs; rely on `PatchNotesStore` so deployments are repeatable.
- Keep new helpers in dedicated modules (e.g., new persistence helpers beside `patch_notes.py`) to keep cog startup simple.
- Prefer descriptive channel topics—`_get_or_create_channel` will align topics automatically when they drift.
- Do not wrap imports in try/except; fail fast during startup to catch missing dependencies.

## Deployment checklist
1. Update `data/patch_notes.json` with the release bullets and authors.
2. Run `python -m compileall .` locally.
3. Commit changes and deploy the updated files to the host.
4. Restart the bot; DevHub automation will align channels, seed onboarding text if needed, refresh the info panel, and broadcast patch notes.

## Troubleshooting
- **Missing permissions**: The cog logs warnings if it cannot move/create/pin channels. Confirm the bot role has Manage Channels/Messages and sits above target roles.
- **Patch notes not posting**: Ensure `data/patch_notes.json` is valid JSON and contains at least one `note`. Check that the `#marcia-patch-notes` channel exists or let `_ensure_channels` create it.
- **Info panel blank**: Verify the database connection used by `command_usage_totals` and review recent logs for traceback details.
