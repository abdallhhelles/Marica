"""
FILE: database.py
USE: Persistent storage for multi-server configurations and trading.
FEATURES: Server-specific trading network, settings, and migration logic.
"""
import os
import shutil
from pathlib import Path

import aiosqlite
from datetime import datetime, timezone
import logging

from time_utils import GAME_TZ

logger = logging.getLogger('MarciaOS.DB')

# Persist data alongside the codebase (data/marcia_os.db) unless overridden.
_BASE_DIR = Path(__file__).resolve().parent
_DEFAULT_PATH = _BASE_DIR / "data" / "marcia_os.db"
_ENV_PATH = os.getenv("MARCIA_DB_PATH")
DB_PATH_OBJ = Path(_ENV_PATH).expanduser() if _ENV_PATH else _DEFAULT_PATH


def _migrate_legacy_db(dest: Path) -> None:
    """Promote older DB files into the canonical location if present."""
    legacy_paths = [
        Path.home() / "marcia_data" / "marcia_os.db",
        _BASE_DIR / "marcia_os.db",
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


_migrate_legacy_db(DB_PATH_OBJ)
DB_PATH_OBJ.parent.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DB_PATH_OBJ)

async def init_db():
    """Initializes the database and migrates legacy data if found."""
    logger.info("🗄️ Database path: %s", DB_PATH)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")

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
                auto_role_id INTEGER,
                server_offset_hours INTEGER DEFAULT -2
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
                PRIMARY KEY (guild_id, user_id)
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

        # 7. Command usage telemetry (guild-isolated)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS command_usage (
                guild_id INTEGER,
                command_name TEXT,
                uses INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, command_name)
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
        await db.commit()

        # Backfill newer mission fields for older installs
        await _ensure_column(db, "server_missions", "location", "TEXT")
        await _ensure_column(db, "server_missions", "ping_role_id", "INTEGER")
        await _ensure_column(db, "server_missions", "tag", "TEXT")
        await _ensure_column(db, "server_missions", "notes", "TEXT")

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

# --- TRADING HELPERS ---

async def add_fish_to_inventory(guild_id, user_id, rarity, index, trade_type):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR IGNORE INTO trade_pool (guild_id, user_id, fish_rarity, fish_index, type)
            VALUES (?, ?, ?, ?, ?)
        ''', (guild_id, user_id, rarity, index, trade_type))
        await db.commit()

async def get_fish_inventory(guild_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM trade_pool 
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id)) as cursor:
            return await cursor.fetchall()

# --- SERVER SETTINGS HELPERS ---

async def get_settings(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM settings WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_setting(guild_id, column, value, server_name=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'''
            INSERT INTO settings (guild_id, server_name, {column}) 
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET 
                {column} = excluded.{column},
                server_name = COALESCE(excluded.server_name, settings.server_name)
        ''', (guild_id, server_name, value))
        await db.commit()

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
        async with db.execute(
            """
            SELECT guild_id, user_id, xp, level, last_msg_ts, last_scavenge_ts
            FROM user_stats
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ) as cursor:
            return await cursor.fetchone()


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


async def update_scavenge_time(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_user(db, guild_id, user_id)
        await db.execute(
            """
            UPDATE user_stats
            SET last_scavenge_ts = ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (datetime.now(GAME_TZ).timestamp(), guild_id, user_id),
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
        await db.commit()