#!/usr/bin/env python3
"""Sample the center NxN pixel block of a level-photo PNG, average it, print R G B.

Used by the light-color/falloff RE probe: every test shot frames the sample point at the image
center (camera aimed with 'look:' at the exact world point being measured), so sampling a small
box around the center is robust to the 1-2px jitter a real renderer can introduce.
"""
import sys
from PIL import Image


def sample_center(path: str, box: int = 12) -> tuple[float, float, float]:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    x0, y0 = w // 2 - box // 2, h // 2 - box // 2
    pixels = [img.getpixel((x0 + dx, y0 + dy)) for dx in range(box) for dy in range(box)]
    n = len(pixels)
    return (sum(p[0] for p in pixels) / n, sum(p[1] for p in pixels) / n, sum(p[2] for p in pixels) / n)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        r, g, b = sample_center(path)
        print(f"{path}: R={r:.1f} G={g:.1f} B={b:.1f}")
