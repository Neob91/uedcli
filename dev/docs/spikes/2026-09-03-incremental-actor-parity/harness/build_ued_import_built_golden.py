#!/usr/bin/env python3
"""The BUILT MAP IMPORT golden — the full-binary parity reference (owner ruling 2026-09-04).

`MAP NEW` -> `MAP IMPORT FILE=` (whole-level T3D) -> `MAP REBUILD` -> `LIGHT APPLY` -> `MAP SAVE`.

MAP IMPORT is the editor ingest path whose SERIALIZATION native's `assemble_unbuilt` already
byte-matches (the 2026-09-02 unbuilt-structure-parity work) AND which brings Movers in with their
own models — unlike the `EDIT PASTE` lit golden, which uses a different table order and drops movers.
Adding `MAP REBUILD` + `LIGHT APPLY` gives the built Model + lighting so native's full built package
can be byte-diffed against a like-for-like reference.

Reuses `build_ued_import_golden`'s helpers (`_quote_str_props`) and the shared editor-driver harness
(`_scratch_project`, `_wait_idle`). Run as a BOUNDED BACKGROUND JOB — the editor wedges silently.

Usage:
  build_ued_import_built_golden.py --trunk <dir-with-actors/> --out <golden.dx> [--overwrite]
                                   [--rebuild-cmd "MAP REBUILD"] [--no-light]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
UNBUILT_HARNESS = ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"
NATIVE_MAT_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(UNBUILT_HARNESS))
sys.path.insert(0, str(NATIVE_MAT_HARNESS))

from uedcli import config, trunk, xfer                              # noqa: E402
from uedcli.apply import _level_referenced_packages                 # noqa: E402
from uedcli.container_assets import resource_mounts                 # noqa: E402
from uedcli.driver import Driver, to_z_path                         # noqa: E402
from uedcli.editor import ensure_editor, stop_editor                # noqa: E402
from uedcli.emit import emit_map                                    # noqa: E402
from uedcli.materialize import levelinfo_first_order, _short_class  # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load         # noqa: E402
from uedcli.uuid7 import uuid7                                      # noqa: E402

from build_ued_golden import _scratch_project, _wait_idle           # noqa: E402
from build_ued_import_golden import _quote_str_props                # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trunk", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--game", default="deusex")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--import-verb", default="MAP IMPORT",
                    help="editor ingest verb: `MAP IMPORT` (replace level) or `MAP IMPORTADD` "
                         "(add to the MAP NEW level).")
    ap.add_argument("--map-new-first", action="store_true",
                    help="run `MAP NEW` before the ingest verb, so its default builder brush occupies "
                         "the sacrificial Actors[1] slot UED22 excludes from CSG. REQUIRED with "
                         "`MAP IMPORTADD` to avoid losing the first real brush (else its CSG is "
                         "dropped; see board/ued22-world-bsp-differs-per-ingest-verb-paste).")
    ap.add_argument("--rebuild-cmd", default="MAP REBUILD",
                    help="';'-separated rebuild verbs (default bare `MAP REBUILD`).")
    ap.add_argument("--no-light", action="store_true", help="skip LIGHT APPLY")
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
    _quote_str_props(lvl, imp_order, project, user_config)
    actors = [lvl.actors[n] for n in imp_order]
    n_brush = sum(1 for n in imp_order if has_brush[n])
    print(f"trunk {trunk_dir.name}: importing {len(actors)} actors ({n_brush} brush) "
          f"lit={not args.no_light}", flush=True)

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
        if args.map_new_first:
            ed.map_new()
            _wait_idle(ed, label="map-new")
        t3d_path = ed.write_work_file(emit_map(actors), ext="t3d")
        ed.exec(f"{args.import_verb} FILE={to_z_path(t3d_path)}")
        _wait_idle(ed, label="map-import", timeout=args.timeout, quiet_reads=args.quiet_reads)
        for i, cmd in enumerate(c.strip() for c in args.rebuild_cmd.split(";") if c.strip()):
            print(f"  REBUILD[{i}]: {cmd} ...", flush=True)
            ed.exec(cmd)
            _wait_idle(ed, label=f"rebuild[{i}]", timeout=args.timeout, quiet_reads=args.quiet_reads)
        if not args.no_light:
            print("  LIGHT APPLY ...", flush=True)
            ed.light_apply()
            _wait_idle(ed, label="light-apply", timeout=args.timeout, quiet_reads=args.quiet_reads)
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
