#!/usr/bin/env python3
"""Build NativeCastle.dx from the castle trunk via the native (editor-free) materialize path.

The castle trunk (`_scratch/castle/uedcli/maps/foobar`, 95 brushes / 62 lights / 1 ZoneInfo /
1 SkyZoneInfo / 1 PlayerStart) is the full-parity target: the SAME geometry the editor built as
`DX/Maps/Test_Castle.dx`.  This is the reproducible acceptance-gate build (was an ad-hoc scratch
script before).

Usage:
  python build_native_castle.py [out.dx] [--trunk DIR] [--unlit]

Emits the package, prints warnings + a zone/leaf/node summary of the built Model, and (unless the
out path is given) writes to DX/Maps/NativeCastle.dx so `uplayctl session start --map NativeCastle`
picks it up.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

from spike_classindex import class_index  # noqa: E402  (schema-aware mover gate's index)
from uedcli import trunk  # noqa: E402
from uedcli.native import materialize as M  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
from uedcli.native.pkg_write import parse_package  # noqa: E402

DEFAULT_TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedcli/maps/foobar"
DEFAULT_OUT = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCastle.dx"
# The project package dirs so LUM_* + Core texture GROUPS resolve (else "Can't find Texture").
PKG_DIRS = [
    "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures",
    "/home/neob91/Games/LutrisDX/drive_c/DX/Textures",
]


def summarize(out):
    pkg = parse_package(Path(out).read_bytes())
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    m = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])
    from collections import Counter
    lz = Counter(l.i_zone for l in m.leaves)
    nz = Counter(tuple(n.i_zone) for n in m.nodes)
    nf = Counter(n.node_flags for n in m.nodes)
    print(f"  nodes={len(m.nodes)} surfs={len(m.surfs)} verts={len(m.verts)} "
          f"leaves={len(m.leaves)} zones={len(m.zones)} shared_sides={m.num_shared_sides}")
    print(f"  leaf iZone histogram: {dict(sorted(lz.items()))}")
    print(f"  node iZone pairs: {dict(sorted(nz.items()))}")
    print(f"  node_flags: {dict(sorted(nf.items()))}")
    for zi, z in enumerate(m.zones):
        an = pkg.name_of_ref(z.actor_ref) if z.actor_ref else None
        print(f"  zone[{zi}] actor_ref={z.actor_ref} name={an} "
              f"conn={z.connectivity:#x} vis={z.visibility:#x}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default=DEFAULT_OUT)
    ap.add_argument("--trunk", default=DEFAULT_TRUNK)
    ap.add_argument("--unlit", action="store_true")
    args = ap.parse_args()

    lvl, _ = trunk.read_level(Path(args.trunk))
    print(f"trunk: {len(lvl.actors)} actors")
    warnings = M.run_materialize_native(
        class_index=class_index(),
        level=lvl, out_path=args.out, overwrite=True, version=68,
        no_light=args.unlit, pkg_dirs=PKG_DIRS)
    print(f"WROTE {args.out} ({Path(args.out).stat().st_size} bytes)")
    for w in warnings:
        print("  WARN:", w)
    summarize(args.out)


if __name__ == "__main__":
    main()
