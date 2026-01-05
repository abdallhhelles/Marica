# OCR helper scripts

These scripts let you crop game profile screenshots and extract key stats with EasyOCR.

## Prerequisites
- Install the OCR extras: `pip install -r requirements-ocr.txt`
- Place your profile screenshots in the top-level `shots/` folder (create it if it doesn't exist).

## Workflow
1. **Pick bounding boxes**: run `python ocr/box_picker.py`. Drag a box for each field and press Enter to save. This writes normalized ratios to `ocr/boxes_ratios.json`.
2. **Run OCR**: drop the screenshots you want to scan into `shots/` and run `python ocr/ocr_runner.py`. The script will crop each image using the saved ratios, run EasyOCR, and print the parsed values.

If either script reports `Input folder 'shots' is missing`, create `shots/` and add at least one screenshot before running again.
