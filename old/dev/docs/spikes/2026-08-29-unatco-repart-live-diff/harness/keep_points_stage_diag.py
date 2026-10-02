#!/usr/bin/env python3
"""Points-residual round 3: stage-by-stage breakdown of `UEDCLI_BSPCSG_WORLD_KEEP_POINTS=1`'s
already-measured regression (final points d=+16 -> +912 UNATCO / +2673 Wanchai, `regression_gate.py`).

WHY. The prior round confirmed the MECHANISM (EmptyModel(0,0) keeps Points at the world-level call,
live-verified) but a naive port regresses badly, and didn't localize WHERE in the pipeline the excess
enters. This reuses the existing UEDCLI_BSPCSG_STAGE_COUNTS instrumentation (already in bspcsg.rs,
already used for the default/clearing path's own stage table in the findings ledger) with
WORLD_KEEP_POINTS=1 layered on top, purely offline (no docker/gdb) -- compares the KEEP-points stage
sequence against the SAME editor-log reference the default-path table already used
(repart-stage-unatco.log / wanchai-ed-repart-stage.log) to see whether the excess enters in one stage
or is spread out.

Usage: .venv/bin/python keep_points_stage_diag.py [unatco|wanchai]
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

os.environ["UEDCLI_BSPCSG_STAGE_COUNTS"] = "1"
os.environ["UEDCLI_BSPCSG_WORLD_KEEP_POINTS"] = "1"

LEVEL = sys.argv[1] if len(sys.argv) > 1 else "unatco"
CASES = {
    "unatco": (ROOT / "_scratch/bsp-parity-proj", "maps/unatco"),
    "wanchai": (ROOT / "dev/games/trunks/tmp-wanchai-market", None),
}
proj, subpath = CASES[LEVEL]
# class_index() needs a project WITH a uedcli.toml (Wanchai's scratch trunk has none) -- always
# resolve the class index against bsp-parity-proj, then read the target trunk directly by path
# (same pattern as wanchai_stage_diag.py).
os.environ["UEDCLI_PROJECT"] = str(ROOT / "_scratch/bsp-parity-proj")

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
import uedcli_native                               # noqa: E402
from spike_classindex import class_index           # noqa: E402


def main():
    ci = class_index()
    if subpath:
        trunk_path = proj / subpath
    elif (proj / "actors").exists():
        trunk_path = proj
    else:
        trunk_path = next((proj / "maps").iterdir())
    level, _ = trunk.read_level(trunk_path)
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    print(f"FINAL: nodes={len(built.nodes)} verts={len(built.verts)} "
          f"points={len(built.points)} surfs={len(built.surfs)} "
          f"vectors={len(built.vectors)} leaves={len(built.leaves)}", file=sys.stderr)


if __name__ == "__main__":
    main()
