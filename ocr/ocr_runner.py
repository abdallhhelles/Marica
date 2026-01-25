"""OCR Runner for profile screenshot analysis.

This module processes profile screenshots using EasyOCR to extract text
from predefined bounding box regions. It's optimized for CPU-only processing
without GPU support.
"""
import importlib.util
import json
import logging
import os
import re
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Check dependencies before importing
_CV2_SPEC = importlib.util.find_spec("cv2")
_EASYOCR_SPEC = importlib.util.find_spec("easyocr")
_NUMPY_SPEC = importlib.util.find_spec("numpy")

if not (_CV2_SPEC and _EASYOCR_SPEC and _NUMPY_SPEC):  # pragma: no cover - CLI helper guard
    missing = []
    if not _CV2_SPEC:
        missing.append("opencv-python-headless")
    if not _EASYOCR_SPEC:
        missing.append("easyocr")
    if not _NUMPY_SPEC:
        missing.append("numpy")
    raise SystemExit(
        f"EasyOCR runner requires: {', '.join(missing)}. "
        "Install with `pip install -r requirements-ocr.txt` before running."
    )

import cv2
import easyocr
import numpy as np

INPUT_DIR = "shots"
BOXES_FILE = "boxes_ratios.json"

# If you want Arabic later add "ar" too: ["en", "ar"]
LANGS = ["en"]

# GPU detection - automatically disable if not available
GPU = False
try:
    import torch
    GPU = torch.cuda.is_available()
    if GPU:
        logger.info("CUDA GPU detected and enabled for OCR processing")
    else:
        logger.info("Running in CPU-only mode (no CUDA GPU detected)")
except ImportError:
    logger.info("PyTorch not available - running in CPU-only mode")

# Confidence threshold - dynamically adjusted for CPU processing
# CPU-only processing may produce slightly lower confidence scores
MIN_CONF = 0.40 if not GPU else 0.45
logger.info(f"OCR confidence threshold set to {MIN_CONF:.2f}")


def list_images(folder: str):
    """List all valid image files in the specified folder.
    
    Args:
        folder: Path to the folder containing images
        
    Returns:
        Sorted list of image filenames
        
    Raises:
        SystemExit: If folder doesn't exist or no images found
    """
    if not os.path.isdir(folder):
        logger.error(f"Input folder '{folder}' does not exist")
        raise SystemExit(
            f"Input folder '{folder}' is missing. Create it and drop profile screenshots inside."
        )

    exts = (".png", ".jpg", ".jpeg", ".webp")
    files = [f for f in os.listdir(folder) if f.lower().endswith(exts)]
    files.sort()
    
    if not files:
        logger.warning(f"No image files found in '{folder}'")
    else:
        logger.info(f"Found {len(files)} image(s) in '{folder}'")
    
    return files


def clamp(v, lo, hi):
    """Clamp a value between min and max bounds."""
    return max(lo, min(hi, v))


def validate_box_ratios(box):
    """Validate that bounding box ratios are within valid range.
    
    Args:
        box: List of 4 ratios [x1, y1, x2, y2]
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not box or len(box) != 4:
        return False
    
    # Check all ratios are between 0 and 1
    if not all(0 <= r <= 1 for r in box):
        return False
    
    # Check x2 > x1 and y2 > y1
    if box[2] <= box[0] or box[3] <= box[1]:
        return False
    
    return True


def crop_by_ratio(img, box):
    """Crop image based on normalized ratio coordinates.
    
    Args:
        img: Input image (numpy array)
        box: Bounding box as ratios [x1, y1, x2, y2] in range 0..1
        
    Returns:
        Cropped image region, or None if invalid
    """
    if not validate_box_ratios(box):
        logger.warning(f"Invalid bounding box ratios: {box}")
        return None
    
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
        logger.warning(f"Invalid crop dimensions after clamping: ({x1},{y1}) to ({x2},{y2})")
        return None

    return img[y1:y2, x1:x2]


def preprocess(crop):
    """Enhanced preprocessing for better OCR accuracy.
    
    Applies multiple image enhancement techniques to improve text recognition:
    - Converts to grayscale for better contrast
    - Upscales 2x for better detail capture
    - Applies Gaussian blur to reduce noise
    - Optional: adaptive thresholding for difficult images
    
    Args:
        crop: Input image crop (numpy array)
        
    Returns:
        Preprocessed grayscale image
    """
    try:
        # Convert to grayscale
        if len(crop.shape) == 3:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = crop
        
        # Upscale for better detail (2x is optimal for most cases)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        # Reduce noise with Gaussian blur (small kernel to preserve text edges)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # Optional: Apply adaptive thresholding for very low contrast images
        # This can help with difficult screenshots but may not always be needed
        # Uncomment the following lines if OCR accuracy is still low:
        # gray = cv2.adaptiveThreshold(
        #     gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        # )
        
        return gray
    except Exception as e:
        logger.error(f"Error in preprocessing: {e}")
        # Return original crop if preprocessing fails
        return crop


def ocr_field(reader, crop):
    """Extract text from a cropped image region using EasyOCR.
    
    Args:
        reader: EasyOCR Reader instance
        crop: Preprocessed image crop
        
    Returns:
        Tuple of (text, confidence) where text is the extracted string
        and confidence is a float between 0 and 1
    """
    try:
        results = reader.readtext(crop)
        if not results:
            return "", 0.0

        # Sort by confidence desc
        results.sort(key=lambda x: x[2], reverse=True)
        best_conf = float(results[0][2])

        # Join all detected text pieces (usually just one for these crops)
        text = " ".join([r[1] for r in results]).strip()
        return text, best_conf
    except Exception as e:
        logger.error(f"Error during OCR processing: {e}")
        return "", 0.0


def clean_number(s: str):
    """Extract digits from a string, removing commas, spaces, and other characters.
    
    Args:
        s: Input string potentially containing numbers
        
    Returns:
        String containing only digits
    """
    # Keep digits only, remove commas/spaces and any stray chars
    digits = re.sub(r"[^\d]", "", s)
    return digits


def main():
    """Main OCR processing pipeline."""
    logger.info("Starting OCR runner...")
    
    # Validate boxes file exists
    if not os.path.exists(BOXES_FILE):
        logger.error(f"Bounding boxes file not found: {BOXES_FILE}")
        raise SystemExit(f"Missing {BOXES_FILE}. Run box_picker.py first.")

    # Load bounding box configuration
    try:
        with open(BOXES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {BOXES_FILE}: {e}")
        raise SystemExit(f"Failed to parse {BOXES_FILE}. Please check JSON syntax.")
    except Exception as e:
        logger.error(f"Error reading {BOXES_FILE}: {e}")
        raise SystemExit(f"Failed to read {BOXES_FILE}: {e}")

    boxes = data.get("template_ratios", {})
    if not boxes:
        logger.error("No template_ratios found in boxes file")
        raise SystemExit("No template_ratios found in boxes file.")
    
    logger.info(f"Loaded {len(boxes)} bounding box template(s)")

    # Validate all boxes
    invalid_boxes = [field for field, box in boxes.items() if not validate_box_ratios(box)]
    if invalid_boxes:
        logger.warning(f"Invalid bounding boxes detected: {', '.join(invalid_boxes)}")

    # List input images
    files = list_images(INPUT_DIR)
    if not files:
        raise SystemExit(f"No images found in '{INPUT_DIR}'.")

    # Initialize EasyOCR reader
    try:
        logger.info(f"Initializing EasyOCR reader (languages: {LANGS}, GPU: {GPU})...")
        reader = easyocr.Reader(LANGS, gpu=GPU)
        logger.info("EasyOCR reader initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize EasyOCR reader: {e}")
        raise SystemExit(f"Failed to initialize EasyOCR: {e}")

    print("\nRunning OCR on screenshots...\n")

    # Process each image
    success_count = 0
    error_count = 0
    
    for fname in files:
        path = os.path.join(INPUT_DIR, fname)
        
        try:
            img = cv2.imread(path)
            if img is None:
                logger.warning(f"Could not read image: {fname}")
                print(f"{fname}: could not read image, skipping.")
                error_count += 1
                continue

            out = {"file": fname}
            confs = {}

            # Process each field
            for field, box in boxes.items():
                crop = crop_by_ratio(img, box)
                if crop is None:
                    logger.debug(f"{fname}: Invalid crop for field '{field}'")
                    out[field] = ""
                    confs[field] = 0.0
                    continue

                proc = preprocess(crop)
                text, conf = ocr_field(reader, proc)
                out[field] = text
                confs[field] = conf

            # Cleaning specific fields (match the actual field names in boxes_ratios.json)
            if "cp" in out:
                out["cp_clean"] = clean_number(out["cp"])
            if "kills" in out:
                out["kills_clean"] = clean_number(out["kills"])
            if "server" in out:
                out["server_clean"] = clean_number(out["server"])
            if "vip" in out:
                out["vip_clean"] = clean_number(out["vip"])

            # Print results (exclude verification fields from low-confidence warnings)
            warn_fields = [k for k, c in confs.items() if c < MIN_CONF and k not in {"account_btn", "settings_btn"}]
            warn = f"  ⚠ low conf: {', '.join(warn_fields)}" if warn_fields else ""

            print(f"=== {fname} ==={warn}")
            print(f"Name:     {out.get('name','')}  (conf {confs.get('name',0):.2f})")
            print(f"CP:       {out.get('cp','')}  -> {out.get('cp_clean','')} (conf {confs.get('cp',0):.2f})")
            print(f"Kills:    {out.get('kills','')}  -> {out.get('kills_clean','')} (conf {confs.get('kills',0):.2f})")
            print(f"Alliance: {out.get('alliance','')}  (conf {confs.get('alliance',0):.2f})")
            print(f"Server:   {out.get('server','')}  -> {out.get('server_clean','')} (conf {confs.get('server',0):.2f})")
            print(f"Likes:    {out.get('likes','')} (conf {confs.get('likes',0):.2f})")
            print(f"VIP:      {out.get('vip','')}  -> {out.get('vip_clean','')} (conf {confs.get('vip',0):.2f})")
            print()
            
            success_count += 1
            
        except Exception as e:
            logger.error(f"Error processing {fname}: {e}")
            print(f"Error processing {fname}: {e}")
            error_count += 1

    # Summary
    logger.info(f"OCR processing complete: {success_count} successful, {error_count} errors")
    print(f"Done. Processed {success_count} image(s), {error_count} error(s).\n")


if __name__ == "__main__":
    main()
