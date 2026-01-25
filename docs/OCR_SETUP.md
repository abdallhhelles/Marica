# OCR setup and troubleshooting

This guide keeps `/scan` (hybrid command) consistent across owner-managed installs. It is not intended for public distribution or third-party hosting.

## Provisioning checklist
1. Install Python packages:
   ```bash
   pip install -r requirements.txt        # base bot only (lightweight)
   pip install --no-cache-dir -r requirements-ocr.txt    # optional OCR extras (CPU wheels)
   ```
   * **Low-memory hosts (<=1 GB RAM):** torch/EasyOCR wheels may be too heavy for tiny panels. Either install only the base bot with `pip install -r requirements-lite.txt` (OCR disabled) or preload wheels on another machine and install with `pip install --no-index --find-links /path/to/wheels -r requirements.txt`. See [Low-memory installation](LOW_MEMORY_INSTALL.md) for step-by-step examples and wheel-cache tips.
2. Install the system Tesseract binary (required by pytesseract):
   * Debian/Ubuntu: `sudo apt-get install -y tesseract-ocr`
   * macOS (Homebrew): `brew install tesseract`
   * Windows (Chocolatey): `choco install tesseract`
3. Verify versions: `tesseract --version` and, if OCR is enabled, `python -m pip show easyocr opencv-python-headless numpy torch torchvision`.
4. Run diagnostics: `python ocr/diagnostics.py` locally to verify all dependencies and system configuration.

## CPU vs GPU Processing
Profile scanning runs purely on CPU by default with **automatic GPU detection**. The system will:
- Detect CUDA availability at runtime (no manual configuration needed)
- Automatically adjust confidence thresholds for CPU vs GPU processing (0.40 for CPU, 0.45 for GPU)
- Log the detected processing mode for transparency

If you later add a CUDA-capable GPU and want faster scans:
1. Install the matching CUDA wheels for torch/torchvision (instead of `+cpu` versions)
2. The system will automatically detect and use the GPU
3. Run diagnostics to verify GPU is detected: `python ocr/diagnostics.py`

## Template workflow (EasyOCR crops)
EasyOCR uses bounding boxes from `ocr/boxes_ratios.json`. If your screenshot layout differs:
1. Place a representative profile screenshot in `shots/`.
2. Build boxes: `python ocr/box_picker.py` (click/drag each field).
3. Validate: `python ocr/ocr_runner.py` and adjust boxes until every field reads cleanly.

## Hosting guidance
* **Containers / game panels:** add both `pip install -r requirements.txt` and `apt-get install -y tesseract-ocr` (or OS equivalent) directly to your startup command; consoles are often non-interactive.
* **Conflicting packages:** third-party images sometimes bundle `googletrans==4.0.0rc1`, which forces `httpx==0.13.3`. Re-pin `httpx` to the version from `requirements.txt` to avoid breaking the bot's HTTP client.

## Diagnostics reference
The enhanced diagnostics script provides comprehensive system checks:
```bash
python ocr/diagnostics.py
```

It reports:
- Python version compatibility (3.8+ recommended)
- All OCR dependencies and their versions
- PyTorch CPU/GPU status and CUDA availability
- Tesseract binary availability and version
- Template configuration validation
- Specific, actionable recommendations for missing components

The output includes clear visual indicators (✓/✗) and suggestions for resolving any issues.
