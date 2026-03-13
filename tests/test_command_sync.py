import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from main import MarciaBot


class _TreeStub:
    def __init__(self):
        self.clear_commands = Mock()
        self.copy_global_to = Mock()
        self.sync = AsyncMock(return_value=[object(), object()])


class CommandSyncRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_interaction_guild_overlay_refreshes_guild(self):
        bot = SimpleNamespace(tree=_TreeStub())

        guild = SimpleNamespace(id=123, name="Sector-1")
        interaction = SimpleNamespace(guild=guild)

        await MarciaBot._sync_interaction_guild_overlay(bot, interaction)

        bot.tree.clear_commands.assert_called_once_with(guild=guild)
        bot.tree.copy_global_to.assert_called_once_with(guild=guild)
        bot.tree.sync.assert_awaited_once_with(guild=guild)

    async def test_recover_from_signature_mismatch_runs_overlay_then_full_sync(self):
        bot = SimpleNamespace()
        interaction = SimpleNamespace(guild=SimpleNamespace(id=456, name="Sector-2"))

        calls = []

        async def _overlay(_interaction):
            calls.append("overlay")

        async def _full_sync(*, force=False):
            calls.append(("full", force))

        bot._sync_interaction_guild_overlay = _overlay
        bot._sync_slash_commands_with_retry = _full_sync

        await MarciaBot._recover_from_signature_mismatch(bot, interaction)

        self.assertEqual(calls, ["overlay", ("full", True)])


if __name__ == "__main__":
    unittest.main()
