#!/usr/bin/env python3
"""Reveal the editor's CSG brush order from the golden surf pool (incremental add order).

golden surfs array is in add-order: each contiguous run of surfs with the same i_actor = one brush's
faces, in brush-processing order.  Compare that sequence against native's trunk name order."""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/workspace/uedcli")
sys.path.insert(0, "/workspace/uedcli/dev/docs/spikes/2026-07-15-native-materialize/harness")
os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance"
from uedcli import trunk
from uedcli.native import brush_marshal as BM
from uedcli.native import umodel as UM
from uedcli.utexture import load_package
from spike_classindex import class_index

GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"
TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"

pkg = load_package(GOLDEN)
models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
g = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])

# golden brush order: sequence of actors as their surfs first appear
seen = {}
order = []
for si, s in enumerate(g.surfs):
    nm = pkg.name_of_ref(s.i_actor)
    if nm is None or s.i_actor == -1:
        continue
    if nm not in seen:
        seen[nm] = si
        order.append(nm)

level, _ranks = trunk.read_level(Path(TRUNK))
ci = class_index()
names = [n for n in level.order
         if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]

print(f"golden pool: {len(g.surfs)} surfs, {len(order)} brushes appear")
print(f"trunk names: {len(names)} world-CSG brushes")

# How many golden-order prefixes match the trunk order?
gidx = {nm: i for i, nm in enumerate(order)}
nidx = {nm: i for i, nm in enumerate(names)}
common = set(order) & set(names)
mis = [(nm, gidx[nm], nidx[nm]) for nm in common]
# rank by golden order; count prefix agreement
g_ = {nm: i for i, nm in enumerate(order) if nm in common}
n_ = {nm: i for i, nm in enumerate(names) if nm in common}
agree = 0
for nm, gi in sorted(g_.items(), key=lambda kv: kv[1]):
    if n_[nm] == agree:
        agree += 1
    else:
        break
print(f"prefix agreement: first {agree} brushes match trunk order")

print("\nfirst 40 in GOLDEN order (glyphs: o=order-match, x=out-of-place vs trunk):")
for nm, gi in sorted(g_.items(), key=lambda kv: kv[1])[:40]:
    f = (nm, gi, n_[nm])
    mark = "o" if gi == n_[nm] else "x"
    print(f"  {mark} {nm}: golden#{gi} trunk#{n_[nm]}")

print("\nBrush323 / 1178 / 32xx-family positions:")
for nm in ["Brush1178", "Brush323", "Brush3256", "Brush3255", "Brush3254", "Brush3246", "Brush7021", "Brush27"]:
    if nm in names or nm in order:
        print(f"  {nm}: golden={gidx.get(nm,'-')} trunk={nidx.get(nm,'-')}")