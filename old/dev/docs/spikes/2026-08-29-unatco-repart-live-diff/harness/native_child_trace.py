#!/usr/bin/env python3
"""Native counterpart to `repart_child_trace.py`: run `build_geometry_bspcsg` on the full UNATCO
trunk with `UEDCLI_REPART_FBS_CHILD` set, capturing native's own split for the same subtree the
live editor capture targets.

Usage: .venv/bin/python native_child_trace.py <child_node_index>
"""
import os
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
os.environ.setdefault("UEDCLI_PROJECT", "/workspace/uedcli/_scratch/bsp-parity-proj")

CHILD = sys.argv[1] if len(sys.argv) > 1 else "6108"
os.environ["UEDCLI_REPART_FBS_CHILD"] = CHILD

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
from spike_classindex import class_index           # noqa: E402

TRUNK = ROOT / "_scratch/bsp-parity-proj/maps/unatco"


def main():
    level, _ = trunk.read_level(TRUNK)
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    print(f"world brushes: {len(names)}", file=sys.stderr)
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))
    print(f"native nodes={len(nm.nodes)} surfs={len(nm.surfs)}", file=sys.stderr)


if __name__ == "__main__":
    main()
