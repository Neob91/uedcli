#!/usr/bin/env python3
"""Wanchai-specific stage/call diagnostics for repartition_frontier — sibling of
regression_gate.py, adapted for the Points/Verts residual investigation
(dev/docs/board/inbox/wanchai-verts-points-residual-independently/).

Runs build_geometry_bspcsg over Wanchai's trunk with UEDCLI_BSPCSG_STAGE_COUNTS /
UEDCLI_REPART_CALL_DIAG (and optionally UEDCLI_BSPCSG_PREPART_NODES) set, so the stderr
diagnostics land in one place. Usage:

    .venv/bin/python wanchai_stage_diag.py [--prepart] [--call-diag] > out.log
"""
import os
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

# Build the class index against a project that HAS a uedcli.toml (Wanchai's scratch trunk
# doesn't) -- spike_classindex memoizes globally, so this is a one-time cost regardless of
# which level's trunk we then read directly by path.
os.environ["UEDCLI_PROJECT"] = str(ROOT / "_scratch/bsp-parity-proj")

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
import uedcli_native                               # noqa: E402
from spike_classindex import class_index           # noqa: E402

WANCHAI_TRUNK = ROOT / "dev/games/trunks/tmp-wanchai-market"


def main():
    ci = class_index()
    level, _ = trunk.read_level(WANCHAI_TRUNK)
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    print(f"built: nodes={len(built.nodes)} verts={len(built.verts)} "
          f"points={len(built.points)} surfs={len(built.surfs)} "
          f"vectors={len(built.vectors)} leaves={len(built.leaves)}", file=sys.stderr)


if __name__ == "__main__":
    main()
