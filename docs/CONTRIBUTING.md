# Contributing to Marcia OS

Thank you for your interest in contributing to Marcia OS! This guide will help you understand the codebase structure and best practices.

## Code Organization

### Directory Structure

```
Marcia/
├── cogs/         # Feature modules (Discord commands)
├── utils/        # Shared utilities and helpers
├── config/       # Static configuration templates
├── legacy/       # Deprecated migration data
├── data/         # Runtime data (auto-generated)
├── docs/         # User documentation
└── ocr/          # OCR profile scanning system
```

### Adding New Features

1. **New Commands**: Add them to the appropriate cog in `cogs/`
   - Each cog should focus on a specific feature domain
   - Use existing cogs as templates for structure

2. **Shared Utilities**: Place in `utils/`
   - `utils/assets.py` - Static game data, quotes, constants
   - `utils/time_utils.py` - Timezone conversion helpers
   - `utils/bug_logging.py` - Error logging utilities
   - `utils/patch_notes.py` - Release notes management

3. **Database Changes**: Update `database.py`
   - Add schema changes to `init_db()`
   - Create helper functions for new tables
   - Include migration logic when needed

## Code Style

### Imports

Use the new organized import structure:

```python
# Standard library imports first
import asyncio
import logging
from datetime import datetime

# Third-party imports
import discord
from discord.ext import commands

# Local imports (use utils.* pattern)
from utils.assets import MARCIA_QUOTES
from utils.time_utils import GAME_TZ
from database import get_settings
```

### Type Hints

Add type hints to new functions for better code safety:

```python
async def get_user_data(guild_id: int, user_id: int) -> dict | None:
    # Function implementation
    pass

async def update_setting(column: str, value: int | str | None) -> None:
    # Function implementation
    pass
```

### Docstrings

Use clear docstrings for complex functions:

```python
async def complex_operation(param: str) -> bool:
    """
    Perform a complex operation with the given parameter.
    
    Args:
        param: Description of the parameter
        
    Returns:
        True if successful, False otherwise
    """
    pass
```

## Database Best Practices

1. **Always use parameterized queries** to prevent SQL injection:
   ```python
   await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
   ```

2. **Use transactions** for multi-step operations:
   ```python
   async with aiosqlite.connect(DB_PATH) as db:
       await db.execute(...)
       await db.execute(...)
       await db.commit()
   ```

3. **Add indexes** for frequently queried columns:
   ```python
   await db.execute("CREATE INDEX IF NOT EXISTS idx_name ON table(column)")
   ```

## Error Handling

Use the centralized error logging system:

```python
from utils.bug_logging import log_command_exception

try:
    # Your code here
    pass
except Exception as error:
    await log_command_exception(
        bot, error, 
        ctx=ctx, 
        source="command-name"
    )
```

## Testing

Before submitting changes:

1. **Syntax check**: Ensure all files compile
   ```bash
   python3 -m py_compile main.py database.py cogs/*.py utils/*.py
   ```

2. **Security scan**: Run CodeQL if available
   ```bash
   # Will be run automatically in CI
   ```

3. **Manual testing**: Test your changes in a development server
   - Create a test Discord server
   - Test all affected commands
   - Verify database changes work correctly

## Git Workflow

1. Create a descriptive branch name:
   ```bash
   git checkout -b feature/add-new-command
   git checkout -b fix/trading-bug
   git checkout -b refactor/optimize-database
   ```

2. Make focused commits:
   ```bash
   git commit -m "Add new leaderboard sorting option"
   git commit -m "Fix: Resolve trading inventory duplication issue"
   ```

3. Keep commits small and focused on a single change

## File Organization Rules

- **Don't commit** to root directory unless it's a core file (main.py, database.py, requirements.txt)
- **Place utilities** in `utils/` not in root
- **Place configs** in `config/` not in root
- **Don't commit** database files, logs, or cache files (they're in .gitignore)
- **Document** new directories with a README.md

## Questions?

If you have questions about the codebase structure or contribution guidelines, please:
1. Check existing code for similar patterns
2. Review the documentation in `docs/`
3. Open an issue for clarification

Thank you for contributing to Marcia OS!
