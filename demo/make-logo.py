#!/usr/bin/env python3
"""Generate a CC0 neon club logo (our own art) as a transparent PNG, for use as a
video/still overlay. No game assets — pure Pillow. Output: demo/assets/logo/neon-strata.png"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = Path(__file__).resolve().parent / "assets" / "logo"
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1400, 520
CYAN, MAGENTA, WHITE = (90, 230, 255), (255, 70, 200), (235, 255, 255)


def font(size: int) -> ImageFont.FreeTypeFont:
    for n in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def tracked(draw, xy, text, fnt, fill, track):
    """Draw uppercase text with letter-spacing; return total width."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + track
    return x - xy[0] - track


def layer(text, fnt, color, track, center_y):
    """One transparent layer with the tracked text, centered horizontally."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = sum(d.textlength(c, font=fnt) + track for c in text) - track
    asc, desc = fnt.getmetrics()
    tracked(d, ((W - w) / 2, center_y - (asc + desc) / 2), text, fnt, color, track)
    return im


def neon(text, fnt, track, cy, glow_hi, glow_lo):
    """Composite a neon word: two colored glow halos + a bright near-white core."""
    core = layer(text, fnt, WHITE, track, cy)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for color, radius, alpha in ((glow_lo, 26, 210), (glow_hi, 12, 235), (glow_hi, 5, 255)):
        halo = layer(text, fnt, color + (alpha,), track, cy).filter(ImageFilter.GaussianBlur(radius))
        out = Image.alpha_composite(out, halo)
    return Image.alpha_composite(out, core)


img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
img = Image.alpha_composite(img, neon("NEON", font(120), 18, 150, MAGENTA, MAGENTA))
img = Image.alpha_composite(img, neon("STRATA", font(210), 26, 350, CYAN, CYAN))
img.save(OUT / "neon-strata.png")

# a version on black, for backgrounds / the club-sign overlay
bg = Image.new("RGBA", (W, H), (6, 7, 12, 255))
black = Image.alpha_composite(bg, img).convert("RGB")
black.save(OUT / "neon-strata-black.png")

# 512x256 opaque BMP — the source for the in-level .utx sign (make_utx.py). Canonical
# orientation (reads left-to-right); the sign face corrects UE1 mapping via pan/rotate, so
# never pre-flip this file. Pure black bg so the unlit texture reads as self-lit neon on glass.
sign = Image.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 255)), img).convert("RGB")
sign.resize((512, 256)).save(OUT / "neon-strata-512.bmp")
print(f"wrote {OUT/'neon-strata.png'}, neon-strata-black.png, neon-strata-512.bmp")
