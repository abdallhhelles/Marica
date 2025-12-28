"""
FILE: database.py
USE: Persistent storage for multi-server configurations and trading.
FEATURES: Server-specific trading network, settings, and migration logic.
"""
import aiosqlite
from datetime import datetime
import logging

logger = logging.getLogger('MarciaOS.DB')
DB_PATH = "marcia_os.db"

async def init_db():
    """Initializes the database and migrates legacy data if found."""
    async with aiosqlite.connect(DB_PATH) as db:
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
        await db.commit()
        
    print("📡 MARCIA OS | Database Core Synchronized (Trading, Missions & Config).")

# --- SYSTEM LOG HELPERS ---

async def can_run_daily_task(task_name, date_str=None):
    today = date_str or datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_run_date FROM system_logs WHERE task_name = ?", (task_name,)) as cursor:
            row = await cursor.fetchone()
            return not (row and row[0] == today)

async def mark_task_complete(task_name, date_str=None):
    today = date_str or datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO system_logs (task_name, last_run_date) 
            VALUES (?, ?) 
            ON CONFLICT(task_name) DO UPDATE SET last_run_date = excluded.last_run_date
        ''', (task_name, today))
        await db.commit()

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
            return await cursor.fetchone()

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

async def add_mission(guild_id, codename, description, target_time, target_utc):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO server_missions (guild_id, codename, description, target_time, target_utc)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, codename) DO UPDATE SET 
                description = excluded.description, 
                target_time = excluded.target_time, 
                target_utc = excluded.target_utc
        ''', (guild_id, codename, description, target_time, target_utc))
        await db.commit()

async def delete_mission(guild_id, codename):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM server_missions WHERE guild_id = ? AND codename = ?", (guild_id, codename))
        await db.commit()