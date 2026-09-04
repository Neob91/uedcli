"""UED22 MAP-SAVE serialization facts, pinned against the 2026-09-02 unbuilt-parity goldens
(`dev/docs/spikes/2026-09-02-unbuilt-structure-parity/`). Each fact was byte-measured off a real
editor save; these tests keep the writer from drifting off them. Install-free (engine-only probe).
"""
from __future__ import annotations

import struct

from uedcli import model
from uedcli.native import actor_write as AW
from uedcli.native.actor_write import Prop
from uedcli.native.pkg_write import parse_package
from uedcli.native.unbuilt import _calc_normal, assemble_unbuilt
from uedcli.normalize import level_order, normalize_level

_POLY = ("         Begin Polygon\n"
         "            Origin   +0.0,+0.0,+0.0\n"
         "            Normal   +0.0,+0.0,+1.0\n"
         "            TextureU +1.0,+0.0,+0.0\n"
         "            TextureV +0.0,+1.0,+0.0\n"
         "            Vertex   +0.0,+0.0,+0.0\n"
         "            Vertex   +128.0,+0.0,+0.0\n"
         "            Vertex   +128.0,+128.0,+0.0\n"
         "            Vertex   +0.0,+128.0,+0.0\n"
         "         End Polygon\n")


def _brush(name: str) -> str:
    return (f"Begin Actor Class=Engine.Brush Name={name}\n    CsgOper=CSG_Subtract\n"
            f"    Begin Brush Name=Model_{name}\n       Begin PolyList\n{_POLY}"
            f"       End PolyList\n    End Brush\n"
            f"    Brush=Model'MyLevel.Model_{name}'\n    Name=\"{name}\"\nEnd Actor\n")


def _point(cls: str, name: str) -> str:
    return (f"Begin Actor Class={cls} Name={name}\n"
            f"    Location=(X=1.0,Y=2.0,Z=3.0)\n    Name=\"{name}\"\nEnd Actor\n")


def _tiny_level(n_points: int = 3, n_brushes: int = 2) -> model.Level:
    t3d = ("Begin Map\n"
           "Begin Actor Class=Engine.LevelInfo Name=LevelInfo0\n    Name=\"LevelInfo0\"\nEnd Actor\n"
           + "".join(_point("Engine.Light", f"L{i}") for i in range(n_points))
           + "".join(_brush(f"B{i}") for i in range(n_brushes))
           + "End Map\n")
    lv = model.parse_t3d(t3d)
    lv.order = level_order(lv)
    normalize_level(lv)
    return lv


def _built(n_points=3, n_brushes=2):
    dx, _w = assemble_unbuilt(_tiny_level(n_points, n_brushes), schema=None, pkg_dirs=None)
    return parse_package(dx)


def test_bool_tag_is_size_code_5_with_zero_size_byte():
    names = {"bAdmin": 7, "None": 0}
    body = AW.write_prop(lambda s: names[s], Prop("bAdmin", AW.PT_BOOL, True))
    assert body[-2:] == bytes([0xD3, 0x00])
    body = AW.write_prop(lambda s: names[s], Prop("bAdmin", AW.PT_BOOL, False))
    assert body[-2:] == bytes([0x53, 0x00])


def test_static_array_element_zero_is_a_plain_tag():
    names = {"Paths": 1}
    t0 = AW.write_prop(lambda s: names[s], Prop("Paths", AW.PT_INT, 5, array_index=0))
    t1 = AW.write_prop(lambda s: names[s], Prop("Paths", AW.PT_INT, 5, array_index=1))
    assert not (t0[1] & 0x80) and len(t0) == 6          # name ci + info + i32
    assert (t1[1] & 0x80) and t1[2] == 1 and len(t1) == 7


def test_twelve_byte_struct_uses_fixed_size_code_3():
    names = {"Location": 1, "Vector": 2}
    tag = AW.write_prop(lambda s: names[s],
                        Prop("Location", AW.PT_STRUCT, AW.struct_vector(1, 2, 3),
                             struct_name="Vector"))
    assert (tag[1] >> 4) & 0x07 == 3 and len(tag) == 15  # name·info·structname·12B value


def test_sphere_radius_single_rounding_matches_golden_brush74():
    # Brush74's local bbox is (-56,-2,-1)..(56,2,1); the UNATCO import golden stores W as
    # 0x42606717 -- sqrt in double * 1.001f, ONE final rounding (the twice-rounded chain
    # yields ...16).
    import math
    f32 = lambda x: struct.unpack("<f", struct.pack("<f", x))[0]  # noqa: E731
    r2 = f32(f32(f32(56.0 * 56.0) + f32(2.0 * 2.0)) + f32(1.0 * 1.0))
    w = f32(math.sqrt(r2) * f32(1.001))
    assert struct.unpack("<I", struct.pack("<f", w))[0] == 0x42606717


def test_calc_normal_recomputes_from_winding():
    assert _calc_normal([(0, 0, 0), (128, 0, 0), (128, 128, 0), (0, 128, 0)]) == (0.0, 0.0, 1.0)


def test_export_layout_and_actors_array_match_the_editor_closed_form():
    np_, nb = 3, 2
    p = _built(np_, nb)
    names = [p.names[e["nm"]] for e in p.exports]
    # ruled builder triple first, then preamble + midpoint hoist: R = (np + 3*nb - 1) // 2
    assert names[:8] == ["LevelInfo0", "Polys4", "Brush", "DefaultBrush",
                         "Polys3", "Camera6", "Camera7", "Model2"]
    assert names[-4:] == ["Camera8", "Camera9", "Camera10", "MyLevel"]
    stream = ["L0", "L1", "L2", "B0", "B1", "Model_B0", "Polys6", "Model_B1",
              "LevelSummary", "Polys8"]
    r = (np_ + 3 * nb - 1) // 2
    expect = [stream[r]] + [s if i != r else "Camera11" for i, s in enumerate(stream)]
    assert names[8:8 + len(expect)] == expect
    # Actors array: [LevelInfo, first brush, None] + points + [None] + rest + Camera6..11
    li = next(i for i, e in enumerate(p.exports) if p.names[e["nm"]] == "MyLevel")
    e = p.exports[li]
    pos = e["soff"]
    from uedcli.upackage import read_compact_index
    _, pos = read_compact_index(p.buf, pos)
    num = struct.unpack_from("<i", p.buf, pos)[0]; pos += 8
    refs = []
    for _ in range(num):
        r_, pos = read_compact_index(p.buf, pos)
        refs.append(p.name_of_ref(r_))
    # Actors[1] = the ALWAYS-synthesized builder brush (owner ruling 2026-09-03); no None holes
    assert refs == (["LevelInfo0", "DefaultBrush", "L0", "L1", "L2", "B0", "B1"]
                    + [f"Camera{i}" for i in range(6, 12)])


def test_name_flags_follow_reference_context():
    p = _built()
    buf, pos = p.buf, 36 + 16 + 4 + 8
    flags = {}
    from uedcli.upackage import read_compact_index
    for _ in range(len(p.names)):
        ln, pos = read_compact_index(buf, pos)
        nm = buf[pos:pos + ln - 1].decode("latin-1"); pos += ln
        flags[nm] = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    assert flags["RendMap"] == 0x40010                   # referenced only by edit-only Cameras
    assert flags["Level"] == 0x70010                     # referenced by load-all actors
    assert flags["None"] == 0x4070410                    # intrinsic engine name
    # in THIS level only edit-only bodies (cameras/brushes) reference Tag, so its load bits are
    # LoadForEdit alone -- the context union at work (UNATCO, with load-all actors, gives 0x4070010)
    assert flags["Tag"] == 0x4040010


def test_unlabeled_poly_item_is_the_none_name_index():
    p = _built()
    i = next(k for k, e in enumerate(p.exports) if p.names[e["nm"]] == "Polys6")
    e = p.exports[i]
    from uedcli.upackage import read_compact_index
    pos = e["soff"]
    _, pos = read_compact_index(p.buf, pos)              # UPolys prop-None
    n, _mx = struct.unpack_from("<ii", p.buf, pos); pos += 8
    assert n == 1
    # FPoly: ci(nverts) + base+normal+U+V (48B) + verts + i32 flags + ci actor + ci texture + item
    nv, pos = read_compact_index(p.buf, pos)
    pos += 48 + nv * 12 + 4
    _, pos = read_compact_index(p.buf, pos)
    _, pos = read_compact_index(p.buf, pos)
    item, _ = read_compact_index(p.buf, pos)
    assert p.names[item] == "None"


def test_msvc_qsort_matches_stdlib_and_is_deterministic():
    # The MAP-SAVE table sort is the MSVC CRT qsort port (saveorder.msvc_qsort); it must
    # order like a correct sort and be deterministic (same input -> same output).
    import random

    from uedcli.native.saveorder import msvc_qsort
    rng = random.Random(0)
    for _ in range(200):
        a = [rng.randrange(6) for _ in range(rng.randrange(40))]
        b = a[:]
        msvc_qsort(b, lambda x, y: x - y)
        assert b == sorted(a)
    a = [3, 1, 2, 1, 3, 2, 1]
    b, c = a[:], a[:]
    msvc_qsort(b, lambda x, y: y - x)
    msvc_qsort(c, lambda x, y: y - x)
    assert b == c and sorted(b, reverse=True) == b


def test_computed_tables_are_count_descending():
    # `compute_tables` (the no-oracle production path) must emit both tables in DESCENDING
    # reference-count order -- the reverse-engineered MAP-SAVE rule. Engine-only, install-free.
    from uedcli.native.saveorder import (collect, compute_tables, import_totals,
                                         map_name_sequence, _import_paths)
    from uedcli.native.unbuilt import _map_import_t3d, assemble_unbuilt
    lv = _tiny_level()
    dx, _w = assemble_unbuilt(lv, schema=None, pkg_dirs=None)
    pkg = parse_package(dx)
    ev = collect(pkg)
    spec = compute_tables(dx, [], map_name_sequence(dx, _map_import_t3d(lv)))
    assert set(spec.names) == set(pkg.names)

    name_counts = {pkg.names[i]: ev.names.get(i, 0) for i in range(len(pkg.names))}
    nc = [name_counts[n] for n in spec.names]
    assert all(nc[i] >= nc[i + 1] for i in range(len(nc) - 1))

    tot = import_totals(pkg, ev)
    path_count = {rec[0]: tot[j] for j, rec in enumerate(_import_paths(pkg))}

    def _path(j: int) -> str:
        parts, k = [], j
        while True:
            _cp, _cn, outer, on = spec.imports[k]
            parts.append(spec.names[on])
            if outer >= 0:
                break
            k = -outer - 1
        return ".".join(reversed(parts)).lower()

    ic = [path_count[_path(j)] for j in range(len(spec.imports))]
    assert all(ic[i] >= ic[i + 1] for i in range(len(ic) - 1))


def test_zoneinfo_serialization_order_comes_from_the_ued22_substrate():
    # The editor MAP SAVE writes each actor's tagged props in its UED22 class field order. The
    # game's own v68 Engine.u disagrees: `Engine.Actor.AmbientSound` ranks AFTER SoundVolume there,
    # but right after `Tag` (before Region/Location/SoundVolume) in UED22 -- the order the golden
    # carries (02_NYC_Bar ZoneInfo5). So the native rank MUST resolve against the UED22 substrate.
    from pathlib import Path

    from uedcli import tool_assets
    from uedcli.uprops.uclass import class_serialization_order

    ued22 = tool_assets.uned_dir() / "UED22"
    paths = {f.stem.casefold(): str(f) for f in ued22.glob("*.u")}
    rank = class_serialization_order("Engine.ZoneInfo",
                                     resolver=lambda p: paths.get(p.casefold()))
    r = lambda n: rank[n.casefold()]
    assert r("Tag") < r("AmbientSound") < r("Region") < r("Location") < r("SoundVolume")
