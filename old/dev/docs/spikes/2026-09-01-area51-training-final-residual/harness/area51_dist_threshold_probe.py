#!/usr/bin/env python3
"""Diagnostic for the classify-BSP over-fragmentation lead (2026-09-01 angr round): for Brush1852's
`i_brush_poly=4` (the single authored poly that alone accounts for 10 of native's 26 vs the editor's
17 terminal fragments at the n=506->507 prefix), dump every `filter_ed_poly` DESCENT trace line
(`bspcsg.rs::descent_scope_matches` + its `DESC ...` eprintln) and report how close each node's
min/max signed distance sits to the +-THRESH_SPLIT_POLY_WITH_PLANE=0.25 classify threshold
(`FPoly::SplitWithPlane`, Engine.dll VA 0x101518b0, disassembly-confirmed this round). A near-zero
margin at ANY node is the signature of a float-precision epsilon flip (native and the editor computing
the same vertex-to-plane distance via a different FP operation order/precision and landing on opposite
sides of 0.25) rather than a logic bug -- this script only measures the margin, it does not fix
anything.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache/"
             "65b9261c371bdf8573cb7bf9128a3f6664b14d2ac360ef6fbfd4a0d292986ece/trunk/maps/15_area51_entrance")
os.environ["UEDCLI_PROJECT"] = str(TRUNK.parent.parent)

from uedcli import trunk as trunk_mod  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402
import uedcli_native  # noqa: E402
from spike_classindex import class_index  # noqa: E402

level, ranks = trunk_mod.read_level(TRUNK)
ci = class_index()
brush_names = [n for n in level.order
               if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
assert brush_names[506] == "Brush1852", brush_names[506]

os.environ["UEDCLI_BSPCSG_DESCENT_ACTOR"] = "506"
os.environ["UEDCLI_BSPCSG_DESCENT_POLY"] = "4"

ins507 = [BM._build_brush_input(nm, level.actors[nm]) for nm in brush_names[:507]]

import tempfile


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


lines = capture(lambda: uedcli_native.build_geometry_bspcsg(ins507))
desc = [l for l in lines if l.startswith("DESC")]
print(f"DESC lines for actor=506 i_brush_poly=4: {len(desc)}")

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
for margin, mn, mx, cls, l in rows[:15]:
    print(f"  margin={margin:.6f}  min={mn:+.5f} max={mx:+.5f}  {cls}")

print(f"\nfull log: {len(desc)} lines")
out = ROOT / "_scratch/area51_p4_desc_trace.log"
out.write_text("\n".join(desc) + "\n")
print("wrote", out)
