"""`brush_of`/`native.umodel.parse_model_body` on an original (1998/Gold) Unreal map (package
version <= 61) — pins the findings of spike `2026-09-11-unreal-gold-v61-model-format`.

Two real format differences from the DX/UT99/UnrealGold-later ("ver > 61") layout the rest of
`umodel.py` targets, both confirmed against the real v61 engine source (`fgsfdsfgs/UE1`,
`Engine/Inc/UnObj.h` + `Engine/Src/UnModel.cpp`; that repo's own `PACKAGE_FILE_VERSION` is 61):

1. `FSphere::operator<<` drops its `W` float entirely at `Ar.Ver()<=61` (a real engine bug, fixed
   only after v61) — the `UPrimitive` prefix is 38 bytes there, not 42.
2. `Vectors`/`Points`/`Nodes`/`Surfs`/`Verts`/`Polys` are each a SEPARATE `UDatabase`-subclass
   export, referenced from the `UModel` body by object ref — not inline `TArray`s. `brush_of` only
   needs the `Polys` ref (a brush's authored polygon list); the other five are recorded but never
   recursively decoded.

The load-bearing oracle, as everywhere else in this decoder, is consume-to-exact-end: a `UModel`
body occupies exactly `[soff, soff+ssize)` (minus any `StateFrame`), so a parse that lands exactly
on the final byte is structurally correct.

Real retail (1998/Gold) Unreal `.unr` maps are used directly (not synthesized), mirroring
`test_mesh_decode.py`'s `test_unrealgold_lodmesh_*` tests for the sibling mesh-format gap — this
project's convention already treats original-Unreal retail content as test-fixture-eligible,
unlike Deus Ex's (`test_mapimport_geometry.py`'s docstring). Gitignored/user-supplied
(`dev/scripts/install-unreal-assets.sh`); every test skips cleanly when absent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from uedcli.mapimport import (
    SchemaError,
    _skip_state_frame,
    brush_of,
    decode_upolys,
)
from uedcli.native.umodel import parse_model_body
from uedcli.upackage import PT_OBJECT, load_package, read_compact_index, read_property_tags

from .conftest import unreal_maps_root


def _pkg_or_skip(path: Path):
    if not path.exists():
        pytest.skip(f"{path} not present")
    return load_package(str(path))


def _brush_refs(pkg) -> dict[str, int]:
    """`{brush actor name: its Brush=Model'…' ref}` for every `Engine.Brush` actor in `pkg`."""
    out: dict[str, int] = {}
    for i, e in enumerate(pkg.exports):
        if pkg.object_path(e["cls"]) != "Engine.Brush":
            continue
        start = _skip_state_frame(pkg, e)
        tags, _pos = read_property_tags(pkg, start, e["soff"] + e["ssize"])
        for tag in tags:
            if tag.name == "Brush" and tag.ptype == PT_OBJECT:
                ref, _ = read_compact_index(tag.raw, 0)
                out[pkg.names[e["nm"]]] = ref
    return out


def test_v61_prefix_is_38_bytes_not_42():
    """`_parse_prefix(version=61)` consumes exactly 38 bytes (FBox 25 + FVector 12 + ci(None) 1),
    not the 42-byte ver>61 prefix (FBox 25 + FSphere 16 + ci(None) 1) — a synthetic, version-free
    check of the one byte-width fact this fix turns on, independent of the real-map fixture."""
    from uedcli.native.umodel import _parse_prefix
    from uedcli.native.codec import write_ci

    body = write_ci(0) + b"\x00" * 24 + b"\x01" + b"\x00" * 12 + b"TAIL"
    *_rest, pos = _parse_prefix(body, version=61)
    assert pos == 38
    assert body[pos:pos + 4] == b"TAIL"

    body69 = write_ci(0) + b"\x00" * 24 + b"\x01" + b"\x00" * 16 + b"TAIL"
    *_rest, pos69 = _parse_prefix(body69, version=69)
    assert pos69 == 42
    assert body69[pos69:pos69 + 4] == b"TAIL"


def test_unrealgold_brush_decodes_via_object_ref():
    """`DmDeck16.unr` (package v60 — the same `<=61` engine-source boundary covers it, not just
    v61 exactly) — a real brush's authored `PolyList`, pinned exactly. Before this fix, every one
    of these raised `SchemaError: brush_of: truncated map body` (the ver>61 inline-array layout
    read garbage past the 4-byte-short prefix)."""
    pkg = _pkg_or_skip(unreal_maps_root() / "DmDeck16.unr")
    assert pkg.version <= 61
    refs = _brush_refs(pkg)
    assert refs["Brush40"] == 1332

    b = brush_of(pkg, refs["Brush40"])
    assert b.model_name == "Model40"
    assert len(b.polys) == 28


def test_unrealgold_every_brush_in_a_map_decodes():
    """Exhaustive within one small real map: every `Engine.Brush` actor's private model resolves
    its `Polys` ref and decodes to EOF via the unmodified, production `decode_upolys` — the same
    function the ver>61 path already used, proving `FPoly`'s own on-disk layout needs no v61
    branch, only the surrounding `UModel` layout that locates it."""
    pkg = _pkg_or_skip(unreal_maps_root() / "DmDeck16.unr")
    refs = _brush_refs(pkg)
    assert len(refs) > 100          # a real level, not an near-empty fixture
    fails = []
    for name, ref in refs.items():
        try:
            brush_of(pkg, ref)
        except SchemaError as ex:
            fails.append((name, str(ex)))
    assert not fails, f"{len(fails)} brush(es) failed to decode: {fails[:5]}"


def test_unrealgold_polys_ref_resolves_to_a_upolys_export():
    """The `Polys` ref `brush_of` reads out of the v61 top-level object-ref layout names a REAL
    `UPolys` export — not a coincidentally-plausible number from a still-misaligned parse. Cross-
    checked independently of `brush_of` by decoding the same export directly."""
    pkg = _pkg_or_skip(unreal_maps_root() / "DmDeck16.unr")
    refs = _brush_refs(pkg)
    brush_ref = refs["Brush40"]
    me = pkg.exports[brush_ref - 1]
    mstart = _skip_state_frame(pkg, me)
    m = parse_model_body(pkg.buf, mstart, me["soff"] + me["ssize"] - mstart, version=pkg.version)
    assert m.field_0x54 > 0
    polys_export = pkg.exports[m.field_0x54 - 1]
    assert pkg.object_path(polys_export["cls"]) == "Engine.Polys"
    polys = decode_upolys(pkg, m.field_0x54 - 1)
    assert len(polys) == 28
