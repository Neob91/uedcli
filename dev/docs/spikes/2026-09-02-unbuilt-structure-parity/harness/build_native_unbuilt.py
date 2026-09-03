#!/usr/bin/env python3
"""Build the native UNBUILT `.dx` (`assemble_unbuilt`, empty world Model) from a T3D trunk,
mirroring the production `apply._materialize*` path: `levelinfo_first_order`, `set_base_pose`,
`substrate_schema` over the editor search dirs. The output is the structural half of `level
materialize` -- actors + tables, no CSG, no lighting -- judged against the editor's own
`MAP NEW` -> `EDIT PASTE` -> `MAP SAVE` of the same trunk.

Usage:
  build_native_unbuilt.py --trunk <dir-with-actors/> --out <native.dx> [--version 68]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from uedcli import config, trunk                                     # noqa: E402
from uedcli.materialize import levelinfo_first_order, _short_class   # noqa: E402
from uedcli.native.unbuilt import assemble_unbuilt, substrate_schema  # noqa: E402
from uedcli.packages import editor_search_dirs                       # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trunk", required=True, help="the T3D trunk dir (holds actors/)")
    ap.add_argument("--out", required=True, help="host path for the native unbuilt .dx")
    ap.add_argument("--game", default="deusex")
    ap.add_argument("--version", type=int, default=69, help="package FileVersion to write")
    ap.add_argument("--seed-tables-from", default=None,
                    help="PARITY-GATE oracle: a golden .dx whose name/import TABLE ORDER is "
                         "pre-seeded into the writer, so the gate judges every other byte "
                         "(the two orders are editor hash-iteration artifacts, spike 2026-09-02)")
    args = ap.parse_args()

    trunk_dir = Path(args.trunk).resolve()
    if not (trunk_dir / "actors").is_dir():
        print(f"not a trunk dir: {trunk_dir}", file=sys.stderr)
        return 2
    maps_root = trunk_dir.parent
    proj_root = maps_root.parent
    toml = proj_root / "uedcli.toml"
    if not toml.exists():
        toml.write_text(f'game = "{args.game}"\nmaps = "{maps_root.name}"\n')
    project = config.load_project(str(proj_root))
    user_config = config.load_user_config()
    pkg_dirs = editor_search_dirs(config.composed_search_dirs(project, user_config))

    lvl, _ranks = trunk.read_level(trunk_dir)
    classes = {n: lvl.actors[n].cls for n in lvl.order}
    has_brush = {n: lvl.actors[n].brush is not None for n in lvl.order}
    lvl.order = levelinfo_first_order(lvl.order, classes, has_brush)

    # NO `set_base_pose`: the editor derives a mover's BasePos/BaseRot at REBUILD, not import, so
    # the unbuilt reference save carries neither (UNATCO import golden, 2026-09-02).
    n_brush = sum(1 for n in lvl.order if has_brush[n])
    print(f"trunk {trunk_dir.name}: {len(lvl.order)} actors ({n_brush} brush) "
          f"classes={sorted({_short_class(c) or '?' for c in classes.values()})}", flush=True)

    oracle = None
    if args.seed_tables_from:
        from uedcli.upackage import load_package
        oracle = load_package(args.seed_tables_from)
    dx_bytes, warnings = assemble_unbuilt(lvl, version=args.version,
                                          schema=substrate_schema(*pkg_dirs), pkg_dirs=pkg_dirs,
                                          table_oracle=oracle)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(dx_bytes)
    print(f"WROTE {out} ({len(dx_bytes)} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
