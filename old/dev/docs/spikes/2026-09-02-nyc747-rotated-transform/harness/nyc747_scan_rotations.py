#!/usr/bin/env python3
"""NYC 747 (03_NYC_747.dx) rotated-brush inventory -- first step of the "is the open node/leaf
residual a rotated-brush FPoly::transform issue" cross-validation (parallel to the same hypothesis
being tested on Area51 Entrance).

`uedcli/rotation.py`'s module header already documents a KNOWN, UNMEASURED gap: a genuine
NON-CARDINAL multi-axis FRotator (arbitrary angle on >=2 axes at once) composes its 3x3 in Python
double (`matmul(Rz, matmul(Ry, Rx))`), while the real editor composes in float32 `FCoords` -- ULP-
approximate, not bit-exact, for that specific case only. Every rotation the DX corpus was checked
against up to that point was either single-axis or CARDINAL multi-axis (angles that are multiples of
90 degrees on every rotated axis), for which double and f32 composition are proven bit-identical
after the final f32 cast. This script checks whether NYC 747 actually contains a genuine non-cardinal
multi-axis case among its world-CSG brushes -- the necessary precondition for that gap to be this
level's root cause.

Usage: .venv/bin/python nyc747_scan_rotations.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNK = (ROOT / "_scratch/uedcli-parity-cache"
         / "3c2fa42895d171d2453f62a38ade7e6be33247f29def5fa335bd2e70e9d1c953"
         / "trunk/maps/03_nyc_747")

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli import rotation as ROT                 # noqa: E402
from spike_classindex import class_index           # noqa: E402
import os                                          # noqa: E402

os.environ.setdefault("UEDCLI_PROJECT", str(TRUNK.parent.parent))


def is_cardinal(uu: int) -> bool:
    """True if this FRotator field, after the GMath low-2-bit truncation, lands on a multiple of
    90 degrees (16384 UU) -- i.e. sin/cos in {0, +-1} up to the table's own float32 rounding."""
    table_idx = (uu >> 2) & 16383   # what gmath_sin/gmath_cos actually index
    return (table_idx % 4096) == 0  # 16384 table entries / 4 quadrants = 4096 per 90 degrees


def axes_rotated(uu_triple) -> int:
    """How many of (Pitch, Yaw, Roll) are non-identity (not table-truncation-zero)."""
    return sum(1 for c in uu_triple if ((c >> 2) & 16383) != 0)


def main():
    level, _ranks = trunk.read_level(TRUNK)
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    print(f"total world-csg brushes: {len(names)}")

    rotated = []
    non_cardinal_multi = []
    for n in names:
        a = level.actors[n]
        uu = ROT.actor_rotation_uu(a)
        if ROT.is_identity_uu(uu):
            continue
        rotated.append((n, uu))
        naxes = axes_rotated(uu)
        if naxes >= 2 and not all(is_cardinal(c) for c in uu):
            non_cardinal_multi.append((n, uu))

    print(f"rotated brushes (non-identity): {len(rotated)} / {len(names)}")
    for n, uu in rotated:
        naxes = axes_rotated(uu)
        card = all(is_cardinal(c) for c in uu)
        print(f"  {n:20s} Pitch={uu[0]:6d} Yaw={uu[1]:6d} Roll={uu[2]:6d} "
              f"axes={naxes} cardinal={card}")

    print(f"\nGENUINE NON-CARDINAL MULTI-AXIS brushes: {len(non_cardinal_multi)}")
    for n, uu in non_cardinal_multi:
        print(f"  {n}: {uu}")


if __name__ == "__main__":
    raise SystemExit(main())
