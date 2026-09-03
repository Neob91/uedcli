#!/usr/bin/env python3
"""The 2-brush Paris Underground minimal case: native counts for [Brush1246(Active), Brush328]
vs [Brush1246 as explicit CSG_Subtract, Brush328]. Editor (live prefix golden n=2): 16/12/6."""
import os
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[5]  # harness/<slug>/spikes/docs/dev -> repo root
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/bdf66b5dc02df008a53f5018b5aeab950cf13481c2a49bd0f683dd714429c718/trunk")
os.environ.setdefault("UEDCLI_PROJECT", str(TRUNK))

from uedcli import trunk as TR
from uedcli.native import brush_marshal as BM
from uedcli.native import umodel as UM
import uedcli_native
from spike_classindex import class_index

level, _ = TR.read_level(TRUNK / "maps/11_paris_underground")
ci = class_index()
names = [n for n in level.order
         if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)][:2]
print("pair:", names)


def build(ins):
    built = uedcli_native.build_geometry_bspcsg(ins)
    body = uedcli_native.serialize_model(built)
    m = UM.parse_model_body(body, 0, len(body))
    return len(m.nodes), len(m.surfs), len(m.leaves)


ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
print("as-authored (Active):     nodes/surfs/leaves =", build(ins))

a = level.actors[names[0]]
a2 = type(a)(**{**a.__dict__, "props": [("CsgOper", "CSG_Subtract")] + [p for p in a.props if p[0] != "CsgOper"]}) \
    if hasattr(a, "__dict__") else None
try:
    ins2 = [BM._build_brush_input(names[0], a2), ins[1]]
    print("Brush1246 -> CSG_Subtract:", build(ins2))
except Exception as e:
    # fallback: mutate props list in place if the actor type resists reconstruction
    print("reconstruct failed:", e)
    a.props.append(("CsgOper", "CSG_Subtract"))
    ins2 = [BM._build_brush_input(names[0], a), ins[1]]
    print("Brush1246 -> CSG_Subtract (in-place):", build(ins2))
