# OCR setup and troubleshooting

This guide keeps `/scan_profile` predictable across the owner-managed environment. It is not intended for public distribution or third-party hosting.

## Provisioning checklist
1. Install Python packages:
   ```bash
   pip install -r requirements.txt        # base bot only (lightweight)
   pip install --no-cache-dir -r requirements-ocr.txt    # optional OCR extras (CPU wheels)
   ```
   * **Low-memory hosts (≤1 GB RAM):** torch/EasyOCR wheels may be too heavy for tiny panels. Either install only the base bot with `pip install -r requirements-lite.txt` (OCR disabled) or preload wheels on another machine and install with `pip install --no-index --find-links /path/to/wheels -r requirements.txt`. See [Low-memory installation](LOW_MEMORY_INSTALL.md) for step-by-step examples and wheel-cache tips.
2. Install the system Tesseract binary (required by pytesseract):
   * Debian/Ubuntu: `sudo apt-get install -y tesseract-ocr`
   * macOS (Homebrew): `brew install tesseract`
   * Windows (Chocolatey): `choco install tesseract`
3. Verify versions: `tesseract --version` and, if OCR is enabled, `python -m pip show easyocr opencv-python-headless numpy torch torchvision`.
4. Run diagnostics: `python ocr/diagnostics.py` locally.

Profile scanning runs purely on CPU by default (see `GPU = False` in `ocr/ocr_runner.py`). If you later add a CUDA-capable GPU
and want faster scans, install the matching CUDA wheels for torch/torchvision and flip that flag to `True`.

## Template workflow (EasyOCR crops)
EasyOCR uses bounding boxes from `ocr/boxes_ratios.json`. If your screenshot layout differs from the default:
1. Place a representative profile screenshot in `shots/`.
2. Build boxes: `python ocr/box_picker.py` (click/drag each field).
3. Validate: `python ocr/ocr_runner.py` and adjust boxes until every field reads cleanly.

## Hosting guidance
* **Containers / game panels:** add both `pip install -r requirements.txt` and `apt-get install -y tesseract-ocr` (or OS equivalent) directly to your startup command; consoles are often non-interactive.
* **Conflicting packages:** third-party images sometimes bundle `googletrans==4.0.0rc1`, which forces `httpx==0.13.3`. Re-pin `httpx` to the version from `requirements.txt` to avoid breaking the bot’s HTTP client.

## Diagnostics reference
The diagnostics script calls out exactly what's missing:
```bash
python ocr/diagnostics.py
```

It surfaces missing Python dependencies, the Tesseract binary, and template issues so you can resolve blockers quickly.
