#!/usr/bin/env python3
"""Bisect the per-brush drop point: attribute surfs by i_actor at the pre-repartition (`--norepart`
equivalent) stage vs the final stage, for named focus brushes."""
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
FOCUS = sys.argv[1:] or ["Brush323"]


def build(norepart: bool):
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    brushes = [BM._build_brush_input(n, level.actors[n]) for n in names]
    os.environ.pop("UEDCLI_BSPCSG_NOREPART", None)
    if norepart:
        os.environ["UEDCLI_BSPCSG_NOREPART"] = "1"
    built = uedcli_native.build_geometry_bspcsg(brushes)
    body = uedcli_native.serialize_model(built)
    return names, UM.parse_model_body(body, 0, len(body))


def attr(model, names):
    c = Counter(s.i_actor for s in model.surfs)
    out = {}
    for idx, n in c.items():
        out[names[idx]] = n if 0 <= idx < len(names) else (idx, n)
    return out


for label, norep in (("FINAL", False), ("NOREPART", True)):
    names, m = build(norep)
    a = attr(m, names)
    print(f"== {label}: nodes={len(m.nodes)} surfs={len(m.surfs)} points={len(m.points)} ==")
    for f in FOCUS:
        print(f"   {f}: {a.get(f, 0)} surfs")
    nzero = sum(1 for n in names if a.get(n, 0) == 0)
    nlive = sum(1 for n in names if a.get(n, 0) > 0)
    print(f"   brushes with 0 surfs: {nzero}; with >0: {nlive}")