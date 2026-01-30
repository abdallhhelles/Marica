"""
FILE: database.py
USE: Persistent storage for multi-server configurations and trading.
FEATURES: Server-specific trading network, settings, and migration logic.
"""
import json
import os
import shutil
import time
from pathlib import Path

import aiosqlite
from datetime import datetime, timezone
import logging

from utils.time_utils import GAME_TZ
from utils.assets import REMINDER_TEMPLATE_STARTER

logger = logging.getLogger('MarciaOS.DB')

# Persist data inside the repo's tracked data directory so pull/push cycles keep live state.
_BASE_DIR = Path(__file__).resolve().parent
_ENV_PATH = os.getenv("MARCIA_DB_PATH")
_REPO_DATA_DIR = _BASE_DIR / "data"
_REPO_DATA_PATH = _REPO_DATA_DIR / "marcia_os.db"
_FEEDBACK_LOG_FILE = _REPO_DATA_DIR / "feedback.log"
_CACHE_TTL = float(os.getenv("MARCIA_DB_CACHE_TTL", "30"))
_SETTINGS_CACHE: dict[int, tuple[float, dict]] = {}
_IGNORED_CACHE: dict[int, tuple[float, set[int]]] = {}

# Legacy locations we may need to hoist into the repo copy when upgrading from older deployments.
_OLD_HOME_STATE = Path.home() / ".local" / "share" / "marcia_os" / "marcia_os.db"
_OLD_FALLBACK_DIR = Path.home() / "marcia_data" / "marcia_os.db"

# --- BACKUP & RESTORE HELPERS ---

def _latest_backup(db_path: Path) -> Path | None:
    """Return the newest backup file if one exists."""
    backups_dir = db_path.parent / "backups"
    if not backups_dir.exists():
        return None

    backups = sorted(backups_dir.glob("marcia_os-*.db"))
    return backups[-1] if backups else None


def _restore_from_backup(db_path: Path) -> bool:
    """Recover the live DB from the most recent backup, if present."""
    latest = _latest_backup(db_path)
    if not latest:
        return False

    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest, db_path)
        logger.info("🧬 Restored database from backup %s", latest)
        return True
    except Exception as e:
        logger.warning("Backup restore failed: %s", e)
        return False


def _migrate_legacy_db(dest: Path) -> None:
    """Promote older DB files into the canonical location if present."""
    legacy_paths = [
        _OLD_FALLBACK_DIR,                               # earliest installs
        _OLD_HOME_STATE,                                 # prior home-scoped persistence
        _BASE_DIR / "marcia_os.db",                     # root-level drop-ins
        _REPO_DATA_PATH,                                 # pre-persist repo data folder
    ]
    for src in legacy_paths:
        if dest.exists() or src.resolve() == dest.resolve() or not src.exists():
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            logger.info("🗂️ Migrated existing database to %s", dest)
            break
        except Exception as e:
            logger.warning("Could not move legacy DB to %s: %s", dest, e)


def _snapshot_db(db_path: Path) -> None:
    """Create timestamped backups so accidental wipes can be recovered after updates."""
    if not db_path.exists():
        return

    backups_dir = db_path.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_file = backups_dir / f"marcia_os-{timestamp}.db"
    try:
        shutil.copy2(db_path, backup_file)
        logger.info("🧰 DB backup created at %s", backup_file)

        # Keep the five most recent backups to avoid filling disk.
        existing = sorted(backups_dir.glob("marcia_os-*.db"))
        for old in existing[:-5]:
            old.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("Backup skipped: %s", e)


def _resolve_db_path() -> Path:
    """Pick the repo-tracked DB location and ensure legacy data is brought forward."""
    if _ENV_PATH:
        chosen = Path(_ENV_PATH).expanduser()
        chosen.parent.mkdir(parents=True, exist_ok=True)
        return chosen

    # Default to a tracked data folder so pull/push cycles keep live state inside Git.
    _REPO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    chosen = _REPO_DATA_PATH
    if not chosen.exists():
        _migrate_legacy_db(chosen)
        if not chosen.exists():
            # If nothing was migrated, attempt recovery from the newest backup.
            _restore_from_backup(chosen)
    elif chosen.stat().st_size == 0:
        # Defensive: a zero-byte DB usually means a host crash mid-write.
        restored = _restore_from_backup(chosen)
        if restored:
            logger.info("💾 Empty database healed from backup.")

    return chosen


DB_PATH_OBJ = _resolve_db_path()
_snapshot_db(DB_PATH_OBJ)
DB_PATH = str(DB_PATH_OBJ)

# Seed fish trade listings captured before data loss so we can repopulate wiped hosts.
_SEED_FILE = _BASE_DIR / "data" / "trade_seed.json"
_SEED_DEFAULT_GUILD: int | None = None
_seed_env = os.getenv("MARCIA_SEED_GUILD_ID")
if _seed_env:
    try:
        parsed_seed = int(_seed_env)
        if parsed_seed > 0:
            _SEED_DEFAULT_GUILD = parsed_seed
        else:
            logger.warning("MARCIA_SEED_GUILD_ID must be positive; got %s", _seed_env)
    except ValueError:
        logger.warning("Invalid MARCIA_SEED_GUILD_ID value %r; seed restore disabled", _seed_env)
_TRADE_SEED_CACHE: dict | None = None

async def init_db():
    """Initializes the database and migrates legacy data if found."""
    logger.info("🗄️ Database path: %s", DB_PATH)
    async with aiosqlite.connect(DB_PATH) as db:
        # Favor durability: WAL + synchronous FULL protects against host restarts while keeping writes snappy enough.
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=FULL")

        # 1. Server Settings
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                guild_id INTEGER PRIMARY KEY,
                server_name TEXT,
                welcome_channel_id INTEGER,
                event_channel_id INTEGER,
                chat_channel_id INTEGER,
                trade_channel_id INTEGER,
                rules_channel_id INTEGER,
                verify_channel_id INTEGER,
                feedback_channel_id INTEGER,
                analytics_channel_id INTEGER,
                auto_role_id INTEGER,
                server_offset_hours INTEGER DEFAULT -2
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS ignored_channels (
                guild_id INTEGER,
                channel_id INTEGER,
                PRIMARY KEY (guild_id, channel_id)
            )
        ''')

        # 2. Trading Table (Modern Structure)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS trade_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER,
                fish_rarity TEXT,
                fish_index INTEGER,
                type TEXT,
                UNIQUE(guild_id, user_id, fish_rarity, fish_index, type)
            )
        ''')

        # 3. Server-Specific Templates
        await db.execute('''
            CREATE TABLE IF NOT EXISTS server_templates (
                guild_id INTEGER,
                template_name TEXT,
                description TEXT,
                PRIMARY KEY (guild_id, template_name)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS reminder_templates (
                guild_id INTEGER,
                template_name TEXT,
                body TEXT,
                PRIMARY KEY (guild_id, template_name)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                channel_id INTEGER,
                creator_id INTEGER,
                body TEXT,
                send_at_utc TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS profile_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS scanner_config (
                guild_id INTEGER PRIMARY KEY,
                profile_scan_enabled INTEGER,
                duel_scan_enabled INTEGER,
                updated_at INTEGER
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS profile_snapshots (
                guild_id INTEGER,
                user_id INTEGER,
                player_name TEXT,
                alliance TEXT,
                server TEXT,
                cp INTEGER,
                kills INTEGER,
                likes INTEGER,
                vip_level INTEGER,
                level INTEGER,
                ownership_verified INTEGER,
                scan_valid INTEGER DEFAULT 1,
                avatar_url TEXT,
                last_image_url TEXT,
                local_image_path TEXT,
                raw_ocr TEXT,
                last_updated INTEGER,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS duel_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER,
                week_key TEXT,
                player_name TEXT,
                score_text TEXT,
                score_int INTEGER,
                raw_ocr TEXT,
                created_at INTEGER
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS reminder_template_seed (
                guild_id INTEGER PRIMARY KEY
            )
        ''')

        # 4. Active Missions
        await db.execute('''
            CREATE TABLE IF NOT EXISTS server_missions (
                guild_id INTEGER,
                codename TEXT,
                description TEXT,
                target_time TEXT,
                target_utc TEXT,
                location TEXT,
                ping_role_id INTEGER,
                tag TEXT,
                notes TEXT,
                PRIMARY KEY (guild_id, codename)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS mission_dm_prompts (
                guild_id INTEGER,
                codename TEXT,
                message_id INTEGER PRIMARY KEY
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS mission_dm_opt_ins (
                guild_id INTEGER,
                codename TEXT,
                user_id INTEGER,
                PRIMARY KEY (guild_id, codename, user_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS mission_rsvp_prompts (
                guild_id INTEGER,
                codename TEXT,
                message_id INTEGER PRIMARY KEY
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS mission_rsvps (
                guild_id INTEGER,
                codename TEXT,
                user_id INTEGER,
                status TEXT,
                PRIMARY KEY (guild_id, codename, user_id)
            )
        ''')

        # 5. System Tracking
        await db.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                task_name TEXT PRIMARY KEY,
                last_run_date TEXT
            )
        ''')
        
        # 6. Leveling & Inventory (Guild-Isolated)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                guild_id INTEGER,
                user_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                last_msg_ts REAL DEFAULT 0,
                last_scavenge_ts REAL DEFAULT 0,
                scavenge_streak INTEGER DEFAULT 0,
                discord_likes INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS discord_message_likes (
                guild_id INTEGER,
                message_id INTEGER,
                user_id INTEGER,
                author_id INTEGER,
                created_at TEXT,
                PRIMARY KEY (message_id, user_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_inventory (
                guild_id INTEGER,
                user_id INTEGER,
                item_id TEXT,
                quantity INTEGER DEFAULT 1,
                rarity TEXT,
                PRIMARY KEY (guild_id, user_id, item_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS inventory_transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                channel_id INTEGER,
                sender_id INTEGER,
                receiver_id INTEGER,
                item_id TEXT,
                quantity INTEGER,
                created_at TEXT
            )
        ''')

        # 7. Command usage telemetry (guild-isolated)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS command_usage (
                guild_id INTEGER,
                command_name TEXT,
                uses INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, command_name)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS activity_metrics (
                guild_id INTEGER,
                metric_name TEXT,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, metric_name)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS feedback_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER,
                channel_id INTEGER,
                feedback TEXT,
                created_at TEXT
            )
        ''')

        # --- AUTOMATIC DATA MIGRATION ---
        try:
            # Check if old table exists
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trading_inventory'")
            if await cursor.fetchone():
                logger.info("📦 Legacy trading data found. Migrating to trade_pool...")
                # Move data: "SSR-1" -> rarity="SSR", index=1 | "extras" -> "spare", "wanted" -> "find"
                async with db.execute("SELECT guild_id, user_id, fish_id, category FROM trading_inventory") as old_cursor:
                    async for row in old_cursor:
                        gid, uid, fid, cat = row
                        try:
                            rarity, idx = fid.split('-')
                            db_type = "spare" if cat == "extras" else "find"
                            await db.execute('''
                                INSERT OR IGNORE INTO trade_pool (guild_id, user_id, fish_rarity, fish_index, type)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (gid, uid, rarity, int(idx), db_type))
                        except Exception as e:
                            logger.error(f"Failed to migrate row {fid}: {e}")
                
                # Rename the old table so we don't migrate it again next time
                await db.execute("ALTER TABLE trading_inventory RENAME TO legacy_trading_inventory")
                await db.commit()
                print("✅ Migration Complete: All legacy fish entries moved to new system.")
        except Exception as e:
            logger.warning(f"Migration skipped or failed: {e}")

        await db.execute("CREATE INDEX IF NOT EXISTS idx_trading_guild ON trade_pool(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_mission_guild ON server_missions(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_guild ON user_stats(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_inventory_guild ON user_inventory(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_inventory_transfers_guild ON inventory_transfers(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_feedback_guild ON feedback_entries(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_discord_likes_guild ON discord_message_likes(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_duel_scores_guild_week ON duel_scores(guild_id, week_key)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_duel_scores_user ON duel_scores(guild_id, user_id)")

        async with db.execute("PRAGMA table_info(user_stats)") as cursor:
            existing_columns = {row[1] async for row in cursor}
        if "scavenge_streak" not in existing_columns:
            await db.execute(
                "ALTER TABLE user_stats ADD COLUMN scavenge_streak INTEGER DEFAULT 0"
            )
        if "discord_likes" not in existing_columns:
            await db.execute(
                "ALTER TABLE user_stats ADD COLUMN discord_likes INTEGER DEFAULT 0"
            )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_metrics_guild ON activity_metrics(guild_id)")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mission_prompt_guild ON mission_dm_prompts(guild_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mission_optins_guild ON mission_dm_opt_ins(guild_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mission_rsvp_guild ON mission_rsvps(guild_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mission_rsvp_prompt_guild ON mission_rsvp_prompts(guild_id)"
        )
        await db.commit()

        # On a fresh DB, repopulate the preserved trade snapshot so lost fish listings return immediately.
        if _SEED_DEFAULT_GUILD is not None:
            await ensure_seed_trade_pool(_SEED_DEFAULT_GUILD)

        # Backfill newer mission fields for older installs
        await _ensure_column(db, "server_missions", "location", "TEXT")
        await _ensure_column(db, "server_missions", "ping_role_id", "INTEGER")
        await _ensure_column(db, "server_missions", "tag", "TEXT")
        await _ensure_column(db, "server_missions", "notes", "TEXT")
        await _ensure_column(db, "profile_snapshots", "local_image_path", "TEXT")
        await _ensure_column(db, "profile_snapshots", "ownership_verified", "INTEGER")
        await _ensure_column(db, "profile_snapshots", "scan_valid", "INTEGER")
        await _ensure_column(db, "settings", "feedback_channel_id", "INTEGER")
        await _ensure_column(db, "settings", "analytics_channel_id", "INTEGER")

    print("📡 MARCIA OS | Database Core Synchronized (Trading, Missions & Config).")


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, col_type: str):
    """Add a column to a table if it does not already exist."""
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        existing = [row[1] async for row in cursor]
    if column not in existing:
        try:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            await db.commit()
            logger.info(f"✅ Added column {column} to {table}")
        except Exception as e:
            logger.warning(f"Could not add column {column} to {table}: {e}")

# --- SYSTEM LOG HELPERS ---

async def can_run_daily_task(task_name, date_str=None):
    today = date_str or datetime.now(GAME_TZ).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_run_date FROM system_logs WHERE task_name = ?", (task_name,)) as cursor:
            row = await cursor.fetchone()
            return not (row and row[0] == today)

async def mark_task_complete(task_name, date_str=None):
    today = date_str or datetime.now(GAME_TZ).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO system_logs (task_name, last_run_date)
            VALUES (?, ?)
            ON CONFLICT(task_name) DO UPDATE SET last_run_date = excluded.last_run_date
        ''', (task_name, today))
        await db.commit()

# --- TRADE SEED HELPERS ---

def _load_trade_seed() -> dict:
    """Cache the fish trade seed snapshot stored in the repo."""
    global _TRADE_SEED_CACHE
    if _TRADE_SEED_CACHE is not None:
        return _TRADE_SEED_CACHE

    if not _SEED_FILE.exists():
        _TRADE_SEED_CACHE = {}
        return _TRADE_SEED_CACHE

    try:
        with _SEED_FILE.open("r", encoding="utf-8") as fp:
            _TRADE_SEED_CACHE = json.load(fp)
    except Exception as e:
        logger.warning("Could not load trade seed file: %s", e)
        _TRADE_SEED_CACHE = {}

    return _TRADE_SEED_CACHE


def _select_seed_for_guild(seed: dict, guild_id: int) -> dict:
    """Return a merged seed map for a specific guild (guild-specific + global)."""
    if not seed:
        return {}

    merged = {"extras": {}, "wanted": {}}

    def _merge_into(target: dict, source: dict | None):
        if not source:
            return
        for fid, users in source.items():
            target.setdefault(fid, [])
            target[fid].extend(users)

    # Start with the global snapshot so all guilds get the preserved listings.
    _merge_into(merged["extras"], seed.get("extras"))
    _merge_into(merged["wanted"], seed.get("wanted"))

    # Then add any guild-specific overrides to reinstate missing listings for that server only.
    guild_map = seed.get("guilds", {})
    _merge_into(merged["extras"], guild_map.get(str(guild_id), {}).get("extras"))
    _merge_into(merged["wanted"], guild_map.get(str(guild_id), {}).get("wanted"))

    return merged


async def ensure_seed_trade_pool(guild_id: int, force: bool = False) -> bool:
    """
    Repopulate missing trade listings from the bundled seed data.

    Returns True if any seed rows were added.
    """
    seed = _select_seed_for_guild(_load_trade_seed(), guild_id)
    if not seed.get("extras") and not seed.get("wanted"):
        return False

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM trade_pool WHERE guild_id = ? LIMIT 1", (guild_id,)) as cursor:
            has_rows = await cursor.fetchone()

        if has_rows and not force:
            return False

        try:
            for cat, entries in seed.items():
                db_type = "spare" if cat == "extras" else "find"
                for fid, users in entries.items():
                    rarity, idx_s = fid.split("-")
                    idx = int(idx_s)
                    for uid in users:
                        await db.execute(
                            '''
                            INSERT OR IGNORE INTO trade_pool (guild_id, user_id, fish_rarity, fish_index, type)
                            VALUES (?, ?, ?, ?, ?)
                            ''',
                            (guild_id, int(uid), rarity, idx, db_type),
                        )
            await db.commit()
            logger.info("🐟 Seeded trade listings for guild %s", guild_id)
            return True
        except Exception as e:
            logger.warning("Trade seed restore failed for guild %s: %s", guild_id, e)
            return False

# --- TELEMETRY HELPERS ---

async def increment_command_usage(guild_id: int | None, command_name: str) -> None:
    """Track how many times commands are executed per guild."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO command_usage (guild_id, command_name, uses)
            VALUES (?, ?, 1)
            ON CONFLICT(guild_id, command_name) DO UPDATE SET uses = uses + 1
            ''',
            (guild_id or 0, command_name),
        )
        await db.commit()


async def command_usage_totals() -> tuple[int, str | None, int]:
    """Return total uses plus the most-used command and its count."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COALESCE(SUM(uses), 0) FROM command_usage") as cursor:
            total_row = await cursor.fetchone()
            total = total_row[0] if total_row else 0

        async with db.execute(
            """
            SELECT command_name, uses
            FROM command_usage
            ORDER BY uses DESC
            LIMIT 1
            """
        ) as cursor:
            top_row = await cursor.fetchone()

    if not top_row:
        return total, None, 0

    return total, top_row[0], top_row[1]


async def top_commands(limit: int = 5) -> list[aiosqlite.Row]:
    """Return the most-used commands across all guilds."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT command_name, SUM(uses) AS total
            FROM command_usage
            GROUP BY command_name
            ORDER BY total DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            return await cursor.fetchall()


async def top_guild_usage(limit: int = 10) -> list[aiosqlite.Row]:
    """Return guilds ranked by total command usage."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT guild_id, SUM(uses) AS total
            FROM command_usage
            WHERE guild_id IS NOT NULL AND guild_id != 0
            GROUP BY guild_id
            ORDER BY total DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            return await cursor.fetchall()


async def increment_activity_metric(guild_id: int | None, metric_name: str, amount: int = 1) -> None:
    """Track custom activity counters per guild."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO activity_metrics (guild_id, metric_name, count)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, metric_name) DO UPDATE SET count = count + excluded.count
            ''',
            (guild_id or 0, metric_name, amount),
        )
        await db.commit()


async def activity_metric_totals(metric_names: list[str]) -> dict[str, int]:
    """Return summed totals for requested metrics across all guilds."""
    if not metric_names:
        return {}

    placeholders = ", ".join("?" for _ in metric_names)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""
            SELECT metric_name, COALESCE(SUM(count), 0) AS total
            FROM activity_metrics
            WHERE metric_name IN ({placeholders})
            GROUP BY metric_name
            """,
            tuple(metric_names),
        ) as cursor:
            rows = await cursor.fetchall()

    totals = {name: 0 for name in metric_names}
    for row in rows:
        totals[row["metric_name"]] = row["total"]
    return totals


async def total_active_missions() -> int:
    """Return the total number of active missions across all guilds."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM server_missions") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def top_global_xp(limit: int = 10) -> list[aiosqlite.Row]:
    """Return highest XP survivors across all guilds."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT guild_id, user_id, xp, level
            FROM user_stats
            ORDER BY level DESC, xp DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            return await cursor.fetchall()


# --- FEEDBACK HELPERS ---

async def log_feedback_entry(
    guild_id: int | None,
    user_id: int | None,
    channel_id: int | None,
    feedback_text: str,
) -> None:
    """Persist user feedback in the database and append to a plaintext journal."""
    created_at = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO feedback_entries (guild_id, user_id, channel_id, feedback, created_at)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (guild_id or 0, user_id or 0, channel_id or 0, feedback_text, created_at),
        )
        await db.commit()

    try:
        _FEEDBACK_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _FEEDBACK_LOG_FILE.open("a", encoding="utf-8") as fp:
            fp.write(
                f"{created_at} | guild={guild_id or 'DM'} | user={user_id or 'unknown'} | channel={channel_id or 'n/a'} | {feedback_text}\n"
            )
    except Exception as exc:  # pragma: no cover - logging only
        logger.warning("Could not append feedback journal entry: %s", exc)

# --- TRADING HELPERS ---

async def add_fish_to_inventory(guild_id: int, user_id: int, rarity: str, index: int, trade_type: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR IGNORE INTO trade_pool (guild_id, user_id, fish_rarity, fish_index, type)
            VALUES (?, ?, ?, ?, ?)
        ''', (guild_id, user_id, rarity, index, trade_type))
        await db.commit()

async def get_fish_inventory(guild_id: int, user_id: int) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM trade_pool 
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id)) as cursor:
            return await cursor.fetchall()

# --- SERVER SETTINGS HELPERS ---

SCANNER_CONFIG_KEYS = ("profile_scan_enabled", "duel_scan_enabled")

async def get_settings(guild_id: int) -> dict | None:
    now = time.monotonic()
    cached = _SETTINGS_CACHE.get(guild_id)
    if cached and now - cached[0] <= _CACHE_TTL:
        return cached[1]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM settings WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            result = dict(row) if row else None
            if result is not None:
                _SETTINGS_CACHE[guild_id] = (now, result)
            return result

async def update_setting(guild_id: int, column: str, value: int | str | None, server_name: str | None = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'''
            INSERT INTO settings (guild_id, server_name, {column}) 
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET 
                {column} = excluded.{column},
                server_name = COALESCE(excluded.server_name, settings.server_name)
        ''', (guild_id, server_name, value))
        await db.commit()
    _SETTINGS_CACHE.pop(guild_id, None)

async def get_scanner_config(guild_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM scanner_config WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def upsert_scanner_config(
    guild_id: int,
    *,
    profile_scan_enabled: int | None,
    duel_scan_enabled: int | None,
) -> dict | None:
    now_ts = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO scanner_config (
                guild_id,
                profile_scan_enabled,
                duel_scan_enabled,
                updated_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                profile_scan_enabled = excluded.profile_scan_enabled,
                duel_scan_enabled = excluded.duel_scan_enabled,
                updated_at = excluded.updated_at
            ''',
            (guild_id, profile_scan_enabled, duel_scan_enabled, now_ts),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM scanner_config WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_ignored_channels(guild_id: int) -> list[int]:
    now = time.monotonic()
    cached = _IGNORED_CACHE.get(guild_id)
    if cached and now - cached[0] <= _CACHE_TTL:
        return sorted(cached[1])
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT channel_id FROM ignored_channels WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            channels = {r[0] for r in rows}
            _IGNORED_CACHE[guild_id] = (now, channels)
            return sorted(channels)


async def is_channel_ignored(guild_id: int, channel_id: int) -> bool:
    now = time.monotonic()
    cached = _IGNORED_CACHE.get(guild_id)
    if cached and now - cached[0] <= _CACHE_TTL:
        return channel_id in cached[1]
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM ignored_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        ) as cursor:
            exists = await cursor.fetchone() is not None
            if exists:
                channels = cached[1] if cached else set()
                channels.add(channel_id)
                _IGNORED_CACHE[guild_id] = (now, channels)
            return exists


async def add_ignored_channel(guild_id: int, channel_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT OR IGNORE INTO ignored_channels (guild_id, channel_id)
            VALUES (?, ?)
            ''',
            (guild_id, channel_id),
        )
        await db.commit()
    _IGNORED_CACHE.pop(guild_id, None)


async def remove_ignored_channel(guild_id: int, channel_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM ignored_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        await db.commit()
    _IGNORED_CACHE.pop(guild_id, None)

# --- PROFILE SNAPSHOT HELPERS ---


async def set_profile_channel(guild_id: int, channel_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO profile_channels (guild_id, channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
            ''',
            (guild_id, channel_id),
        )
        await db.commit()


async def clear_profile_channel(guild_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM profile_channels WHERE guild_id = ?",
            (guild_id,),
        )
        await db.commit()


async def get_profile_channel(guild_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT channel_id FROM profile_channels WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def upsert_profile_snapshot(
    guild_id: int,
    user_id: int,
    *,
    player_name: str | None = None,
    alliance: str | None = None,
    server: str | None = None,
    cp: int | None = None,
    kills: int | None = None,
    likes: int | None = None,
    vip_level: int | None = None,
    level: int | None = None,
    ownership_verified: bool | None = None,
    scan_valid: bool | None = True,
    avatar_url: str | None = None,
    last_image_url: str | None = None,
    local_image_path: str | None = None,
    raw_ocr: str | None = None,
) -> None:
    now_ts = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO profile_snapshots (
                guild_id, user_id, player_name, alliance, server, cp, kills, likes,
                vip_level, level, ownership_verified, scan_valid, avatar_url, last_image_url, local_image_path, raw_ocr, last_updated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                player_name = COALESCE(excluded.player_name, profile_snapshots.player_name),
                alliance = COALESCE(excluded.alliance, profile_snapshots.alliance),
                server = COALESCE(excluded.server, profile_snapshots.server),
                cp = COALESCE(excluded.cp, profile_snapshots.cp),
                kills = COALESCE(excluded.kills, profile_snapshots.kills),
                likes = COALESCE(excluded.likes, profile_snapshots.likes),
                vip_level = COALESCE(excluded.vip_level, profile_snapshots.vip_level),
                level = COALESCE(excluded.level, profile_snapshots.level),
                ownership_verified = COALESCE(excluded.ownership_verified, profile_snapshots.ownership_verified),
                scan_valid = excluded.scan_valid,
                avatar_url = COALESCE(excluded.avatar_url, profile_snapshots.avatar_url),
                last_image_url = COALESCE(excluded.last_image_url, profile_snapshots.last_image_url),
                local_image_path = COALESCE(excluded.local_image_path, profile_snapshots.local_image_path),
                raw_ocr = COALESCE(excluded.raw_ocr, profile_snapshots.raw_ocr),
                last_updated = excluded.last_updated
            ''',
            (
                guild_id,
                user_id,
                player_name,
                alliance,
                server,
                cp,
                kills,
                likes,
                vip_level,
                level,
                int(ownership_verified) if ownership_verified is not None else None,
                int(scan_valid) if scan_valid is not None else None,
                avatar_url,
                last_image_url,
                local_image_path,
                raw_ocr,
                now_ts,
            ),
        )
        await db.commit()


async def get_profile_snapshot(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT guild_id, user_id, player_name, alliance, server, cp, kills, likes,
                   vip_level, level, ownership_verified, scan_valid, avatar_url, last_image_url, local_image_path, raw_ocr, last_updated
            FROM profile_snapshots
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_profile_snapshots(
    guild_id: int, limit: int = 25, *, include_invalid: bool = True
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        where_clause = "" if include_invalid else "AND COALESCE(scan_valid, 1) = 1"
        async with db.execute(
            f"""
            SELECT guild_id, user_id, player_name, alliance, server, cp, kills, likes,
                   vip_level, level, ownership_verified, scan_valid, avatar_url, last_image_url,
                   local_image_path, raw_ocr, last_updated
            FROM profile_snapshots
            WHERE guild_id = ? {where_clause}
            ORDER BY last_updated DESC
            LIMIT ?
            """,
            (guild_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def set_profile_scan_valid(guild_id: int, user_id: int, is_valid: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE profile_snapshots SET scan_valid = ? WHERE guild_id = ? AND user_id = ?",
            (int(is_valid), guild_id, user_id),
        )
        await db.commit()


async def delete_profile_snapshot(guild_id: int, user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM profile_snapshots WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()


async def top_profile_stat(guild_id: int, column: str, limit: int = 10):
    allowed = {
        "cp": "cp",
        "kills": "kills",
        "likes": "likes",
        "vip_level": "vip_level",
        "level": "level",
    }
    target = allowed.get(column)
    if not target:
        return []

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f'''
            SELECT user_id, player_name, {target} as value
            FROM profile_snapshots
            WHERE guild_id = ? AND {target} IS NOT NULL AND COALESCE(scan_valid, 1) = 1
            ORDER BY {target} DESC
            LIMIT ?
            ''',
            (guild_id, limit),
        ) as cursor:
            return await cursor.fetchall()


async def top_global_profile_stat(column: str, limit: int = 10):
    allowed = {
        "cp": "cp",
        "kills": "kills",
        "likes": "likes",
        "vip_level": "vip_level",
        "level": "level",
    }
    target = allowed.get(column)
    if not target:
        return []

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f'''
            SELECT guild_id, user_id, player_name, server, {target} as value
            FROM profile_snapshots
            WHERE {target} IS NOT NULL AND COALESCE(scan_valid, 1) = 1
            ORDER BY {target} DESC
            LIMIT ?
            ''',
            (limit,),
        ) as cursor:
            return await cursor.fetchall()

# --- DUEL SCORE HELPERS ---


async def add_duel_score(
    guild_id: int,
    user_id: int,
    *,
    week_key: str,
    player_name: str | None = None,
    score_text: str | None = None,
    score_int: int | None = None,
    raw_ocr: str | None = None,
) -> None:
    now_ts = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO duel_scores (
                guild_id, user_id, week_key, player_name, score_text, score_int, raw_ocr, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                guild_id,
                user_id,
                week_key,
                player_name,
                score_text,
                score_int,
                raw_ocr,
                now_ts,
            ),
        )
        await db.commit()


async def get_latest_duel_score(guild_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT guild_id, user_id, week_key, player_name, score_text, score_int, raw_ocr, created_at
            FROM duel_scores
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_duel_scores_for_user(
    guild_id: int, user_id: int, limit: int = 10
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT guild_id, user_id, week_key, player_name, score_text, score_int, raw_ocr, created_at
            FROM duel_scores
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (guild_id, user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_latest_duel_week(guild_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT week_key
            FROM duel_scores
            WHERE guild_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_duel_weeks(guild_id: int, limit: int = 12) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT week_key, MAX(created_at) AS latest_scan
            FROM duel_scores
            WHERE guild_id = ?
            GROUP BY week_key
            ORDER BY latest_scan DESC
            LIMIT ?
            """,
            (guild_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_duel_leaderboard(
    guild_id: int, week_key: str, limit: int = 10
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT user_id,
                   player_name,
                   MAX(score_int) AS score_int,
                   MAX(score_text) AS score_text
            FROM duel_scores
            WHERE guild_id = ? AND week_key = ?
            GROUP BY user_id, player_name
            ORDER BY score_int DESC
            LIMIT ?
            """,
            (guild_id, week_key, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

# --- LEVELING HELPERS ---

async def _ensure_user(db: aiosqlite.Connection, guild_id: int, user_id: int) -> None:
    await db.execute(
        '''
        INSERT INTO user_stats (guild_id, user_id)
        VALUES (?, ?)
        ON CONFLICT(guild_id, user_id) DO NOTHING
        ''',
        (guild_id, user_id),
    )


async def get_user_stats(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_user(db, guild_id, user_id)
        # Persist the default row so read-only calls (like /profile) don't return empty
        # data until a write operation happens later in the session.
        await db.commit()
        async with db.execute(
            """
            SELECT guild_id, user_id, xp, level, last_msg_ts, last_scavenge_ts, scavenge_streak, discord_likes
            FROM user_stats
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ) as cursor:
            return await cursor.fetchone()


async def add_discord_like(guild_id: int, message_id: int, user_id: int, author_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_user(db, guild_id, author_id)
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO discord_message_likes (guild_id, message_id, user_id, author_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, message_id, user_id, author_id, datetime.now(timezone.utc).isoformat()),
        )
        if cursor.rowcount:
            await db.execute(
                """
                UPDATE user_stats
                SET discord_likes = discord_likes + 1
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, author_id),
            )
        await db.commit()
        return cursor.rowcount > 0


async def remove_discord_like(guild_id: int, message_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT author_id
            FROM discord_message_likes
            WHERE guild_id = ? AND message_id = ? AND user_id = ?
            """,
            (guild_id, message_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return False

        author_id = row["author_id"]
        await db.execute(
            """
            DELETE FROM discord_message_likes
            WHERE guild_id = ? AND message_id = ? AND user_id = ?
            """,
            (guild_id, message_id, user_id),
        )
        await db.execute(
            """
            UPDATE user_stats
            SET discord_likes = CASE
                WHEN discord_likes > 0 THEN discord_likes - 1
                ELSE 0
            END
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, author_id),
        )
        await db.commit()
        return True


async def update_user_xp(guild_id: int, user_id: int, xp_delta: int, new_level: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_user(db, guild_id, user_id)
        if new_level is None:
            await db.execute(
                """
                UPDATE user_stats
                SET xp = xp + ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (xp_delta, guild_id, user_id),
            )
        else:
            await db.execute(
                """
                UPDATE user_stats
                SET xp = ?, level = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (xp_delta, new_level, guild_id, user_id),
            )
        await db.commit()


async def add_to_inventory(guild_id: int, user_id: int, item_name: str, quantity: int, rarity: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_user(db, guild_id, user_id)
        await db.execute(
            '''
            INSERT INTO user_inventory (guild_id, user_id, item_id, quantity, rarity)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity
            ''',
            (guild_id, user_id, item_name, quantity, rarity),
        )
        await db.commit()


async def get_inventory(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_user(db, guild_id, user_id)
        async with db.execute(
            """
            SELECT item_id, quantity, rarity
            FROM user_inventory
            WHERE guild_id = ? AND user_id = ?
            ORDER BY rarity DESC, item_id ASC
            """,
            (guild_id, user_id),
        ) as cursor:
            return await cursor.fetchall()


async def remove_from_inventory(guild_id: int, user_id: int, item_name: str, quantity: int) -> bool:
    """Remove quantity of an item; returns True if successful."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_user(db, guild_id, user_id)
        async with db.execute(
            "SELECT quantity FROM user_inventory WHERE guild_id=? AND user_id=? AND item_id=?",
            (guild_id, user_id, item_name),
        ) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] < quantity:
                return False

        await db.execute(
            """
            UPDATE user_inventory
            SET quantity = quantity - ?
            WHERE guild_id=? AND user_id=? AND item_id=?
            """,
            (quantity, guild_id, user_id, item_name),
        )
        await db.execute(
            "DELETE FROM user_inventory WHERE quantity <= 0 AND guild_id=? AND user_id=? AND item_id=?",
            (guild_id, user_id, item_name),
        )
        await db.commit()
    return True


async def transfer_inventory(guild_id: int, sender: int, receiver: int, item_name: str, quantity: int) -> bool:
    """Atomic transfer of loot between survivors."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_user(db, guild_id, sender)
        await _ensure_user(db, guild_id, receiver)
        async with db.execute(
            "SELECT quantity, rarity FROM user_inventory WHERE guild_id=? AND user_id=? AND item_id=?",
            (guild_id, sender, item_name),
        ) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] < quantity:
                return False
            rarity = row[1]

        await db.execute(
            """
            UPDATE user_inventory
            SET quantity = quantity - ?
            WHERE guild_id=? AND user_id=? AND item_id=?
            """,
            (quantity, guild_id, sender, item_name),
        )
        await db.execute(
            "DELETE FROM user_inventory WHERE quantity <= 0 AND guild_id=? AND user_id=? AND item_id=?",
            (guild_id, sender, item_name),
        )
        await db.execute(
            '''
            INSERT INTO user_inventory (guild_id, user_id, item_id, quantity, rarity)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity
            ''',
            (guild_id, receiver, item_name, quantity, rarity),
        )
        await db.commit()
    return True


async def log_inventory_transfer(
    guild_id: int,
    channel_id: int,
    sender_id: int,
    receiver_id: int,
    item_name: str,
    quantity: int,
) -> None:
    """Persist a transfer audit entry for inventory movement."""
    created_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO inventory_transfers
                (guild_id, channel_id, sender_id, receiver_id, item_id, quantity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (guild_id, channel_id, sender_id, receiver_id, item_name, quantity, created_at),
        )
        await db.commit()


async def update_scavenge_time(guild_id: int, user_id: int, streak: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_user(db, guild_id, user_id)
        if streak is None:
            await db.execute(
                """
                UPDATE user_stats
                SET last_scavenge_ts = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (datetime.now(GAME_TZ).timestamp(), guild_id, user_id),
            )
        else:
            await db.execute(
                """
                UPDATE user_stats
                SET last_scavenge_ts = ?, scavenge_streak = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (datetime.now(GAME_TZ).timestamp(), streak, guild_id, user_id),
            )
        await db.commit()


async def guild_analytics_snapshot(guild_id: int) -> dict:
    """Return per-guild counts for analytics dashboards."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async def fetch_value(query: str, params: tuple = ()):
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

        trade_total = await fetch_value(
            "SELECT COUNT(*) FROM trade_pool WHERE guild_id = ?", (guild_id,)
        )
        traders = await fetch_value(
            "SELECT COUNT(DISTINCT user_id) FROM trade_pool WHERE guild_id = ?", (guild_id,)
        )
        missions_active = await fetch_value(
            "SELECT COUNT(*) FROM server_missions WHERE guild_id = ?", (guild_id,)
        )
        templates_saved = await fetch_value(
            "SELECT COUNT(*) FROM server_templates WHERE guild_id = ?", (guild_id,)
        )
        survivors_tracked = await fetch_value(
            "SELECT COUNT(*) FROM user_stats WHERE guild_id = ?", (guild_id,)
        )
        total_items = await fetch_value(
            "SELECT COALESCE(SUM(quantity), 0) FROM user_inventory WHERE guild_id = ?",
            (guild_id,),
        )

        return {
            "trade_listings": trade_total,
            "traders": traders,
            "missions_active": missions_active,
            "templates": templates_saved,
            "survivors_tracked": survivors_tracked,
            "items": total_items,
        }


async def global_analytics_snapshot() -> dict:
    """Return global counts for analytics dashboards across all guilds."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async def fetch_value(query: str, params: tuple = ()):
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

        trade_total = await fetch_value("SELECT COUNT(*) FROM trade_pool")
        traders = await fetch_value("SELECT COUNT(DISTINCT user_id) FROM trade_pool")
        missions_active = await fetch_value("SELECT COUNT(*) FROM server_missions")
        templates_saved = await fetch_value("SELECT COUNT(*) FROM server_templates")
        survivors_tracked = await fetch_value("SELECT COUNT(*) FROM user_stats")
        total_items = await fetch_value("SELECT COALESCE(SUM(quantity), 0) FROM user_inventory")

        return {
            "trade_listings": trade_total,
            "traders": traders,
            "missions_active": missions_active,
            "templates": templates_saved,
            "survivors_tracked": survivors_tracked,
            "items": total_items,
        }


async def top_xp_leaderboard(guild_id: int, limit: int = 10):
    """Return top survivors by XP for a guild."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT user_id, xp, level
            FROM user_stats
            WHERE guild_id = ?
            ORDER BY level DESC, xp DESC
            LIMIT ?
            """,
            (guild_id, limit),
        ) as cursor:
            return await cursor.fetchall()

# --- REMINDER TEMPLATE HELPERS ---


async def seed_reminder_templates(guild_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM reminder_template_seed WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            if await cursor.fetchone():
                return

        for template in REMINDER_TEMPLATE_STARTER:
            await db.execute(
                '''
                INSERT OR IGNORE INTO reminder_templates (guild_id, template_name, body)
                VALUES (?, ?, ?)
                ''',
                (guild_id, template["template_name"], template["body"]),
            )

        await db.execute(
            "INSERT OR IGNORE INTO reminder_template_seed (guild_id) VALUES (?)",
            (guild_id,),
        )
        await db.commit()


async def get_reminder_templates(guild_id: int):
    await seed_reminder_templates(guild_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reminder_templates WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            return await cursor.fetchall()


async def add_reminder_template(guild_id: int, name: str, body: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO reminder_templates (guild_id, template_name, body)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, template_name) DO UPDATE SET body = excluded.body
            ''',
            (guild_id, name, body),
        )
        await db.commit()


async def delete_reminder_template(guild_id: int, name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM reminder_templates WHERE guild_id = ? AND template_name = ?",
            (guild_id, name),
        )
        await db.commit()


async def add_scheduled_reminder(
    guild_id: int,
    channel_id: int,
    creator_id: int,
    body: str,
    send_at_utc: str,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO scheduled_reminders (guild_id, channel_id, creator_id, body, send_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, creator_id, body, send_at_utc),
        )
        await db.commit()
        return cursor.lastrowid


async def get_scheduled_reminders(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, channel_id, creator_id, body, send_at_utc
            FROM scheduled_reminders
            WHERE guild_id = ?
            ORDER BY send_at_utc ASC
            """,
            (guild_id,),
        ) as cursor:
            return await cursor.fetchall()


async def delete_scheduled_reminder(guild_id: int, reminder_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM scheduled_reminders WHERE guild_id = ? AND id = ?",
            (guild_id, reminder_id),
        )
        await db.commit()


# --- MISSION & TEMPLATE HELPERS ---

async def get_templates(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM server_templates WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchall()

async def add_template(guild_id, name, description):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO server_templates (guild_id, template_name, description)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, template_name) DO UPDATE SET description = excluded.description
        ''', (guild_id, name, description))
        await db.commit()

async def delete_template(guild_id, name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM server_templates WHERE guild_id = ? AND template_name = ?", (guild_id, name))
        await db.commit()

async def get_all_active_missions():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM server_missions") as cursor:
            return await cursor.fetchall()

async def get_guild_missions(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM server_missions WHERE guild_id = ? ORDER BY target_utc",
            (guild_id,),
        ) as cursor:
            return await cursor.fetchall()

async def get_upcoming_missions(guild_id, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        async with db.execute(
            """
            SELECT * FROM server_missions
            WHERE guild_id = ? AND target_utc > ?
            ORDER BY target_utc
            LIMIT ?
            """,
            (guild_id, now_iso, limit),
        ) as cursor:
            return await cursor.fetchall()

async def add_mission(guild_id, codename, description, target_time, target_utc, location=None, ping_role_id=None, tag=None, notes=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO server_missions (guild_id, codename, description, target_time, target_utc, location, ping_role_id, tag, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, codename) DO UPDATE SET
                description = excluded.description,
                target_time = excluded.target_time,
                target_utc = excluded.target_utc,
                location = excluded.location,
                ping_role_id = excluded.ping_role_id,
                tag = excluded.tag,
                notes = excluded.notes
        ''', (guild_id, codename, description, target_time, target_utc, location, ping_role_id, tag, notes))
        await db.commit()

async def delete_mission(guild_id, codename):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM server_missions WHERE guild_id = ? AND codename = ?", (guild_id, codename))
        await db.execute(
            "DELETE FROM mission_dm_prompts WHERE guild_id = ? AND codename = ?",
            (guild_id, codename),
        )
        await db.execute(
            "DELETE FROM mission_dm_opt_ins WHERE guild_id = ? AND codename = ?",
            (guild_id, codename),
        )
        await db.execute(
            "DELETE FROM mission_rsvp_prompts WHERE guild_id = ? AND codename = ?",
            (guild_id, codename),
        )
        await db.execute(
            "DELETE FROM mission_rsvps WHERE guild_id = ? AND codename = ?",
            (guild_id, codename),
        )
        await db.commit()


async def upsert_dm_prompt(guild_id: int, codename: str, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO mission_dm_prompts (guild_id, codename, message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET guild_id = excluded.guild_id, codename = excluded.codename
            ''',
            (guild_id, codename, message_id),
        )
        await db.commit()


async def lookup_dm_prompt(message_id: int) -> tuple[int, str] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guild_id, codename FROM mission_dm_prompts WHERE message_id = ?",
            (message_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return (row[0], row[1]) if row else None


async def add_mission_opt_in(guild_id: int, codename: str, user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT OR IGNORE INTO mission_dm_opt_ins (guild_id, codename, user_id)
            VALUES (?, ?, ?)
            ''',
            (guild_id, codename, user_id),
        )
        await db.commit()


async def get_mission_opt_ins(guild_id: int, codename: str) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM mission_dm_opt_ins WHERE guild_id = ? AND codename = ?",
            (guild_id, codename),
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def clear_mission_opt_ins(guild_id: int, codename: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM mission_dm_prompts WHERE guild_id = ? AND codename = ?",
            (guild_id, codename),
        )
        await db.execute(
            "DELETE FROM mission_dm_opt_ins WHERE guild_id = ? AND codename = ?",
            (guild_id, codename),
        )
        await db.commit()


async def upsert_rsvp_prompt(guild_id: int, codename: str, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO mission_rsvp_prompts (guild_id, codename, message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET guild_id = excluded.guild_id, codename = excluded.codename
            ''',
            (guild_id, codename, message_id),
        )
        await db.commit()


async def lookup_rsvp_prompt(message_id: int) -> tuple[int, str] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guild_id, codename FROM mission_rsvp_prompts WHERE message_id = ?",
            (message_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return (row[0], row[1]) if row else None


async def set_rsvp_status(guild_id: int, codename: str, user_id: int, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO mission_rsvps (guild_id, codename, user_id, status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, codename, user_id) DO UPDATE SET status = excluded.status
            ''',
            (guild_id, codename, user_id, status),
        )
        await db.commit()


async def remove_rsvp_status(guild_id: int, codename: str, user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM mission_rsvps WHERE guild_id = ? AND codename = ? AND user_id = ?",
            (guild_id, codename, user_id),
        )
        await db.commit()


async def get_rsvp_counts(guild_id: int, codename: str) -> dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            '''
            SELECT status, COUNT(*) as total
            FROM mission_rsvps
            WHERE guild_id = ? AND codename = ?
            GROUP BY status
            ''',
            (guild_id, codename),
        ) as cursor:
            rows = await cursor.fetchall()
            counts = {"going": 0, "maybe": 0, "no": 0}
            for status, total in rows:
                if status in counts:
                    counts[status] = total
            return counts


async def get_rsvp_members(
    guild_id: int, codename: str, *, status: str = "going"
) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            '''
            SELECT user_id
            FROM mission_rsvps
            WHERE guild_id = ? AND codename = ? AND status = ?
            ''',
            (guild_id, codename, status),
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def clear_rsvp_data(guild_id: int, codename: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM mission_rsvp_prompts WHERE guild_id = ? AND codename = ?",
            (guild_id, codename),
        )
        await db.execute(
            "DELETE FROM mission_rsvps WHERE guild_id = ? AND codename = ?",
            (guild_id, codename),
        )
        await db.commit()
