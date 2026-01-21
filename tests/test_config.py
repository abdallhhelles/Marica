import unittest
from unittest import mock

from utils.config import load_config


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            config = load_config()
        self.assertIsNone(config.token)
        self.assertEqual(config.ai_base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(config.ai_model, "meta-llama/llama-3.1-8b-instruct:free")
        self.assertEqual(config.http_timeout, 10.0)
        self.assertEqual(config.profile_scan_workers, 1)

    def test_discord_token_fallback(self):
        with mock.patch.dict("os.environ", {"DISCORD_TOKEN": "fallback"}, clear=True):
            config = load_config()
        self.assertEqual(config.token, "fallback")


if __name__ == "__main__":
    unittest.main()
