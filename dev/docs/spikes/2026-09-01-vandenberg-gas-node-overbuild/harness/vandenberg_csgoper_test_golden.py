#!/usr/bin/env python3
"""Decisive live test: does the real editor treat Brush230 (the real world-CSG-order idx-0 brush of
`12_Vandenberg_Gas.dx`, which has NO `CsgOper=` property at all) as a CSG participant, or skip it?

Brush230's T3D carries no `CsgOper=` line. `Engine.Brush.CsgOper`'s class default (an ECsgOper enum,
`CSG_Active`/`CSG_Add`/`CSG_Subtract`/`CSG_Intersect`/`CSG_Deintersect`, ordinal 0) resolves to
`CSG_Active` (no override text in the class defaults) -- i.e. the "builder brush" inactive state, NOT
`CSG_Add`. `uedcli/native/brush_marshal.py::_build_brush_input` currently defaults an absent
`CsgOper` to `"CSG_Add"` (`raw.get("CsgOper", "CSG_Add")`) -- if the real editor actually SKIPS a
CSG_Active brush during `MAP REBUILD`, this default wrongly makes Brush230 an active leading-Add
brush, triggering `bspcsg.rs`'s `first_add_seed` convex-seed shortcut on a bogus single NotSolid
poly and corrupting the ROOT of the whole subsequent world tree (every later brush, however far
away spatially, gets classified against this single root plane first).

Test: build the real first 4 world-CSG-order brushes of Vandenberg Gas TWO ways --
  (A) Brush2054, Brush73, Brush54           (skip Brush230)
  (B) Brush230, Brush2054, Brush73, Brush54  (include it, real order)
If the editor skips Brush230 (CSG_Active == inactive), (A) and (B) build IDENTICAL geometry.

Usage: .venv/bin/python vandenberg_csgoper_test_golden.py
Run as a bounded background job -- the editor wedges silently (dev/docs/rules/background-work.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/vandenberg-gas-parity")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness"))

from uedcli import config, trunk, writes, xfer                     # noqa: E402
from uedcli.container_assets import resource_mounts                # noqa: E402
from uedcli.driver import Driver                                   # noqa: E402
from uedcli.editor import ensure_editor, stop_editor                # noqa: E402
from uedcli.uuid7 import uuid7                                     # noqa: E402
import build_ued_golden as bg                                      # noqa: E402
from geo_golden_driver import _wait_idle                           # noqa: E402

TRUNK = (ROOT / "_scratch/uedcli-parity-cache/"
         "7d06dd6155e5daa7c78e76ed19a66068852973670d1c56dddd9628b2ca393c13/trunk/maps/12_vandenberg_gas")
OUT_DIR = ROOT / "_scratch/vandenberg-csgoper-test"


def build_one(names, out_name, container_state):
    lvl, _ranks = trunk.read_level(TRUNK)
    brush_actors = [lvl.actors[n] for n in names]

    user_config = config.load_user_config()
    project = bg._scratch_project(TRUNK, "deusex")
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    ed_id = uuid7()
    container = ensure_editor(ed_id, mounts=mounts, state_dir=state_dir)
    ed = Driver(container=container)
    out = OUT_DIR / out_name
    try:
        print(f"[{out_name}] editor up: {container}", flush=True)
        ed.map_new()
        _wait_idle(container, label="map-new")
        ed.set_grid(1, 1, 1)
        t3d = writes.emit_map([writes._shift_for_paste(a) for a in brush_actors])
        ed.set_clipboard(t3d)
        ed.edit_paste()
        _wait_idle(container, label="paste")
        print(f"[{out_name}] pasted, MAP REBUILD ...", flush=True)
        ed.exec("MAP REBUILD")
        _wait_idle(container, label="rebuild", timeout=600, quiet_reads=8, min_seconds=5)
        work_out = xfer.work_path("dx")
        size = ed.map_save(work_out)
        xfer.cp_out(container, work_out, str(out))
        print(f"[{out_name}] WROTE {out} ({size} bytes)", flush=True)
    finally:
        try:
            stop_editor(ed_id, state_dir)
        except Exception as e:
            print(f"[{out_name}] teardown note: {e}", flush=True)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    build_one(["Brush2054", "Brush73", "Brush54"], "A_no230.dx", None)
    build_one(["Brush230", "Brush2054", "Brush73", "Brush54"], "B_with230.dx", None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
