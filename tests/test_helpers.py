import unittest

from cogs.events import MARCIA_SERVER_ID, _effective_reminder_ping_role_id
from main import MarciaBot


class HelperTests(unittest.TestCase):
    def test_format_cooldown(self):
        self.assertEqual(MarciaBot._format_cooldown(45), "45s")
        self.assertEqual(MarciaBot._format_cooldown(65), "1m 05s")

    def test_marcia_server_forces_t60_everyone_ping(self):
        self.assertEqual(_effective_reminder_ping_role_id(MARCIA_SERVER_ID, 60, None), -1)
        self.assertEqual(_effective_reminder_ping_role_id(MARCIA_SERVER_ID, 60, 1234), -1)

    def test_non_marcia_servers_keep_configured_ping(self):
        self.assertIsNone(_effective_reminder_ping_role_id(1, 60, None))
        self.assertEqual(_effective_reminder_ping_role_id(1, 60, 1234), 1234)
        self.assertEqual(_effective_reminder_ping_role_id(MARCIA_SERVER_ID, 30, 1234), 1234)


if __name__ == "__main__":
    unittest.main()
