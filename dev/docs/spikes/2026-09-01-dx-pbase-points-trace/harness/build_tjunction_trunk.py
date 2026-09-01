#!/usr/bin/env python3
"""Build a synthetic trunk whose CSG split PERSISTS in the final model (round 12 of the `p_base`
thread — `native-materialize-findings.md` "Round 11" already captured a genuine mid-CSG-split
`bspAddPoint` sequence but it was fully TRANSIENT: `bspMergeCoplanars` fused both fragments back into
one whole polygon before save. Round 11's own conclusion: a future round needs a case that DEFEATS
the merge).

Geometry: `Room` (`CSG_Subtract`, hollow box) + `PillarB`/`PillarC` (`CSG_Add`, two 512-cubes
overlapping 256uu along X — IDENTICAL to round 11's setup, so `PillarC`'s -Y/-Z straddling faces are
a CONTROL that should reproduce round 11's transient-merge result) + `PillarD` (`CSG_Add` chosen
variant below), a small brush positioned to interrupt ONLY the OUTER half (X:256-512) of `PillarC`'s
+Y/+Z straddling faces, well clear of the X=256 split boundary and of `PillarB` itself. Per
`unrealed/quirks.md` "CSG model", `bspMergeCoplanars` requires the two fragments to share one FULL
edge with no third neighbor interrupting — `PillarD`'s corner-bite breaks that precondition for the
+Y/+Z faces only, while leaving -Y/-Z untouched as the reproducibility control.

Usage:  build_tjunction_trunk.py <trunk-dir>
  writes maps/<name>/actors/... under <trunk-dir>, ready for build_ued_golden.py --trunk.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from uedcli import builders, trunk          # noqa: E402
from uedcli.model import Level              # noqa: E402
from uedcli.t3dtree import initial_ranks    # noqa: E402


def build_actors():
    actors = []

    room = builders.cube(2048, 2048, 2048)
    actors.append(builders.make_brush_actor("Room", room, (0, 0, 0), csg="subtract"))

    pillar_b = builders.cube(512, 512, 512)
    actors.append(builders.make_brush_actor("PillarB", pillar_b, (0, 0, 0), csg="add"))

    # Same shape/overlap as round 11 (X:[0,512], overlapping PillarB by 256uu in X) — left
    # untouched by PillarD on its -Y/-Z faces, so those reproduce round 11's transient-merge finding
    # as a control.
    pillar_c = builders.cube(512, 512, 512)
    actors.append(builders.make_brush_actor("PillarC", pillar_c, (256, 0, 0), csg="add"))

    # Corner-bite: a small additive box that only intersects PillarC's OUTER fragment region
    # (X:[400,464], well inside PillarC's outer half X:[256,512] and 144uu clear of the X=256 split
    # boundary; also clear of PillarB entirely, whose own X extent stops at 256). Sized to poke
    # OUTWARD past PillarC's +Y (Y=256) and +Z (Z=256) faces so its own CSG_Add creates new solid
    # material overhanging past PillarC's original face plane there, forcing PillarC's own +Y/+Z
    # straddling-face fragments (inner vs outer half) into different final shapes on that side —
    # PillarD's own new faces intervene, so bspMergeCoplanars' "no third neighbor interrupting"
    # precondition fails for +Y/+Z, unlike -Y/-Z which stay a plain flush two-fragment split.
    pillar_d = builders.cube(64, 128, 128)
    actors.append(builders.make_brush_actor("PillarD", pillar_d, (432, 224, 224), csg="add"))

    return actors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_tjunction_trunk.py <trunk-dir>", file=sys.stderr)
        return 2
    trunk_dir = Path(sys.argv[1]).resolve()
    actors = build_actors()
    level = Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])
    ranks = dict(zip(level.order, initial_ranks(len(level.order))))
    trunk_dir.mkdir(parents=True, exist_ok=True)
    trunk.write_level(trunk_dir, level, ranks)
    print(f"wrote trunk: {trunk_dir} ({len(actors)} actors: {[a.name for a in actors]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
