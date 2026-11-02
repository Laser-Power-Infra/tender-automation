"""Read the portal CAPTCHA with ddddocr.

  python -m nic_automation.captcha_decoder img1.png [img2.png ...]

  from nic_automation.captcha_decoder import solve
  solve("docs/distorted-image.png")  # -> "ekU3vk"
"""
import sys
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import cast

import ddddocr
import numpy as np
from PIL import Image

X_HEIGHT = set("acemnorsuvwxz")


@lru_cache(maxsize=1)
def _model():
    return ddddocr.DdddOcr(show_ad=False, beta=True)


def _flatten_image(data):
    """The portal draws black glyphs on a transparent background; flatten onto white or they read as black-on-black."""
    image = Image.open(BytesIO(data)).convert("RGBA")
    background = Image.new("RGBA", image.size, "white")
    background.alpha_composite(image)
    return background.convert("RGB")


def _glyph_mask(rgb):
    """Near-grey dark pixels only, so the blue dots and coloured noise lines drop out."""
    a = np.asarray(rgb).astype(int)
    return (a.max(axis=2) - a.min(axis=2) < 40) & (a.max(axis=2) < 120)


def _to_bytes(image):
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def solve_bytes(data: bytes) -> str:
    """Return the CAPTCHA text read from the flattened image."""
    return cast(str, _model().classification(_to_bytes(_flatten_image(data)), png_fix=True))


def solve_candidates(data: bytes) -> list[str]:
    """Plain and cleaned reads, best first."""
    rgb = _flatten_image(data)
    cleaned = Image.fromarray((~_glyph_mask(rgb) * 255).astype("uint8"))
    cleaned = cleaned.resize((cleaned.width * 2, cleaned.height * 2), Image.Resampling.LANCZOS)
    return [solve_bytes(data), cast(str, _model().classification(_to_bytes(cleaned), png_fix=True))]


def _clean_mask(mask):
    """Keep only glyph-sized components: the black noise squares are <=5 px tall."""
    import cv2

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype("uint8"), connectivity=8)
    clean = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_HEIGHT] >= 15:
            clean[labels == i] = True
    return clean


def _boxes(mask):
    """Six glyph columns: drop the tiny black noise squares, then merge the narrowest gaps down to six."""
    clean = _clean_mask(mask)
    cols = np.where(clean.any(axis=0))[0]
    if len(cols) == 0:
        return []
    runs = []
    start = prev = cols[0]
    for x in cols[1:]:
        if x - prev > 1:
            runs.append([start, prev])
            start = x
        prev = x
    runs.append([start, prev])
    while len(runs) > 6:
        gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
        i = gaps.index(min(gaps))
        runs[i][1] = runs[i + 1][1]
        del runs[i + 1]
    if len(runs) < 6:
        return []
    boxes = []
    for x0, x1 in runs:
        rows = np.where(clean[:, x0:x1 + 1].any(axis=1))[0]
        boxes.append((int(x0), int(x1), int(rows.min()), int(rows.max())))
    return boxes


def fix_case(text: str, data: bytes) -> str:
    """ddddocr reads the letters well but leans lowercase; uppercase x-height letters are taller than nearby ones.

    Height is compared against the shortest glyph in a +-3 window, because the wave distortion shifts and scales
    glyphs along x. Ascenders/descenders (T/t, B/b, J/j...) are left to ddddocr: their cases look alike at this size.
    """
    rgb = _flatten_image(data)
    boxes = _boxes(_glyph_mask(rgb))
    if len(boxes) != len(text):
        return text
    heights = [bottom - top + 1 for (_, _, top, bottom) in boxes]
    out = []
    for i, (ch, height) in enumerate(zip(text, heights)):
        low = ch.lower()
        if low in X_HEIGHT and ch.isalpha():
            ref = min(heights[max(0, i - 3):i + 4])
            if height >= ref * 1.2:
                ch = low.upper()
            elif height <= ref * 0.75:
                ch = low
        out.append(ch)
    return "".join(out)


def save_captcha(data, path):
    """Save the flattened image (what OCR saw) so it can be checked by eye."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _flatten_image(data).save(path)


def solve(path):
    """Return the CAPTCHA text read from the image at `path`."""
    return solve_bytes(Path(path).read_bytes())


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(f"{p}: {solve(p)}")


