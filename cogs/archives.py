"""
FILE: cogs/archives.py
USE: Local file-system logging for server intel and member activity. All logging is silent-no Discord messages are sent while
backfilling or recording events.
"""
import asyncio
import datetime
import json
import logging
import os
from typing import AsyncIterator

import discord
from discord.ext import commands

from database import is_channel_ignored
from utils.async_utils import create_tracked_task

logger = logging.getLogger("MarciaOS.Archives")

class Archives(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.root_dir = "archives"
        if not os.path.exists(self.root_dir):
            os.makedirs(self.root_dir)

        # Server-scoped chat logging
        self.chat_log_server_id = 1403997721962086480
        self._seeded_channels: set[int] = set()

    def _channel_log_name(self, channel: discord.abc.GuildChannel) -> str:
        safe_name = str(channel.name).replace(" ", "_") or "channel"
        return f"{safe_name}_{channel.id}.log"

    def get_server_path(self, guild):
        # Creates a folder named "ServerName_ID"
        folder_name = f"{guild.name.replace(' ', '_')}_{guild.id}"
        path = os.path.join(self.root_dir, folder_name)
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    async def update_server_files(self, guild):
        path = self.get_server_path(guild)

        # 1. Server Info File
        server_info_path = os.path.join(path, "server_info.txt")
        server_info = (
            f"SERVER: {guild.name}\n"
            f"ID: {guild.id}\n"
            f"OWNER: {guild.owner} ({guild.owner_id})\n"
            f"CREATED: {guild.created_at}\n"
            f"MEMBERS: {guild.member_count}\n"
        )
        await self._write_text(server_info_path, server_info)

        # 2. Member List File (JSON for easy reading)
        member_data = []
        for m in guild.members:
            member_data.append({
                "username": str(m),
                "id": m.id,
                "roles": [r.name for r in m.roles if r.name != "@everyone"],
                "joined_at": str(m.joined_at)
            })
        members_path = os.path.join(path, "members.json")
        await self._write_json(members_path, member_data)

    async def log_action(self, guild, user, action):
        path = self.get_server_path(guild)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self._append_text(
            os.path.join(path, "actions.log"),
            f"[{timestamp}] {user} ({user.id}): {action}\n",
        )

    def _should_log_message(self, guild):
        return guild and guild.id == self.chat_log_server_id

    def _seed_marker_path(self, guild: discord.Guild) -> str:
        return os.path.join(self.get_server_path(guild), "_history_seeded")

    async def _restore_seed_state(self, guild: discord.Guild):
        """Hydrate the in-memory seeded cache from disk markers."""
        try:
            payload = await asyncio.to_thread(self._read_json, self._seed_marker_path(guild))
        except FileNotFoundError:
            return
        except Exception:
            return

        for cid in payload.get("channels", []):
            try:
                self._seeded_channels.add(int(cid))
            except (TypeError, ValueError):
                continue

    async def _persist_seed_marker(self, guild: discord.Guild):
        """Write a marker file documenting which channels have been backfilled."""
        channels = sorted(self._seeded_channels)
        payload = {
            "guild_id": guild.id,
            "seeded_at": datetime.datetime.utcnow().isoformat() + "Z",
            "channels": channels,
        }

        try:
            await self._write_json(self._seed_marker_path(guild), payload)
        except Exception:
            return

    async def _write_chat_log(self, guild, channel, line, *, timestamp: datetime.datetime | None = None):
        path = self.get_server_path(guild)
        log_name = self._channel_log_name(channel)
        stamp = (timestamp or datetime.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        await self._append_text(
            os.path.join(path, log_name),
            f"[{stamp}] {line}\n",
        )

    def _dm_log_path(self, user: discord.User | discord.Member) -> str:
        safe_name = str(user).replace(" ", "_") or "user"
        path = os.path.join(self.root_dir, "dms", f"{safe_name}_{user.id}")
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, "dm.log")

    async def _write_dm_log(
        self,
        user: discord.User | discord.Member,
        line: str,
        *,
        timestamp: datetime.datetime | None = None,
    ) -> None:
        stamp = (timestamp or datetime.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        await self._append_text(self._dm_log_path(user), f"[{stamp}] {line}\n")

    async def _write_text(self, path: str, content: str) -> None:
        await asyncio.to_thread(self._write_text_sync, path, content)

    async def _append_text(self, path: str, content: str) -> None:
        await asyncio.to_thread(self._append_text_sync, path, content)

    async def _write_json(self, path: str, payload: object) -> None:
        await asyncio.to_thread(self._write_json_sync, path, payload)

    @staticmethod
    def _write_text_sync(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _append_text_sync(path: str, content: str) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _write_json_sync(path: str, payload: object) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)

    @staticmethod
    def _read_json(path: str) -> object:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _dm_log_user(self, message: discord.Message) -> discord.User | discord.Member:
        recipient = getattr(message.channel, "recipient", None)
        return recipient or message.author

    def _format_attachments(self, message: discord.Message) -> str:
        if not message.attachments:
            return ""
        urls = ", ".join(att.url for att in message.attachments)
        return f" | Attachments: {urls}"

    async def _iter_log_targets(
        self, guild: discord.Guild
    ) -> AsyncIterator[discord.abc.GuildChannel]:
        """Yield text channels and their threads so we can log them consistently."""

        for channel in guild.text_channels:
            yield channel

            # Active threads the bot can currently see
            for thread in channel.threads:
                yield thread

            # Archived threads are not covered by channel.threads; fetch both public
            # and private archives to ensure historical messages are captured.
            for private in (False, True):
                try:
                    async for thread in channel.archived_threads(limit=None, private=private):
                        yield thread
                except Exception:
                    continue

    @commands.Cog.listener()
    async def on_ready(self):
        # When bot starts, update info for all servers
        for guild in self.bot.guilds:
            await self.update_server_files(guild)

            # Hydrate seeded cache so we do not double-write history on restarts
            await self._restore_seed_state(guild)

            if self._should_log_message(guild):
                async for channel in self._iter_log_targets(guild):
                    if channel.id not in self._seeded_channels:
                        create_tracked_task(
                            self._seed_chat_history(guild, channel),
                            name=f"archive-seed-{channel.id}",
                            logger=logger,
                        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if (
            isinstance(channel, discord.TextChannel)
            and self._should_log_message(channel.guild)
            and channel.id not in self._seeded_channels
        ):
            create_tracked_task(
                self._seed_chat_history(channel.guild, channel),
                name=f"archive-seed-{channel.id}",
                logger=logger,
            )

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if (
            self._should_log_message(thread.guild)
            and thread.id not in self._seeded_channels
        ):
            create_tracked_task(
                self._seed_chat_history(thread.guild, thread),
                name=f"archive-seed-{thread.id}",
                logger=logger,
            )

    @commands.Cog.listener()
    async def on_command(self, ctx):
        # Logs every command used
        if ctx.guild:
            await self.log_action(ctx.guild, ctx.author, f"Command executed: {ctx.prefix}{ctx.command}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        # Logs every button click (Trade terminal etc)
        if interaction.guild and interaction.data:
            custom_id = interaction.data.get("custom_id", "Unknown UI Interaction")
            await self.log_action(interaction.guild, interaction.user, f"UI Interaction: {custom_id}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            log_user = self._dm_log_user(message)
            channel_info = f"DM ({message.channel.id})"
            content = message.content or "[No content]"
            line = (
                f"DM MESSAGE {message.id} | {channel_info} | "
                f"{message.author} ({message.author.id}): {content}"
            )
            line += self._format_attachments(message)
            await self._write_dm_log(log_user, line)
            return

        if not self._should_log_message(message.guild):
            return

        if await is_channel_ignored(message.guild.id, message.channel.id):
            return

        channel_info = f"#{message.channel.name} ({message.channel.id})"
        content = message.content or "[No content]"
        line = (
            f"MESSAGE {message.id} | {channel_info} | "
            f"{message.author} ({message.author.id}): {content}"
        )
        line += self._format_attachments(message)
        await self._write_chat_log(message.guild, message.channel, line)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild:
            log_user = self._dm_log_user(before)
            channel_info = f"DM ({before.channel.id})"
            before_content = before.content or "[No content]"
            after_content = after.content or "[No content]"
            line = (
                f"DM EDIT {before.id} | {channel_info} | "
                f"{before.author} ({before.author.id}) | "
                f"Before: {before_content} | After: {after_content}"
            )
            line += self._format_attachments(after)
            await self._write_dm_log(log_user, line)
            return

        if not self._should_log_message(before.guild):
            return

        if await is_channel_ignored(before.guild.id, before.channel.id):
            return

        channel_info = f"#{before.channel.name} ({before.channel.id})"
        before_content = before.content or "[No content]"
        after_content = after.content or "[No content]"
        line = (
            f"EDIT {before.id} | {channel_info} | "
            f"{before.author} ({before.author.id}) | "
            f"Before: {before_content} | After: {after_content}"
        )
        line += self._format_attachments(after)
        await self._write_chat_log(before.guild, before.channel, line)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild:
            log_user = self._dm_log_user(message)
            channel_info = f"DM ({message.channel.id})"
            content = message.content or "[No content]"
            line = (
                f"DM DELETE {message.id} | {channel_info} | "
                f"{message.author} ({message.author.id}): {content}"
            )
            line += self._format_attachments(message)
            await self._write_dm_log(log_user, line)
            return

        if not self._should_log_message(message.guild):
            return

        if await is_channel_ignored(message.guild.id, message.channel.id):
            return

        channel_info = f"#{message.channel.name} ({message.channel.id})"
        content = message.content or "[No content]"
        line = (
            f"DELETE {message.id} | {channel_info} | "
            f"{message.author} ({message.author.id}): {content}"
        )
        line += self._format_attachments(message)
        await self._write_chat_log(message.guild, message.channel, line)

    async def _seed_chat_history(
        self, guild: discord.Guild, channel: discord.TextChannel | discord.Thread
    ):
        """Backfill logs with existing channel or thread history for the target guild."""

        if channel.id in self._seeded_channels:
            return

        try:
            async for message in channel.history(limit=None, oldest_first=True):
                content = message.content or "[No content]"
                line = (
                    f"MESSAGE {message.id} | #{channel.name} ({channel.id}) | "
                    f"{message.author} ({message.author.id}): {content}"
                )
                line += self._format_attachments(message)
                await self._write_chat_log(
                    guild,
                    channel,
                    line,
                    timestamp=message.created_at or datetime.datetime.now(),
                )
        except Exception as exc:
            print(
                f"[Archives] Failed to seed history for {channel} ({channel.id}): {exc}",
                flush=True,
            )
            return

        self._seeded_channels.add(channel.id)
        await self._persist_seed_marker(guild)

async def setup(bot):
    await bot.add_cog(Archives(bot))
