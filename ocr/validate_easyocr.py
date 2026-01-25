#!/usr/bin/env python3
"""EasyOCR Installation Validator

This script validates that EasyOCR and all its dependencies are properly installed.
Run this after installing requirements-ocr.txt to confirm the setup is working.

Usage:
    python ocr/validate_easyocr.py

Exit codes:
    0 - All dependencies are properly installed
    1 - One or more dependencies are missing or misconfigured
"""
import sys
import importlib.util
from pathlib import Path


def check_import(module_name: str, package_name: str = None) -> tuple[bool, str]:
    """Check if a module can be imported.
    
    Args:
        module_name: Name of the module to import
        package_name: Optional display name for the package
        
    Returns:
        Tuple of (success, message)
    """
    package_name = package_name or module_name
    spec = importlib.util.find_spec(module_name)
    
    if spec is None:
        return False, f"✗ {package_name} is NOT installed"
    
    try:
        module = importlib.import_module(module_name)
        version = getattr(module, '__version__', 'unknown')
        return True, f"✓ {package_name} is installed (version {version})"
    except Exception as e:
        return False, f"✗ {package_name} failed to import: {e}"


def check_torch_cpu() -> tuple[bool, str]:
    """Check if PyTorch is installed with CPU support."""
    try:
        import torch
        version = torch.__version__
        
        if '+cpu' in version:
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                return True, f"✓ PyTorch {version} (CPU build with CUDA available)"
            else:
                return True, f"✓ PyTorch {version} (CPU-only mode)"
        else:
            return True, f"⚠ PyTorch {version} (not a CPU-only build, may require CUDA)"
    except ImportError:
        return False, "✗ PyTorch is NOT installed"
    except Exception as e:
        return False, f"✗ PyTorch check failed: {e}"


def check_tesseract() -> tuple[bool, str]:
    """Check if Tesseract binary is available."""
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        return True, f"✓ Tesseract binary is available (version {version})"
    except ImportError:
        return False, "✗ pytesseract is NOT installed"
    except Exception as e:
        return False, f"✗ Tesseract binary not found: {e}\n  Install with: apt-get install tesseract-ocr (Debian/Ubuntu) or brew install tesseract (macOS)"


def check_easyocr_reader() -> tuple[bool, str]:
    """Check if EasyOCR Reader can be instantiated (without downloading models)."""
    try:
        import easyocr
        # Just check that the Reader class exists
        if hasattr(easyocr, 'Reader'):
            return True, "✓ EasyOCR Reader class is available"
        else:
            return False, "✗ EasyOCR Reader class not found"
    except ImportError:
        return False, "✗ EasyOCR is NOT installed"
    except Exception as e:
        return False, f"✗ EasyOCR check failed: {e}"


def check_boxes_file() -> tuple[bool, str]:
    """Check if the OCR bounding boxes configuration file exists."""
    boxes_path = Path(__file__).resolve().parent / "boxes_ratios.json"
    
    if not boxes_path.exists():
        return False, f"✗ OCR template file not found: {boxes_path}\n  Run: python ocr/box_picker.py to create it"
    
    try:
        import json
        with open(boxes_path, 'r') as f:
            data = json.load(f)
            boxes = data.get('template_ratios', {})
            count = len(boxes)
            
            if count == 0:
                return False, f"✗ OCR template file is empty: {boxes_path}\n  Run: python ocr/box_picker.py to configure it"
            
            return True, f"✓ OCR template file found with {count} bounding box(es)"
    except Exception as e:
        return False, f"✗ Failed to read OCR template file: {e}"


def main():
    """Run all validation checks and report results."""
    print("=" * 70)
    print("EasyOCR Installation Validator")
    print("=" * 70)
    print()
    
    checks = [
        ("Pillow", lambda: check_import("PIL", "Pillow")),
        ("pytesseract", lambda: check_import("pytesseract")),
        ("Tesseract Binary", check_tesseract),
        ("opencv-python", lambda: check_import("cv2", "opencv-python-headless")),
        ("numpy", lambda: check_import("numpy")),
        ("PyTorch", check_torch_cpu),
        ("torchvision", lambda: check_import("torchvision")),
        ("EasyOCR", lambda: check_import("easyocr")),
        ("EasyOCR Reader", check_easyocr_reader),
        ("OCR Template", check_boxes_file),
    ]
    
    all_passed = True
    results = []
    
    for name, check_func in checks:
        success, message = check_func()
        results.append((name, success, message))
        if not success:
            all_passed = False
    
    # Print results
    for name, success, message in results:
        print(message)
    
    print()
    print("=" * 70)
    
    if all_passed:
        print("✓ All EasyOCR dependencies are properly installed!")
        print()
        print("Next steps:")
        print("  1. If you haven't already, run: python ocr/box_picker.py")
        print("  2. Test OCR with: python ocr/ocr_runner.py")
        print("  3. Or use the /scan command in Discord")
        return 0
    else:
        print("✗ Some dependencies are missing or misconfigured")
        print()
        print("Installation instructions:")
        print("  pip install --no-cache-dir -r requirements-ocr.txt")
        print("  apt-get install tesseract-ocr  # Debian/Ubuntu")
        print("  brew install tesseract          # macOS")
        print()
        print("For more details, see: docs/OCR_SETUP.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())
