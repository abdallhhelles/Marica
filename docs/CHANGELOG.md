# Changelog

All notable changes to Marcia are documented in this file.

## [Unreleased] - Code Organization Refactor

### Added
- Created `utils/` package for shared utility modules
  - `utils/assets.py` - Static data (quotes, lore, constants)
  - `utils/time_utils.py` - Game timezone helpers (UTC-2)
  - `utils/bug_logging.py` - Error logging and Discord notifications
  - `utils/patch_notes.py` - Release notes persistence
- Created `config/` directory for configuration templates
- Added README files to `utils/` and `config/` directories
- Added type hints to database helper functions for better code safety
- Enhanced project structure documentation in main README
- Documented runtime cache directories (`shots/`) and test coverage (`tests/`)

### Changed
- Reorganized project file structure for better maintainability
- Updated all import statements across 16 Python files to use new structure
- Moved configuration JSON files to `config/` directory
- Updated `.gitignore` to exclude:
  - `.local/` directory (pip artifacts)
  - `data/*.db` and `data/backups/` (database files)
  - `data/logs/` (log files)
- Removed obsolete refactoring and verification documentation to reduce clutter

### Improved
- Better separation of concerns across modules
- Cleaner import structure with `utils.*` pattern
- More maintainable codebase organization
- Enhanced documentation throughout the project

### Security
- Ran CodeQL security scan: 0 vulnerabilities detected
- All Python files compile successfully with no errors

### Migration Notes
- All changes are backward compatible
- Old import paths automatically updated
- No database schema changes required

---

## Project Structure (After Refactor)

```
Marica/
├── cogs/              # Discord command modules (features)
│   ├── akrott.py      # Translation and internationalization
│   ├── archives.py    # Message archiving system
│   ├── automation.py  # Welcome/farewell automation
│   ├── devhub.py      # Developer tools and analytics
│   ├── events.py      # Mission scheduling and reminders
│   ├── leveling.py    # XP system and scavenging
│   ├── missions.py    # Mission management
│   ├── profile_scanner.py # OCR profile scanning
│   ├── reminders.py   # Reminder system
│   ├── settings.py    # Server configuration wizard
│   ├── trading.py     # Fish trading system
│   └── utility.py     # General utility commands
├── utils/             # Shared utilities (NEW)
│   ├── __init__.py
│   ├── assets.py      # Static game data
│   ├── bug_logging.py # Error handling
│   ├── patch_notes.py # Release notes
│   └── time_utils.py  # Timezone helpers
├── config/            # Configuration templates (NEW)
│   ├── README.md
│   ├── templates.json
│   └── trade_config.json
├── data/              # Runtime data (auto-created)
│   ├── marcia_os.db   # Main database
│   ├── backups/       # Database backups
│   └── logs/          # Application logs
├── docs/              # Documentation
│   ├── USAGE.md
│   └── OCR_SETUP.md
├── ocr/               # Profile scanning OCR
│   ├── boxes_ratios.json
│   ├── box_picker.py
│   ├── diagnostics.py
│   └── ocr_runner.py
├── shots/             # Cached profile screenshots & temp OCR inputs
├── tests/             # Automated test coverage
├── main.py            # Bot entry point
├── database.py        # Database operations
└── requirements.txt   # Python dependencies
```
