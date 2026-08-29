#!/usr/bin/env python3
"""Task 2 — per-brush native-vs-golden surf attribution for Area51 Entrance.

Attributions:
- Golden: read `golden_area51.dx` (a `.dx` package), find the world UModel export (max-size
  Model export), parse with `umodel.parse_model_body`; each surf's `i_actor` is an object ref ->
  brush-actor export name.
- Native: marshal the trunk's world-CSG brush set exactly as `native_dumps.py` does, run
  `uedcli_native.build_geometry_bspcsg`, serialize + re-parse; each surf's `i_actor` is the index
  into the CSG-ordered names list.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

import os
os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance"

from uedcli import trunk
from uedcli.native import brush_marshal as BM
from uedcli.native import umodel as UM
from uedcli.utexture import load_package
import uedcli_native
from spike_classindex import class_index

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"
GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"


def load_world_model(path):
    pkg = load_package(path)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    model = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])
    print(f"  world model export {mi} size={e['ssize']}: "
          f"nodes={len(model.nodes)} surfs={len(model.surfs)} points={len(model.points)}")
    return pkg, model


def main():
    print("== GOLDEN ==")
    g_pkg, g = load_world_model(GOLDEN)
    gold_by_actor = Counter()
    gold_other = Counter()
    for s in g.surfs:
        nm = g_pkg.name_of_ref(s.i_actor)
        if nm is None:
            gold_other[("unresolved", s.i_actor)] += 1
        else:
            gold_by_actor[nm] += 1
    print(f"  golden surfs attributed to {len(gold_by_actor)} named actor refs; "
          f"unresolved i_actor count: {sum(gold_other.values())}")
    for k, c in gold_other.most_common(10):
        print(f"    other {k}: {c}")

    print("\n== NATIVE ==")
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    brushes = [BM._build_brush_input(n, level.actors[n]) for n in names]
    print(f"  {len(names)} world-CSG brushes (native order index = i_actor)")
    built = uedcli_native.build_geometry_bspcsg(brushes)
    body = uedcli_native.serialize_model(built)
    nat = UM.parse_model_body(body, 0, len(body))
    print(f"  native final: nodes={len(nat.nodes)} surfs={len(nat.surfs)} points={len(nat.points)}")
    nat_by_idx = Counter(s.i_actor for s in nat.surfs)
    nat_by_actor = Counter()
    unres = Counter()
    for idx, c in nat_by_idx.items():
        if 0 <= idx < len(names):
            nat_by_actor[names[idx]] += c
        else:
            unres[idx] = c
    print(f"  native surfs attributed to {len(nat_by_actor)} named brushes; "
          f"out-of-range i_actor counts: {dict(unres)}")

    print("\n== PER-BRUSH DELTA (golden - native, surfs) ==")
    all_names = sorted(set(gold_by_actor) | set(nat_by_actor))
    rows = []
    for n in all_names:
        gh = gold_by_actor.get(n, 0)
        nh = nat_by_actor.get(n, 0)
        rows.append((gh - nh, n, gh, nh))
    rows.sort(reverse=True)
    losses = [r for r in rows if r[0] > 0]
    gains = [r for r in rows if r[0] < 0]
    zero = [r for r in rows if r[0] == 0]
    print(f"  brushes with geometry in EITHER build: {len(all_names)}")
    print(f"  brushes LOSING surfs in native: {len(losses)}  (sum delta {sum(r[0] for r in losses)})")
    print(f"  brushes GAINING surfs in native: {len(gains)}  (sum delta {sum(r[0] for r in gains)})")
    print(f"  brushes with equal count: {len(zero)}")
    print("\n  top 25 losses:")
    for delta, n, gh, nh in losses[:25]:
        print(f"    {n:45s} golden={gh:4d} native={nh:4d} delta={delta:+4d}")
    print("\n  top 10 gains:")
    for delta, n, gh, nh in gains[:10]:
        print(f"    {n:45s} golden={gh:4d} native={nh:4d} delta={delta:+4d}")

    # Scaled-brush over-representation: which brushes are scaled (MainScale/PostScale non-identity)?
    from uedcli import rotation as ROT
    def is_scaled(a):
        return not (ROT.actor_main_scale(a).is_identity() and ROT.actor_post_scale(a).is_identity())
    loss_names = {r[1] for r in losses}
    gain_names = {r[1] for r in gains}
    zero_names = {r[1] for r in zero}
    scaled_total = sum(1 for n in names if is_scaled(level.actors[n]))
    scaled_in_loss = sum(1 for n in loss_names if is_scaled(level.actors[n]))
    scaled_in_gain = sum(1 for n in gain_names if is_scaled(level.actors[n]))
    scaled_in_zero = sum(1 for n in zero_names if is_scaled(level.actors[n]))
    print(f"\n  scaled brushes: total-in-CSG={scaled_total}; "
          f"in-loss-set={scaled_in_loss}/{len(loss_names)}; "
          f"in-gain-set={scaled_in_gain}/{len(gain_names)}; "
          f"in-zero-set={scaled_in_zero}/{len(zero_names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())