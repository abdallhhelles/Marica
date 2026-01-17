# 📂 MARCIA OS v3.0 | Helles Hub Tactical Bot

![Status](https://img.shields.io/badge/Status-Online-brightgreen)
![Library](https://img.shields.io/badge/Library-Discord.py-blue)
![License](https://img.shields.io/badge/License-Private-red)

> *"Freedom is expensive. Don't waste my time for free."* — **Marcia**

**Private-use notice:** Marcia is a personal, owner-operated bot. It is **not** intended for public installation, third-party hosting, or redistribution.

Marcia is the tactical operations bot for the **Helles Hub Alliance**. She orchestrates ops, translations, trading, and player progression with the reliability expected from production-grade services. For hands-on usage, see [USAGE.md](USAGE.md).

**Quick feature overview (automated + commands):**
* **Automated:** XP leveling on message activity, scheduled event reminders, scavenging contracts with streak tracking, auto-matching trade requests, and profile scan snapshot caching.
* **Command-driven:** `/event` scheduling + upcoming ops, Join Event reactions with DM reminders, `/remind` for flexible reminders with templates, `/leaderboard` unified views with global rankings and server numbers, `/profile` snapshots, `/profile_review` admin scan controls, `/heroes` codex lookups, and admin setup commands like `/setup` and `/setup_trade`.

## Table of contents
1. [System capabilities](#system-capabilities)
2. [Project structure](#project-structure)
3. [Deployment overview](#deployment-overview)
4. [Hosting patterns](#hosting-patterns)
5. [Local configuration](#local-configuration)
6. [Operations & troubleshooting](#operations--troubleshooting)

---

## Project structure

The codebase is organized for maintainability and clarity:

```
Marica/
├── cogs/              # Discord command modules (features)
├── utils/             # Shared utilities and helpers
│   ├── assets.py      # Static data (quotes, lore, constants)
│   ├── time_utils.py  # Game timezone helpers (UTC-2)
│   ├── bug_logging.py # Error logging and Discord notifications
│   └── patch_notes.py # Release notes persistence
├── config/            # Configuration templates (JSON)
├── data/              # Runtime data (database, logs, backups)
├── docs/              # Documentation files
├── ocr/               # Profile scanning OCR system
├── legacy/            # Legacy migration data
├── main.py            # Bot entry point
└── database.py        # Database operations and schema
```

**Key directories:**
* **cogs/**: Each file is a feature module (trading, leveling, events, etc.)
* **utils/**: Shared code used across multiple cogs
* **data/**: Auto-created at runtime for database and logs
* **config/**: Static configuration templates

For the full map and module list, see [STRUCTURE.md](STRUCTURE.md).

---

## System capabilities

### Fish-Link Network (trading)
* **Auto-matchmaking:** DMs users when a duplicate fish meets another player’s “Wanted” list.
* **Anchored UI:** Keeps the trade menu at the channel bottom, even under heavy chat.
* **Inventory tools:** Add extras, discover needs, and clear listings quickly.

### Survivor progression & scavenging
* **Endless XP tiers:** Message-based XP (60s cooldown) that auto-creates “Uplink Tier” roles every 5 levels.
* **Prestige collections:** Hourly scavenging runs feature zone hazard pay, streak + overclock bonuses, milestone XP, and Common → Mythic loot; completing the set grants **Vaultwalker**.
* **Loot economy:** Fish-Link trading keeps swap requests centralized and matchable.

### Commander protocols (events)
* **Guided creation:** `/event` runs a DM wizard that captures codename, tag, instructions, start time (`YYYY-MM-DD HH:MM` in UTC-2), optional location/voice link, and ping target.
* **Cadenced reminders:** Posts a channel ping at T-minus 60 minutes (always `@everyone`). All other reminders are DM-only for opt-in members.
* **Join Event tracking:** Participants react with 🤝 to join; DM reminders fire for those who opted in by reacting.
* **Visibility:** `/event` includes an upcoming ops view for the current server with UTC-2 timestamps.
* **Cleanup & reuse:** `/event` includes a Remove Event flow; templates can be archived and reused.

### Profile scanning (Profile Scan)
* **Channel guard:** `/setup` scopes ingestion to a specific channel; other channels are ignored by design.
* **Metric extraction:** Parses CP, kills, server, and alliance from uploaded screenshots, including the extended **More** tab layouts.
* **Review & ranking:** `/profile` shows the last snapshot (CP, kills, likes, VIP, alliance/server, and a self-view check that looks for the in-game Account/Settings buttons); `/profile_review` lets admins invalidate or delete scans; `/leaderboard` surfaces XP plus CP/kills/likes/VIP (profile scan) with 10/25/50/100 row controls, a DM-friendly export, and cached uploads to avoid repeat downloads.
* **Health checks:** `python ocr/diagnostics.py` verifies dependencies/templates. See [OCR_SETUP.md](OCR_SETUP.md).

---

## Deployment overview
These steps are for the owner’s private deployment only.

### Runtime requirements
* Python 3.8+
* `discord.py`, `httpx`, `python-dotenv`, `aiosqlite`

### Profile scan add-on (OCR, enables `/scan_profile`)
* All Python OCR deps (Pillow, pytesseract, easyocr, opencv-python-headless, numpy) ship in `requirements.txt` (PyTorch entries are pinned to **CPU-only** wheels to keep installs light on GPU-less hosts)
* System `tesseract-ocr` binary
* Checklist and template workflow: [OCR_SETUP.md](OCR_SETUP.md)
* Optional external fallback: set `OCR_SPACE_API_KEY` to offload scans to OCR.space when local OCR is missing.

**Low-memory hosts (≤1 GB RAM):** installing torch/EasyOCR can OOM on tiny game panels. You can:

* Use the lightweight install to skip OCR: `pip install -r requirements-lite.txt` (scanning stays disabled, everything else works).
* If you need OCR, prebuild wheels on a bigger machine and upload them to the host. Install with `pip install --no-index --find-links /path/to/wheels -r requirements.txt`.
* Or set `OCR_SPACE_API_KEY` to let `/scan_profile` call the OCR.space API instead of loading torch/EasyOCR locally.

### Deployment checklist (all hosts)
1. Install Python deps:
   * `pip install -r requirements.txt` (includes OCR extras)
2. Install Tesseract: `apt-get install -y tesseract-ocr` (Debian/Ubuntu), `brew install tesseract` (macOS), or `choco install tesseract` (Windows).
3. Verify versions: `tesseract --version` and `python -m pip show httpx` (match `requirements.txt`).
4. Run diagnostics when OCR is enabled: `python ocr/diagnostics.py`.

---

## Hosting patterns
Owner-only hosting notes, included for internal reference.

### Containers / Pterodactyl / read-only consoles
Panels often install only `requirements.txt` and skip system packages. Bake everything into the start command so every boot is self-contained:

```bash
apt-get update && apt-get install -y tesseract-ocr \
  && pip install -r requirements.txt \
  && python main.py
```

Notes:
* Keep the command on one line in panel settings; do not rely on interactive consoles.
* Remove or pin conflicting preinstalls (e.g., `googletrans==4.0.0rc1` forces `httpx==0.13.3` and breaks the bot). Lock `httpx` to the version in `requirements.txt` if your host injects extras.

### Local development
Clone the repo, create `.env`, install dependencies (include OCR if you need scanning), and run `python main.py` from the repo root. The bot pins its working directory automatically.

---

## Local configuration
1. Clone the repository.
2. Create a `.env` file in the root directory:

```env
TOKEN=your_discord_bot_token_here
```

**Mention replies (optional AI)**
* `MARCIA_AI_API_KEY` — API key for a hosted LLM (tested with OpenRouter free-tier).
* `MARCIA_AI_BASE_URL` — Defaults to `https://openrouter.ai/api/v1`.
* `MARCIA_AI_MODEL` — Defaults to `meta-llama/llama-3.1-8b-instruct:free`.
* `MARCIA_AI_APP_NAME` — Defaults to `Marcia OS` (sent as `X-Title`).
* `MARCIA_AI_APP_URL` — Optional referer URL for provider analytics.
* `MARCIA_MENTION_COOLDOWN` — Seconds between AI replies per user (default: `45`).
* `MARCIA_BUSY_COOLDOWN` — Seconds between “busy” notices per user (default: `120`).
* **Troubleshooting 404s:** OpenRouter returns `404 Not Found` when the model name is invalid. Set `MARCIA_AI_MODEL` to a model listed in your OpenRouter dashboard.

**Profile scan tuning**
* `PROFILE_SCAN_WORKERS` — Number of queued scan workers (default: `1`).
* `PROFILE_SCAN_CONCURRENCY` — Max concurrent OCR jobs (default: `2`).
* `PROFILE_SCAN_REVIEW_TIMEOUT` — Seconds before auto-accepting scan review (default: `90`).
* `OCR_SPACE_TIMEOUT` — Seconds to wait on OCR.space (default: `60`).

**Data persistence**
* Default database: `data/marcia_os.db` (auto-created). Override with `MARCIA_DB_PATH` if your host mounts storage elsewhere.

**Moderation logging**
* For the moderated guild (`1403997721962086480`), transcripts live under `archives/<ServerName>_<ServerID>/`, one `<channel>_<channel_id>.log` per text channel or thread.
* A `.history_seeded` marker appears after the first full backfill (including archived threads). New channels/threads are captured automatically.
* Logging is silent—no channel posts during backfill or transcript writes.

---

## Operations & troubleshooting
* **`ModuleNotFoundError: cogs`** — The bot forces its working directory to the repo root. If the error appears on panel hosts, ensure `main.py` and `cogs/` are co-located and the start command runs from this folder.
* **Profile scans are blank** — Confirm `tesseract` is installed, OCR extras are present (from `requirements.txt`), and templates match your screenshot layout (see [OCR_SETUP.md](OCR_SETUP.md)).
* **HTTP client conflicts** — Third-party images that preinstall `googletrans==4.0.0rc1` downgrade `httpx`. Re-pin to the version in `requirements.txt` and remove conflicting packages.

---
