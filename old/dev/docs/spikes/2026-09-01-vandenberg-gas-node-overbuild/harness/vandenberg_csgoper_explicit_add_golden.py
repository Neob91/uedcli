#!/usr/bin/env python3
"""Decisive follow-up to `vandenberg_csgoper_test_golden.py`'s refuted hypothesis: does an
EXPLICIT `CsgOper=CSG_Add` on Brush230's own (degenerate, 1-poly, NotSolid) geometry reproduce
the SAME collapse (B_with230.dx: nodes=181) the CsgOper-absent version showed, when compared
against A (Brush2054,Brush73,Brush54 alone, nodes=483)? If yes, this confirms the mechanism is
`bspcsg.rs`'s ALREADY-KNOWN, ALREADY-FILED `first_add_seed` gap ("WRONG for a leading Add that is
a small solid... tracked in board/inbox, first_add_seed, p3") -- i.e. ANY leading Add that isn't a
real world-enclosing shell hits this, independent of whether CsgOper was literally absent or
explicit -- not a CsgOper-defaulting bug specific to Brush230.

Usage: .venv/bin/python vandenberg_csgoper_explicit_add_golden.py
Run as a bounded background job -- the editor wedges silently (dev/docs/rules/background-work.md).
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/vandenberg-csg-active")
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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lvl, _ranks = trunk.read_level(TRUNK)
    b230 = lvl.actors["Brush230"]
    # Same actor, props list with an EXPLICIT CsgOper=CSG_Add prepended.
    new_props = [("CsgOper", "CSG_Add")] + list(b230.props)
    b230_add = dataclasses.replace(b230, props=new_props)
    names = ["Brush2054", "Brush73", "Brush54"]
    brush_actors = [b230_add] + [lvl.actors[n] for n in names]

    user_config = config.load_user_config()
    project = bg._scratch_project(TRUNK, "deusex")
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    ed_id = uuid7()
    container = ensure_editor(ed_id, mounts=mounts, state_dir=state_dir)
    ed = Driver(container=container)
    out = OUT_DIR / "C_230_explicit_add.dx"
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
        print(f"WROTE {out} ({size} bytes)", flush=True)
    finally:
        try:
            stop_editor(ed_id, state_dir)
        except Exception as e:
            print(f"teardown note: {e}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
