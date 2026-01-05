# OCR setup and troubleshooting

This guide keeps `/scan_profile` predictable across laptops, dedicated servers, and container panels.

## Provisioning checklist
1. Install Python packages:
   ```bash
   pip install -r requirements.txt       # base bot + pytesseract/Pillow
   pip install -r requirements-ocr.txt   # EasyOCR, OpenCV, numpy
   ```
2. Install the system Tesseract binary (required by pytesseract):
   * Debian/Ubuntu: `sudo apt-get install -y tesseract-ocr`
   * macOS (Homebrew): `brew install tesseract`
   * Windows (Chocolatey): `choco install tesseract`
3. Verify versions: `tesseract --version` and `python -m pip show easyocr opencv-python-headless numpy`.
4. Run diagnostics: `python ocr/diagnostics.py` locally or `/ocr_status` inside Discord.

## Template workflow (EasyOCR crops)
EasyOCR uses bounding boxes from `ocr/boxes_ratios.json`. If your screenshot layout differs from the default:
1. Place a representative profile screenshot in `shots/`.
2. Build boxes: `python ocr/box_picker.py` (click/drag each field).
3. Validate: `python ocr/ocr_runner.py` and adjust boxes until every field reads cleanly.

## Hosting guidance
* **Containers / game panels:** add both `pip install -r requirements-ocr.txt` and `apt-get install -y tesseract-ocr` (or OS equivalent) directly to your startup command; consoles are often non-interactive.
* **Conflicting packages:** third-party images sometimes bundle `googletrans==4.0.0rc1`, which forces `httpx==0.13.3`. Re-pin `httpx` to the version from `requirements.txt` to avoid breaking the bot’s HTTP client.

## Diagnostics reference
The diagnostics scripts call out exactly what's missing:
* **Local CLI:**
  ```bash
  python ocr/diagnostics.py
  ```
* **Discord slash command:** `/ocr_status`

Both paths surface missing Python dependencies, the Tesseract binary, and template issues so you can resolve blockers quickly.
