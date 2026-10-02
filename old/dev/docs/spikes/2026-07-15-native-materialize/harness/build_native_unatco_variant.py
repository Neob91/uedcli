#!/usr/bin/env python3
"""Build a VARIANT of NativeUnatco for load-hang bisection (spike section 88).

Same as build_native_unatco.py but supports isolating structural suspects so we can tell a
GEOMETRY load-hang from the DeusExMover class-import fault:

  --strip-movers   drop the 28 DeusExMover actors from the trunk before materialize.  This removes
                   BOTH the bad `Engine.DeusExMover` class import (see §88) AND the mover brush
                   models, leaving a pure world-BSP build.  If THIS loads, the world geometry is
                   fine and the blocker is the mover import; if it still hangs, a geometry loop
                   remains.

Writes to a distinct --out (default DX/Maps/NativeUnatcoNoMov.dx).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))

from spike_classindex import class_index  # noqa: E402  (schema-aware mover gate's index)
from uedcli import trunk  # noqa: E402
from uedcli.native import materialize as M  # noqa: E402

DEFAULT_TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/unatco/uedcli/maps/unatco"
PKG_DIRS = [
    "/home/neob91/Games/LutrisDX/drive_c/DX/Textures",
    "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeUnatcoNoMov.dx")
    ap.add_argument("--trunk", default=DEFAULT_TRUNK)
    ap.add_argument("--strip-movers", action="store_true")
    ap.add_argument("--lit", action="store_true")
    args = ap.parse_args()

    lvl, _ = trunk.read_level(Path(args.trunk))
    if args.strip_movers:
        before = len(lvl.actors)
        lvl.actors = {n: a for n, a in lvl.actors.items() if a.cls != "DeusExMover"}
        if hasattr(lvl, "order"):
            lvl.order = [n for n in lvl.order if n in lvl.actors]
        print(f"stripped movers: {before} -> {len(lvl.actors)} actors")
    else:
        print(f"trunk: {len(lvl.actors)} actors")
    warnings = M.run_materialize_native(
        class_index=class_index(),
        level=lvl, out_path=args.out, overwrite=True, version=68,
        no_light=not args.lit, pkg_dirs=PKG_DIRS)
    print(f"WROTE {args.out} ({Path(args.out).stat().st_size} bytes), {len(warnings)} warnings")


if __name__ == "__main__":
    main()
