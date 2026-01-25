# OCR helper scripts

These scripts crop profile screenshots and extract stats with EasyOCR. They’re designed for
repeatable templates and fast local validation.

## Prerequisites
- Install OCR extras: `pip install --no-cache-dir -r requirements-ocr.txt` (CPU-only wheels)
- Install the system Tesseract binary (required by pytesseract)
- Save profile screenshots to the top-level `shots/` folder (create it if needed)

## Workflow
1. **Pick bounding boxes**: run `python ocr/box_picker.py`. Drag a box for each field and press Enter to save. This writes normalized ratios to `ocr/boxes_ratios.json` (or to `OCR_BOXES_FILE` if the environment variable is set).
2. **Run OCR**: place screenshots in `shots/` and run `python ocr/ocr_runner.py`. The script crops each image using the saved ratios, runs EasyOCR, and prints parsed values.

If you need to store templates elsewhere, set `OCR_BOXES_FILE=/path/to/boxes_ratios.json` before running either script.

If either script reports `Input folder 'shots' is missing`, create `shots/` and add at least one screenshot before running again.

## Diagnostics
- Run `python ocr/diagnostics.py` locally to confirm dependencies, the Tesseract binary, and templates are available.

## Validation & Testing

### Quick validation
```bash
python ocr/validate_easyocr.py
```
Fast check specifically for EasyOCR dependencies with clear pass/fail indicators.

### Unit tests
```bash
python -m unittest tests.test_ocr_dependencies
```
Automated tests for all OCR dependencies including voice support (PyNaCl).
