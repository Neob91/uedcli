#!/usr/bin/env python3
"""Incremental N-brush subset differential: the "master tool" (spike method 2).

Builds an N-brush prefix of the castle trunk BOTH ways and node-diffs the two Model trees,
to binary-search / scan for the SMALLEST N where the native `build_geometry_bspcsg` tree first
diverges from what UnrealEd's `MAP REBUILD` produces.  That N's brush + operation is the concrete
first-diverging culprit.

  * NATIVE  — `uedctl_native.build_geometry_bspcsg` over the first N brushes (in trunk order),
              serialized and re-parsed to a `Model` (identical to castle_build.build_native but
              on a prefix).
  * EDITOR  — a SUBSET TRUNK holding all non-brush actors (LevelInfo/PlayerStart/lights — they do
              not affect CSG) plus the first N brush actors, materialized through the real UED22
              container via `apply.run_materialize` → golden `.dx`, largest Model export parsed.

The editor build is the expensive part (~1-2 min each, shared box); results are CACHED under
`_scratch/castle-subset/goldenN.dx` so a re-run reuses them.  Non-brush actors are kept so the
materialize self-check (Actors[0]=LevelInfo, Actors[1]=Brush, PlayerStart) passes unchanged.

Usage:
  subset_diff.py build N            # editor-materialize the N-brush subset (cached)
  subset_diff.py diff N [--tol t]   # node-diff native-vs-editor for the N-brush subset
  subset_diff.py scan A B           # build+diff each N in [A,B], print first-divergence table
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedctl import config, trunk, apply  # noqa: E402
from uedctl.native import materialize as M, umodel as UM  # noqa: E402
import uedctl_native  # noqa: E402
import utexture_decode as UT  # noqa: E402

import castle_build  # noqa: E402
import node_diff  # noqa: E402

CASTLE_PROJECT = ROOT.parent.parent / "_scratch/castle/uedctl"       # .../castle/uedctl (project dir)
FULL_TRUNK = Path(castle_build.TRUNK)                                 # .../maps/foobar
SUBSET_ROOT = ROOT.parent.parent / "_scratch/castle-subset"          # scratch outputs (gitignored)


def _brush_order(level):
    return [n for n in level.order if level.actors[n].brush is not None]


def _make_subset_trunk(n: int) -> Path:
    """Create a subset trunk dir with all non-brush actors + the first N brush actors."""
    level, ranks = trunk.read_level(FULL_TRUNK)
    brushes = _brush_order(level)
    keep_brushes = set(brushes[:n])
    dst = SUBSET_ROOT / f"trunk{n}" / "maps" / "foobar"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    src_actors = FULL_TRUNK / "actors"
    dst_actors = dst / "actors"
    dst_actors.mkdir()
    for name in level.order:
        a = level.actors[name]
        if a.brush is not None and name not in keep_brushes:
            continue
        shutil.copytree(src_actors / name, dst_actors / name)
    return dst


def _composed(project):
    """(load_set, search_dirs) for the castle project — mirrors dispatch._composed_*."""
    from uedctl.packages import search_path_package_names
    uc = config.load_user_config()
    load_set = search_path_package_names(config.composed_search_files(project, uc))
    search_dirs = config.composed_search_dirs(project, uc)
    return load_set, search_dirs


def golden_path(n: int) -> Path:
    return SUBSET_ROOT / f"golden{n}.dx"


def build_editor_subset(n: int, force: bool = False) -> Path:
    """Editor-materialize the N-brush subset; cache the .dx.  Returns its path."""
    out = golden_path(n)
    if out.exists() and not force:
        return out
    subset_trunk = _make_subset_trunk(n)
    level, _ = trunk.read_level(subset_trunk)
    project = config.load_project(str(CASTLE_PROJECT))
    load_set, search_dirs = _composed(project)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    res = apply.run_materialize(level=level, packages=load_set, search_dirs=search_dirs,
                                out_path=str(out), overwrite=True, no_verify=True)
    if res.rc != 0:
        raise SystemExit(f"editor materialize N={n} FAILED: {res.message}")
    return out


def build_native_subset(n: int) -> UM.Model:
    level, _ = trunk.read_level(FULL_TRUNK)
    brushes = _brush_order(level)[:n]
    bs = [M._build_brush_input(name, level.actors[name]) for name in brushes]
    native = uedctl_native.build_geometry_bspcsg(bs)
    body = uedctl_native.serialize_model(native)
    return UM.parse_model_body(body, 0, len(body))


def load_editor_model(path: Path):
    pkg = UT.load_package(str(path))
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def diff(n: int, tol: float = 1e-3, force: bool = False):
    native = build_native_subset(n)
    ed_path = build_editor_subset(n, force=force)
    editor = load_editor_model(ed_path)
    res = node_diff.diff_nodes(native, editor, tol=tol)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("n", type=int); b.add_argument("--force", action="store_true")
    d = sub.add_parser("diff"); d.add_argument("n", type=int); d.add_argument("--tol", type=float, default=1e-3)
    d.add_argument("--force", action="store_true"); d.add_argument("--top", type=int, default=6)
    s = sub.add_parser("scan"); s.add_argument("a", type=int); s.add_argument("b", type=int)
    s.add_argument("--tol", type=float, default=1e-3)
    args = ap.parse_args()

    if args.cmd == "build":
        p = build_editor_subset(args.n, force=args.force)
        print(f"built editor subset N={args.n} -> {p}")
    elif args.cmd == "diff":
        res = diff(args.n, tol=args.tol, force=args.force)
        print(f"=== SUBSET N={args.n} ===")
        node_diff.print_report(res, top=args.top)
    elif args.cmd == "scan":
        print(f"{'N':>3} {'nat':>5} {'ed':>5} {'prefix':>7} {'shared':>7} {'onlyN':>6} {'onlyE':>6}  first-div")
        for n in range(args.a, args.b + 1):
            res = diff(n, tol=args.tol)
            ms = res['multiset']
            fd = res['first_divergence']
            fdesc = "MATCH" if fd is None else f"node[{fd['index']}] {','.join(fd['fields'])}"
            print(f"{n:>3} {res['len_native']:>5} {res['len_editor']:>5} {res['prefix']:>7} "
                  f"{ms['shared']:>7} {ms['only_native']:>6} {ms['only_editor']:>6}  {fdesc}")


if __name__ == "__main__":
    main()
