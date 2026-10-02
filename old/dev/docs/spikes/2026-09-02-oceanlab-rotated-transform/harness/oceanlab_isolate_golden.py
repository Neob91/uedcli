#!/usr/bin/env python3
"""Isolated live-editor golden for ONE or FEW OceanLab Lab brushes -- adapted from
`dev/docs/spikes/2026-09-01-oceanlab-overbuild/harness/oceanlab_isolate_golden.py` (same
"synthetic ADD shell + SUBTRACT room, MAP NEW -> EDIT PASTE -> MAP REBUILD -> MAP SAVE" technique),
retargeted at this round's worktree and at the ROTATED-brush transform-bit-exactness question
(node/leaf residual localization, not the surf-merge question the original round answered).

Usage: .venv/bin/python oceanlab_isolate_golden.py Brush1081 [Brush128 ...]
Run as a bounded background job -- the editor wedges silently (dev/docs/rules/background-work.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/agent-ad11af2d5c5e7d2ab")
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
    """A synthetic ADD shell + SUBTRACT room around `center` -- Unreal's world is solid by
    default, so a lone CSG_Add brush with nothing subtracted first is a documented no-op
    (`dev/docs/unrealed/quirks.md` "CSG model")."""
    cx, cy, cz = center
    shell = builders.make_brush_actor(
        "CtxShell", builders.cube(16000, 16000, 16000), location=(cx, cy, cz), csg="add")
    room = builders.make_brush_actor(
        "CtxRoom", builders.cube(4000, 4000, 4000), location=(cx, cy, cz), csg="subtract")
    return [shell, room]


def main() -> int:
    names = sys.argv[1:] or ["Brush1081"]
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
