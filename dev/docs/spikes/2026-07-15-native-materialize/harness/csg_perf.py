#!/usr/bin/env python3
"""Native CSG-core perf + byte-identity harness.

Two jobs (see `dev/docs/architecture.md` "Native CSG build performance"):

  time   — time `uedctl_native.build_geometry` over UNATCO brush-count subsets, isolating the
           pure Rust CSG/BSP core (no lighting, no package assembly).  Confirms where the cost
           lives (the per-brush classify-BSP rebuild in `build::build_bsp`, NOT `point_in_solid`).

  hash   — serialize the built Model and print its sha256 + node/surf/vert counts for the castle
           and UNATCO subsets.  Byte-identity gate for a behavior-preserving CSG optimization:
           stash the change, rebuild, run `hash`, compare — every sha must be UNCHANGED.

Usage:
  python csg_perf.py time [N ...]     # default subsets 60 150 300 (762 = full UNATCO)
  python csg_perf.py hash             # castle + unatco150 + unatco300 model hashes
"""
import hashlib
import sys
import time
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))

from uedctl import trunk  # noqa: E402
from uedctl.native import materialize as M  # noqa: E402
import uedctl_native  # noqa: E402

CASTLE = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedctl/maps/foobar"
UNATCO = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/unatco/uedctl/maps/unatco"


def _brushes(trunk_path, n=None):
    lvl, _ = trunk.read_level(Path(trunk_path))
    order = [x for x in lvl.order if lvl.actors[x].brush is not None]
    if n is not None:
        order = order[:n]
    return [M._build_brush_input(x, lvl.actors[x]) for x in order]


def cmd_time(counts):
    for n in counts:
        bs = _brushes(UNATCO, n)
        t0 = time.time()
        built = uedctl_native.build_geometry(bs)
        dt = time.time() - t0
        print(f"N={n:4d}  build={dt:8.2f}s  nodes={built.num_nodes} "
              f"surfs={built.num_surfs} verts={built.num_verts}")


def cmd_hash():
    for label, path, n in [("castle", CASTLE, None), ("unatco150", UNATCO, 150),
                           ("unatco300", UNATCO, 300)]:
        bs = _brushes(path, n)
        built = uedctl_native.build_geometry(bs)
        body = uedctl_native.serialize_model(built)
        h = hashlib.sha256(body).hexdigest()[:16]
        print(f"{label:<12} brushes={len(bs):4d} nodes={built.num_nodes} "
              f"surfs={built.num_surfs} verts={built.num_verts} bytes={len(body)} sha={h}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "time"
    if mode == "hash":
        cmd_hash()
    else:
        counts = [int(x) for x in sys.argv[2:]] or [60, 150, 300]
        cmd_time(counts)


if __name__ == "__main__":
    main()
