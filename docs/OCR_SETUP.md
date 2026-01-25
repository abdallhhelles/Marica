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
3. **Validate the installation:**
   ```bash
   # Quick validation of EasyOCR setup
   python ocr/validate_easyocr.py
   
   # Comprehensive diagnostics
   python ocr/diagnostics.py
   
   # Or run unit tests
   python -m unittest tests.test_ocr_dependencies
   ```
4. Verify versions: `tesseract --version` and, if OCR is enabled, `python -m pip show easyocr opencv-python-headless numpy torch torchvision`.

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
* **Conflicting packages:** third-party images sometimes bundle `googletrans==4.0.0rc1`, which forces `httpx==0.13.3`. The bot will detect this conflict and warn you at startup. Since `googletrans` is not used by this bot, you should uninstall it (`pip uninstall googletrans`) to avoid the conflict with the required `httpx==0.28.1` version.

## Diagnostics reference

### Quick Validation (`validate_easyocr.py`)
Fast check specifically for EasyOCR dependencies:
```bash
python ocr/validate_easyocr.py
```

This validator:
- Checks all required OCR packages are installed
- Verifies PyTorch is CPU-configured
- Validates Tesseract binary is available
- Confirms OCR template file exists
- Provides clear next steps if issues are found

### Comprehensive Diagnostics (`diagnostics.py`)
Full system check with detailed reporting:
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

### Unit Tests
Run automated tests to validate dependencies:
```bash
# Test OCR dependencies
python -m unittest tests.test_ocr_dependencies

# Test all dependencies including voice support (PyNaCl)
python -m unittest discover tests
```

## Testing the /scan Command

After validating the dependencies, test the `/scan` command in Discord:

### Prerequisites
1. Ensure the bot is running and connected to Discord
2. Have a clear profile screenshot ready (PNG, JPG, JPEG, or WEBP format)
3. OCR templates are configured in `ocr/boxes_ratios.json`

### Testing Steps
1. **Command-line testing (recommended first):**
   ```bash
   # Place your test screenshot in the shots/ directory
   cp your_profile_screenshot.png shots/
   
   # Run the OCR processor directly
   python ocr/ocr_runner.py
   
   # Review the output to ensure fields are extracted correctly
   ```
   
2. **Discord testing:**
   - Use the `/scan` command in a Discord server where the bot is installed
   - The bot will open a DM conversation with you
   - Follow the prompts to upload your profile screenshot
   - The bot will process the image and extract stats (CP, kills, server, VIP, etc.)
   - Review the extracted data for accuracy

3. **Verify results:**
   - Check that all numeric fields are extracted correctly
   - Verify text fields (name, alliance) are readable
   - Confidence scores should be above the threshold (0.40 for CPU, 0.45 for GPU)
   - Low confidence warnings indicate the screenshot quality or templates may need adjustment

### Troubleshooting
- **Poor OCR accuracy:** Adjust bounding boxes with `python ocr/box_picker.py`
- **Fields not detected:** Ensure screenshot matches the template layout
- **Command not responding:** Check bot logs for dependency errors or missing permissions
- **Low confidence scores:** Use higher resolution screenshots or improve lighting/contrast
