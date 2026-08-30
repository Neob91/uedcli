#!/usr/bin/env python3
"""Print raw authored vertices for Brush143's 6 polys, and scan all freeclinic08 trunk
brushes for any poly whose plane sits near Z=-274 within the brush's XY footprint
(candidate for the coincident face the editor's CSG drops)."""
import os
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
os.environ.setdefault("UEDCLI_PROJECT", "/workspace/uedcli/_scratch/geo-confirm-freeclinic08-wk")

from uedcli import trunk  # noqa: E402

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-freeclinic08-wk/maps/freeclinic08"
TARGET = "Brush143"


def main():
    level, _ranks = trunk.read_level(Path(TRUNK))
    actor = level.actors[TARGET]
    loc = actor.location
    print(f"{TARGET} Location={loc}")
    for i, poly in enumerate(actor.brush.polys):
        verts_world = [(float(v[0]) + float(loc[0]), float(v[1]) + float(loc[1]),
                         float(v[2]) + float(loc[2])) for v in poly.vertices]
        print(f"poly {i}: tex={poly.texture} normal(authored)={poly.normal} origin(authored)={poly.origin}")
        for v in poly.vertices:
            print(f"    raw vert (brush-local) = {v}")

    print("\n--- scanning all brushes for a poly plane near Z in [-276,-272], XY overlap with Brush143's footprint ---")
    # Brush143 world footprint from native surf dump: X in [1088,1160], Y in [-2504,-2432]
    xlo, xhi = 1080, 1170
    ylo, yhi = -2510, -2425
    for name in level.order:
        a = level.actors[name]
        if a.brush is None or name == TARGET:
            continue
        aloc = a.location or (0, 0, 0)
        for i, poly in enumerate(a.brush.polys):
            if poly.origin is None or poly.normal is None:
                continue
            ox = float(poly.origin[0]) + float(aloc[0])
            oy = float(poly.origin[1]) + float(aloc[1])
            oz = float(poly.origin[2]) + float(aloc[2])
            nz = float(poly.normal[2])
            if abs(nz) > 0.9 and -277 <= oz <= -271 and xlo <= ox <= xhi and ylo <= oy <= yhi:
                print(f"  {name} poly{i}: tex={poly.texture} origin_world=({ox:.2f},{oy:.2f},{oz:.2f}) "
                      f"normal={poly.normal}")


if __name__ == "__main__":
    raise SystemExit(main())
