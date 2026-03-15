import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import cogs.reminders as reminders_module
from cogs.reminders import Reminders


class _Guild:
    def __init__(self):
        self.id = 1
        self._channels = {10: SimpleNamespace(id=10, mention="#events")}

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)


class _Ctx:
    def __init__(self):
        self.guild = _Guild()
        self.author = SimpleNamespace(id=77)
        self.sent = []

    async def send(self, message=None, **kwargs):
        self.sent.append({"message": message, "kwargs": kwargs})


class ReminderCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cog = Reminders.__new__(Reminders)
        self._orig_get_settings = reminders_module.get_settings
        self._orig_is_ignored = reminders_module.is_channel_ignored

    async def asyncTearDown(self):
        reminders_module.get_settings = self._orig_get_settings
        reminders_module.is_channel_ignored = self._orig_is_ignored

    async def test_requires_first_run_for_daily(self):
        ctx = _Ctx()
        reminders_module.get_settings = AsyncMock(return_value={"event_channel_id": 10})
        reminders_module.is_channel_ignored = AsyncMock(return_value=False)
        self.cog._send_or_schedule = AsyncMock()

        await Reminders.remind.callback(self.cog, ctx, body="Ping", repeat="daily")

        self.assertIn("Recurring reminders need `when`", ctx.sent[0]["message"])
        self.cog._send_or_schedule.assert_not_awaited()

    async def test_uses_default_channel_and_schedules_once(self):
        ctx = _Ctx()
        reminders_module.get_settings = AsyncMock(return_value={"event_channel_id": 10})
        reminders_module.is_channel_ignored = AsyncMock(return_value=False)
        self.cog._send_or_schedule = AsyncMock()

        await Reminders.remind.callback(self.cog, ctx, body="Ping")

        self.cog._send_or_schedule.assert_awaited_once()
        call = self.cog._send_or_schedule.await_args
        self.assertEqual(call.args[2], "Ping")
        self.assertEqual(call.kwargs["recurrence_type"], "once")

    async def test_without_body_opens_menu(self):
        ctx = _Ctx()
        reminders_module.get_settings = AsyncMock(return_value={"event_channel_id": 10})
        reminders_module.is_channel_ignored = AsyncMock(return_value=False)
        self.cog._send_or_schedule = AsyncMock()

        await Reminders.remind.callback(self.cog, ctx)

        self.cog._send_or_schedule.assert_not_awaited()
        self.assertEqual(ctx.sent[0]["message"], None)
        self.assertIn("embed", ctx.sent[0]["kwargs"])
        self.assertIn("view", ctx.sent[0]["kwargs"])


if __name__ == "__main__":
    unittest.main()
