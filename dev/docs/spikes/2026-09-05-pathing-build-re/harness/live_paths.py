#!/usr/bin/env python3
"""Drive an ephemeral UED22 editor through a path build and capture the results.

Two sources: a trunk (`--trunk <dir>`: MAP IMPORT with the sacrificial builder brush, MAP REBUILD)
or a retail `.dx` (`--dx <file>`: MAP LOAD). Then, for each `--step NAME=VERB[;VERB]` in order, run
the verbs and `MAP SAVE` to `<out-dir>/<NAME>.dx`. The editor log written during the run is saved
to `<out-dir>/editor.log`. Run as a bounded background job (the editor wedges silently).

Usage:
  live_paths.py --trunk <dir> --out-dir <dir> --step base= --step build="PATHS BUILD" ...
  live_paths.py --dx <retail.dx> --out-dir <dir> --step load= --step build="PATHS BUILD"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ASSET_ROOT  # noqa: E402
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli import config, trunk, xfer                              # noqa: E402
from uedcli.apply import _level_referenced_packages                 # noqa: E402
from uedcli.container_assets import resource_mounts                 # noqa: E402
from uedcli.driver import Driver, to_z_path                         # noqa: E402
from uedcli.editor import ensure_editor, stop_editor                # noqa: E402
from uedcli.emit import emit_map                                    # noqa: E402
from uedcli.materialize import levelinfo_first_order                # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load         # noqa: E402
from uedcli.upackage import load_package                            # noqa: E402
from uedcli.uuid7 import uuid7                                      # noqa: E402

from build_ued_import_built_golden import _dummy_builder_actor      # noqa: E402
from build_ued_import_golden import _quote_str_props                # noqa: E402


def dx_root_packages(path: str) -> list[str]:
    pkg = load_package(path)
    out = []
    for cp, cn, pi, on in pkg.imports:
        if pkg.names[cn] == "Package" and pi == 0:
            name = pkg.names[on]
            if name not in ("Core", "Engine") and name not in out:
                out.append(name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trunk")
    ap.add_argument("--dx")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--step", action="append", default=[], help="NAME=VERB[;VERB] (empty VERB = save only)")
    ap.add_argument("--timeout", type=float, default=3600.0)
    args = ap.parse_args()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    user_config = config.load_user_config()
    project = config.load_project(str(ASSET_ROOT / "dev/games"))
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    if args.trunk:
        trunk_dir = Path(args.trunk).resolve()
        lvl, _ = trunk.read_level(trunk_dir)
        classes = {n: lvl.actors[n].cls for n in lvl.order}
        has_brush = {n: lvl.actors[n].brush is not None for n in lvl.order}
        imp_order = levelinfo_first_order(lvl.order, classes, has_brush)
        _quote_str_props(lvl, imp_order, project, user_config)
        actors = [lvl.actors[n] for n in imp_order]
        actors.insert(1, _dummy_builder_actor())
        ref_pkgs = _level_referenced_packages(type("L", (), {"actors": {n: lvl.actors[n] for n in imp_order}})())
        t3d_text = emit_map(actors)
    else:
        ref_pkgs = dx_root_packages(args.dx)
        t3d_text = None
    print(f"referenced packages: {ref_pkgs}", flush=True)

    ed_id = uuid7()
    container = None
    saves: list[tuple[str, str]] = []
    try:
        container = ensure_editor(ed_id, mounts=mounts, state_dir=state_dir)
        ed = Driver(container=container)
        print(f"editor up: {container}", flush=True)
        log0 = ed.log_size()
        ed.begin_script()
        ensure_load(ed, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        if args.trunk:
            t3d_path = ed.write_work_file(t3d_text, ext="t3d")
            ed.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
            ed.exec("MAP REBUILD")
        else:
            dx_path = ed.write_work_file(open(args.dx, "rb").read(), ext="dx")
            ed.exec(f"MAP LOAD FILE={to_z_path(dx_path)}")
        for step in args.step:
            name, _, verbs = step.partition("=")
            for v in (x.strip() for x in verbs.split(";") if x.strip()):
                ed.exec(v)
            wp = xfer.work_path("dx")
            ed.exec(f"MAP SAVE FILE={to_z_path(wp)}")
            saves.append((name, wp))
        print(f"running {len(saves)} steps ...", flush=True)
        ed.run_script(produces=saves[-1][1], timeout=args.timeout)
        for name, wp in saves:
            host = out_dir / f"{name}.dx"
            xfer.cp_out(container, wp, str(host))
            print(f"  {name}: {host.stat().st_size} bytes", flush=True)
        (out_dir / "editor.log").write_text(ed.read_log_since(log0))
        print("log saved", flush=True)
    finally:
        if container:
            xfer.remove(container, *[wp for _, wp in saves])
            stop_editor(ed_id, state_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
