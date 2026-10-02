#!/usr/bin/env python3
"""Diff two built packages' PER-LEAF permeating-light lists (`Model.Lights` region 1).

    leaf_perm_diff.py <native.dx> <ref.dx>          # run from the repo root

`Model.Lights` is two arrays end to end: region 1, the per-leaf permeating lists indexed by
`FLeaf.iPermeating` (`uedcli-native/src/permeating_lights.rs`), and region 2, the per-surf shadow
runs indexed by `FLightMapIndex.iLightActors` (`light::bake`). `lmdiag.py` covers region 2 only, so
a divergence in region 1 shows up there as nothing at all — while shifting every region-2 offset by
the size of the difference and failing the gate on the whole `Model` body.

That is exactly WanChai N=45: identical lightmap runs, one over-included permeating light in leaf 20
(`spikes/2026-09-07-gather-box-verdict/spike.md`).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"))

import model_dump as md      # noqa: E402
import parity_gate as pg     # noqa: E402
from uedcli.upackage import load_package  # noqa: E402


def load(path: str):
    p = load_package(path)
    for i, e in enumerate(p.exports):
        if (p.object_class_name(i + 1) or "") == "Model" and p.names[e["nm"]].lower() == "model2":
            break
    else:
        raise SystemExit(f"no world Model named 'Model2' in {path}")
    d = md.decode(p, i)
    idt = pg.Ident(p)
    return d, [idt.ref_identity(v) for v in d["lights"]]


def permeating(d, lights) -> list[tuple]:
    """Per leaf: `(iZone, its permeating light run, iVolumetric)`, the run resolved to identities so
    two packages with different Actors orders compare."""
    out = []
    for (i_zone, i_permeating, i_volumetric), _visible_zones in d["leaves"]:
        run, j = [], i_permeating
        while 0 <= j < len(lights) and lights[j] != "None":
            run.append(lights[j])
            j += 1
        out.append((i_zone, tuple(run), i_volumetric))
    return out


def main() -> int:
    da, ga = load(sys.argv[1])
    db, gb = load(sys.argv[2])
    pa, pb = permeating(da, ga), permeating(db, gb)
    print(f"leaves {len(pa)} {len(pb)}; Model.Lights {len(ga)} {len(gb)}")
    if len(pa) != len(pb):
        print("LEAF COUNT differs — the BSP itself diverged, not just the light lists")
    bad = 0
    for i, (a, b) in enumerate(zip(pa, pb)):
        if a == b:
            continue
        bad += 1
        extra = [x for x in a[1] if x not in b[1]]
        missing = [x for x in b[1] if x not in a[1]]
        print(f"leaf[{i}] zone={a[0]}/{b[0]} iVolumetric={a[2]}/{b[2]}")
        print(f"    nat={a[1]}")
        print(f"    ued={b[1]}")
        print(f"    extra={extra} missing={missing}")
    print("differing leaves:", bad, "of", min(len(pa), len(pb)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
