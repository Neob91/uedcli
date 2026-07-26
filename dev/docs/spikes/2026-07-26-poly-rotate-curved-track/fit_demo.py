#!/usr/bin/env python3
"""SPIKE — what `--fit-perimeter` does, what it FAILS to do, and the corrected version.

`brush poly align --ring --fit-perimeter` is documented as giving "an exact seam meet". It does not.
It snaps the around-ring density so the total U advance is a whole number of TEXELS:

    target = max(1, round(total_chord * density_u))          # polyalign.py

but a texture repeats every **W texels** (256 for a typical DX texture), not every 1. So on the
standard 8-sided R=256 cylinder it moves the closing-seam error from 1567.47 to 1567.00 texels —
and 1567 mod 256 = 31, so 31 texels of the pattern are still visibly out of step at the seam.

This script renders the three states so the difference is visible, and prototypes the fix:

    --mode leave   the default: no fitting at all          (31.47 texels out)
    --mode texel   what --fit-perimeter does today          (31.00 texels out)
    --mode tile    the CORRECTED fit: round to a whole      ( 0.00 texels out)
                   number of TILES, not texels

The corrected form needs the texture's pixel width, which uedcli's texture catalog already records
(`texture_catalog` entries carry `width`/`height`). That is the same dependency `align one-tile`
needs, so it is not a new coupling for the verb — `--fit-perimeter` has needed it since it shipped.

    fit_demo.py --trunk <maps/<level>> --brush NAME --mode leave|texel|tile [--texture-width 256]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli import polyalign                                    # noqa: E402
from uedcli.dispatch import TrunkLevelSource                    # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trunk", required=True)
    ap.add_argument("--brush", required=True)
    ap.add_argument("--mode", choices=["leave", "texel", "tile"], required=True)
    ap.add_argument("--texture-width", type=int, default=256)
    args = ap.parse_args(argv)

    src = TrunkLevelSource(Path(args.trunk))
    level = src.load()
    name = polyalign.resolve_actor_name(level, args.brush)
    actor = level.actors[name]
    sides = polyalign.find_faces(actor, name, item="Side")
    tokens = [f"{name}:{i}" for i in sides]

    if args.mode == "tile":
        # The corrected fit: monkey-patch the rounding so the TOTAL lands on a whole number of
        # TILES. Done by patching rather than reimplementing so this exercises the SHIPPED
        # _ring_align path end to end — only the rounding rule differs.
        W = args.texture_width
        real_round = polyalign.round if hasattr(polyalign, "round") else round

        import builtins
        orig = builtins.round

        def tile_round(x, *a):
            # _ring_align's only round() call is `round(total_chord * density_u)`.
            return max(W, orig(x / W) * W) if not a else orig(x, *a)

        builtins.round = tile_round
        try:
            polyalign.align(level, tokens, "ring", fit_perimeter=True)
        finally:
            builtins.round = orig
    else:
        polyalign.align(level, tokens, "ring", fit_perimeter=(args.mode == "texel"))

    src.save(verb="fit-demo", args={"mode": args.mode}, level=level, touched=[name])
    print(f"{name}: {len(sides)} side faces, mode={args.mode}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
