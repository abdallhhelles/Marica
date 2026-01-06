import importlib.util
import json
import os
import re

_CV2_SPEC = importlib.util.find_spec("cv2")
_EASYOCR_SPEC = importlib.util.find_spec("easyocr")

if not (_CV2_SPEC and _EASYOCR_SPEC):  # pragma: no cover - CLI helper guard
    raise SystemExit(
        "EasyOCR runner requires easyocr and opencv-python-headless. "
        "Install with `pip install -r requirements.txt` before running."
    )

import cv2
import easyocr

INPUT_DIR = "shots"
BOXES_FILE = "boxes_ratios.json"

# If you want Arabic later add "ar" too: ["en", "ar"]
LANGS = ["en"]

# If you have a GPU and CUDA set up, set gpu=True
GPU = False

# Confidence threshold, below this we warn
MIN_CONF = 0.45


def list_images(folder: str):
    if not os.path.isdir(folder):
        raise SystemExit(
            f"Input folder '{folder}' is missing. Create it and drop profile screenshots inside."
        )

    exts = (".png", ".jpg", ".jpeg", ".webp")
    files = [f for f in os.listdir(folder) if f.lower().endswith(exts)]
    files.sort()
    return files


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def crop_by_ratio(img, box):
    """box = [x1r, y1r, x2r, y2r] ratios in 0..1"""
    h, w = img.shape[:2]
    x1 = int(w * box[0])
    y1 = int(h * box[1])
    x2 = int(w * box[2])
    y2 = int(h * box[3])

    # safety clamp
    x1 = clamp(x1, 0, w - 1)
    x2 = clamp(x2, 1, w)
    y1 = clamp(y1, 0, h - 1)
    y2 = clamp(y2, 1, h)

    if x2 <= x1 or y2 <= y1:
        return None

    return img[y1:y2, x1:x2]


def preprocess(crop):
    """Simple UI-friendly preprocess."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return gray


def ocr_field(reader, crop):
    """
    Returns: (text, conf)
    EasyOCR returns list of (bbox, text, conf). We pick the best conf and join if needed.
    """
    results = reader.readtext(crop)
    if not results:
        return "", 0.0

    # Sort by confidence desc
    results.sort(key=lambda x: x[2], reverse=True)
    best_conf = float(results[0][2])

    # Join all detected text pieces (usually just one for these crops)
    text = " ".join([r[1] for r in results]).strip()
    return text, best_conf


def clean_number(s: str):
    # Keep digits only, remove commas/spaces and any stray chars
    digits = re.sub(r"[^\d]", "", s)
    return digits


def main():
    if not os.path.exists(BOXES_FILE):
        raise SystemExit(f"Missing {BOXES_FILE}. Run box_picker.py first.")

    with open(BOXES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    boxes = data.get("template_ratios", {})
    if not boxes:
        raise SystemExit("No template_ratios found in boxes file.")

    files = list_images(INPUT_DIR)
    if not files:
        raise SystemExit(f"No images found in '{INPUT_DIR}'.")

    reader = easyocr.Reader(LANGS, gpu=GPU)

    print("\nRunning OCR on screenshots...\n")

    for fname in files:
        path = os.path.join(INPUT_DIR, fname)
        img = cv2.imread(path)
        if img is None:
            print(f"{fname}: could not read image, skipping.")
            continue

        out = {"file": fname}
        confs = {}

        for field, box in boxes.items():
            crop = crop_by_ratio(img, box)
            if crop is None:
                out[field] = ""
                confs[field] = 0.0
                continue

            proc = preprocess(crop)
            text, conf = ocr_field(reader, proc)
            out[field] = text
            confs[field] = conf

        # Cleaning specific fields
        if "power_cp" in out:
            out["power_cp_clean"] = clean_number(out["power_cp"])
        if "kills" in out:
            out["kills_clean"] = clean_number(out["kills"])
        if "state" in out:
            out["state_clean"] = clean_number(out["state"])

        # Print nicely
        warn_fields = [k for k, c in confs.items() if c < MIN_CONF]
        warn = f"  ⚠ low conf: {', '.join(warn_fields)}" if warn_fields else ""

        print(f"=== {fname} ==={warn}")
        print(f"Name:     {out.get('name','')}  (conf {confs.get('name',0):.2f})")
        print(f"Power:    {out.get('power_cp','')}  -> {out.get('power_cp_clean','')} (conf {confs.get('power_cp',0):.2f})")
        print(f"Kills:    {out.get('kills','')}  -> {out.get('kills_clean','')} (conf {confs.get('kills',0):.2f})")
        print(f"Alliance: {out.get('alliance','')}  (conf {confs.get('alliance',0):.2f})")
        print(f"State:    {out.get('state','')}  -> {out.get('state_clean','')} (conf {confs.get('state',0):.2f})")
        print()

    print("Done.\n")


if __name__ == "__main__":
    main()
