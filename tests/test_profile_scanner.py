import unittest
from types import SimpleNamespace
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

import cogs.profile_scanner as profile_scanner
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

    async def test_perform_ocr_skips_decode_when_persisted_path_exists(self):
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

        async def fake_easyocr(*_args, **_kwargs):
            return {"parsed": {"cp": 777}, "raw": "cp: 777"}

        async def fake_easyocr_full(*_args, **_kwargs):
            return ""

        async def fake_tesseract(*_args, **_kwargs):
            return ""

        scanner._run_easyocr = fake_easyocr
        scanner._run_easyocr_full_text = fake_easyocr_full
        scanner._run_pytesseract = fake_tesseract

        def fail_decode(*_args, **_kwargs):
            raise AssertionError("decode should not run when persisted file exists")

        scanner._decode_cv2_image = fail_decode

        with NamedTemporaryFile(suffix=".png") as tmp:
            parsed, raw_text, _ = await scanner._perform_ocr(
                b"fake-image",
                filename="profile.png",
                persisted_path=Path(tmp.name),
            )

        self.assertEqual(parsed.get("cp"), 777)
        self.assertEqual(raw_text, "cp: 777")

    async def test_run_easyocr_falls_back_to_byte_decode_when_imread_fails(self):
        if profile_scanner.cv2 is None or profile_scanner.np is None:
            self.skipTest("OpenCV/numpy not available in this environment")

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
        scanner._easyocr_boxes = {"cp": [0, 0, 1, 1]}
        scanner._easyocr_reader = object()

        async def ready():
            return True

        scanner._ensure_easyocr = ready
        scanner._easyocr_read_best = lambda *_args, **_kwargs: ("123", 0.99)

        fake_image = profile_scanner.np.zeros((20, 20, 3), dtype=profile_scanner.np.uint8)
        with NamedTemporaryFile(suffix=".png") as tmp:
            with patch.object(profile_scanner.cv2, "imread", return_value=None), patch.object(
                profile_scanner.cv2, "imdecode", return_value=fake_image
            ):
                result = await scanner._run_easyocr(
                    b"fake-image",
                    temp_path=Path(tmp.name),
                    decoded_image=None,
                )

        self.assertIsNotNone(result)
        self.assertEqual(result["parsed"].get("cp"), 123)


if __name__ == "__main__":
    unittest.main()
