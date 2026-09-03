"""`build_mover_shape_model` (the native `csgPrepMovingBrush`) must reproduce the editor's built
mover shape models BYTE-exactly. Fixtures are committed extracts from the UNATCO `MAP IMPORT`
golden (`uedcli-native/fixtures/mover/`, 2026-09-02): per mover a `.polys` blob (none_index,
Polys ref, the source brush polys, and the golden `Polys` body's saved per-poly iLink) and the
golden UModel `.body` bytes. The same fixtures pin the Rust core in `cargo test`
(`mover_model_fixtures_byte_exact`); this test covers the full Python path on top -- the
`umodel.write_model_body` serialization including the prefix bbox/sphere and the
RootOutside/Linked trailer."""
import struct
from pathlib import Path

import pytest

from uedcli.native.actor_write import FPoly
from uedcli.native import umodel as UM

pytest.importorskip("uedcli_native")

_FIXDIR = Path(__file__).parents[2] / "uedcli-native" / "fixtures" / "mover"
_NAMES = ["Model_DeusExMover0", "Model_DeusExMover5",
          "Model_DeusExMover21", "Model_DeusExMover22"]


def _decode_fixture(blob: bytes):
    """`(none_index, polys_ref, polys, saved_links)` -- format owned by
    `dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness/extract_mover_fixtures.py`."""
    none_index, polys_ref, n_polys = struct.unpack_from("<Iii", blob, 0)
    off = 12
    polys = []
    for _ in range(n_polys):
        nv = struct.unpack_from("<I", blob, off)[0]
        base, normal, tu, tv = (struct.unpack_from("<3f", blob, off + 4 + 12 * k)
                                for k in range(4))
        off += 52
        verts = []
        for _ in range(nv):
            verts.append(struct.unpack_from("<3f", blob, off))
            off += 12
        flags, tex, pan_u, pan_v = struct.unpack_from("<iiii", blob, off)
        off += 16
        polys.append(FPoly(verts=verts, base=base, normal=normal, texture_u=tu, texture_v=tv,
                           poly_flags=flags, texture_ref=tex, pan_u=pan_u, pan_v=pan_v))
    saved_links = list(struct.unpack_from(f"<{n_polys}i", blob, off))
    off += 4 * n_polys
    assert off == len(blob), "fixture blob not fully consumed"
    return none_index, polys_ref, polys, saved_links


@pytest.mark.parametrize("name", _NAMES)
def test_mover_shape_model_byte_exact(name):
    from uedcli.native.unbuilt import build_mover_shape_model
    none_index, polys_ref, polys, saved_links = _decode_fixture(
        (_FIXDIR / f"{name}.polys").read_bytes())
    want = (_FIXDIR / f"{name}.body").read_bytes()
    model, links = build_mover_shape_model(polys)
    model.none_index = none_index
    model.field_0x54 = polys_ref
    got = UM.write_model_body(model)
    assert links == saved_links, f"{name}: saved Polys iLink diverges"
    assert got == want, (f"{name}: body diverges (len {len(got)} vs {len(want)}, first at "
                         f"{next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), None)})")
