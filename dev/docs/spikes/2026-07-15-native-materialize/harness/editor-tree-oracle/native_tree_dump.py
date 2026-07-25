#!/usr/bin/env python3
r"""NATIVE-TREE DUMP — the native counterpart of the editor-tree oracle.

Runs `uedctl_native.build_geometry_bspcsg` over the first N castle brushes (trunk order) with the
env-gated `UEDCTL_BSPCSG_TREE_DUMP` hook (bspcsg.rs `trace_node_add`) enabled, capturing every
INCREMENTAL world-BSP-tree node add on stderr:

    NADD phase={ADD|SUB|FWTB} node=<idx> parent=<i> place=<code> flags=<hex> ilink=<i> nv=<n> \
         N=<nx,ny,nz> B=<bx,by,bz>

`phase` distinguishes the emitter: `ADD`/`SUB` are the LOOP-2 `leaf_func` incremental adds (the
brush face descending the growing world tree); `FWTB` is the `FilterWorldThroughBrush` re-add of an
outside cut fragment.  This is the SAME node stream the editor-tree oracle captures at `bspAddNode`
(Editor 0x34e80) — minus the final `bspRepartition`/`SplitPolyList` rebuild, which native does not
run in the incremental phase and which the editor log carries under its own `ret` call-site.

Usage:
  native_tree_dump.py N [--out DIR]     # writes native-N.log (NADD lines only)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))


def _inputs_castle(n: int):
    """First N castle brushes in trunk order (no mover exclusion — the castle has none)."""
    from uedctl import trunk
    from uedctl.native import materialize as M
    import castle_build
    level, _ = trunk.read_level(Path(castle_build.TRUNK))
    brush_names = [nm for nm in level.order if level.actors[nm].brush is not None][:n]
    return [M._build_brush_input(nm, level.actors[nm]) for nm in brush_names]


def _inputs_unatco(n: int):
    """First N UNATCO brushes in trunk order, then DROP the movers — mirrors
    `unatco_subset.native_surfs` / `materialize._in_world_csg` (movers are never CSG'd into the
    world, and the editor golden excludes them), so the native ADD stream matches the golden's."""
    from spike_classindex import class_index   # the schema-aware mover gate's ClassIndex
    from uedctl import trunk
    from uedctl.native import materialize as M
    import unatco_subset as U
    level, _ = trunk.read_level(U.FULL_TRUNK)
    brush_order = [nm for nm in level.order if level.actors[nm].brush is not None][:n]
    brush_names = [nm for nm in brush_order if M._in_world_csg(level.actors[nm], class_index())]
    return [M._build_brush_input(nm, level.actors[nm]) for nm in brush_names]


_INPUTS = {"castle": _inputs_castle, "unatco": _inputs_unatco}


def run(n: int, out_dir: Path, target: str = "castle") -> Path:
    """Build the N-brush native subset with the trace hook on, capturing NADD lines from stderr.

    The hook writes to the process's real fd 2; to capture it we redirect fd 2 to a temp file around
    the (native, GIL-releasing) build call, then read it back and keep only NADD lines."""
    out_dir.mkdir(parents=True, exist_ok=True)
    import uedctl_native

    if target not in _INPUTS:
        raise SystemExit(f"unknown --target {target!r} (choose from {sorted(_INPUTS)})")
    inputs = _INPUTS[target](n)

    raw = out_dir / f"native-{n}.raw"
    saved = os.dup(2)
    fd = os.open(str(raw), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.environ["UEDCTL_BSPCSG_TREE_DUMP"] = "1"
    try:
        os.dup2(fd, 2)
        uedctl_native.build_geometry_bspcsg(inputs)
    finally:
        os.dup2(saved, 2)
        os.close(fd)
        os.close(saved)

    lines = [ln for ln in raw.read_text(errors="replace").splitlines() if ln.startswith("NADD ")]
    out = out_dir / f"native-{n}.log"
    out.write_text("\n".join(lines) + ("\n" if lines else ""))
    raw.unlink(missing_ok=True)
    print(f"[native] N={n}: {len(lines)} NADD lines -> {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("n", type=int, help="subset size (number of brushes, trunk order)")
    ap.add_argument("--target", default="castle", choices=sorted(_INPUTS),
                    help="brush source: castle (default) or unatco (movers excluded, world CSG only)")
    ap.add_argument("--out", type=Path, default=HERE / "logs", help="output dir for native-N.log")
    args = ap.parse_args()
    run(args.n, args.out, target=args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
