"""
FILE: cogs/archives.py
USE: Local file-system logging for server intel and member activity.
"""
import discord
from discord.ext import commands
import os
import json
import datetime

class Archives(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.root_dir = "archives"
        if not os.path.exists(self.root_dir):
            os.makedirs(self.root_dir)

        # Server-scoped chat logging
        self.chat_log_server_id = 1403997721962086480
        self.chat_log_file = "chat.log"

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
        with open(os.path.join(path, "server_info.txt"), "w", encoding="utf-8") as f:
            f.write(f"SERVER: {guild.name}\n")
            f.write(f"ID: {guild.id}\n")
            f.write(f"OWNER: {guild.owner} ({guild.owner_id})\n")
            f.write(f"CREATED: {guild.created_at}\n")
            f.write(f"MEMBERS: {guild.member_count}\n")

        # 2. Member List File (JSON for easy reading)
        member_data = []
        for m in guild.members:
            member_data.append({
                "username": str(m),
                "id": m.id,
                "roles": [r.name for r in m.roles if r.name != "@everyone"],
                "joined_at": str(m.joined_at)
            })
        with open(os.path.join(path, "members.json"), "w", encoding="utf-8") as f:
            json.dump(member_data, f, indent=4)

    def log_action(self, guild, user, action):
        path = self.get_server_path(guild)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(path, "actions.log"), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {user} ({user.id}): {action}\n")

    def _should_log_message(self, guild):
        return guild and guild.id == self.chat_log_server_id

    def _write_chat_log(self, guild, line):
        path = self.get_server_path(guild)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(path, self.chat_log_file), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {line}\n")

    def _format_attachments(self, message: discord.Message) -> str:
        if not message.attachments:
            return ""
        urls = ", ".join(att.url for att in message.attachments)
        return f" | Attachments: {urls}"

    @commands.Cog.listener()
    async def on_ready(self):
        # When bot starts, update info for all servers
        for guild in self.bot.guilds:
            await self.update_server_files(guild)

    @commands.Cog.listener()
    async def on_command(self, ctx):
        # Logs every command used
        if ctx.guild:
            self.log_action(ctx.guild, ctx.author, f"Command executed: {ctx.prefix}{ctx.command}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        # Logs every button click (Trade terminal etc)
        if interaction.guild and interaction.data:
            custom_id = interaction.data.get("custom_id", "Unknown UI Interaction")
            self.log_action(interaction.guild, interaction.user, f"UI Interaction: {custom_id}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not self._should_log_message(message.guild):
            return

        channel_info = f"#{message.channel.name} ({message.channel.id})"
        content = message.content or "[No content]"
        line = (
            f"MESSAGE {message.id} | {channel_info} | "
            f"{message.author} ({message.author.id}): {content}"
        )
        line += self._format_attachments(message)
        self._write_chat_log(message.guild, line)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or not self._should_log_message(before.guild):
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
        self._write_chat_log(before.guild, line)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or not self._should_log_message(message.guild):
            return

        channel_info = f"#{message.channel.name} ({message.channel.id})"
        content = message.content or "[No content]"
        line = (
            f"DELETE {message.id} | {channel_info} | "
            f"{message.author} ({message.author.id}): {content}"
        )
        line += self._format_attachments(message)
        self._write_chat_log(message.guild, line)

async def setup(bot):
    await bot.add_cog(Archives(bot))
