"""Test OCR dependencies are properly installed and configured.

This test validates that all OCR-related dependencies are available
and can be imported successfully. It's designed to catch missing
dependencies early in the development/deployment process.
"""
import sys
import unittest
from importlib.util import find_spec


class TestOCRDependencies(unittest.TestCase):
    """Test suite for OCR dependency validation."""

    def test_pillow_available(self):
        """Verify Pillow (PIL) is installed."""
        self.assertIsNotNone(
            find_spec("PIL"),
            "Pillow is required for image processing. Install with: pip install -r requirements-ocr.txt"
        )

    def test_pytesseract_available(self):
        """Verify pytesseract is installed."""
        self.assertIsNotNone(
            find_spec("pytesseract"),
            "pytesseract is required for OCR. Install with: pip install -r requirements-ocr.txt"
        )

    def test_opencv_available(self):
        """Verify opencv-python-headless is installed."""
        self.assertIsNotNone(
            find_spec("cv2"),
            "opencv-python-headless is required for image processing. Install with: pip install -r requirements-ocr.txt"
        )

    def test_numpy_available(self):
        """Verify numpy is installed."""
        self.assertIsNotNone(
            find_spec("numpy"),
            "numpy is required for array processing. Install with: pip install -r requirements-ocr.txt"
        )

    def test_easyocr_available(self):
        """Verify EasyOCR is installed."""
        self.assertIsNotNone(
            find_spec("easyocr"),
            "EasyOCR is required for OCR functionality. Install with: pip install -r requirements-ocr.txt"
        )

    def test_torch_available(self):
        """Verify PyTorch is installed."""
        self.assertIsNotNone(
            find_spec("torch"),
            "PyTorch is required for EasyOCR. Install with: pip install -r requirements-ocr.txt"
        )

    def test_torchvision_available(self):
        """Verify torchvision is installed."""
        self.assertIsNotNone(
            find_spec("torchvision"),
            "torchvision is required for EasyOCR. Install with: pip install -r requirements-ocr.txt"
        )

    def test_easyocr_can_initialize(self):
        """Verify EasyOCR can be imported and basic functionality works."""
        try:
            import easyocr
            # Basic smoke test - just verify the module can be loaded
            # Don't initialize a reader here as it downloads models
            self.assertTrue(hasattr(easyocr, 'Reader'), "EasyOCR Reader class should be available")
        except ImportError as e:
            self.fail(f"Failed to import easyocr: {e}")

    def test_torch_cpu_mode(self):
        """Verify PyTorch is configured for CPU mode."""
        try:
            import torch
            # Verify torch version indicates CPU build
            version = torch.__version__
            self.assertIn(
                '+cpu', version,
                f"PyTorch should be CPU-only build (+cpu in version). Got: {version}"
            )
        except ImportError:
            self.skipTest("PyTorch not installed - skipping CPU mode check")

    def test_tesseract_binary(self):
        """Verify Tesseract binary is available on the system."""
        try:
            import pytesseract
            version = pytesseract.get_tesseract_version()
            self.assertIsNotNone(version, "Tesseract binary should be available")
            # Version should be a tuple of integers (major, minor, patch)
            self.assertIsInstance(version, tuple)
            self.assertGreater(len(version), 0)
        except ImportError:
            self.skipTest("pytesseract not installed - skipping binary check")
        except Exception as e:
            self.fail(
                f"Tesseract binary not found or not accessible: {e}. "
                "Install with: apt-get install tesseract-ocr (Debian/Ubuntu) "
                "or brew install tesseract (macOS)"
            )


class TestVoiceDependencies(unittest.TestCase):
    """Test suite for voice support dependencies."""

    def test_pynacl_available(self):
        """Verify PyNaCl is installed for voice support."""
        self.assertIsNotNone(
            find_spec("nacl"),
            "PyNaCl is required for Discord voice support. Install with: pip install -r requirements.txt"
        )


if __name__ == '__main__':
    unittest.main()
