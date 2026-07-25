#!/usr/bin/env python3
"""Build NativeUnatco with CORRECT class->package imports, to see if a geometry load-hang lurks
BEHIND the class-import fault (spike section 88).

The native build imports every bare class under `Engine` (pkgref `_package_of_class` falls back to
"Engine" because `uprops.package_of_class` does not exist), so the game aborts loading on the first
non-Engine class (`Engine.DeusExMover`, then `Engine.ATM`, ...).  This harness derives the TRUE
package of every class from the shipped golden `03_NYC_UNATCOHQ.dx` import table and RUNTIME-patches
`uedctl.uprops.package_of_class` with that map (no production file is edited) so every class resolves
to its real `Package.Class`.  If the resulting map LOADS, the whole load blocker is import
resolution; if it still spins CPU-bound, a real geometry loop remains.
"""
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))

from spike_classindex import class_index  # noqa: E402  (schema-aware mover gate's index)
from uedctl import trunk, uprops  # noqa: E402
from uedctl.native import materialize as M  # noqa: E402
from uedctl.native.pkg_write import parse_package  # noqa: E402

DEFAULT_TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/unatco/uedctl/maps/unatco"
GOLDEN = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/03_NYC_UNATCOHQ.dx"
OUT = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeUnatcoQual.dx"
PKG_DIRS = [
    "/home/neob91/Games/LutrisDX/drive_c/DX/Textures",
    "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures",
]


def class_package_map(golden):
    """classname -> defining package chain, read from the golden's import table.
    A `Class` import's outer chain (Package imports) IS the class's package."""
    pkg = parse_package(Path(golden).read_bytes())
    nm = pkg.names
    imps = pkg.imports  # tuples (class_pkg, class_name, package_index(objref), object_name)

    def outer_chain(objref):
        parts = []
        while objref < 0:
            cp, cn, pi, on = imps[-objref - 1]
            parts.append(nm[on])
            objref = pi
        return list(reversed(parts))

    out = {}
    for (cp, cn, pi, on) in imps:
        if nm[cn] == "Class":
            chain = outer_chain(pi)          # the package chain the class lives in
            if chain:
                out[nm[on]] = ".".join(chain)
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--strip-nonengine", action="store_true",
                    help="drop every actor whose class lives in a non-Engine package (DeusEx "
                         "furniture/NPCs/movers) — keeps world brushes + Engine-class actors "
                         "(PlayerStart/PathNode/Light/ZoneInfo). Isolates whether the load hang is "
                         "the world BSP or the DeusEx decoration/mesh actors.")
    args = ap.parse_args()

    cmap = class_package_map(GOLDEN)
    print(f"class->package map from golden: {len(cmap)} classes "
          f"(e.g. DeusExMover={cmap.get('DeusExMover')}, ATM={cmap.get('ATM')})")
    # RUNTIME patch (harness-only): give pkgref._package_of_class a real class->package source.
    uprops.package_of_class = lambda c: cmap.get(c)

    lvl, _ = trunk.read_level(Path(DEFAULT_TRUNK))
    if args.strip_nonengine:
        before = len(lvl.actors)
        def is_engine(a):
            pkg = cmap.get(a.cls)
            return a.brush is not None or pkg in (None, "Engine")
        lvl.actors = {n: a for n, a in lvl.actors.items() if is_engine(a)}
        if hasattr(lvl, "order"):
            lvl.order = [n for n in lvl.order if n in lvl.actors]
        print(f"stripped non-Engine actors: {before} -> {len(lvl.actors)}")
    print(f"trunk: {len(lvl.actors)} actors")
    warnings = M.run_materialize_native(
        class_index=class_index(),
        level=lvl, out_path=args.out, overwrite=True, version=68, no_light=True, pkg_dirs=PKG_DIRS)
    print(f"WROTE {args.out} ({Path(args.out).stat().st_size} bytes), {len(warnings)} warnings")
    # verify the fix took
    p = parse_package(Path(args.out).read_bytes())
    nm = p.names
    for (cp, cn, pi, on) in p.imports:
        if nm[cn] == "Class" and nm[on] in ("DeusExMover", "ATM"):
            # decode outer package
            r = pi; chain = []
            while r < 0:
                icp, icn, ipi, ion = p.imports[-r - 1]
                chain.append(nm[ion]); r = ipi
            print(f"  import {nm[on]}: outer={'.'.join(reversed(chain))}")


if __name__ == "__main__":
    main()
