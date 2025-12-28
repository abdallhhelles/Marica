# Privacy Policy for Marcia OS
**Last Updated: January 2026**

Marcia OS ("the bot") is operated for the Helles Hub Alliance and public servers. This policy explains what data we collect and how it is used.

### 1. Data We Collect
* **Discord identifiers:** User IDs, guild IDs, and role IDs to deliver leveling, inventories, reminders, and Fish-Link matches.
* **Event and analytics data:** Operation codenames, schedules (UTC-2 timestamps), tags, and aggregated counts per guild.
* **Message metadata:** Timestamps to enforce XP and scavenging cooldowns; translation requests trigger temporary processing of the original message text.
* **Inventory & trade data:** Items found via scavenging, trade listings, and template data are stored per guild.

### 2. How We Use Data
* **Leveling & progression:** Track XP, levels, loot, and prestige progress for each guild separately.
* **Reminders & events:** Schedule and post announcements using server-linked channels and optional role mentions.
* **Trading:** Match spare/wanted fish or items and DM participants when a match appears.
* **Diagnostics:** Generate per-guild analytics so admins can audit usage; data is never shared across guilds.

### 3. Storage & Retention
* Data is stored in the SQLite database `marcia_os.db` and server-specific archive files on the host.
* Trading, leveling, event, and template records are scoped to each guild and are not shared between servers.
* Data persists while the bot is installed. Removing the bot or requesting deletion from a server admin will purge that server’s records where feasible.

### 4. Third-Party Sharing
* We do **not** sell data.
* Translation requests may send message text to Google Translate; we do not retain these texts after processing.

### 5. Your Controls
* Remove your trade listings via the Fish-Link UI or ask an admin to clear your data.
* Server admins can delete templates or missions and may request a guild data wipe.
* For questions or deletion requests, contact the server’s alliance leadership or the bot maintainers.
