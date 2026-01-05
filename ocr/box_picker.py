import os
import json
import cv2

INPUT_DIR = "shots"
OUT_FILE = "boxes_ratios.json"

FIELDS = ["name", "power_cp", "kills", "alliance", "state"]

# Make selection easier on small images
SCALE = 3  # 1 = original, 2 or 3 recommended

WINDOW_W = 1200
WINDOW_H = 1800


def list_images(folder: str):
    if not os.path.isdir(folder):
        raise SystemExit(
            f"Input folder '{folder}' is missing. Create it and drop profile screenshots inside."
        )

    exts = (".png", ".jpg", ".jpeg", ".webp")
    files = [f for f in os.listdir(folder) if f.lower().endswith(exts)]
    files.sort()
    return files


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def main():
    files = list_images(INPUT_DIR)
    if not files:
        raise SystemExit(f"No images found in '{INPUT_DIR}'. Put screenshots in that folder.")

    ref_name = files[0]
    ref_path = os.path.join(INPUT_DIR, ref_name)

    img0 = cv2.imread(ref_path)
    if img0 is None:
        raise SystemExit(
            f"Could not read '{ref_path}'. If OpenCV can't read .webp, convert to .png first."
        )

    ref_h0, ref_w0 = img0.shape[:2]
    ref_aspect = ref_w0 / ref_h0

    # Scale up for easier selection
    img = img0
    if SCALE != 1:
        img = cv2.resize(img0, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)

    scaled_h, scaled_w = img.shape[:2]

    cv2.namedWindow("image", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("image", WINDOW_W, WINDOW_H)

    print("\nROI Picker (Saves ratios, works across phones)")
    print("For each field: drag a rectangle, press ENTER to accept. Press ESC to redo.\n")

    boxes_ratios = {}

    for field in FIELDS:
        while True:
            print(f"Select region for: {field}")
            x, y, w, h = cv2.selectROI("image", img, showCrosshair=True, fromCenter=False)
            x, y, w, h = int(x), int(y), int(w), int(h)

            if w <= 0 or h <= 0:
                print("Nothing selected. Try again.\n")
                continue

            # Convert from scaled pixels -> ratios (0..1) relative to scaled image
            x1r = clamp01(x / scaled_w)
            y1r = clamp01(y / scaled_h)
            x2r = clamp01((x + w) / scaled_w)
            y2r = clamp01((y + h) / scaled_h)

            boxes_ratios[field] = [x1r, y1r, x2r, y2r]
            print(f"Saved {field} ratios: {boxes_ratios[field]}\n")
            break

    cv2.destroyAllWindows()

    data = {
        "meta": {
            "reference_image": ref_name,
            "reference_size_px": [ref_w0, ref_h0],
            "reference_aspect": ref_aspect,
            "selection_scale": SCALE,
            "fields": FIELDS,
            "note": "Boxes are stored as ratios: [x1_ratio, y1_ratio, x2_ratio, y2_ratio]."
        },
        "template_ratios": boxes_ratios
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Done. Saved to '{OUT_FILE}'.")
    print("Next step: OCR runner will convert ratios back to pixels for each screenshot.")


if __name__ == "__main__":
    main()
