# Changelog

All notable changes to Marcia are documented in this file.

## [Unreleased]

### Changed
- Synced root `README.md`, `docs/README.md`, and `docs/USAGE.md` to match the current command surface and deployment reality.
  - Replaced legacy command references (`/event_remove`, `/events`, `/profile_stats`, `/profile_leaderboard`, `/trade_item`) with active workflows (`/event`, `/profile`, `/leaderboard`, `/scan_status`, `/profile_review`).
  - Clarified install profiles:
    - `requirements.txt` = full install (includes OCR stack)
    - `requirements-lite.txt` = lightweight install (no OCR)
    - `requirements-ocr.txt` = OCR add-on for lite installs
- Added a dedicated feature planning document: `docs/FEATURE_IDEAS.md`.

### Documentation
- Added a "Feature ideas backlog" section and links in primary docs for easier roadmap discovery.
- Kept ops language consistent around scan review, event flows, and OCR diagnostics.

---

## [Previous] - Code Organization Refactor

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
