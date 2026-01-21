import unittest

from main import MarciaBot


class HelperTests(unittest.TestCase):
    def test_format_cooldown(self):
        self.assertEqual(MarciaBot._format_cooldown(45), "45s")
        self.assertEqual(MarciaBot._format_cooldown(65), "1m 05s")


if __name__ == "__main__":
    unittest.main()
