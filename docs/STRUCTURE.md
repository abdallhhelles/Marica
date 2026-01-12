# Marcia OS | Project Structure

Brief, single-source map of the repository so operators and contributors can find systems fast.

```
Marica/
├── cogs/                 # Feature modules (events, reminders, leveling, etc.)
├── utils/                # Shared utilities + static assets
├── config/               # Config templates (JSON)
├── data/                 # Runtime data (SQLite DB, logs, backups)
├── docs/                 # Documentation (usage, setup, structure)
├── ocr/                  # Profile scan OCR tooling + templates
├── legacy/               # Legacy migration artifacts
├── shots/                # Cached profile screenshots & temp OCR inputs
├── main.py               # Bot entry + boot sequence
└── database.py           # Database schema + queries
```

## Key modules
- **Events & operations:** `cogs/events.py`
- **Reminders:** `cogs/reminders.py`
- **Progression & leaderboards:** `cogs/leveling.py`
- **Profile scanning:** `cogs/profile_scanner.py` + `ocr/`
- **Utilities & about:** `cogs/utility.py`

## Data flow notes
- **Guild isolation:** Data is always scoped by guild ID in `database.py`.
- **OCR assets:** `ocr/boxes_ratios.json` defines template crop ratios.
- **Cached scans:** Stored under `shots/profiles/<guild_id>/`.
