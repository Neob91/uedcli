#!/usr/bin/env python3
"""Native half of the per-brush Pass-1 tree-shape trace: runs `build_geometry_bspcsg` on UNATCO's
world-CSG brush list with `UEDCLI_BSPCSG_BRUSH_STATE` set, so stderr carries one `BRUSHSTATE` line
per structural brush (and `P1NODE` node-array lines when FULL:<lo>-<hi> is requested).  Pairs with
the editor-side `pass1_brush_trace_unatco.py` gdb capture; diff via `pass1_compare.py`.

All imports resolve against THIS worktree (`parents[5]`), never the shared main checkout — see the
findings ledger's "methodology note" on `sys.path` contamination.  Trunk + project data are read
from the main checkout's `_scratch/bsp-parity-proj` (stable data, read-only).

Usage: .venv/bin/python pass1_native_states.py [COUNTS|FULL:<lo>-<hi>] 2> <log>
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

PROJECT = "/workspace/uedcli/_scratch/bsp-parity-proj"
os.environ["UEDCLI_PROJECT"] = PROJECT
os.environ["UEDCLI_BSPCSG_BRUSH_STATE"] = sys.argv[1] if len(sys.argv) > 1 else "COUNTS"

from uedcli import trunk                           # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
from spike_classindex import class_index           # noqa: E402


def main() -> int:
    level, _ = trunk.read_level(Path(PROJECT) / "maps/unatco")
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))
    # bi -> actor name map on stdout, for attributing a divergent k to a named brush.
    for bi, n in enumerate(names):
        print(f"BI {bi} {n}")
    print(f"FINAL nodes={len(nm.nodes)} surfs={len(nm.surfs)} leaves={len(nm.leaves)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
