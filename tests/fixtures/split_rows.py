"""
Split piyao.org.cn rumor table images into individual row crops.
Each table has a header + 10 data rows. We detect horizontal borders
by finding rows of pixels that are mostly bright (>=240) — these are
the table lines separating rows.
"""
from PIL import Image
import numpy as np
import os

FIXTURES = "F:/Project/BullshitDetector/tests/fixtures"

TASKS = [
    ("real_piyao_policy_rumor_2024.png",  "fake_piyao_policy"),
    ("real_piyao_disaster_rumor_2024.png", "fake_piyao_disaster"),
    ("real_piyao_food_safety_2024.png",    "fake_piyao_food"),
    ("real_piyao_ai_rumor_2024.png",       "fake_piyao_ai"),
]

def find_horizontal_borders(gray_arr, brightness_thresh=230, coverage_thresh=0.85):
    """
    Return sorted list of y-coordinates where a row of pixels is
    mostly bright (table border line).
    """
    h, w = gray_arr.shape
    borders = []
    for y in range(h):
        row = gray_arr[y]
        bright_frac = np.mean(row >= brightness_thresh)
        if bright_frac >= coverage_thresh:
            borders.append(y)
    return borders

def group_borders(borders, min_gap=3):
    """Collapse runs of consecutive border rows into single y-values (midpoints)."""
    if not borders:
        return []
    groups = []
    run = [borders[0]]
    for b in borders[1:]:
        if b - run[-1] <= min_gap:
            run.append(b)
        else:
            groups.append(int(np.mean(run)))
            run = [b]
    groups.append(int(np.mean(run)))
    return groups

def crop_rows(img, border_ys, n_expected=10, padding=2):
    """
    Given border y-coordinates, extract data-row crops.
    border_ys should include top and bottom of table.
    Returns list of (y_start, y_end, crop_image).
    """
    crops = []
    w = img.width
    # Gaps between consecutive borders = cells (header + 10 data rows)
    segments = list(zip(border_ys[:-1], border_ys[1:]))
    # The header is typically the first (tallest or first) segment; skip it
    # We want the last n_expected segments as data rows
    data_segs = segments[-n_expected:] if len(segments) >= n_expected else segments
    for y0, y1 in data_segs:
        y0c = max(0, y0 + padding)
        y1c = min(img.height, y1 - padding)
        crop = img.crop((0, y0c, w, y1c))
        crops.append((y0c, y1c, crop))
    return crops

for fname, prefix in TASKS:
    path = os.path.join(FIXTURES, fname)
    img = Image.open(path).convert("RGB")
    gray = np.array(img.convert("L"))

    borders_raw = find_horizontal_borders(gray, brightness_thresh=230, coverage_thresh=0.85)
    borders = group_borders(borders_raw, min_gap=4)

    print(f"\n{'='*60}")
    print(f"File: {fname}")
    print(f"Image size: {img.size}")
    print(f"Detected border y-coords ({len(borders)}): {borders}")

    # Structure: outer top border | header dark band | 10 data rows | outer bottom border
    # The header band is ~2x the height of a data row (takes up 2/12 of total height).
    # Scan for the transition from the dark header to the first bright data row border.
    # Strategy: find the first y where brightness jumps back up after the dark header band.
    h_img = img.height
    gray_rows = gray  # already computed above

    # Find header end: scan downward from y=60, find first row with avg brightness >= 180
    # after crossing the dark header region (avg < 100)
    header_end = None
    in_dark = False
    for y in range(60, h_img):
        row_avg = np.mean(gray_rows[y])
        if not in_dark and row_avg < 100:
            in_dark = True
        if in_dark and row_avg >= 170:
            header_end = y
            break

    if header_end is None:
        # Fallback: assume header occupies top 2/12 of image
        header_end = int(h_img * 2 / 12)
        print(f"  WARNING: could not detect header end, using fallback y={header_end}")
    else:
        print(f"  Header ends at y={header_end}")

    # 10 data rows span from header_end to bottom of image
    bottom = h_img - 2
    row_h = (bottom - header_end) / 10
    data_borders = [int(header_end + i * row_h) for i in range(11)]
    print(f"  Data row borders (11): {data_borders}")

    crops = crop_rows(img, data_borders, n_expected=10, padding=2)
    print(f"Crops produced: {len(crops)}")

    for i, (y0, y1, crop) in enumerate(crops, start=1):
        out_name = f"{prefix}_{i:02d}.png"
        out_path = os.path.join(FIXTURES, out_name)
        crop.save(out_path)
        print(f"  [{i:02d}] y={y0}-{y1} (h={y1-y0}) -> {out_name}")

print("\nDone.")
