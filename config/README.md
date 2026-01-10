# Configuration Files

This directory contains static configuration templates used by Marcia OS.

## Files

* **templates.json** - Event and operation templates for common mission types
* **trade_config.json** - Active trading channel configurations

## Usage

These files are maintained for reference and backup purposes. Most configuration is now managed through Discord commands:

* Use `/setup` for initial server configuration
* Use `/event` to create and manage operations
* Use `/setup_trade` for trading system configuration

Configuration data is persisted in the SQLite database at `data/marcia_os.db`.
