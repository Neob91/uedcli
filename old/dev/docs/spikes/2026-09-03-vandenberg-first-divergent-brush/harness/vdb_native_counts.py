#!/usr/bin/env python3
"""Native half of the Vandenberg per-brush Pass-1 count trace (generic twin of
`2026-08-29-unatco-repart-live-diff/harness/pass1_native_states.py`): builds the cached
Vandenberg trunk with `UEDCLI_BSPCSG_BRUSH_STATE` set so stderr carries one `BRUSHSTATE`
line per structural brush.  Pairs with the editor-side `pass1_brush_trace_unatco.py`
run on the cached golden; diff via that spike's `pass1_compare.py`.

Usage: .venv/bin/python vdb_native_counts.py [COUNTS|FULL:<lo>-<hi>] 2> <log>
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["UEDCLI_BSPCSG_BRUSH_STATE"] = sys.argv[1] if len(sys.argv) > 1 else "COUNTS"
import vdb_lib as V  # noqa: E402

from uedcli.native import brush_marshal as BM  # noqa: E402
from uedcli.native import umodel as UM         # noqa: E402
import uedcli_native                            # noqa: E402


def main() -> int:
    level, names = V.world_csg_names()
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))
    for bi, n in enumerate(names):
        print(f"BI {bi} {n}")
    print(f"FINAL nodes={len(nm.nodes)} surfs={len(nm.surfs)} leaves={len(nm.leaves)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
