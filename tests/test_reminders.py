import asyncio
import unittest
from datetime import datetime, timedelta, timezone

import cogs.reminders as reminders_module
from cogs.reminders import Reminders


class _Guild:
    def __init__(self, guild_id: int):
        self.id = guild_id


class _Channel:
    def __init__(self, guild_id: int = 1, channel_id: int = 10):
        self.guild = _Guild(guild_id)
        self.id = channel_id
        self.sent_messages = []

    async def send(self, content: str, allowed_mentions=None):
        self.sent_messages.append(content)


class ReminderSchedulingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cog = Reminders.__new__(Reminders)
        self.cog.scheduled_tasks = {}

        self._original_sleep_until = reminders_module.discord.utils.sleep_until
        self._original_get = reminders_module.get_scheduled_reminders
        self._original_is_ignored = reminders_module.is_channel_ignored
        self._original_update = reminders_module.update_scheduled_reminder
        self._original_delete = reminders_module.delete_scheduled_reminder

        async def _no_sleep(_when):
            return None

        reminders_module.discord.utils.sleep_until = _no_sleep

    async def asyncTearDown(self):
        reminders_module.discord.utils.sleep_until = self._original_sleep_until
        reminders_module.get_scheduled_reminders = self._original_get
        reminders_module.is_channel_ignored = self._original_is_ignored
        reminders_module.update_scheduled_reminder = self._original_update
        reminders_module.delete_scheduled_reminder = self._original_delete

    async def test_ignored_channel_does_not_send_but_reschedules(self):
        channel = _Channel()
        when_utc = datetime.now(timezone.utc)
        updates = []

        async def _get_scheduled(_guild_id):
            return [{"id": 1, "recurrence_type": "daily", "recurrence_value": None}]

        async def _is_ignored(_guild_id, _channel_id):
            return True

        async def _update(_guild_id, _reminder_id, send_at_utc):
            updates.append(send_at_utc)

        async def _delete(*_args, **_kwargs):
            raise AssertionError("delete should not be called for recurring reminder")

        reminders_module.get_scheduled_reminders = _get_scheduled
        reminders_module.is_channel_ignored = _is_ignored
        reminders_module.update_scheduled_reminder = _update
        reminders_module.delete_scheduled_reminder = _delete

        self.cog._schedule_reminder = lambda *_args, **_kwargs: None
        await self.cog._run_scheduled_reminder(1, channel, "body", when_utc)

        self.assertEqual(channel.sent_messages, [])
        self.assertEqual(len(updates), 1)
        expected = (when_utc + timedelta(days=1)).isoformat()
        self.assertEqual(updates[0], expected)

    async def test_non_ignored_channel_sends_message(self):
        channel = _Channel()
        when_utc = datetime.now(timezone.utc)

        async def _get_scheduled(_guild_id):
            return [{"id": 2, "recurrence_type": "once", "recurrence_value": None}]

        async def _is_ignored(_guild_id, _channel_id):
            return False

        deleted = []

        async def _delete(guild_id, reminder_id):
            deleted.append((guild_id, reminder_id))

        reminders_module.get_scheduled_reminders = _get_scheduled
        reminders_module.is_channel_ignored = _is_ignored
        reminders_module.update_scheduled_reminder = lambda *_args, **_kwargs: None
        reminders_module.delete_scheduled_reminder = _delete

        await self.cog._run_scheduled_reminder(2, channel, "body", when_utc)

        self.assertEqual(len(channel.sent_messages), 1)
        self.assertEqual(deleted, [(1, 2)])


if __name__ == "__main__":
    unittest.main()
