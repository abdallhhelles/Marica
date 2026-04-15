import unittest

import cogs.settings as settings_module
from cogs.settings import Settings


class _Guild:
    def __init__(self, guild_id: int):
        self.id = guild_id


class _Channel:
    def __init__(self, guild_id: int, channel_id: int):
        self.guild = _Guild(guild_id)
        self.id = channel_id


class _NoGuildChannel:
    guild = None
    id = 999


class SettingsIgnoreCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_remove = settings_module.remove_ignored_channel

    async def asyncTearDown(self):
        settings_module.remove_ignored_channel = self._original_remove

    async def test_channel_delete_removes_ignored_entry(self):
        calls: list[tuple[int, int]] = []

        async def _remove(guild_id: int, channel_id: int):
            calls.append((guild_id, channel_id))

        settings_module.remove_ignored_channel = _remove
        cog = Settings(bot=object())

        await cog.on_guild_channel_delete(_Channel(123, 456))

        self.assertEqual(calls, [(123, 456)])

    async def test_channel_delete_without_guild_is_ignored(self):
        called = False

        async def _remove(_guild_id: int, _channel_id: int):
            nonlocal called
            called = True

        settings_module.remove_ignored_channel = _remove
        cog = Settings(bot=object())

        await cog.on_guild_channel_delete(_NoGuildChannel())

        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
