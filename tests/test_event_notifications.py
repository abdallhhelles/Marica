import unittest

import cogs.events as events_module
from cogs.events import Events


class _User:
    def __init__(self, user_id: int, is_bot: bool = False):
        self.id = user_id
        self.bot = is_bot
        self.messages = []

    async def send(self, content: str):
        self.messages.append(content)


class _Guild:
    def __init__(self, members=None):
        self._members = members or {}

    def get_member(self, user_id: int):
        return self._members.get(user_id)


class _Bot:
    def __init__(self, guild=None, users=None, fetched_users=None):
        self._guild = guild
        self._users = users or {}
        self._fetched_users = fetched_users or {}

    def get_guild(self, _guild_id: int):
        return self._guild

    def get_user(self, user_id: int):
        return self._users.get(user_id)

    async def fetch_user(self, user_id: int):
        user = self._fetched_users.get(user_id)
        if user is None:
            raise AssertionError(f"Unexpected fetch_user({user_id}) call")
        return user


class EventNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_get_rsvp_members = events_module.get_rsvp_members

    async def asyncTearDown(self):
        events_module.get_rsvp_members = self._original_get_rsvp_members

    async def test_notify_dm_participants_fetches_uncached_users(self):
        fetched_user = _User(42)
        bot = _Bot(guild=_Guild(), fetched_users={42: fetched_user})
        events_cog = Events.__new__(Events)
        events_cog.bot = bot

        async def _get_rsvp_members(_guild_id, _codename, *, status="going"):
            self.assertEqual(status, "going")
            return [42]

        events_module.get_rsvp_members = _get_rsvp_members

        await events_cog._notify_dm_participants(1, "Night Op", 15, "Move out", "Gate")

        self.assertEqual(len(fetched_user.messages), 1)
        self.assertIn("Night Op", fetched_user.messages[0])


if __name__ == "__main__":
    unittest.main()
