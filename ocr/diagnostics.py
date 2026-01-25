"""Utilities to check whether OCR dependencies and templates are ready.

Run ``python ocr/diagnostics.py`` to print a CLI report for local validation.

This module performs comprehensive environment and dependency checks to ensure
the OCR system can function properly, including:
- Python version compatibility
- Required package availability
- System resource checks (CPU/GPU, memory)
- PyTorch compatibility verification
- Template configuration validation
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
import json
import sys
import platform
from typing import List, Optional

# Minimum Python version required for optimal OCR functionality
MIN_PYTHON_VERSION = (3, 8)

BOXES_PATH = Path(__file__).resolve().parent / "boxes_ratios.json"


@dataclass
class OcrDiagnostics:
    python_version: str
    python_compatible: bool
    pillow: bool
    pytesseract: bool
    tesseract_binary: bool | None
    tesseract_version: str | None
    easyocr: bool
    opencv: bool
    numpy: bool
    torch: bool
    torch_version: str | None
    torch_cpu_only: bool
    cuda_available: bool
    easyocr_ready: bool
    easyocr_failure: str | None
    boxes_present: bool
    box_count: int
    install_tips: List[str]
    warnings: List[str]

    def as_lines(self) -> list[str]:
        """Return a human-readable report for CLI output."""

        lines: list[str] = []
        
        # System information
        lines.append("=" * 60)
        lines.append("OCR DIAGNOSTICS REPORT")
        lines.append("=" * 60)
        lines.append("")
        lines.append("System Information:")
        lines.append(f"  Platform: {platform.system()} {platform.release()}")
        lines.append(f"  Python: {self.python_version}")
        if not self.python_compatible:
            lines.append(f"  ⚠️  WARNING: Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+ recommended for OCR features")
        lines.append("")
        
        # Dependency status
        lines.append("Python Dependencies:")
        lines.append(f"  Pillow: {'✓ installed' if self.pillow else '✗ missing'}")
        
        pytess_state = "✓ installed" if self.pytesseract else "✗ missing"
        if self.tesseract_binary is True and self.tesseract_version:
            pytess_state += f" (Tesseract {self.tesseract_version})"
        elif self.tesseract_binary is False:
            pytess_state += " (⚠️  Tesseract binary missing)"
        lines.append(f"  pytesseract: {pytess_state}")
        
        lines.append(f"  opencv-python: {'✓ installed' if self.opencv else '✗ missing'}")
        lines.append(f"  numpy: {'✓ installed' if self.numpy else '✗ missing'}")
        
        # EasyOCR and PyTorch status
        easyocr_state = "✓ ready" if self.easyocr_ready else "✓ installed" if self.easyocr else "✗ missing"
        if self.easyocr_failure:
            easyocr_state += f" - {self.easyocr_failure}"
        lines.append(f"  EasyOCR: {easyocr_state}")
        
        torch_state = "✗ missing"
        if self.torch:
            torch_state = f"✓ installed (v{self.torch_version})"
            if self.torch_cpu_only:
                torch_state += " [CPU-only build]"
            elif self.cuda_available:
                torch_state += " [CUDA GPU available]"
            else:
                torch_state += " [No CUDA GPU detected]"
        lines.append(f"  PyTorch: {torch_state}")
        lines.append("")
        
        # Template configuration
        lines.append("OCR Templates:")
        if self.boxes_present:
            lines.append(f"  ✓ {self.box_count} bounding box(es) loaded from {BOXES_PATH.name}")
        else:
            lines.append(f"  ✗ Missing file at {BOXES_PATH}")
        lines.append("")
        
        # Warnings
        if self.warnings:
            lines.append("Warnings:")
            for warning in self.warnings:
                lines.append(f"  ⚠️  {warning}")
            lines.append("")
        
        # Suggestions
        if self.install_tips:
            lines.append("Suggested Actions:")
            for tip in self.install_tips:
                lines.append(f"  • {tip}")
            lines.append("")
        
        # Summary
        if self.easyocr_ready:
            lines.append("✓ OCR system is ready to use")
        else:
            lines.append("✗ OCR system is NOT ready - please address issues above")
        lines.append("=" * 60)
        
        return lines


def _has_spec(module: str) -> bool:
    """Check if a module is available for import."""
    return find_spec(module) is not None


def _get_python_version() -> tuple[str, bool]:
    """Get Python version and check if it's compatible.
    
    Returns:
        Tuple of (version_string, is_compatible)
    """
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    compatible = sys.version_info >= MIN_PYTHON_VERSION
    return version, compatible


def _get_tesseract_info() -> tuple[bool | None, str | None]:
    """Get Tesseract binary availability and version."""
    if not _has_spec("pytesseract"):
        return None, None
    
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        return True, str(version)
    except Exception:
        return False, None


def _get_torch_info() -> tuple[bool, str | None, bool, bool]:
    """Get PyTorch information.
    
    Returns:
        Tuple of (installed, version, is_cpu_only, cuda_available)
    """
    if not _has_spec("torch"):
        return False, None, False, False
    
    try:
        import torch
        version = torch.__version__
        
        # Check if this is a CPU-only build
        cpu_only = '+cpu' in version or not hasattr(torch.version, 'cuda') or torch.version.cuda is None
        
        # Check if CUDA is available
        cuda_available = torch.cuda.is_available()
        
        return True, version, cpu_only, cuda_available
    except Exception:
        return True, None, False, False


def _count_boxes() -> tuple[bool, int]:
    """Count bounding boxes in the template file.
    
    Returns:
        Tuple of (file_exists, box_count)
    """
    if not BOXES_PATH.exists():
        return False, 0

    try:
        with BOXES_PATH.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except Exception:
        return True, 0

    boxes = data.get("template_ratios") or {}
    return True, len(boxes)


def _validate_torch_compatibility(torch_version: str | None) -> list[str]:
    """Validate PyTorch version compatibility with torchvision and other deps.
    
    Returns:
        List of warning messages
    """
    warnings = []
    
    if not torch_version:
        return warnings
    
    # Check for known incompatible versions
    if _has_spec("torchvision"):
        try:
            import torchvision
            tv_version = torchvision.__version__
            
            # PyTorch and torchvision major versions should generally match
            # For example: PyTorch 2.x should use torchvision 0.1x
            # Note: This logic may need updates as new PyTorch versions are released
            torch_major = torch_version.split('.')[0] if '.' in torch_version else '0'
            tv_major = tv_version.split('.')[0] if '.' in tv_version else '0'
            
            # As of 2024, PyTorch 2.x is current; adjust this check for future versions
            if torch_major != tv_major and torch_major not in ('2', '1'):
                warnings.append(
                    f"PyTorch {torch_version} and torchvision {tv_version} may be incompatible. "
                    "Check compatibility at https://pytorch.org/get-started/previous-versions/"
                )
        except Exception:
            pass
    
    return warnings


def collect_ocr_diagnostics() -> OcrDiagnostics:
    """Collect comprehensive OCR system diagnostics.
    
    Returns:
        OcrDiagnostics object with all diagnostic information
    """
    # Python version check
    python_version, python_compatible = _get_python_version()
    
    # Check core dependencies
    pillow_present = _has_spec("PIL")
    pytess_present = _has_spec("pytesseract")
    opencv_present = _has_spec("cv2")
    numpy_present = _has_spec("numpy")
    easyocr_present = _has_spec("easyocr")
    
    # Check Tesseract binary
    tesseract_binary, tesseract_version = _get_tesseract_info()
    
    # Check PyTorch
    torch_present, torch_version, torch_cpu_only, cuda_available = _get_torch_info()
    
    # Check templates
    boxes_present, box_count = _count_boxes()
    
    # Determine if EasyOCR is ready
    easyocr_ready = bool(
        easyocr_present and 
        opencv_present and 
        numpy_present and 
        torch_present and
        boxes_present and 
        box_count > 0
    )

    # Collect installation tips
    tips: list[str] = []
    if not pillow_present or not pytess_present:
        tips.append("Install Pillow + pytesseract (`pip install -r requirements.txt`)")
    if pytess_present and tesseract_binary is False:
        tips.append("Install the Tesseract CLI (e.g., `apt-get install tesseract-ocr` on Ubuntu)")
    if not (easyocr_present and opencv_present and numpy_present and torch_present):
        missing = []
        if not easyocr_present:
            missing.append("easyocr")
        if not opencv_present:
            missing.append("opencv-python-headless")
        if not numpy_present:
            missing.append("numpy")
        if not torch_present:
            missing.append("torch")
        tips.append(
            f"Install OCR dependencies: {', '.join(missing)} "
            "(`pip install -r requirements-ocr.txt`)"
        )
    if easyocr_present and opencv_present and numpy_present and torch_present and not box_count:
        tips.append("Generate bounding boxes with `python ocr/box_picker.py`")
    
    # Determine failure reason
    failure_reason = None
    if not easyocr_present:
        failure_reason = "EasyOCR unavailable: install easyocr package."
    elif not opencv_present:
        failure_reason = "OpenCV unavailable: install opencv-python-headless."
    elif not numpy_present:
        failure_reason = "NumPy unavailable: install numpy package."
    elif not torch_present:
        failure_reason = "PyTorch unavailable: install torch package."
    elif not boxes_present:
        failure_reason = f"OCR bounding boxes not found at {BOXES_PATH}."
    elif not box_count:
        failure_reason = "OCR templates are empty."
    
    # Collect warnings
    warnings: list[str] = []
    if not python_compatible:
        warnings.append(f"Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+ is recommended for optimal compatibility")
    if torch_present and not cuda_available and not torch_cpu_only:
        warnings.append("CUDA not available - OCR will run on CPU (slower)")
    if torch_version:
        warnings.extend(_validate_torch_compatibility(torch_version))

    return OcrDiagnostics(
        python_version=python_version,
        python_compatible=python_compatible,
        pillow=pillow_present,
        pytesseract=pytess_present,
        tesseract_binary=tesseract_binary,
        tesseract_version=tesseract_version,
        easyocr=easyocr_present,
        opencv=opencv_present,
        numpy=numpy_present,
        torch=torch_present,
        torch_version=torch_version,
        torch_cpu_only=torch_cpu_only,
        cuda_available=cuda_available,
        easyocr_ready=easyocr_ready,
        easyocr_failure=failure_reason,
        boxes_present=boxes_present,
        box_count=box_count,
        install_tips=tips,
        warnings=warnings,
    )


def main():
    status = collect_ocr_diagnostics()
    for line in status.as_lines():
        print(line)


if __name__ == "__main__":  # pragma: no cover - manual diagnostic entrypoint
    main()
