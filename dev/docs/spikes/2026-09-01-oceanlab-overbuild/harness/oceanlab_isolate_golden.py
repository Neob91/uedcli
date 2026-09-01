#!/usr/bin/env python3
"""Isolated live-editor golden for ONE or FEW OceanLab Lab brushes -- the same "isolate the offending
brush(es) into a fresh MAP NEW, EDIT PASTE, MAP REBUILD, MAP SAVE" technique as
`a51_isolate.py`/`smuggler_b547_isolated_golden.py`, adapted to a single-shot (not chunked/resumable
-- the target brush sets are tiny, no need for resume logic).

Investigates the OceanLab Lab surf over-build (+27 across 9 identical-shape "2D Loft" PF_Semisolid
CSG_Add decorative brushes, all d=+3): decides whether the merge-count gap (native 18 vs golden 15
surfs for a 26-poly brush) is INTRINSIC to native's `bsp_validate_brush_links` coplanar-merge
algorithm on this brush's own geometry (reproduces even fully isolated, no other brushes) or
CONTEXTUAL (only appears when the brush interacts with the rest of the level's CSG).

Usage: .venv/bin/python oceanlab_isolate_golden.py Brush784 [Brush844 ...]
Run as a bounded background job -- the editor wedges silently (dev/docs/rules/background-work.md).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness"))

from uedcli import config, trunk, writes, xfer                     # noqa: E402
from uedcli.container_assets import resource_mounts                # noqa: E402
from uedcli.driver import Driver                                   # noqa: E402
from uedcli.editor import ensure_editor, stop_editor                # noqa: E402
from uedcli.uuid7 import uuid7                                     # noqa: E402
from uedcli import builders                                        # noqa: E402
import build_ued_golden as bg                                      # noqa: E402
from geo_golden_driver import _wait_idle                           # noqa: E402

TRUNK = (ROOT / "_scratch/uedcli-parity-cache/"
         "4e3757c3f3b2144f3750084db83cdbbc8bd4412047aadffa17c0494f4fa51a39/trunk/maps/14_oceanlab_lab")
OUT_DIR = ROOT / "_scratch/oceanlab-isolate"


def _context_brushes(center):
    """A synthetic ADD shell + SUBTRACT room around `center`, so a lone PF_Semisolid CSG_Add
    detail brush (which the real editor no-ops on when pasted with NO other geometry -- "Unreal's
    world is solid by default... additive brushes only matter where something was subtracted",
    `dev/docs/unrealed/quirks.md` "CSG model" -- confirmed live: an isolated Brush784 alone golden
    is 0 nodes/0 surfs) has real carved-out space to sit inside, matching its real in-level
    context without needing the rest of OceanLab's 1886 brushes."""
    cx, cy, cz = center
    shell = builders.make_brush_actor(
        "CtxShell", builders.cube(16000, 16000, 16000), location=(cx, cy, cz), csg="add")
    room = builders.make_brush_actor(
        "CtxRoom", builders.cube(4000, 4000, 4000), location=(cx, cy, cz), csg="subtract")
    return [shell, room]


def main() -> int:
    names = sys.argv[1:] or ["Brush784"]
    out = OUT_DIR / f"golden_{'_'.join(names)}.dx"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lvl, _ranks = trunk.read_level(TRUNK)
    brush_actors = [lvl.actors[n] for n in names]
    focus_loc = brush_actors[0].location
    ctx = _context_brushes((float(focus_loc[0]), float(focus_loc[1]), float(focus_loc[2])))
    brush_actors = ctx + brush_actors

    user_config = config.load_user_config()
    project = bg._scratch_project(TRUNK, "deusex")
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    ed_id = uuid7()
    container = ensure_editor(ed_id, mounts=mounts, state_dir=state_dir)
    ed = Driver(container=container)
    try:
        print(f"editor up: {container}", flush=True)
        ed.map_new()
        _wait_idle(container, label="map-new")
        ed.set_grid(1, 1, 1)
        t3d = writes.emit_map([writes._shift_for_paste(a) for a in brush_actors])
        ed.set_clipboard(t3d)
        ed.edit_paste()
        _wait_idle(container, label="paste")
        print("  pasted, MAP REBUILD ...", flush=True)
        ed.exec("MAP REBUILD")
        _wait_idle(container, label="rebuild", timeout=600, quiet_reads=8, min_seconds=5)
        work_out = xfer.work_path("dx")
        size = ed.map_save(work_out)
        xfer.cp_out(container, work_out, str(out))
        print(f"WROTE {out} ({size} bytes container-side, {out.stat().st_size} host-side)",
              flush=True)
    finally:
        try:
            stop_editor(ed_id, state_dir)
        except Exception as e:
            print(f"teardown note: {e}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
