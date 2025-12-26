# 📂 MARICA OS v3.0 | Helles Hub Tactical Bot

![Status](https://img.shields.io/badge/Status-Online-brightgreen)
![Library](https://img.shields.io/badge/Library-Discord.py-blue)
![License](https://img.shields.io/badge/License-Private-red)

> *"Freedom is expensive. Don't waste my time for free."* — **Marcia**

**Marcia** is a custom tactical bot built for the **Helles Hub Alliance**. She is a cunning hacker turned hub guardian who manages survivor ranks, wasteland scavenging, and the "Fish-Link" trade network.

---

## 🛠️ System Features

### 1. 🎣 Fish-Link Network
A dynamic, auto-anchored trading interface for the Arctic Ice Pit.
* **Matchmaking:** Marcia automatically DMs users when a duplicate fish matches their "Wanted" list.
* **UI Anchoring:** The trade menu automatically stays at the bottom of the channel, even during heavy chat.
* **Management:** Users can easily add extras, find needs, and clear their listings.

### 2. 🧟 Survivor Progression
* **XP System:** Survivors earn 10 XP per message (with a 60-second cooldown).
* **Auto-Ranks:** Automatic role rewards at Level 5 (Scout), Level 10 (Veteran), and Level 20 (Alliance Elite).
* **Scavenging:** Deploy drones once an hour to find supplies like Stim-packs or Canned Beans and gain bonus XP.

### 3. 🚁 Commander Protocols
* **Event Management:** Set up missions with automated reminders at T-minus 60, 30, 15, 3, and 0 minutes.
* **Intel Database:** Quick-access information regarding hub rules, roles, and lore.
* **Translations:** React with a flag emoji to have Marcia decode messages into any language using Google Translate.

---

## 🚀 Installation & Setup

### 1. Requirements
* Python 3.8+
* `discord.py`
* `googletrans==3.1.0a0`
* `python-dotenv`

### 2. Local Setup
1. Clone this repository to your private server.
2. Create a `.env` file in the root directory:
```env
TOKEN=your_discord_bot_token_here
