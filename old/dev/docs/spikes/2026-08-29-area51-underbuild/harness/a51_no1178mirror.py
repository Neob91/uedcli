#!/usr/bin/env python3
"""Ablation: full build with Brush1178's transform forced to identity R (no MainScale mirror).

Hypothesis: the trunk model verts for Brush1178 already carry the MainScale (1,1,-1) mirror, so the
editor rebuild applies only (prepivot, rot, loc).  Native's baked L=(1,1,-1) double-mirrors -> the
carve is displaced and the dome region stays void.  If R=I restores Brush323's dome, confirmed."""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance"
ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli import trunk
from uedcli.native import brush_marshal as BM
from uedcli.native import umodel as UM
import uedcli_native
from spike_classindex import class_index

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"
I = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def load():
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    return names, ins


def build(brushes):
    built = uedcli_native.build_geometry_bspcsg(brushes)
    body = uedcli_native.serialize_model(built)
    return UM.parse_model_body(body, 0, len(body))


def attr(model, names):
    c = Counter(s.i_actor for s in model.surfs)
    return {names[idx]: n for idx, n in c.items() if 0 <= idx < len(names)}


def main():
    names, ins = load()
    focus = ["Brush323", "Brush1178"] + [n for n in names if n.startswith("Brush32") and n not in ("Brush320", "Brush321", "Brush3257", "Brush3256", "Brush3255", "Brush3254", "Brush3252")]
    focus = ["Brush323", "Brush1178"]

    variants = [("FULL", ins)]
    v2 = [list(b) for b in ins]
    v2[names.index("Brush1178")][6] = I                   # R=I for 1178
    variants.append(("R=I-for-1178", [tuple(b) for b in v2]))

    for label, br in variants:
        m = build(br)
        a = attr(m, names)
        print(f"{label}: nodes={len(m.nodes)} surfs={len(m.surfs)} points={len(m.points)}")
        for f in focus:
            print(f"   {f}: {a.get(f, 0)}")


if __name__ == "__main__":
    main()