#!/usr/bin/env python3
"""Build a prefix of the Area51 entrance trunk's world-CSG brushes in a LIVE UnrealEd (debug
image) and read the world BSP surf count attributed to each brush.

The golden's per-brush surf counts (final 1343-brush tree) come from the same editor.  This probe
rebuilds the level incrementally ONE brush at a time so we can watch how the editor's per-brush
face retention changes as the prefix grows — which native's isolated fixtures cannot show (native
keeps all 26 authored polys of a subtract loft, the golden's final tree keeps 10).

Per prefix N (world-CSG brush count), we:
  MAP NEW
  _re_add(LevelInfo0 + first N CSG brushes)      # same add path as build_ued_golden
  MAP REBUILD + idle barrier
  MAP SAVE + structural check -> parse .dx world model -> per-brush surf count

Chains all prefixes in ONE editor session (no H3 verify => the reused-editor MAP SAVE loss does not
apply).  Prints, per prefix, the per-brush surf count for every brush in that prefix and the total.

Run as a BOUNDED BACKGROUND JOB — the editor wedges silently (~20-min hang detector).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/workspace/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
ORACLE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(ORACLE))

from uedcli import config, trunk, xfer                          # noqa: E402
from uedcli.container_assets import resource_mounts             # noqa: E402
from uedcli.driver import Driver, to_z_path                     # noqa: E402
import editor_tree_oracle as O                                  # noqa: E402
from uedcli.writes import _re_add                               # noqa: E402
from uedcli.uuid7 import uuid7                                  # noqa: E402
from uedcli.native import brush_marshal as BM                   # noqa: E402
from uedcli.native import umodel as UM                          # noqa: E402
from uedcli import utexture                                     # noqa: E402
from spike_classindex import class_index                        # noqa: E402

UEDCLI_PROJ = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance"
TRUNK_DIR = Path(UEDCLI_PROJ) / "maps" / "area51-entrance"
GOLDEN = Path(UEDCLI_PROJ) / "golden_area51.dx"
OUT_DIR = Path("/workspace/uedcli/_scratch/a51-editor-trace")
PREFIXES = [4, 5, 6, 7, 8, 9, 10, 14, 20, 32, 48]
REBUILD_TIMEOUT = 2400.0


def _wait_idle(container, label, thresh=30.0, quiet_reads=4, min_seconds=2.0, timeout=REBUILD_TIMEOUT):
    t0 = time.time()
    quiet = 0
    while True:
        r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}", container],
                           capture_output=True, text=True)
        cpu = float((r.stdout.strip().rstrip("%")) or 0.0)
        quiet = quiet + 1 if cpu < thresh else 0
        el = time.time() - t0
        if quiet >= quiet_reads and el >= min_seconds:
            print(f"    [{label}] idle after {el:.0f}s", flush=True)
            return el
        if el > timeout:
            raise TimeoutError(f"not idle [{label}] after {timeout:.0f}s cpu={cpu}")
        time.sleep(1.0)


def _surf_counts_by_name(dx_path):
    """Parse a .dx world model; return {brush_name: surf_count}."""
    pkg = utexture.load_package(str(dx_path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    from collections import Counter
    c = Counter()
    for s in m.surfs:
        nm = pkg.name_of_ref(s.i_actor)
        if nm is not None:
            c[nm] += 1
    return m, dict(c)


def load_trunk_csg_order():
    level, _ = trunk.read_level(TRUNK_DIR)
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    return level, names


def golden_counts():
    _, gc = _surf_counts_by_name(GOLDEN)
    return gc


def main():
    os.environ["UEDCLI_PROJECT"] = UEDCLI_PROJ
    level, csg_names = load_trunk_csg_order()
    print(f"world CSG brushes: {len(csg_names)}", flush=True)
    gcount = golden_counts()

    # LevelInfo point actor to carry a valid level (geometry-independent; brushes drive CSG).
    linfo = [level.actors[n] for n in level.order if level.actors[n].cls in ("LevelInfo",)
             and level.actors[n].brush is None][:1]
    print("levelinfo:", [a.cls for a in linfo], flush=True)
    byname = {n: i for i, n in enumerate(csg_names)}

    project = config.load_project(UEDCLI_PROJ)
    uc = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, uc)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-a51-prefix"
    # The sandbox HOME (/home/agent) is private to the shell, so the daemon cannot create a mount
    # source there.  Point the per-user uedcli home (which the compose file mounts at /stubs, and
    # which start_dbg_editor re-derives from config.stub_cache_root) at a repo-tree path the docker
    # daemon can see.  Geometry-only prefix builds never OBJ LOAD the stubs, so content is irrelevant
    # — it just has to be a mountable path.
    uedhome = (Path("/workspace/uedcli/_scratch/a51-editor-trace") / "uedhome")
    uedhome.mkdir(parents=True, exist_ok=True)
    os.environ["UEDCLI_HOME"] = str(uedhome)
    O.stop_dbg_editor(container, state_dir)
    print(f"starting editor {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    ed = Driver(container=container)
    ed.map_new()
    _wait_idle(container, "map-new")

    # Golden per-brush (final full tree) for reference at the top of output.
    print("\n=== golden final per-brush (full 1343-brush tree) ===")
    for i, n in enumerate(csg_names[:max(PREFIXES)]):
        print(f"  idx{i} {n:12s} golden={gcount.get(n,0)}")
    print("=== end golden ===\n", flush=True)

    try:
        for N in PREFIXES:
            subset = csg_names[:N]
            actors = [level.actors[n] for n in subset]
            # Build: fresh LevelInfo + these brushes.  _re_add pastes brushes (shifted) + imports
            # points.  Use a fresh MAP NEW per prefix so each is independent.
            ed.map_new()
            _wait_idle(container, f"map-new-p{N}")
            _re_add(ed, linfo + actors)
            _wait_idle(container, f"add-p{N}", timeout=REBUILD_TIMEOUT)
            ed.exec("MAP REBUILD")
            _wait_idle(container, f"rebuild-p{N}", timeout=REBUILD_TIMEOUT)
            work = xfer.work_path("dx")
            ed.map_save(work)
            host = OUT_DIR / f"a51_prefix_{N:02d}.dx"
            xfer.cp_out(container, work, str(host))
            xfer.remove(container, work)
            m, c = _surf_counts_by_name(host)
            print(f"\n### prefix N={N} nodes={len(m.nodes)} surfs={len(m.surfs)} "
                  f"golden_total={gcount and sum(gcount.values()) or '?'}", flush=True)
            for i, n in enumerate(subset):
                print(f"  idx{i} {n:12s} native-ish prefix count={c.get(n,0)} golden_final={gcount.get(n,0)}",
                      flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
