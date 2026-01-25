# Marcia

![Status](https://img.shields.io/badge/Status-Online-brightgreen)
![Library](https://img.shields.io/badge/Library-Discord.py-blue)
![License](https://img.shields.io/badge/License-Private-red)

> *"Freedom is expensive. Don't waste my time for free."* — **Marcia**

Marcia is the tactical operations lead for the **Helles Hub Alliance**. She runs ops, translations, trading, and player progression with production-grade reliability - and she speaks like a real person in chat, not a faceless system. For hands-on usage, see [docs/USAGE.md](docs/USAGE.md).

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
* **DM intake:** `/scan` opens a DM flow; uploads happen privately and stats are linked to your server.
* **Metric extraction:** Parses CP, kills, likes, VIP, level, server, and alliance from uploaded screenshots.
* **Review & ranking:** `/profile_stats` shows the last snapshot; `/profile_leaderboard` surfaces the top CP/kills/likes/VIP/level.
* **Health checks:** `python ocr/diagnostics.py` verifies dependencies/templates. See [docs/OCR_SETUP.md](docs/OCR_SETUP.md).

---

## Deployment overview

### Runtime requirements
* Python 3.8+
* Base deps: `discord.py`, `httpx`, `python-dotenv`, `aiosqlite`

### OCR add-on (enables `/scan_profile`)
* Python OCR deps live in `requirements-ocr.txt` (Pillow, pytesseract, opencv-python-headless, numpy, EasyOCR, torch/torchvision pinned to the PyTorch **CPU** wheels, no NVIDIA downloads)
* System `tesseract-ocr` binary
* Checklist and template workflow: [docs/OCR_SETUP.md](docs/OCR_SETUP.md)
* Optional external fallback: set `OCR_SPACE_API_KEY` to offload scans to OCR.space when local OCR is missing.
* CPU mode is the default; if you later add a CUDA GPU and install matching torch/torchvision wheels, set `GPU = True` in `ocr/ocr_runner.py` for faster local scans.

**Low-memory hosts (≤1–3 GB RAM):** keep the base install tiny and opt into OCR only when resources allow. The OCR file pulls +cpu wheels and skips CUDA extras; add `--no-cache-dir` on tight disks.

* Use the lightweight install to skip OCR: `pip install -r requirements-lite.txt` (scanning stays disabled, everything else works).
* If you need OCR, prebuild wheels on a bigger machine and upload them to the host. Install with `pip install --no-index --find-links /path/to/wheels -r requirements.txt`.
* 512 MB RAM panels almost always OOM on torch; preload wheels instead of live installing (see [Low-memory install guide](docs/LOW_MEMORY_INSTALL.md)).

### Deployment checklist (all hosts)
1. Install Python deps:
   * Base bot: `pip install -r requirements.txt`
   * Enable OCR locally: `pip install --no-cache-dir -r requirements-ocr.txt`
2. Install Tesseract: `apt-get install -y tesseract-ocr` (Debian/Ubuntu), `brew install tesseract` (macOS), or `choco install tesseract` (Windows).
3. Verify versions: `tesseract --version` and `python -m pip show httpx` (match `requirements.txt`). If OCR is enabled, also check `python -m pip show torch torchvision easyocr`.
4. Run diagnostics when OCR is enabled: `python ocr/diagnostics.py`.

---

## Hosting patterns

### Containers / Pterodactyl / read-only consoles
Panels often install only `requirements.txt` and skip system packages. Bake everything into the start command so every boot is self-contained:

```bash
apt-get update && apt-get install -y tesseract-ocr \
  && pip install -r requirements.txt \
  && pip install --no-cache-dir -r requirements-ocr.txt \
  && python main.py
```

Notes:
* Keep the command on one line in panel settings; do not rely on interactive consoles.
* Translation uses the public Google Translate endpoint over `httpx`; avoid installing legacy `googletrans` packages that pin incompatible `httpx` versions.

### Local development
Clone the repo, create `.env`, install dependencies (include OCR if you need scanning), and run `python main.py` from the repo root. The bot pins its working directory automatically.

**Pinned installs:** Use `pip install -r requirements.lock` if you want exact versions aligned with the latest stable deploy.

---

## Local configuration
1. Clone the repository.
2. Create a `.env` file in the root directory:

```env
TOKEN=your_discord_bot_token_here
```

**Token alias**
* `DISCORD_TOKEN` is accepted for legacy setups but `TOKEN` is the source of truth.

**Mention replies (optional AI)**
* `MARCIA_AI_API_KEY` — API key for a hosted LLM (tested with OpenRouter free-tier).
* `MARCIA_AI_BASE_URL` — Defaults to `https://openrouter.ai/api/v1`.
* `MARCIA_AI_MODEL` — Defaults to `meta-llama/llama-3.1-8b-instruct:free`.
* `MARCIA_AI_APP_NAME` — Defaults to `Marcia` (sent as `X-Title`).
* `MARCIA_AI_APP_URL` — Optional referer URL for provider analytics.
* `MARCIA_MENTION_COOLDOWN` — Seconds between AI replies per user (default: `45`).
* `MARCIA_BUSY_COOLDOWN` — Seconds between “busy” notices per user (default: `120`).

**HTTP guardrails**
* `MARCIA_HTTP_TIMEOUT` — Default timeout in seconds for external calls (default: `10`).
* `MARCIA_HTTP_RETRIES` — Retry attempts for safe calls (default: `2`).
* `MARCIA_HTTP_BACKOFF` — Base backoff seconds for retries (default: `0.6`).
* `MARCIA_HTTP_BREAKER_FAILURES` — Failures before opening the circuit (default: `3`).
* `MARCIA_HTTP_BREAKER_RESET` — Seconds before a circuit resets (default: `30`).

**Profile scan tuning**
* `PROFILE_SCAN_WORKERS` — Number of queued scan workers (default: `1`).
* `PROFILE_SCAN_CONCURRENCY` — Max concurrent OCR jobs (default: `2`).
* `PROFILE_SCAN_REVIEW_TIMEOUT` — Seconds before auto-accepting scan review (default: `90`).
* `OCR_SPACE_API_KEY` — Optional OCR.space key for fallback.
* `OCR_SPACE_TIMEOUT` — Seconds to wait on OCR.space (default: `60`).

**Metrics**
* `MARCIA_METRICS_INTERVAL` — Seconds between metrics snapshots (default: `120`).

**Data persistence**
* Default database: `data/marcia_os.db` (auto-created). Override with `MARCIA_DB_PATH` if your host mounts storage elsewhere.
* `MARCIA_DB_CACHE_TTL` — Seconds to cache settings/ignore lists (default: `30`).

**Moderation logging**
* For the moderated guild (`1403997721962086480`), transcripts live under `archives/servers/<ServerName>_<ServerID>/logs/` with `channels/` and `threads/` subfolders.
* Log files are named `channel_<name>_<id>.log` or `thread_<name>_<id>.log` for quick scans.
* A `metadata/history_seeded.json` marker appears after the first full backfill (including archived threads). New channels/threads are captured automatically.
* Logging is silent—no channel posts during backfill or transcript writes.

---

## Operations & troubleshooting
* **`ModuleNotFoundError: cogs`** — The bot forces its working directory to the repo root. If the error appears on panel hosts, ensure `main.py` and `cogs/` are co-located and the start command runs from this folder.
* **Profile scans are blank** — Confirm `tesseract` is installed, OCR extras are present (from `requirements.txt`), and templates match your screenshot layout (see [docs/OCR_SETUP.md](docs/OCR_SETUP.md)).
* **HTTP client conflicts** — Third-party images that preinstall `googletrans==4.0.0rc1` downgrade `httpx`. Re-pin to the version in `requirements.txt` and remove conflicting packages.

---

## Outreach blurb
Use this when someone asks what Marica is or how to try her:

> Hey! I play **Dark War Survival** and built Marica to make life easier for my alliance—translations, ops reminders, trading, and more. She's updated daily with new in-game helpers. Invite her: https://discord.com/oauth2/authorize?client_id=1428179195938476204. Join the beta/test hub: https://discord.gg/TneGDQXG. Check `/commands`, `/features`, or `/showcase` for a quick tour, and run `/setup` right after inviting. I'm open to ideas and feedback!
