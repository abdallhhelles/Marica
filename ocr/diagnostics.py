"""Utilities to check whether OCR dependencies and templates are ready.

Run ``python ocr/diagnostics.py`` to print a CLI report. The helper functions are
reused by the bot's ``/ocr_status`` command to surface the same details in Discord.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
import json
from typing import List

BOXES_PATH = Path(__file__).resolve().parent / "boxes_ratios.json"


@dataclass
class OcrDiagnostics:
    pillow: bool
    pytesseract: bool
    tesseract_binary: bool | None
    easyocr: bool
    easyocr_ready: bool
    easyocr_failure: str | None
    boxes_present: bool
    box_count: int
    install_tips: List[str]

    def as_lines(self) -> list[str]:
        """Return a human-readable report for CLI output."""

        lines: list[str] = []
        lines.append(f"Pillow: {'installed' if self.pillow else 'missing'}")
        pytess_state = "installed" if self.pytesseract else "missing"
        if self.tesseract_binary is True:
            pytess_state += " (Tesseract binary found)"
        elif self.tesseract_binary is False:
            pytess_state += " (Tesseract binary missing)"
        lines.append(f"pytesseract: {pytess_state}")

        easyocr_state = "ready" if self.easyocr_ready else "installed" if self.easyocr else "missing"
        if self.easyocr_failure:
            easyocr_state += f" — {self.easyocr_failure}"
        lines.append(f"EasyOCR: {easyocr_state}")

        if self.boxes_present:
            lines.append(f"Templates: {self.box_count} bounding boxes loaded from {BOXES_PATH}")
        else:
            lines.append(f"Templates: missing file at {BOXES_PATH}")

        if self.install_tips:
            lines.append("Suggested actions:")
            lines.extend([f"  - {tip}" for tip in self.install_tips])
        return lines


def _has_spec(module: str) -> bool:
    return find_spec(module) is not None


def _count_boxes():
    if not BOXES_PATH.exists():
        return False, 0

    try:
        with BOXES_PATH.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except Exception:
        return True, 0

    boxes = data.get("template_ratios") or {}
    return True, len(boxes)


def collect_ocr_diagnostics() -> OcrDiagnostics:
    pillow_present = _has_spec("PIL")
    pytess_present = _has_spec("pytesseract")
    easyocr_present = _has_spec("easyocr") and _has_spec("cv2") and _has_spec("numpy")

    tesseract_binary: bool | None
    tesseract_binary = None
    if pytess_present:
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            tesseract_binary = True
        except Exception:
            tesseract_binary = False

    boxes_present, box_count = _count_boxes()
    easyocr_ready = bool(easyocr_present and boxes_present and box_count)

    tips: list[str] = []
    if not pillow_present or not pytess_present:
        tips.append("Install Pillow + pytesseract (pip install -r requirements.txt)")
    if pytess_present and tesseract_binary is False:
        tips.append("Install the Tesseract CLI (e.g., apt-get install tesseract-ocr)")
    if not easyocr_present:
        tips.append(
            "Install EasyOCR extras (pip install -r requirements-ocr.txt) for template-based scans"
        )
    if easyocr_present and not box_count:
        tips.append("Regenerate bounding boxes with python ocr/box_picker.py")

    failure_reason = None
    if not easyocr_present:
        failure_reason = "EasyOCR unavailable: install easyocr, opencv-python-headless, and numpy."
    elif not boxes_present:
        failure_reason = f"OCR bounding boxes not found at {BOXES_PATH}."
    elif not box_count:
        failure_reason = "OCR templates are empty."

    return OcrDiagnostics(
        pillow=pillow_present,
        pytesseract=pytess_present,
        tesseract_binary=tesseract_binary,
        easyocr=easyocr_present,
        easyocr_ready=easyocr_ready,
        easyocr_failure=failure_reason,
        boxes_present=boxes_present,
        box_count=box_count,
        install_tips=tips,
    )


def main():
    status = collect_ocr_diagnostics()
    for line in status.as_lines():
        print(line)


if __name__ == "__main__":  # pragma: no cover - manual diagnostic entrypoint
    main()
