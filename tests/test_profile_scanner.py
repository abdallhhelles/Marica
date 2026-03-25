import unittest
from types import SimpleNamespace

from cogs.profile_scanner import ProfileScanner, _parse_duel_score, _parse_roi


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


class ProfileScannerOcrFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_perform_ocr_falls_back_when_easyocr_has_only_ownership_marker(self):
        bot = SimpleNamespace(
            config=SimpleNamespace(
                ocr_space_api_key=None,
                ocr_space_timeout=5,
                profile_scan_review_timeout=30,
                profile_scan_workers=1,
                profile_scan_concurrency=1,
                profile_scan_release_ocr=False,
            )
        )
        scanner = ProfileScanner(bot)

        async def fake_stash(*_args, **_kwargs):
            return None

        async def fake_easyocr(*_args, **_kwargs):
            return {"parsed": {"ownership_verified": None}, "raw": ""}

        async def fake_easyocr_full(*_args, **_kwargs):
            return ""

        async def fake_tesseract(*_args, **_kwargs):
            return "CP: 123456"

        scanner._stash_temp_image = fake_stash
        scanner._run_easyocr = fake_easyocr
        scanner._run_easyocr_full_text = fake_easyocr_full
        scanner._run_pytesseract = fake_tesseract

        parsed, raw_text, _ = await scanner._perform_ocr(b"fake-image", filename="profile.png")

        self.assertEqual(parsed.get("cp"), 123456)
        self.assertEqual(raw_text, "CP: 123456")


if __name__ == "__main__":
    unittest.main()
