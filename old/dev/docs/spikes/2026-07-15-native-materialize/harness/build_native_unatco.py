#!/usr/bin/env python3
"""Build NativeUnatco.dx from the UNATCO-HQ trunk via the native (editor-free) materialize path.

This is the OCCASIONAL cross-check of the castle-tuned native core against a REAL, much larger
shipped level.  All byte-parity tuning so far rides on the 95-brush `Test_Castle.dx`; this harness
materializes the retail **03_NYC_UNATCOHQ** trunk (762 brush-bearing actors — 734 Brush + 28
DeusExMover — / 1437 actors total) so we can watch whether the deterministic GEOMETRY dimensions
(nodes / verts / points / surfs / bounds / leafhulls) generalize past the castle.

Trunk↔golden identity was pinned by Brush-class export count: the trunk has 734 Brush actors, which
matches ONLY `03_NYC_UNATCOHQ.dx` (734); 01=721, 04=735, 05=730.  Model count 763 = 762
brush-bearing actors + 1 level model.

Writes to a DISTINCT output (`DX/Maps/NativeUnatco.dx`) so it never collides with the castle's
`NativeCastle.dx`.  Builds UNLIT by default: the LIT lightmap bake OOMs at UNATCO scale
(board/inbox note 2026-07-17); geometry generalization is the question here, and geometry is
lighting-independent.  Sibling of `build_native_castle.py`.

Usage:
  python build_native_unatco.py [out.dx] [--trunk DIR] [--lit]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))

from spike_classindex import class_index  # noqa: E402  (schema-aware mover gate's index)
from uedcli import trunk  # noqa: E402
from uedcli.native import materialize as M  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
from uedcli.native.pkg_write import parse_package  # noqa: E402

DEFAULT_TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/unatco/uedcli/maps/unatco"
DEFAULT_OUT = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeUnatco.dx"
# The game texture dirs so UNATCO.utx / CoreTex* GROUPS resolve (else "Can't find Texture").
PKG_DIRS = [
    "/home/neob91/Games/LutrisDX/drive_c/DX/Textures",
    "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures",
]


def summarize(out):
    pkg = parse_package(Path(out).read_bytes())
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    m = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])
    from collections import Counter
    lz = Counter(l.i_zone for l in m.leaves)
    print(f"  nodes={len(m.nodes)} surfs={len(m.surfs)} verts={len(m.verts)} "
          f"points={len(m.points)} vectors={len(m.vectors)} leaves={len(m.leaves)} "
          f"zones={len(m.zones)} shared_sides={m.num_shared_sides}")
    print(f"  leaf iZone histogram (top): {dict(sorted(lz.items())[:12])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default=DEFAULT_OUT)
    ap.add_argument("--trunk", default=DEFAULT_TRUNK)
    ap.add_argument("--lit", action="store_true",
                    help="run the LIT lightmap bake (WARNING: OOMs at UNATCO scale — default UNLIT)")
    args = ap.parse_args()

    lvl, _ = trunk.read_level(Path(args.trunk))
    print(f"trunk: {len(lvl.actors)} actors")
    warnings = M.run_materialize_native(
        class_index=class_index(),
        level=lvl, out_path=args.out, overwrite=True, version=68,
        no_light=not args.lit, pkg_dirs=PKG_DIRS)
    print(f"WROTE {args.out} ({Path(args.out).stat().st_size} bytes)")
    for w in warnings[:40]:
        print("  WARN:", w)
    if len(warnings) > 40:
        print(f"  ... +{len(warnings) - 40} more warnings")
    summarize(args.out)


if __name__ == "__main__":
    main()
