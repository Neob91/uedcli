"""The texture-colours pre-fill — the asset catalog's ONE inference exception (TEXTURE arm T4).

A small FIXED named palette per texture, ordered by descending share of the image. It earns the
exception (`direction/asset-catalog.md`) because it reads nothing but that texture's OWN pixels:
`texture search --color brown` works on a fresh clone before anything is classified. An LLM-supplied
`colors` overrides the pre-fill and wins.

Pure + offline: `derive_colors` takes decoded `(width, height, rgb)` — no Pillow decode, no package,
no corpus scan. It downsamples big images with a deterministic stride purely as a sampling cap.
"""
from __future__ import annotations

# A fixed, closed colour vocabulary (colours ARE a closed set, unlike the open `tags`). Reference
# RGBs are canonical centroids; ORDER is load-bearing — the tie-break for equal-share colours and for
# an equidistant per-pixel snap. Matched to the retired manifest catalog's palette so a re-derive on
# an already-classified corpus is stable.
PALETTE: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("black", (0, 0, 0)),
    ("white", (255, 255, 255)),
    ("grey", (128, 128, 128)),
    ("red", (200, 30, 30)),
    ("orange", (220, 120, 30)),
    ("yellow", (225, 215, 60)),
    ("green", (40, 150, 60)),
    ("blue", (40, 80, 190)),
    ("purple", (120, 50, 160)),
    ("pink", (230, 130, 170)),
    ("brown", (110, 70, 40)),
    ("tan", (200, 175, 130)),
)
PALETTE_NAMES: tuple[str, ...] = tuple(name for name, _ in PALETTE)
_ORDER = {name: i for i, name in enumerate(PALETTE_NAMES)}

COLOR_MIN_SHARE = 0.12
COLOR_CAP = 3
_SAMPLE_CAP = 64 * 64                                # never snap more than this many pixels


def nearest_color(rgb: tuple[int, int, int]) -> str:
    """Nearest palette name by squared RGB distance; an equidistant tie breaks by PALETTE order."""
    best_name, best_d2 = PALETTE[0][0], None
    for name, (pr, pg, pb) in PALETTE:
        d2 = (rgb[0] - pr) ** 2 + (rgb[1] - pg) ** 2 + (rgb[2] - pb) ** 2
        if best_d2 is None or d2 < best_d2:            # strict < => earlier PALETTE entry wins ties
            best_name, best_d2 = name, d2
    return best_name


def validate_colors(names: list[str]) -> None:
    """Reject any colour name not in the fixed palette (raises `ValueError` naming the offenders),
    so an LLM-supplied `--colors` can never store a name `--color` search will never match."""
    bad = [n for n in names if n not in PALETTE_NAMES]
    if bad:
        raise ValueError(f"unknown color(s): {', '.join(bad)} — valid: {', '.join(PALETTE_NAMES)}")


def derive_colors(width: int, height: int, rgb: bytes) -> list[str]:
    """The texture's named colours from its mip-0 pixels: snap each pixel to the nearest of the 12
    names, rank names by pixel share, keep those over `COLOR_MIN_SHARE` up to `COLOR_CAP`, ordered
    by descending share then PALETTE order. A high-entropy image where no name clears the threshold
    keeps its single most-frequent name. Big images are strided down to `_SAMPLE_CAP` pixels
    (deterministic) purely as a sampling cap. A coarse browse aid, not a precise readout."""
    total_px = width * height
    if total_px == 0:
        return []
    step = max(1, total_px // _SAMPLE_CAP)             # deterministic stride, not a resample
    tally: dict[str, int] = {}
    sampled = 0
    for i in range(0, total_px, step):
        px = (rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2])
        name = nearest_color(px)
        tally[name] = tally.get(name, 0) + 1
        sampled += 1
    kept = [(name, n) for name, n in tally.items() if n / sampled >= COLOR_MIN_SHARE]
    kept.sort(key=lambda kn: (-kn[1], _ORDER[kn[0]]))
    names = [name for name, _ in kept[:COLOR_CAP]]
    if not names and tally:                            # nothing clears the threshold — keep the top
        names = [max(tally.items(), key=lambda kn: (kn[1], -_ORDER[kn[0]]))[0]]
    return names
