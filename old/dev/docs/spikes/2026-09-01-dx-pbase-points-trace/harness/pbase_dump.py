"""Dump native (flag-on) vs golden Points arrays + per-surf p_base for DX.dx, plus Brush T3D
origins/vertices, to pin the exact remaining insertion-order divergence."""
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / "dev/docs/spikes/2026-08-31-native-parity-report/harness"
sys.path.insert(0, str(HARNESS))

import parity_compare as pc

trunk = Path(__file__).resolve().parents[1] / "_scratch/uedcli-parity-cache/39ce756a02e8c5cbf3a348387f9e64e6e9b0e48539ca891022ea3fa45ac4bc3a/trunk/maps/dx"
golden = Path("/tmp/uedcli-parity-cache/39ce756a02e8c5cbf3a348387f9e64e6e9b0e48539ca891022ea3fa45ac4bc3a/golden.dx")

native_model, level = pc.build_native_model(trunk)
golden_model = pc.parse_dx_model(golden)

def dump(tag, m):
    print(f"== {tag}: {len(m.points)} points")
    for i, p in enumerate(m.points):
        print(f"  P[{i:2d}] = ({p[0]:.2f},{p[1]:.2f},{p[2]:.2f})")
    print(f"   p_base: {[s.p_base for s in m.surfs]}")

dump("NATIVE", native_model)
dump("GOLDEN", golden_model)

# T3D authored data for world brushes
for name in level.order:
    a = level.actors[name]
    if a.brush is None:
        continue
    print(f"-- {name}")
    for pi, poly in enumerate(a.brush.polys):
        o = poly.origin
        print(f"  poly{pi} Origin=({o[0]:.2f},{o[1]:.2f},{o[2]:.2f}) verts={[tuple(round(c,2) for c in v) for v in poly.vertices]}")
