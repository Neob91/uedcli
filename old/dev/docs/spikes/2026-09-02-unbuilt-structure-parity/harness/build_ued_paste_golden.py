#!/usr/bin/env python3
"""Build the PURE EDIT PASTE unbuilt golden: `MAP NEW` -> one `EDIT PASTE` of the whole level's
T3D (every actor, points included) -> `MAP SAVE`. No `MAP IMPORTADD`, no rebuild, no lighting.

The third editor-side reference for the unbuilt-structure parity spike, next to the
`build_ued_lit_golden.py --rebuild-cmd "" --no-light` hybrid (IMPORTADD points + PASTE brushes)
and `build_ued_import_golden.py` (whole-level `MAP IMPORT`). Every pasted actor lands
+32uu-drifted on all axes (`writes.PASTE_DRIFT`), so every actor -- points too -- is pre-shifted
-32 via `writes._shift_for_paste` to save at its authored Location.

Usage:
  build_ued_paste_golden.py --trunk <dir-with-actors/> --out <golden.dx> [--overwrite]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli import config, trunk, xfer                              # noqa: E402
from uedcli.apply import _level_referenced_packages                 # noqa: E402
from uedcli.container_assets import resource_mounts                 # noqa: E402
from uedcli.driver import Driver                                    # noqa: E402
from uedcli.editor import ensure_editor, stop_editor                # noqa: E402
from uedcli.emit import emit_map                                    # noqa: E402
from uedcli.materialize import levelinfo_first_order, _short_class  # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load         # noqa: E402
from uedcli.uuid7 import uuid7                                      # noqa: E402
from uedcli.writes import _shift_for_paste                          # noqa: E402

from build_ued_golden import _scratch_project, _wait_idle           # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trunk", required=True, help="the T3D trunk dir (holds actors/)")
    ap.add_argument("--out", required=True, help="host path for the golden .dx")
    ap.add_argument("--game", default="deusex")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--timeout", type=float, default=3600.0)
    ap.add_argument("--quiet-reads", type=int, default=30)
    args = ap.parse_args()

    trunk_dir = Path(args.trunk).resolve()
    host_out = Path(args.out).resolve()
    if not (trunk_dir / "actors").is_dir():
        print(f"not a trunk dir: {trunk_dir}", file=sys.stderr)
        return 2
    if host_out.exists() and not args.overwrite:
        print(f"refusing to overwrite {host_out} (--overwrite)", file=sys.stderr)
        return 2

    user_config = config.load_user_config()
    project = _scratch_project(trunk_dir, args.game)
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)

    lvl, _ranks = trunk.read_level(trunk_dir)
    classes = {n: lvl.actors[n].cls for n in lvl.order}
    has_brush = {n: lvl.actors[n].brush is not None for n in lvl.order}
    imp_order = levelinfo_first_order(lvl.order, classes, has_brush)
    actors = [_shift_for_paste(lvl.actors[n]) for n in imp_order]
    n_brush = sum(1 for n in imp_order if has_brush[n])
    print(f"trunk {trunk_dir.name}: pasting {len(actors)} actors ({n_brush} brush) "
          f"classes={sorted({_short_class(c) or '?' for c in classes.values()})}", flush=True)

    ref_pkgs = _level_referenced_packages(
        type("L", (), {"actors": {n: lvl.actors[n] for n in imp_order}})())
    print(f"referenced packages to OBJ LOAD: {ref_pkgs}", flush=True)

    state_dir = config.state_dir(project.root, create=True)
    ed_id = uuid7()
    container = work_out = None
    try:
        container = ensure_editor(ed_id, mounts=mounts, state_dir=state_dir)
        ed = Driver(container=container)
        print(f"editor up: {container}", flush=True)
        ensure_load(ed, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        _wait_idle(ed, label="obj-load")
        ed.map_new()
        _wait_idle(ed, label="map-new")
        ed.set_grid(1, 1, 1)
        ed.set_clipboard(emit_map(actors))
        ed.edit_paste()
        _wait_idle(ed, label="edit-paste", timeout=args.timeout, quiet_reads=args.quiet_reads)
        work_out = xfer.work_path("dx")
        print("  MAP SAVE ...", flush=True)
        size = ed.map_save(work_out)
        host_out.parent.mkdir(parents=True, exist_ok=True)
        xfer.cp_out(container, work_out, str(host_out))
        print(f"WROTE {host_out} ({size} bytes container-side, "
              f"{host_out.stat().st_size} host-side)", flush=True)
    finally:
        if container and work_out:
            xfer.remove(container, work_out)
        stop_editor(ed_id, state_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
