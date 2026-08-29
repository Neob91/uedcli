#!/usr/bin/env python3
"""Ablation: full build minus a named brush; watch focus brushes' surf counts.

If Brush323 emits surfs once a candidate upstream brush is removed, that brush's carve is what voids
the dome region in native.
"""
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


def load():
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    brushes = [BM._build_brush_input(n, level.actors[n]) for n in names]
    return names, brushes


def build(brushes):
    built = uedcli_native.build_geometry_bspcsg(brushes)
    body = uedcli_native.serialize_model(built)
    return UM.parse_model_body(body, 0, len(body))


def attr(model, names):
    c = Counter(s.i_actor for s in model.surfs)
    return {names[idx]: n for idx, n in c.items() if 0 <= idx < len(names)}


def main():
    names, brushes = load()
    focus = sys.argv[1:] or ["Brush323"]
    print(f"focus: {focus}")
    runs = [("FULL", names, brushes)]
    for drop in ["Brush1178", "Brush27"]:
        i = names.index(drop)
        runs.append((f"without-{drop}", names[:i] + names[i+1:], brushes[:i] + brushes[i+1:]))
    for label, nm, br in runs:
        m = build(br)
        a = attr(m, nm)
        print(f"{label}: nodes={len(m.nodes)} surfs={len(m.surfs)} points={len(m.points)}")
        for f in focus:
            print(f"   {f}: {a.get(f, 0)}")


if __name__ == "__main__":
    main()