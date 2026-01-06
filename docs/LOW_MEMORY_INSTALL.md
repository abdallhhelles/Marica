# Low-memory installation (≤512 MB RAM)

Tiny game panels often get OOM-killed when torch or EasyOCR wheels are built on-device. Use one of these approaches to deploy Marica without live-compiling heavy dependencies.

## Option A: Skip OCR entirely
* Install the lightweight requirements: `pip install -r requirements-lite.txt`
* OCR features (e.g., `/scan_profile`) stay disabled; the rest of the bot runs normally.

## Option B: Preload wheels from a larger machine
1. On a machine with more RAM and the **same Python version/architecture** as your host, download all wheels:
   ```bash
   mkdir -p marica-wheels
   pip download -r requirements.txt -d marica-wheels
   ```
2. Compress and upload the folder to your host (e.g., `scp -r marica-wheels user@host:/home/container/`).
3. Install from the local cache (no internet downloads):
   ```bash
   pip install --no-index --find-links /home/container/marica-wheels -r requirements.txt
   ```
4. Keep the wheel cache around so restarts avoid re-downloading.

## Option C: Preload only OCR wheels and run lite install
If storage is tight, you can mix the lite requirements with a small OCR wheel cache:
1. Install core deps: `pip install -r requirements-lite.txt`
2. Download only the OCR extras elsewhere and copy them over:
   ```bash
   mkdir -p marica-ocr-wheels
   pip download easyocr torch torchvision opencv-python-headless pillow numpy pytesseract -d marica-ocr-wheels
   ```
3. Install the OCR extras from the cache when you enable scanning:
   ```bash
   pip install --no-index --find-links /home/container/marica-ocr-wheels easyocr torch torchvision opencv-python-headless pillow numpy pytesseract
   ```

## Notes
* Torch wheels are large (~900 MB). Do not attempt to build from source on a 512 MB host.
* Make sure the wheel cache matches the host’s Python version (e.g., cp312) and CPU architecture (x86_64 vs aarch64).
* The system `tesseract-ocr` binary still needs to be installed through the OS package manager.
