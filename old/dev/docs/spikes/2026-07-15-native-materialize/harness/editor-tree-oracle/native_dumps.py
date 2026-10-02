#!/usr/bin/env python3
r"""Native counterpart of the editor oracles here: build a whole real level's world BSP offline and
capture the env-gated `bspcsg.rs` dumps the oracles are diffed against.

Every editor-side script in this directory needs a live, gdb-attached editor and takes minutes. The
native side needs none of that, but the hooks are env vars on `build_geometry_bspcsg`, so each
comparison was being driven by a throwaway inline script. This is that driver, committed, so a
board item's reproduce recipe is runnable rather than pseudo-code.

Each `--*` flag turns on one hook and routes the Rust `eprintln!` stream (fd 2) to the named file:

  --stage-counts            UEDCLI_BSPCSG_STAGE_COUNTS — node/vert/point counts per pipeline stage
  --tree-struct  <log>      UEDCLI_BSPCSG_TREE_STRUCT  — the committed pre-repartition tree
                            (pairs with `ed_committed_tree.py` via `committed_tree_diff.py`)
  --soup-order   <log>      UEDCLI_BSPCSG_SOUP_ORDER   — the post-merge repartition soup, in the
                            order `bsp_build` consumes it (pairs with `ed_soup.py`)
  --repart-nodes <log>      UEDCLI_BSPCSG_REPART_NODES — the post-repartition tree
                            (pairs with `repart_tree_unatco.py`)
  --norepart                UEDCLI_BSPCSG_NOREPART     — stop after the structural CSG loop

The brush set is the same one `level materialize` carves: brush-bearing actors that pass
`brush_marshal._in_world_csg` (so movers are excluded), in trunk CSG order.

Usage:
  native_dumps.py <project-dir> <trunk-dir> [--stage-counts] [--tree-struct LOG]
                  [--soup-order LOG] [--repart-nodes LOG] [--norepart]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", help="project root holding uedcli.toml (for the mover ClassIndex)")
    ap.add_argument("trunk", help="the T3D trunk dir to build (holds actors/)")
    ap.add_argument("--stage-counts", action="store_true",
                    help="print per-stage node/vert/point counts to stderr")
    ap.add_argument("--tree-struct", metavar="LOG",
                    help="dump the committed pre-repartition tree to LOG")
    ap.add_argument("--soup-order", metavar="LOG",
                    help="dump the post-merge repartition soup to LOG")
    ap.add_argument("--repart-nodes", metavar="LOG",
                    help="dump the post-repartition tree to LOG")
    ap.add_argument("--norepart", action="store_true",
                    help="skip the repartition and everything after it")
    args = ap.parse_args()

    trunk_dir = Path(args.trunk).resolve()
    if not (trunk_dir / "actors").is_dir():
        print(f"not a trunk dir: {trunk_dir}", file=sys.stderr)
        return 2
    # The dumps all share fd 2, so two file-routed hooks would interleave into one log.
    routed = [f for f in (args.tree_struct, args.soup_order, args.repart_nodes) if f]
    if len(routed) > 1:
        print("one file-routed dump per run (they all share fd 2): "
              f"got {', '.join(routed)}", file=sys.stderr)
        return 2

    os.environ["UEDCLI_PROJECT"] = str(Path(args.project).resolve())
    if args.stage_counts:
        os.environ["UEDCLI_BSPCSG_STAGE_COUNTS"] = "1"
    if args.tree_struct:
        os.environ["UEDCLI_BSPCSG_TREE_STRUCT"] = "1"
    if args.soup_order:
        os.environ["UEDCLI_BSPCSG_SOUP_ORDER"] = "1"
    if args.repart_nodes:
        os.environ["UEDCLI_BSPCSG_REPART_NODES"] = "1"
    if args.norepart:
        os.environ["UEDCLI_BSPCSG_NOREPART"] = "1"

    from uedcli import trunk as trunk_mod
    from uedcli.native import brush_marshal as BM
    import uedcli_native
    from spike_classindex import class_index

    level, _ranks = trunk_mod.read_level(trunk_dir)
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    brushes = [BM._build_brush_input(n, level.actors[n]) for n in names]
    print(f"{trunk_dir.name}: {len(level.actors)} actors, {len(brushes)} world CSG brushes",
          file=sys.stderr, flush=True)

    out = routed[0] if routed else None
    saved = fd = None
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        saved = os.dup(2)
        os.dup2(fd, 2)
    try:
        model = uedcli_native.build_geometry_bspcsg(brushes)
    finally:
        if saved is not None:
            os.dup2(saved, 2); os.close(saved); os.close(fd)
    if out:
        print(f"wrote {out}", file=sys.stderr, flush=True)
    print(f"FINAL nodes={model.num_nodes} surfs={model.num_surfs} points={model.num_points}",
          file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
