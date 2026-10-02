#!/usr/bin/env python3
"""Second TEXALIGN fixture: ONE wedge per level, whose single test face has a normal that BRACKETS
one of the guard thresholds read out of `Editor.dll`'s `.rdata` (0.05 for FLOOR/WALLX/WALLY, 0.95
for WALLDIR/WALLPAN).

One brush per level on purpose. The three projection modes anchor the surface at
`plane_offset / N[axis]`, which BLOWS UP as `N[axis]` approaches the guard, and keeping each wedge's
local origin at the world origin keeps that anchor a couple of hundred uu instead of tens of
thousands. NO claim is made that a large anchor crashes anything: an earlier six-wedge version of
this fixture did kill the editor twice, but a later run of the same fixture died on a round that ran
no `TEXALIGN` at all, so those deaths are the ordinary UED22 flakiness (`unrealed/quirks.md`
"Stability"). Small levels are simply cheaper to re-run when it dies.

`CASES` maps a level name to (target |N[axis]|, the mode whose guard it brackets).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli import builders                     # noqa: E402
from uedcli.model import Brush                  # noqa: E402

TEX = "GameMisc.ex_Bricks"
LEG = 200.0
DEPTH = 128.0

# level -> (t, axis-in-profile, extrude axis, swap, mode under test)
CASES = {
    "NZ049": (0.049, "y", False, "FLOOR"),      # |N.Z| just below 0.05  -> expect SKIP
    "NZ051": (0.051, "y", False, "FLOOR"),      # just above             -> expect APPLY
    "NZ949": (0.949, "y", False, "WALLDIR"),    # |N.Z| just below 0.95  -> expect APPLY
    "NZ951": (0.951, "y", False, "WALLDIR"),    # just above             -> expect SKIP
    "NY049": (0.049, "z", False, "WALLY"),      # |N.Y| just below 0.05  -> expect SKIP
    "NY051": (0.051, "z", False, "WALLY"),
    "NX049": (0.049, "z", True, "WALLX"),       # |N.X| just below 0.05  -> expect SKIP
    "NX051": (0.051, "z", True, "WALLX"),
}
TEST_POLY = 3                                    # the hypotenuse, in `_prism`'s face order


def _prism(profile, depth, axis):
    h = depth / 2.0
    if axis == "y":
        def P(a, b, s):
            return (a, s * h, b)
    else:
        def P(a, b, s):
            return (a, b, s * h)
    lo = [P(a, b, -1) for a, b in profile]
    hi = [P(a, b, +1) for a, b in profile]
    out_lo = (0, -1, 0) if axis == "y" else (0, 0, -1)
    out_hi = (0, 1, 0) if axis == "y" else (0, 0, 1)
    faces = [(lo, out_lo), (list(reversed(hi)), out_hi)]
    for i in range(len(profile)):
        a0, b0 = profile[i]
        a1, b1 = profile[(i + 1) % len(profile)]
        ring = [P(a0, b0, -1), P(a1, b1, -1), P(a1, b1, +1), P(a0, b0, +1)]
        faces.append((ring, P(b1 - b0, -(a1 - a0), 0)))
    return Brush(model_name="Model",
                 polys=[builders._face(r, o, TEX, 0, item="OUTSIDE") for r, o in faces])


def build_actors(case: str):
    t, axis, swap, _mode = CASES[case]
    w = LEG * t / math.sqrt(1.0 - t * t)
    prof = ([(0.0, 0.0), (LEG, 0.0), (0.0, w)] if swap
            else [(0.0, 0.0), (w, 0.0), (0.0, LEG)])
    room = builders.cube(2048, 1024, 1024, texture=TEX)
    wedge = _prism(prof, DEPTH, axis)
    return [builders.make_brush_actor("Room", room, (0, 0, 0), csg="subtract"),
            builders.make_brush_actor(case, wedge, (0, 0, 0), csg="add")]
