#!/usr/bin/env python3
"""Extract the ground-truth zone/leaf/node table from a real `.dx` map's level UModel.

Reuses the proven package reader (`utexture_decode.load_package`) + the productionized
UModel body parser (`uedctl.native.umodel.parse_model_body`).  Prints, for the largest
level Model:
  - NumZones and each FZoneProperties (ZoneActor ref -> actor name/class, Connectivity, Visibility)
  - leaf count + each leaf's iZone
  - node count, distinct node iZone pairs, node_flags histogram, num_shared_sides
  - collision-bound coverage (nodes with iCollisionBound >= 0)

This is the differential oracle for the native zone port (validate MEMBERSHIP, never counts).

Usage: python zone_ground_truth.py /path/to/Map.dx
"""
import sys
from collections import Counter
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]  # Tools/uedctl (harness/ -> spike/ -> spikes/ -> dev/ -> docs/ -> uedctl)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))

import utexture_decode as UT  # noqa: E402
from uedctl.native import umodel as UM  # noqa: E402


def largest_model_export(pkg):
    best = None
    for i, e in enumerate(pkg.exports):
        if pkg.class_of_export(i) == "Model" and e["ssize"] > 0:
            if best is None or e["ssize"] > pkg.exports[best]["ssize"]:
                best = i
    return best


def main(path):
    pkg = UT.load_package(path)
    mi = largest_model_export(pkg)
    if mi is None:
        print("no Model export")
        return
    e = pkg.exports[mi]
    # Try progressively: the UModel body parser expects (buf, offset, size).
    model = None
    err = None
    for extra in (0,):
        try:
            model = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])
            break
        except Exception as ex:
            err = ex
    if model is None:
        print(f"parse failed: {err}")
        # dump a few bytes to help
        return

    print(f"== {Path(path).name}  (Model export #{mi}, ssize={e['ssize']})")
    print(f"nodes={len(model.nodes)} surfs={len(model.surfs)} verts={len(model.verts)} "
          f"points={len(model.points)} vectors={len(model.vectors)}")
    print(f"num_shared_sides={model.num_shared_sides}")
    print(f"leaves={len(model.leaves)}  zones={len(model.zones)}")
    for zi, z in enumerate(model.zones):
        actor = pkg.name_of_ref(z.actor_ref) if z.actor_ref else None
        acls = None
        if z.actor_ref and z.actor_ref > 0:
            acls = pkg.class_of_export(z.actor_ref - 1)
        print(f"  zone[{zi}] actor_ref={z.actor_ref} name={actor} class={acls} "
              f"conn={z.connectivity:#018x} vis={z.visibility:#018x}")
    # leaf zone histogram
    lz = Counter(l.i_zone for l in model.leaves)
    print(f"  leaf iZone histogram: {dict(sorted(lz.items()))}")
    # node iZone pairs
    nz = Counter((n.i_zone[0], n.i_zone[1]) for n in model.nodes)
    print(f"  distinct node iZone pairs: {len(nz)} -> {dict(sorted(nz.items()))}")
    nf = Counter(n.node_flags for n in model.nodes)
    print(f"  node_flags histogram: {dict(sorted(nf.items()))}")
    ncoll = sum(1 for n in model.nodes if n.i_collision_bound >= 0)
    nrend = sum(1 for n in model.nodes if n.i_render_bound >= 0)
    print(f"  nodes iCollisionBound>=0: {ncoll}   iRenderBound>=0: {nrend}")
    # leaf iZone set size vs zones
    print(f"  distinct leaf zones: {sorted(set(l.i_zone for l in model.leaves))}")


if __name__ == "__main__":
    main(sys.argv[1])
