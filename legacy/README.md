# Legacy Data

This directory contains deprecated data files that are maintained only for migration purposes.

## Files

* **levels.json** - Legacy user XP and inventory data. Use `/import_old_levels` command to migrate to the database.

## Migration

If you have an old `levels.json` file from a previous version of Marcia OS:
1. Place it in this `legacy/` directory
2. Run `/import_old_levels` in your Discord server (requires Manage Server permission)
3. The data will be imported into the SQL database

**Note:** After successful migration, you can safely delete or archive the JSON file.
