#!/usr/bin/env python3
"""Characterize the editor `Model.Lights` REGION 1 — the per-LEAF permeating-light lists — from the
golden `Test_Castle.dx` (spike section 20 §21 (A)). This is the DECODE for the un-ported Stage-2
work: `Lights` region 1 `[0, iLightActors_min)` indexed by `FLeaf.iPermeating`, which native still
stubs (`zones.rs iPermeating=0`), leaving `Lights` at 3955 vs the editor's 11392.

What it prints (RAW, no normalization):
  * region split: min/max `iPermeating` (region 1) vs min `iLightActors` (region 2) — a clean cut.
  * how many leaves carry a run; the per-leaf run-length distribution.
  * the ref->light-index mapping check (editor Lights refs -> our participating-light order, by
    actor NAME) — must be 0 unmatched, proving we can express the set in native's index space.
  * two REFUTED geometric predicates (so a later session doesn't re-try them):
      - centroid radius reach: does light `i` permeate leaf `L` iff dist(centroid_L, loc_i) <
        worldRadius_i (+ leaf radius)?  -> mean Jaccard ~0.31, 0 exact.  REFUTED.
      - (prior, §21 (A)) union of the leaf's bounding-surf shadow lights -> Jaccard 0.427.  REFUTED.
    => region 1 is a genuine SHADOWED volumetric flood (radius reach AND BSP line-of-sight through
    portals), matching UnrealEd's `shadowIlluminateBsp` per-leaf gather; the within-run order is the
    gather-DISCOVERY order (e.g. leaf0 = light indices [2,1,3,6,7,11,12], not sorted), so a faithful
    port must replicate the editor's light/leaf iteration order for byte-exact runs.

Usage: .venv/bin/python .../harness/perm_region_decode.py
Editor golden: DX/Maps/Test_Castle.dx; light positions from the castle trunk.
"""
from __future__ import annotations

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))

from uedctl import trunk  # noqa: E402
from uedctl.native import materialize as M  # noqa: E402
from uedctl.native import umodel as UM  # noqa: E402
import utexture_decode as UT  # noqa: E402

EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"
TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedctl/maps/foobar"


def load(path: str):
    pkg = UT.load_package(path)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"]), pkg


def world_radius(radbyte: int) -> float:
    return (radbyte + 1) * 25.0


def dist(a, b) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def main() -> int:
    m, pkg = load(EDITOR)
    lvl, _ = trunk.read_level(Path(TRUNK))
    lights, names = M._participating_lights(lvl)
    name2idx = {n: i for i, n in enumerate(names)}

    ips = [l.i_permeating for l in m.leaves]
    ila = [r.i_light_actors for r in m.light_map if r.i_light_actors >= 0]
    print(f"leaves={len(m.leaves)}  Lights len={len(m.lights)}")
    print(f"region 1 iPermeating: min={min(ips)} max={max(ips)}  runs={sum(1 for x in ips if x >= 0)}"
          f"  none(-1)={sum(1 for x in ips if x < 0)}")
    print(f"region 2 iLightActors: min={min(ila)} max={max(ila)}  (clean split at {min(ila)})")

    def run(start: int):
        r = []
        i = start
        while i < len(m.lights) and m.lights[i] != 0:
            r.append(m.lights[i]); i += 1
        return r

    # per-leaf permeating set in our light-index space (by actor name)
    leaf_lights = {}
    unmatched = 0
    rl = Counter()
    for li, l in enumerate(m.leaves):
        if l.i_permeating < 0:
            leaf_lights[li] = []; rl[-1] += 1; continue
        refs = run(l.i_permeating)
        rl[len(refs)] += 1
        idxs = []
        for rf in refs:
            nm = pkg.name_of_ref(rf)
            if nm in name2idx:
                idxs.append(name2idx[nm])
            else:
                unmatched += 1
        leaf_lights[li] = idxs
    print(f"ref->light-index unmatched: {unmatched} (0 => set is expressible in native index space)")
    print(f"per-leaf run-length dist: {dict(sorted(rl.items()))}")
    print(f"leaf0 permeating light indices (gather order, NOT sorted): {leaf_lights[0]}")

    # representative leaf points from node boundary verts
    leaf_pts = defaultdict(list)
    for n in m.nodes:
        vs = [m.points[m.verts[n.i_vert_pool + k].i_vertex] for k in range(n.num_vertices)]
        for side in (0, 1):
            child = n.i_front if side == 0 else n.i_back
            if child == -1:
                lf = n.i_leaf[side]
                if 0 <= lf < len(m.leaves):
                    leaf_pts[lf].extend(vs)

    tested = exact = 0
    jac = 0.0
    for li in range(len(m.leaves)):
        pts = leaf_pts[li]
        if not pts or (not leaf_lights[li] and m.leaves[li].i_permeating < 0):
            continue
        c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts),
             sum(p[2] for p in pts) / len(pts))
        lr = max((dist(c, p) for p in pts), default=0.0)
        pred = {i for i, (loc, rb) in enumerate(lights) if dist(c, loc) < world_radius(rb) + lr}
        act = set(leaf_lights[li])
        tested += 1
        if pred == act:
            exact += 1
        u = len(pred | act)
        if u:
            jac += len(pred & act) / u
    print(f"REFUTED centroid-radius predicate: {tested} leaves, {exact} exact-set, "
          f"mean Jaccard {jac / max(tested, 1):.3f} (=> genuine shadowed flood, not a radius test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
