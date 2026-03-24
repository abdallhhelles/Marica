import unittest

from cogs.profile_scanner import _parse_duel_score, _parse_roi


class ProfileScannerParsingTests(unittest.TestCase):
    def test_parse_roi_allows_zero_origin(self):
        self.assertEqual(_parse_roi("0,0,0.5,0.5"), (0.0, 0.0, 0.5, 0.5))

    def test_parse_roi_rejects_non_positive_dimensions(self):
        self.assertIsNone(_parse_roi("0.1,0.2,0,0.5"))
        self.assertIsNone(_parse_roi("0.1,0.2,0.5,-0.5"))

    def test_parse_duel_score_prefers_decimal_suffix_candidate(self):
        score_text, score_int = _parse_duel_score("124M")
        self.assertEqual(score_text, "12.4M")
        self.assertEqual(score_int, 12_400_000)


if __name__ == "__main__":
    unittest.main()
