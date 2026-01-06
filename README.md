# 📂 MARICA OS v3.0 | Helles Hub Tactical Bot

![Status](https://img.shields.io/badge/Status-Online-brightgreen)
![Library](https://img.shields.io/badge/Library-Discord.py-blue)
![License](https://img.shields.io/badge/License-Private-red)

> *"Freedom is expensive. Don't waste my time for free."* — **Marcia**

Marica is the tactical operations bot for the **Helles Hub Alliance**. She orchestrates ops, translations, trading, and player progression with the reliability expected from production-grade services. For hands-on usage, see [docs/USAGE.md](docs/USAGE.md).

## Table of contents
1. [System capabilities](#system-capabilities)
2. [Deployment overview](#deployment-overview)
3. [Hosting patterns](#hosting-patterns)
4. [Local configuration](#local-configuration)
5. [Operations & troubleshooting](#operations--troubleshooting)
6. [Outreach blurb](#outreach-blurb)

---

## System capabilities

### Fish-Link Network (trading)
* **Auto-matchmaking:** DMs users when a duplicate fish meets another player’s “Wanted” list.
* **Anchored UI:** Keeps the trade menu at the channel bottom, even under heavy chat.
* **Inventory tools:** Add extras, discover needs, and clear listings quickly.

### Survivor progression & scavenging
* **Endless XP tiers:** Message-based XP (60s cooldown) that auto-creates “Sector Rank” roles every 5 levels.
* **Prestige collections:** Hourly scavenging drops Common → Mythic loot; completing the set grants **Vaultwalker**.
* **Loot economy:** `/trade_item` lets squadmates exchange scavenged items.

### Commander protocols (events)
* **Guided creation:** `/event` runs a DM wizard that captures codename, tag, instructions, start time (`YYYY-MM-DD HH:MM` in UTC-2), optional location/voice link, and ping target.
* **Cadenced reminders:** Posts at T-minus 60/30/15/3/0 minutes with consistent formatting and allowed mentions.
* **Visibility:** `/events` lists upcoming operations for the current server with UTC-2 timestamps.
* **Cleanup & reuse:** `/event_remove <codename>` removes an operation; templates can be archived and reused.

### Profile scanning (OCR)
* **Channel guard:** `/setup_profile_channel` scopes ingestion to a specific channel; other channels are ignored by design.
* **Metric extraction:** Parses CP, kills, likes, VIP, level, server, and alliance from uploaded screenshots.
* **Review & ranking:** `/profile_stats` shows the last snapshot; `/leaderboard` surfaces XP plus CP/kills/likes/VIP/level (OCR).
* **Health checks:** `/ocr_status` and `python ocr/diagnostics.py` verify dependencies/templates. See [docs/OCR_SETUP.md](docs/OCR_SETUP.md).

---

## Deployment overview

### Runtime requirements
* Python 3.8+
* `discord.py`, `httpx`, `python-dotenv`, `aiosqlite`

### OCR add-on (enables `/scan_profile`)
* All Python OCR deps (Pillow, pytesseract, easyocr, opencv-python-headless, numpy) ship in `requirements.txt` (PyTorch entries are pinned to **CPU-only** wheels to keep installs light on GPU-less hosts)
* System `tesseract-ocr` binary
* Checklist and template workflow: [docs/OCR_SETUP.md](docs/OCR_SETUP.md)
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
4. Run diagnostics when OCR is enabled: `python ocr/diagnostics.py` or `/ocr_status` in Discord.

---

## Hosting patterns

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

**Data persistence**
* Default database: `data/marcia_os.db` (auto-created). Override with `MARCIA_DB_PATH` if your host mounts storage elsewhere.

**Moderation logging**
* For the moderated guild (`1403997721962086480`), transcripts live under `archives/<ServerName>_<ServerID>/`, one `<channel>_<channel_id>.log` per text channel or thread.
* A `.history_seeded` marker appears after the first full backfill (including archived threads). New channels/threads are captured automatically.
* Logging is silent—no channel posts during backfill or transcript writes.

---

## Operations & troubleshooting
* **`ModuleNotFoundError: cogs`** — The bot forces its working directory to the repo root. If the error appears on panel hosts, ensure `main.py` and `cogs/` are co-located and the start command runs from this folder.
* **Profile scans are blank** — Confirm `tesseract` is installed, OCR extras are present (from `requirements.txt`), and templates match your screenshot layout (see [docs/OCR_SETUP.md](docs/OCR_SETUP.md)).
* **HTTP client conflicts** — Third-party images that preinstall `googletrans==4.0.0rc1` downgrade `httpx`. Re-pin to the version in `requirements.txt` and remove conflicting packages.

---

## Outreach blurb
Use this when someone asks what Marica is or how to try her:

> Hey! I play **Dark War Survival** and built Marica to make life easier for my alliance—translations, ops reminders, trading, and more. She's updated daily with new in-game helpers. Invite her: https://discord.com/oauth2/authorize?client_id=1428179195938476204. Join the beta/test hub: https://discord.gg/ePhRntSzB. Check `/commands`, `/features`, or `/showcase` for a quick tour, and run `/setup` right after inviting. I'm open to ideas and feedback!
