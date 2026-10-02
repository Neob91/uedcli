#!/usr/bin/env python3
"""Native geometry counts for the structural-only (non-semisolid) smuggler trunk."""
import os
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
os.environ.setdefault("UEDCLI_PROJECT", "/workspace/uedcli/_scratch/smuggler-structural-only")

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
from spike_classindex import class_index           # noqa: E402

TRUNK = "/workspace/uedcli/_scratch/smuggler-structural-only/maps/smuggler"


def main():
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    print("total world-csg brushes:", len(names))

    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))
    print(f"native structural-only: nodes={len(nm.nodes)} surfs={len(nm.surfs)} leaves={len(nm.leaves)} "
          f"verts={len(nm.verts)} points={len(nm.points)} vectors={len(nm.vectors)}")


if __name__ == "__main__":
    raise SystemExit(main())
