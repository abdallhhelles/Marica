# OCR setup and troubleshooting

Follow these steps to make the profile scanner's OCR feature work reliably.

## Install Python dependencies
1. Base packages (bot + pytesseract/Pillow):
   ```bash
   pip install -r requirements.txt
   ```
2. EasyOCR extras (template-driven scans, also re-installs Pillow + pytesseract for convenience):
   ```bash
   pip install -r requirements-ocr.txt
   ```

## Install the Tesseract binary
pytesseract needs the system `tesseract` CLI. Install it with a package manager:
- Debian/Ubuntu: `sudo apt-get install tesseract-ocr`
- macOS (Homebrew): `brew install tesseract`
- Windows (Chocolatey): `choco install tesseract`

## Provide templates
EasyOCR uses bounding boxes from `ocr/boxes_ratios.json`. If your screenshots use a
different layout, regenerate them:
1. Place an example profile screenshot in the top-level `shots/` folder.
2. Run `python ocr/box_picker.py` to draw boxes for each field.
3. Run `python ocr/ocr_runner.py` to verify EasyOCR can read the crops.

## Diagnose the environment
- Local CLI: `python ocr/diagnostics.py`
- In Discord: `/ocr_status`

Both paths report missing dependencies, templates, and setup tips so you can fix
what's blocking OCR.
