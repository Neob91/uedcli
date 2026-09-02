#!/usr/bin/env python3
"""Bit-for-bit compare of Brush562's OWN surf plane floats (native `build_geometry_bspcsg` output
vs the real self-built golden's raw `BspSurf`/`Points` bytes) -- the vertex/normal-level half of the
`brush562_bitcheck.py` matrix check, closing the loop the task asked for: does the 2-ULP rotation-
matrix divergence found there (`R[0][1]` differs by 2 ULP between native's double-precision compose
and a simulated editor float32 FCoords compose) actually propagate into a different transformed
vertex or plane once the matrix is applied to Brush562's real local-space poly coordinates?

Usage: .venv/bin/python brush562_vertex_compare.py
"""
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

CACHE = ROOT / "_scratch/uedcli-parity-cache/3c2fa42895d171d2453f62a38ade7e6be33247f29def5fa335bd2e70e9d1c953"
TRUNK = CACHE / "trunk/maps/03_nyc_747"
GOLDEN = Path("/tmp/uedcli-parity-cache/3c2fa42895d171d2453f62a38ade7e6be33247f29def5fa335bd2e70e9d1c953/golden.dx")
os.environ.setdefault("UEDCLI_PROJECT", str(CACHE / "trunk"))

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return pkg, m


def f32_bits(x: float) -> int:
    return struct.unpack("I", struct.pack("f", x))[0]


def main():
    level, _ranks = trunk.read_level(TRUNK)
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    b562_idx = names.index("Brush562")
    print(f"Brush562 world-csg index: {b562_idx}")

    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))

    epkg, em = parse_golden(GOLDEN)

    # `plane` lives on the NODE, not the surf; a surf owns Points[p_base] (the transformed FPoly
    # Base) and Vectors[v_normal] (the transformed FPoly Normal). Gather every node whose surf is
    # owned by Brush562, on both sides.
    n_nodes = [nd for nd in nm.nodes if 0 <= nd.i_surf < len(nm.surfs)
               and nm.surfs[nd.i_surf].i_actor == b562_idx]
    e_nodes = [nd for nd in em.nodes if 0 <= nd.i_surf < len(em.surfs)
               and epkg.name_of_ref(em.surfs[nd.i_surf].i_actor) == "Brush562"]
    print(f"native nodes owned by Brush562: {len(n_nodes)}")
    print(f"editor nodes owned by Brush562: {len(e_nodes)}")

    n_surf_planes = [(nd.i_surf, nd.plane) for nd in n_nodes]
    e_surf_planes = [(nd.i_surf, nd.plane) for nd in e_nodes]

    print("\n--- native Brush562 node planes ---")
    for isurf, plane in n_surf_planes:
        bits = tuple(f32_bits(v) for v in plane)
        print(f"  i_surf={isurf} plane={plane} bits={[hex(b) for b in bits]}")

    print("\n--- editor (golden) Brush562 node planes ---")
    for isurf, plane in e_surf_planes:
        bits = tuple(f32_bits(v) for v in plane)
        print(f"  i_surf={isurf} plane={plane} bits={[hex(b) for b in bits]}")

    # Pair by plane proximity (nearest-plane match) since surf/node ORDER need not agree even when
    # the SET of planes does -- a naive index zip would misreport a reordering as a value mismatch.
    print("\n--- nearest-plane pairing + bit compare ---")
    unmatched_e = list(range(len(e_surf_planes)))
    any_diff = False
    for isurf, plane in n_surf_planes:
        best = None
        best_d = None
        for k, ei in enumerate(unmatched_e):
            _, eplane = e_surf_planes[ei]
            d = sum((a - b) ** 2 for a, b in zip(plane, eplane)) ** 0.5
            if best_d is None or d < best_d:
                best_d, best = d, k
        if best is None:
            print(f"  native i_surf={isurf}: NO editor node left to pair")
            continue
        ei = unmatched_e.pop(best)
        _, eplane = e_surf_planes[ei]
        exact = plane == eplane
        any_diff = any_diff or not exact
        print(f"  native i_surf={isurf} <-> editor i_surf={e_surf_planes[ei][0]}  "
              f"dist={best_d:.6g}  BIT-EXACT={exact}")
        if not exact:
            for c, (a, b) in enumerate(zip(plane, eplane)):
                if a != b:
                    print(f"      component[{c}]: native={a!r} (0x{f32_bits(a):08x})  "
                          f"editor={b!r} (0x{f32_bits(b):08x})  "
                          f"delta_bits={f32_bits(a) - f32_bits(b):+d}")

    print(f"\nany plane differs at all (after nearest-neighbour pairing): {any_diff}")


if __name__ == "__main__":
    raise SystemExit(main())
