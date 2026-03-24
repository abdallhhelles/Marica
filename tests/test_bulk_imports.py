import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from cogs.events import Events
from cogs.reminders import Reminders


class _Role:
    def __init__(self, role_id: int, name: str):
        self.id = role_id
        self.name = name
        self.mention = f"@{name}"


class _Channel:
    def __init__(self, channel_id: int, name: str):
        self.id = channel_id
        self.name = name
        self.mention = f"#{name}"


class _Guild:
    def __init__(self):
        self.id = 1
        self.name = "Test Sector"
        self.roles = [_Role(22, "Raid Team")]
        self.text_channels = [_Channel(10, "events"), _Channel(11, "officers")]

    def get_role(self, role_id: int):
        return next((role for role in self.roles if role.id == role_id), None)

    def get_channel(self, channel_id: int):
        return next((channel for channel in self.text_channels if channel.id == channel_id), None)


class BulkImportParserTests(unittest.TestCase):
    def setUp(self):
        self.guild = _Guild()
        self.events = Events.__new__(Events)
        self.reminders = Reminders.__new__(Reminders)

    def test_parse_bulk_events_supports_optional_fields(self):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        date_value = future.strftime("%Y-%m-%d")
        time_value = future.strftime("%H:%M")
        rows, errors = self.events._parse_bulk_event_rows(
            self.guild,
            (
                "name | date | time | desc | location | ping\n"
                f"Fortress Push | {date_value} | {time_value} | - | - | none\n"
                f"Desert Reset | {date_value} | {time_value} | Briefing | VC 2 | Raid Team"
            ),
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[0]["location"])
        self.assertIsNone(rows[0]["ping_role_id"])
        self.assertEqual(rows[1]["ping_role_id"], 22)

    def test_parse_bulk_reminders_uses_default_channel_and_validates(self):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        when_value = future.strftime("%Y-%m-%d %H:%M")
        rows, errors = self.reminders._parse_bulk_reminder_rows(
            self.guild,
            (
                "body | when | repeat | weekdays | channel\n"
                f"Shield up | {when_value} | once | - | -\n"
                f"Officer prep | {when_value} | weekdays | Mon,Wed,Fri | #officers"
            ),
            self.guild.get_channel(10),
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["channel"].id, 10)
        self.assertEqual(rows[1]["channel"].id, 11)
        self.assertEqual(rows[1]["recurrence_type"], "custom_weekdays")

    def test_parse_bulk_reminders_reports_missing_weekdays(self):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        when_value = future.strftime("%Y-%m-%d %H:%M")
        rows, errors = self.reminders._parse_bulk_reminder_rows(
            self.guild,
            f"Broken row | {when_value} | weekdays | - | #events",
            self.guild.get_channel(10),
        )

        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("Pick at least one day", errors[0])


if __name__ == "__main__":
    unittest.main()
