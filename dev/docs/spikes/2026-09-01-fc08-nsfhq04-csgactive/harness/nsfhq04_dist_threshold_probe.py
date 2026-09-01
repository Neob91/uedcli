#!/usr/bin/env python3
"""Epsilon-margin probe for NSFHQ04's `Brush842` (2026-09-01 continuation), adapted from
`dev/docs/spikes/2026-09-01-area51-training-final-residual/harness/area51_dist_threshold_probe.py`.

`Brush842` is the brush localized by `nsfhq04_prefix_search2.py`'s binary search as the SECOND
divergent brush post-`CsgOper::Active` (`528e602`): prefix n=512 (`Brush841`) is byte-exact,
n=513 (adds `Brush842`) diverges `d_nodes=+131 d_surfs=+0 d_leaves=+38`. `Brush842`'s authored
poly 0 is near-but-not-exactly planar (`Normal=(-0.002003, 0, 1.0)`, ~0.08uu Z-spread across its
4 vertices) despite an algebraically-trivial 180-degree-flip rotation -- flagged in the findings
ledger ("NSFHQ04 5th continuation") as a plausible trigger for a coplanar/split-epsilon
classification difference during `filter_ed_poly`'s classify-BSP descent, the SAME symptom shape
(node/leaf-only delta, surf-exact) the Area51 Entrance `Brush1852` investigation converged on the
same round -- and which that investigation's OWN threshold probe then RULED OUT (closest margin
0.2498, no node within 0.25 of the actual +-THRESH_SPLIT_POLY_WITH_PLANE=0.25 classify boundary).

Unlike the Area51 probe (which scoped to one already-attributed poly, `i_brush_poly=4`, found via
a separate per-poly fragment-count attribution pass), this script scopes only `UEDCLI_BSPCSG_
DESCENT_ACTOR=512` (Brush842's 0-based world-CSG index in the structural-only 660-brush list) and
leaves `_DESCENT_POLY` UNSET, so `descent_scope_matches` traces EVERY authored poly (and every
split-fragment) of Brush842's own `filter_ed_poly` descent through the n=512 world tree -- a
single run answers "is ANY node's classification anywhere near the +-0.25 threshold" without
needing a prior attribution step, since Brush842 has only 6 authored polys total.

Margin = distance from a node's min/max signed vertex-to-plane distance to the nearest of
+-THRESH_SPLIT_POLY_WITH_PLANE (0.25, `Engine.dll` VA 0x101518b0, disassembly-confirmed in the
`angr`-decompiler round). A near-zero margin at ANY node is the signature of a float-precision
epsilon flip; this script only measures, it does not fix anything.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]  # harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNK = ROOT / "_scratch/nsfhq04-structural-only2/maps/nsfhq04"
os.environ["UEDCLI_PROJECT"] = str(TRUNK.parent.parent)

from uedcli import trunk as trunk_mod  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402
import uedcli_native  # noqa: E402
from spike_classindex import class_index  # noqa: E402

level, ranks = trunk_mod.read_level(TRUNK)
ci = class_index()
brush_names = [n for n in level.order
               if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
assert brush_names[512] == "Brush842", brush_names[512]

os.environ["UEDCLI_BSPCSG_DESCENT_ACTOR"] = "512"
# _DESCENT_POLY deliberately UNSET -- trace every authored poly of Brush842 (see docstring).

ins513 = [BM._build_brush_input(nm, level.actors[nm]) for nm in brush_names[:513]]


def capture(fn):
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".log")
    tf.close()
    fd = os.open(tf.name, os.O_WRONLY)
    saved = os.dup(2)
    os.dup2(fd, 2)
    try:
        fn()
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(fd)
    return open(tf.name).read().splitlines()


lines = capture(lambda: uedcli_native.build_geometry_bspcsg(ins513))
desc = [l for l in lines if l.startswith("DESC")]
print(f"DESC lines for actor=512 (Brush842, all polys): {len(desc)}")

by_poly = {}
for l in desc:
    m = re.search(r"i_brush_poly=(-?\d+)", l)
    by_poly.setdefault(m.group(1), 0)
    by_poly[m.group(1)] += 1
print("DESC lines per i_brush_poly:", by_poly)

THRESH = 0.25
rows = []
for l in desc:
    mn = float(re.search(r"min=([-\d.]+)", l).group(1))
    mx = float(re.search(r"max=([-\d.]+)", l).group(1))
    cls = l.split("-> ", 1)[1] if "-> " in l else "?"
    margin_hi = abs(mx - THRESH)
    margin_lo = abs(mn - (-THRESH))
    margin = min(margin_hi, margin_lo)
    rows.append((margin, mn, mx, cls, l))

rows.sort(key=lambda r: r[0])
print("\nClosest-to-threshold nodes (margin = distance from min/max to +-0.25):")
for margin, mn, mx, cls, l in rows[:20]:
    print(f"  margin={margin:.6f}  min={mn:+.5f} max={mx:+.5f}  {cls}")

print(f"\nfull log: {len(desc)} lines")
out = ROOT / "_scratch/nsfhq04_brush842_desc_trace.log"
out.write_text("\n".join(desc) + "\n")
print("wrote", out)
