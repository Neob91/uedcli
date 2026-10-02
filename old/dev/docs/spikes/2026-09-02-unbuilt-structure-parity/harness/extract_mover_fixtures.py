#!/usr/bin/env python3
"""Extract every built mover shape model from a MAP IMPORT golden into fixture pairs for the
mover-build byte tests (`uedcli-native/fixtures/mover/`, `cargo test mover_`, and
`uedcli/tests/test_mover_shape_model.py`).

Per mover: `<name>.polys` — u32 none_index, i32 polys_ref, u32 n_polys; per poly u32 nv,
f32 base[3] normal[3] tu[3] tv[3] verts[nv*3], i32 poly_flags, i32 texture_ref, i32 pan_u,
i32 pan_v; then n_polys * i32 saved iLink (the golden `Polys` body's csgPrepMovingBrush-assigned
links) — and `<name>.body`, the golden UModel body bytes.

Usage: extract_mover_fixtures.py <golden.dx> <out_dir> [<export-name-prefix>]
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from uedcli.mapimport import decode_upolys                      # noqa: E402
from uedcli.native.umodel import parse_model_body               # noqa: E402
from uedcli.upackage import load_package, read_compact_index    # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    golden, out = sys.argv[1], Path(sys.argv[2])
    prefix = sys.argv[3] if len(sys.argv) > 3 else "Model_DeusExMover"
    out.mkdir(parents=True, exist_ok=True)
    pkg = load_package(golden)
    count = 0
    for e in pkg.exports:
        name = pkg.names[e["nm"]]
        if not name.startswith(prefix):
            continue
        body = pkg.buf[e["soff"]:e["soff"] + e["ssize"]]
        m = parse_model_body(pkg.buf, e["soff"], e["ssize"])
        none_index, _ = read_compact_index(body, 0)
        polys = decode_upolys(pkg, m.field_0x54 - 1)
        blob = bytearray(struct.pack("<Iii", none_index, m.field_0x54, len(polys)))
        for p in polys:
            blob += struct.pack("<I", len(p.verts))
            for tri in (p.base, p.normal, p.texture_u, p.texture_v):
                blob += struct.pack("<3f", *tri)
            for v in p.verts:
                blob += struct.pack("<3f", *v)
            blob += struct.pack("<iiii", p.poly_flags, p.texture_ref, p.pan_u, p.pan_v)
        for p in polys:
            blob += struct.pack("<i", p.i_link)
        (out / f"{name}.polys").write_bytes(blob)
        (out / f"{name}.body").write_bytes(body)
        count += 1
    print(f"wrote {count} fixture pairs to {out}")
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main())
