"""Offline tests for the native (editor-free) materialize glue.

Covers the M0 end-to-end proof (a carved-room `.dx` that passes the always-on self-check
and re-parses cleanly), the codec/serializer round-trips, and the self-check's rejection
of malformed packages.  Pure-Python — no Rust extension, no editor, no external maps.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from uedctl.native import codec, umodel, materialize, assemble
from uedctl.native.actor_write import Prop, PT_STRUCT, struct_vector
from uedctl.native.materialize import BuildError, self_check, build_carved_box_package
from uedctl.native.pkg_write import parse_package

from uedctl.tests.conftest import StubClassIndex

IDX = StubClassIndex()          # the offline class resolver `movers.is_mover` needs


def test_compact_index_roundtrip():
    for v in [0, 1, -1, 63, 64, -64, 65, 8191, 8192, -8192, 0x7FFFFFFF, -0x7FFFFFFF]:
        enc = codec.write_ci(v)
        dec, pos = codec.read_ci(enc, 0)
        assert dec == v and pos == len(enc), (v, enc.hex())
    assert codec.write_ci(0) == b"\x00"
    assert not (codec.write_ci(0)[0] & 0x80)


def test_fstring_roundtrip():
    for s in ["", "deusex", "Index.dx", "A longer string here"]:
        enc = codec.write_fstring(s)
        got, pos = codec.read_fstring(enc, 0)
        assert got == s and pos == len(enc)


def test_umodel_body_roundtrip():
    m = umodel.Model(
        none_index=0, vectors=[(0, 0, 1), (1, 0, 0), (0, 1, 0)],
        points=[(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        surfs=[umodel.BspSurf(v_normal=0, p_base=0, v_texture_u=1, v_texture_v=2)],
        nodes=[umodel.BspNode(plane=(0, 0, 1, 0), i_surf=0, i_vert_pool=0, num_vertices=3)],
        verts=[umodel.BspVert(i_vertex=0), umodel.BspVert(i_vertex=1),
               umodel.BspVert(i_vertex=2)],
        leaves=[umodel.BspLeaf()], zones=[])
    body = umodel.write_model_body(m)
    m2 = umodel.parse_model_body(body, 0, len(body))
    assert len(m2.surfs) == 1 and len(m2.nodes) == 1 and len(m2.verts) == 3
    assert m2.surfs[0].v_normal == 0 and m2.surfs[0].p_base == 0
    # re-serialize the parsed model -> byte-identical (writer/parser symmetry)
    m2.none_index = 0
    m2.bbox_min = m.bbox_min
    m2.bbox_max = m.bbox_max
    assert umodel.write_model_body(m2) == body


def test_umodel_bounds_and_leafhulls_roundtrip():
    """The `Bounds` (c0, FBox) + `LeafHulls` (cc, INT — box-sweep collision hulls) arrays
    (de)serialize byte-exact; a populated model round-trips through parse->write unchanged."""
    m = umodel.Model(
        none_index=0, vectors=[(0, 0, 1)], points=[(0, 0, 0)],
        surfs=[umodel.BspSurf(v_normal=0, p_base=0)],
        nodes=[umodel.BspNode(plane=(0, 0, 1, 0), i_surf=0, num_vertices=0,
                              i_collision_bound=0, i_render_bound=0)],
        verts=[], leaves=[umodel.BspLeaf()], zones=[],
        bounds=[umodel.FBox(min=(-512.0, -512.0, -512.0), max=(512.0, 512.0, 512.0), valid=1)],
        # one hull run: 4 FLIP plane refs + plain ref + -1 terminator + 6 bitcast-f32 bbox floats
        leaf_hulls=[0 | 0x40000000, 1 | 0x40000000, 2, -1]
        + [struct.unpack("<i", struct.pack("<f", f))[0]
           for f in (-256.0, -256.0, -32768.0, 256.0, 256.0, -128.0)])
    body = umodel.write_model_body(m)
    m2 = umodel.parse_model_body(body, 0, len(body))
    assert len(m2.bounds) == 1 and m2.bounds[0].min == (-512.0, -512.0, -512.0)
    assert m2.bounds[0].max == (512.0, 512.0, 512.0) and m2.bounds[0].valid == 1
    assert m2.leaf_hulls == m.leaf_hulls
    m2.none_index = 0
    m2.bbox_min, m2.bbox_max = m.bbox_min, m.bbox_max
    assert umodel.write_model_body(m2) == body


def test_m0_carved_box_self_check():
    pkg = build_carved_box_package()
    self_check(pkg)                                  # raises on any inconsistency
    p = parse_package(pkg)                           # re-parses to EOF
    assert p.version == 68
    classes = [p.class_of_export(i) for i in range(len(p.exports))]
    assert "LevelInfo" in classes and "PlayerStart" in classes and "Level" in classes
    # Actors[0]/[1] invariant is enforced by self_check; assert the Model export is present
    assert classes.count("Model") >= 1


def test_m0_carved_box_v69():
    pkg = build_carved_box_package(version=69)
    self_check(pkg)
    assert parse_package(pkg).version == 69


def test_m0_export_flags_match_real_map_load_contract():
    """Regression: non-actor helper exports must carry the RF_Load* context bits or a
    standalone game SKIPS loading them — a skipped level Model makes MyLevel.ModelRef
    unresolvable and the whole ULevel load aborts ("Failed to find object 'Level
    None.MyLevel'").  Flags below match a real DeusEx map (DXOnly.dx), verified live: the
    level BSP Model + default-brush Polys carry LoadForClient|Server|Edit (0x00070001); the
    brush *shape* Model is edit-only (0x00340001).  See assemble._FLAGS_LOAD/_FLAGS_BRUSH."""
    p = parse_package(build_carved_box_package())
    flags_by_name = {p.names[e["nm"]]: e["flags"] for e in p.exports}
    RF_LOAD = 0x00010000 | 0x00020000              # LoadForClient | LoadForServer
    # every export the game must instantiate has BOTH client+server load bits...
    assert flags_by_name["Model_Level"] == 0x00070001, "level Model must be game-loadable"
    assert flags_by_name["BrushPolys"] == 0x00070001
    # ...and the level Model in particular is NEVER left as a bare RF_Transactional (0x1),
    # which is exactly the from-scratch bug that skipped it in-game.
    assert flags_by_name["Model_Level"] & RF_LOAD == RF_LOAD
    # brush shape Model is edit-only (real maps: 0x00340001) — the game skips it, which is fine.
    assert flags_by_name["Brush"] == 0x00340001
    # no non-actor helper is left with the bare-transactional flag that broke game-load.
    for name in ("Model_Level", "BrushPolys", "Brush"):
        assert flags_by_name[name] != 0x00000001, f"{name} has the bad bare-load flag"


def test_self_check_rejects_missing_playerstart():
    model = materialize.carved_box_model()
    # a level with no PlayerStart -> assemble refuses (invariant)
    with pytest.raises(ValueError, match="PlayerStart"):
        assemble.assemble_level(level_model=model, actors=[], brush_shapes=[])


def test_self_check_rejects_truncated_package():
    pkg = build_carved_box_package()
    with pytest.raises(BuildError):
        self_check(pkg[:-4])                          # truncate: export table won't reach EOF


def test_native_ext_ffi_smoke():
    """The Rust extension imports and builds the M0 box handle over the FFI boundary."""
    un = pytest.importorskip("uedctl_native")
    built = un.build_carved_box(512.0, 256.0)
    assert built.num_nodes == 6 and built.num_surfs == 6 and built.num_verts == 24
    # bake_lighting with no lights runs cleanly (dark records, no bits); build_paths is still N-5.
    un.bake_lighting(built, [])
    with pytest.raises(un.BuildError):
        un.build_paths(built)


def test_gate5_dual_serializer_byte_identical():
    """§6 gate 5 (anti-drift): the runtime Rust `model_write` serializes the built UModel
    body byte-identically to the proven Python oracle `umodel.write_model_body`."""
    un = pytest.importorskip("uedctl_native")
    built = un.build_carved_box(512.0, 256.0)
    rust_body = un.serialize_model(built)
    py_body = umodel.write_model_body(materialize.carved_box_model(512.0, 256.0))
    assert rust_body == py_body


def test_gate5_populated_hulls_rust_matches_python():
    """§6 gate 5 extended to POPULATED collision hulls: the Rust `serialize_model` of a real
    CSG build (which runs `bsp_build_bounds`, filling `LeafHulls`/`iCollisionBound`) re-parses and
    Python-re-serializes byte-identically — pinning the Rust c0/cc (`FBox` + INT-array) emission
    against the Python oracle for a NON-empty array (the empty-carved-box gate5 can't).  """
    un = pytest.importorskip("uedctl_native")
    from uedctl import model as trunk_model
    from uedctl.native.csg_golden import _case_single_subtract
    lvl = trunk_model.Level()
    for a in _case_single_subtract():
        lvl.actors[a.name] = a
        lvl.order.append(a.name)
    m, *_ = materialize._build_level_model(lvl, index=IDX, core="coarse")
    assert len(m.leaf_hulls) > 0, "build produced no hulls — nothing to pin"
    # the Rust body re-serializes byte-identically through the Python oracle (parse->write).
    body = un.serialize_model(un.build_geometry(
        [materialize._build_brush_input(n, lvl.actors[n]) for n in lvl.order
         if lvl.actors[n].brush is not None]))
    m2 = umodel.parse_model_body(body, 0, len(body))
    assert m2.leaf_hulls == m.leaf_hulls and len(m2.bounds) == len(m.bounds)
    # the parser doesn't capture the UPrimitive prefix bbox; copy it from the Rust body so the
    # byte comparison isolates the array (c0/cc) encoding — the thing being pinned.
    m2.bbox_min = struct.unpack_from("<3f", body, 1)
    m2.bbox_max = struct.unpack_from("<3f", body, 13)
    assert umodel.write_model_body(m2) == body


def test_bspspike_parser_agrees():
    """Independent read-back: the original bspspike parser accepts the level Model."""
    import sys, os, importlib
    here = os.path.dirname(__file__)
    spike = os.path.normpath(os.path.join(here, "..", "..", "dev", "docs", "spikes",
                                          "bspspike"))
    if not os.path.isdir(spike):
        pytest.skip("bspspike harness not present")
    if spike not in sys.path:
        sys.path.insert(0, spike)
    P = importlib.import_module("umodel_parser")
    pkg = build_carved_box_package()
    # locate the level Model export by class + largest size
    p = parse_package(pkg)
    models = [(i, e) for i, e in enumerate(p.exports) if p.class_of_export(i) == "Model"]
    i0, e = max(models, key=lambda t: t[1]["ssize"])
    m = P.parse_model_serial(pkg, e["soff"], e["ssize"])
    assert not P.sanity_check(m)                      # no issues
    assert len(m.nodes) == 6 and len(m.surfs) == 6


def _single_subtract_model():
    """Build the finalized real-CSG world Model for a single subtracted room via the Rust
    core (skips if the extension is absent)."""
    pytest.importorskip("uedctl_native")
    from uedctl import model as trunk_model
    from uedctl.native.csg_golden import _case_single_subtract
    lvl = trunk_model.Level()
    for a in _case_single_subtract():
        lvl.actors[a.name] = a
        lvl.order.append(a.name)
    m, *_ = materialize._build_level_model(lvl, index=IDX)
    return m


def _lit_single_subtract_level():
    """A trunk Level: one subtracted room + a PlayerStart + a steady Light at the centre."""
    pytest.importorskip("uedctl_native")
    from uedctl import model as trunk_model
    from uedctl.native.csg_golden import _case_single_subtract
    lvl = trunk_model.Level()
    for a in _case_single_subtract():
        lvl.actors[a.name] = a
        lvl.order.append(a.name)
    ps = trunk_model.Actor(name="PS0", cls="Engine.PlayerStart", props=[],
                           location=(0.0, 0.0, -88.0))
    light = trunk_model.Actor(name="Light0", cls="Engine.Light",
                              props=[("LightType", "LT_Steady"), ("LightBrightness", "220"),
                                     ("LightRadius", "48")],
                              location=(0.0, 0.0, 96.0))
    for a in (ps, light):
        lvl.actors[a.name] = a
        lvl.order.append(a.name)
    return lvl


def test_native_lightmap_bake_round_trips_and_self_checks(tmp_path):
    """End-to-end N-4 (spike section 20): a lit single-room level bakes a non-empty lightmap,
    the built .dx passes the always-on self-check + re-parses to EOF, every wall is lightmapped,
    some lumel is lit, and the Model's `lights` array resolves to the Light actor's export ref
    (index-and-terminator form patched by assembly)."""
    lvl = _lit_single_subtract_level()
    out = tmp_path / "lit.dx"
    materialize.run_materialize_native(level=lvl, class_index=IDX, out_path=str(out),
                                       overwrite=True, version=68,
                                       no_light=False)

    pkg = parse_package(out.read_bytes())                 # re-parses to EOF
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    m = umodel.parse_model_body(pkg.buf, e["soff"], e["ssize"])

    assert len(m.surfs) == 6
    assert all(s.i_light_map != -1 for s in m.surfs), "every room wall is lightmapped"
    assert len(m.light_map) == 6
    assert len(m.light_bits) > 0 and any(b != 0 for b in m.light_bits), "some lumel is lit"
    # `lights` runs are [<light export ref>, 0(NULL)] — the single Light0 export, terminated.
    assert 0 in m.lights, "each light run is NULL-terminated"
    light_refs = {r for r in m.lights if r != 0}
    assert len(light_refs) == 1, "one distinct light ref"
    (ref,) = light_refs
    assert pkg.class_of_export(ref - 1) == "Light", "lights[] resolves to the Light export"


def _lit_model_of(out, pkg_parse):
    pkg = pkg_parse(out.read_bytes())
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return umodel.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def test_default_build_is_lit(tmp_path):
    """The DEFAULT build (no `no_light` arg) is LIT — with a participating Light, surfaces carry
    lightmap records and the Model's light arrays are populated.  Lit renders clean since the
    FBspSurf field-order fix (spike section 20 §14, 2026-07-16)."""
    lvl = _lit_single_subtract_level()
    out = tmp_path / "lit.dx"
    materialize.run_materialize_native(level=lvl, class_index=IDX, out_path=str(out),
                                       overwrite=True, version=68)
    m = _lit_model_of(out, parse_package)
    assert any(s.i_light_map != -1 for s in m.surfs)
    assert m.light_map and m.lights
    # every lightmapped surf indexes an in-range LightMap record (the bug the field-order fix cured)
    assert all(0 <= s.i_light_map < len(m.light_map) for s in m.surfs if s.i_light_map != -1)


def test_no_light_true_is_unlit(tmp_path):
    """Opt-out: `no_light=True` yields an explicitly unlit build — every surf iLightMap=-1, no
    lightmap arrays — even with a participating Light present."""
    lvl = _lit_single_subtract_level()
    out = tmp_path / "unlit.dx"
    materialize.run_materialize_native(level=lvl, class_index=IDX, out_path=str(out),
                                       overwrite=True, version=68,
                                       no_light=True)
    m = _lit_model_of(out, parse_package)
    assert all(s.i_light_map == -1 for s in m.surfs)
    assert not m.light_map and not m.light_bits and not m.lights


def test_multizone_build_assigns_zones_and_zoneactors():
    """The native build now DOES emit multiple zones (real leaves + portal flood, zones.rs) —
    superseding the old single-zone `_multizone_warning`.  A two-room map with a ZoneInfo yields
    >1 interior zone, and the ZoneInfo's zone gets its ZoneActor wired (Pass G / _patch_zone_refs)."""
    pytest.importorskip("uedctl_native")
    from uedctl import model as trunk_model
    from uedctl.builders import cube, make_brush_actor
    lvl = trunk_model.Level()
    for nm, x in (("RoomA", -400.0), ("RoomB", 400.0)):
        a = make_brush_actor(nm, cube(300, 300, 256), location=(x, 0.0, 0.0), csg="subtract")
        lvl.actors[nm] = a
        lvl.order.append(nm)
    # a ZoneInfo inside RoomB
    zi = trunk_model.Actor(name="ZI", cls="Engine.ZoneInfo", props=[], location=(400.0, 0.0, 0.0))
    lvl.actors["ZI"] = zi
    lvl.order.append("ZI")
    m, _c, _l, zone_actors = materialize._build_level_model(lvl, index=IDX, bake_light=False)
    zone_ids = {lf.i_zone for lf in m.leaves}
    assert len(zone_ids) >= 2, f"expected multiple interior zones, got {zone_ids}"
    # the ZoneInfo resolved into some interior zone -> Pass G maps that zone to the actor.
    assert zone_actors and "ZI" in zone_actors.values()


def test_water_portal_keeps_playerstart_out_of_water_zone():
    """A `PF_Portal` water-surface sheet must SPLIT the interior so the water zone (its bWaterZone
    ZoneInfo) does NOT bleed into the dry zone containing the PlayerStart — otherwise the pawn
    spawns SWIMMING (phys=3) instead of WALKING (phys=1).  Regression for the native CSG dropping
    the non-solid portal sheet (void-on-both-sides -> annihilated as a cospatial shared wall), which
    collapsed the whole interior into the single water zone.  Faithful to how UnrealEd's
    `Test_Castle.dx` keeps the water-surface `PF_Portal` faces (the fix lives in csg.rs)."""
    pytest.importorskip("uedctl_native")
    from uedctl import model as trunk_model
    from uedctl.builders import (
        PF_NOTSOLID, PF_TWOSIDED, cube, make_brush_actor, sheet,
    )
    PF_PORTAL = 0x0400_0000

    lvl = trunk_model.Level()
    # One big subtracted room: interior spans z in [-300, 300], centred on origin.
    room = make_brush_actor("Room", cube(600, 600, 600), location=(0.0, 0.0, 0.0), csg="subtract")
    lvl.actors["Room"] = room
    lvl.order.append("Room")
    # A horizontal PF_Portal water-surface sheet at z=0, wider than the room so it fully seals the
    # cross-section (CSG clips it back to the walls).  CSG_Add, non-solid — the zone boundary.
    surf = sheet(700, 700, plane="xy", flags=PF_TWOSIDED | PF_NOTSOLID | PF_PORTAL)
    lvl.actors["WaterSurf"] = make_brush_actor("WaterSurf", surf, location=(0.0, 0.0, 0.0), csg="add")
    lvl.order.append("WaterSurf")
    # bWaterZone ZoneInfo in the LOWER half (the water); PlayerStart in the UPPER half (dry).
    zi = trunk_model.Actor(name="WaterZI", cls="Engine.ZoneInfo",
                           props=[("bWaterZone", "True")], location=(0.0, 0.0, -150.0))
    lvl.actors["WaterZI"] = zi
    lvl.order.append("WaterZI")

    m, _c, _l, zone_actors = materialize._build_level_model(lvl, index=IDX, bake_light=False)

    # The portal sheet must survive CSG as PF_Portal surf(s) (else there is nothing to cut on).
    assert any(s.poly_flags & PF_PORTAL for s in m.surfs), \
        "PF_Portal water-surface sheet was dropped by CSG (no portal surf in the built model)"
    # Upper (PlayerStart) and lower (water) points resolve to DIFFERENT interior zones.
    z_dry = materialize._model_point_zone(m, (0.0, 0.0, 150.0))
    z_water = materialize._model_point_zone(m, (0.0, 0.0, -150.0))
    assert z_dry > 0 and z_water > 0, (z_dry, z_water)
    assert z_dry != z_water, \
        f"water zone bled into the dry zone (both zone {z_dry}) — pawn would swim"
    # The bWaterZone ZoneInfo owns the WATER zone, and the PlayerStart's dry zone is NOT that zone.
    assert zone_actors.get(z_water) == "WaterZI", (zone_actors, z_water)
    assert zone_actors.get(z_dry) != "WaterZI", \
        f"PlayerStart's zone {z_dry} carries the bWaterZone ZoneInfo (pawn would spawn swimming)"


def test_finalize_render_bound_is_load_safe():
    """Regression for the OccludeBsp NULL-FBox render crash (commit 51e47618b).  The native build
    now EMITS the render `Bounds` (c0) array to byte-parity with UnrealEd (faithful `FilterBound`
    port — passes.rs `bsp_build_bounds`), so the crash-safety invariant is no longer "Bounds stays
    empty" but the property that actually protects `URender::OccludeBsp`: every node's
    `iRenderBound` is EITHER -1 (the "no bound" sentinel) OR a valid index into a non-empty
    `Bounds`, and every emitted FBox is IsValid=1 with well-formed extents (`min<=max`).  A >=0
    `iRenderBound` that dereferences a NULL/invalid FBox is what triggers the per-frame "Anomalous
    singularity in DrawWorld".  `iCollisionBound` is a SEPARATE surface indexing `LeafHulls` (cc)
    — see the next test.  See spike sections/50-model-ondisk-layout-and-render.md +
    re-raw-zones/bounds-and-zonelayout.md §1."""
    m = _single_subtract_model()
    assert len(m.nodes) == 6
    # Render bounds ARE built now: exactly the interior nodes (>=1 front/back child) carry one,
    # indexed in post-order (root gets the last index).
    interior = [i for i, n in enumerate(m.nodes)
                if n.i_front != -1 or n.i_back != -1]
    n_rb = sum(1 for n in m.nodes if n.i_render_bound != -1)
    assert n_rb == len(interior), (n_rb, len(interior), "render bound set != interior-node set")
    assert len(m.bounds) == n_rb, "Bounds array length must equal the render-bound node count"
    for i, n in enumerate(m.nodes):
        rb = n.i_render_bound
        if rb == -1:
            assert i not in interior, (i, "interior node missing its render bound")
            continue
        assert 0 <= rb < len(m.bounds), (i, rb, "iRenderBound out of range -> NULL FBox deref")
    # Every emitted FBox must be load-safe: IsValid=1 and non-inverted extents (the actual
    # OccludeBsp crash surface).
    for k, b in enumerate(m.bounds):
        assert b.valid == 1, (k, "emitted render FBox has IsValid=0 (OccludeBsp deref risk)")
        assert all(b.min[c] <= b.max[c] for c in range(3)), (k, b.min, b.max, "inverted FBox")
    # And the leaf markers must land in the fixed-i32 iLeaf slot (NOT the ci bound slots): at
    # least one terminal side carries the interior leaf 0.
    assert any(0 in n.i_leaf for n in m.nodes), "no node carries the interior leaf marker"


def test_finalize_builds_collision_hulls():
    """The native build MUST emit per-node collision hulls (`LeafHulls` + `iCollisionBound`), or
    the pawn falls through the floor: the game's box-sweep collision
    (`FBoxLineCheckInfo::BoxLineCheck`) has NO node-plane fallback and produces a hit ONLY by
    clipping the swept box against `LeafHulls[node.iCollisionBound]`; `iCollisionBound == -1` =>
    NON-SOLID to every pawn/actor sweep (root cause — re-raw-zones/linecheck-oracle.md).  For a
    single subtracted room every node bounds a solid exterior cell, so every node carries a hull;
    each `iCollisionBound` indexes a valid `LeafHulls` run (`[plane refs…, -1, 6× bbox]`)."""
    m = _single_subtract_model()
    assert len(m.leaf_hulls) > 0, "no collision hulls built (pawn would fall through)"
    n_hull = sum(1 for n in m.nodes if n.i_collision_bound >= 0)
    assert n_hull == 6, f"expected all 6 nodes to carry a collision hull, got {n_hull}"
    for i, n in enumerate(m.nodes):
        if n.i_collision_bound < 0:
            continue
        j = n.i_collision_bound
        assert 0 <= j < len(m.leaf_hulls), (i, "iCollisionBound out of range")
        # the run must contain a -1 terminator followed by 6 bbox ints, all within the array.
        k = j
        while k < len(m.leaf_hulls) and m.leaf_hulls[k] != -1:
            k += 1
        assert k + 6 < len(m.leaf_hulls), (i, "hull run missing -1 terminator + 6-int bbox")


_SPIKE = "dev/docs/spikes/2026-07-15-native-materialize/harness"


def _load_line_check():
    """Import the committed box-sweep collision oracle from the spike harness.

    The harness is SPIKE code, not library code: `line_check.py` pulls in siblings from other spike
    harnesses (`utexture_decode`, from the 2026-06-27 spike) through its own hardcoded `sys.path`
    edits, so whether it imports at all depends on the spike tree's layout rather than on uedctl. When
    it does not import, SKIP with a reason naming the spike env — a permanently-red suite trains
    everyone to ignore red. A failure to import `uedctl` itself is NOT skipped: that is a real
    regression in the code under test, and swallowing it would hide exactly what these tests guard."""
    import importlib
    import os
    import sys
    harness = os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "..", *_SPIKE.split("/")))
    if not os.path.isfile(os.path.join(harness, "line_check.py")):
        pytest.skip(f"line_check oracle absent — needs the spike harness at {_SPIKE}")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    try:
        return importlib.import_module("line_check")
    except ImportError as e:
        if (e.name or "").split(".")[0] == "uedctl":      # the code under test — a real failure
            raise
        pytest.skip(f"line_check oracle needs the spike env ({_SPIKE}): {type(e).__name__}: {e}")


def test_line_check_loader_skips_on_a_spike_dep_but_not_on_a_uedctl_one(monkeypatch):
    """Pins `_load_line_check`'s two branches. A spike-side dependency that will not import (the
    harness reaches into a SIBLING spike's tree via its own hardcoded `sys.path` edits) must produce
    a SKIP naming the spike env — a permanently-red suite trains everyone to ignore red. An
    ImportError from `uedctl` itself must PROPAGATE: that is a regression in the code under test."""
    import importlib
    import os

    def _raise(name):
        raise ImportError("blocked", name=_raise.missing)

    # Force past the harness-absent guard, so BOTH branches below are genuinely exercised on a
    # checkout that has no spike tree (otherwise the loader skips before it ever imports, and this
    # test would pass without testing anything).
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(importlib, "import_module", _raise)
    _raise.missing = "utexture_decode"                   # a spike-harness sibling → skip
    with pytest.raises(pytest.skip.Exception) as skipped:
        _load_line_check()
    assert "needs the spike env" in str(skipped.value) and _SPIKE in str(skipped.value)
    _raise.missing = "uedctl.native.umodel"              # the code under test → surface it
    with pytest.raises(ImportError):
        _load_line_check()


def test_box_sweep_lands_on_native_floor(tmp_path):
    """The pawn-sized BOX sweep must HIT the floor of a freshly materialized native room and
    land ~extent above it — the actual "pawn falls through the floor" bug, which the structural
    hull tests above cannot see.  Guards hull ORIENTATION (the FLIP bit) and the solid-cell set:
    an inverted FLIP or a wrong `outside` propagation passes the structural tests but MISSES here.
    The game's box collision (`FBoxLineCheckInfo::BoxLineCheck`) hits ONLY by clipping the swept
    box against `LeafHulls[iCollisionBound]`.  Uses the committed offline oracle; depends only on a
    synthetic native map (never on gitignored real maps)."""
    pytest.importorskip("uedctl_native")
    LC = _load_line_check()
    lvl = _lit_single_subtract_level()      # 512x512x256 subtract -> floor at z=-128, + PlayerStart
    out = tmp_path / "sweep.dx"
    materialize.run_materialize_native(level=lvl, class_index=IDX, out_path=str(out), overwrite=True,
                                       version=68, no_light=True)
    lm = LC.load_level_model(out)           # reads bounds/leaf_hulls/root_outside off the .dx
    # downward pawn sweep from inside the room must land ~extent (44) above the floor (-128),
    # i.e. rest at z=-84 — NOT sink to the floor plane (-128), which is the fall-through symptom.
    start, end = (0.0, 0.0, 0.0), (0.0, 0.0, -400.0)
    hit = LC.line_check(lm, start, end, extent=(20, 20, 44))
    assert hit is not None, "box sweep fell through the floor (collision hull wrong/missing)"
    # the engine's reported time carries a fixed 0.1-of-sweep-length backoff (Engine 0xf403b);
    # recover the true contact height and assert it is extent-above the floor.
    backoff = max(0.1 / abs(end[2] - start[2]), 0.1)
    true_z = start[2] + (hit["time"] + backoff) * (end[2] - start[2])
    assert abs(true_z - (-128.0 + 44)) < 3.0, (true_z, hit)
    # the pawn must rest WELL ABOVE the floor plane, never sink onto it (the bug signature).
    assert hit["location"][2] > -100.0, hit["location"]
    # a horizontal sweep across the OPEN room must NOT hit (guards over-solid / mis-oriented hulls).
    assert LC.line_check(lm, (0, 0, 0), (60, 0, 0), extent=(20, 20, 44)) is None


def test_point_below_floor_is_solid_after_hulls(tmp_path):
    """Point (zero-extent) guard: with `iCollisionBound>=0` the game's `PointCheck` now consults
    the hulls (its `iColl==-1` skip is bypassed).  A point below the floor must classify SOLID and
    a point inside the room EMPTY — so populating hulls doesn't regress point-encroachment
    (spec §3.2 guard)."""
    pytest.importorskip("uedctl_native")
    LC = _load_line_check()
    lvl = _lit_single_subtract_level()
    out = tmp_path / "pt.dx"
    materialize.run_materialize_native(level=lvl, class_index=IDX, out_path=str(out), overwrite=True,
                                       version=68, no_light=True)
    lm = LC.load_level_model(out)
    # zero-extent trace straight down from interior must stop at the floor (solid below).
    hit = LC.line_check(lm, (0, 0, 0), (0, 0, -400), extent=(0.0, 0.0, 0.0))
    assert hit is not None, "point trace fell through the floor"
    assert hit["location"][2] < 0.0 and hit["location"][2] > -132.0, hit["location"]


def test_finalize_collision_topology_matches_dxonly():
    """Regression for the "player falls through the floor" bug (spike 60-leaf-solidity-collision.md).
    Live-verified fix: the pawn only stands (phys=Walking) once (a) NF_IsNew is cleared so
    `FBspNode::IsCsg()` treats a wall as a blocker, and (b) the FRONT child sits in the engine's
    iChild[1] slot (our `i_back`) so `LineCheck` descends the correct halfspace. This pins both,
    matching DXOnly's single-box pattern: every node has NF_IsNew clear, the tree chains through
    `i_back` (front terminals), and exactly the interior terminal carries leaf 0 (solid = -1)."""
    m = _single_subtract_model()
    NF_IS_NEW = 0x20
    for i, n in enumerate(m.nodes):
        assert not (n.node_flags & NF_IS_NEW), (i, "NF_IsNew must be cleared for IsCsg/collision")
        # iLeaf[0] (BACK/solid slot) is never the interior leaf; only a terminal FRONT (i_back==-1)
        # may carry leaf 0.
        assert n.i_leaf[0] == -1, (i, "solid (back) slot must be -1")
        assert n.i_leaf[1] == (0 if n.i_back == -1 else -1), (i, "interior leaf only on front terminal")
    # Like DXOnly: exactly one interior terminal (the single connected empty leaf).
    assert sum(1 for n in m.nodes if n.i_leaf[1] == 0) == 1
    # Explicit swap pin (independent of the self-referential asserts above): after the fix the
    # FRONT child lives in `i_back` (engine iChild[1]), so a single convex room chains entirely
    # through `i_back` and every node's `i_front` (iChild[0]/BACK/solid) is a terminal -1. Without
    # the swap the chain would run through `i_front` and this would fail.
    assert all(n.i_front == -1 for n in m.nodes), "chain must run through i_back (FRONT=iChild[1])"


# The real-map semantic pin needs a stock/known map outside the mod repo; discover it (or
# accept an override) and skip cleanly when it isn't on this machine.
def _dxonly_map_path():
    import os
    from pathlib import Path
    env = os.environ.get("UEDCTL_TEST_REALMAP")
    if env and Path(env).is_file():
        return Path(env)
    cand = Path(__file__).resolve().parents[5] / "Maps" / "DXOnly.dx"  # .../DX/Maps/DXOnly.dx
    return cand if cand.is_file() else None


def test_dxonly_fbspnode_semantics_pinned():
    """Pin the CORRECTED on-disk FBspNode field semantics against a real map. The writer/parser
    round-trip tests can't catch a re-swap of the two index pairs (both sides stay
    self-consistent), so ONLY a real map — decoded independently in the spike doc — anchors
    which slot is `iCollisionBound`/`iRenderBound` (ci pair) vs `iLeaf[2]` (fixed i32). Values
    hand-decoded from DXOnly.dx in sections/50-model-ondisk-layout-and-render.md."""
    path = _dxonly_map_path()
    if path is None:
        pytest.skip("DXOnly.dx not available (set UEDCTL_TEST_REALMAP to a real .dx to run)")
    p = parse_package(path.read_bytes())
    mi = [i for i in range(len(p.exports)) if p.class_of_export(i) == "Model"]
    mi.sort(key=lambda i: p.exports[i]["ssize"], reverse=True)
    e = p.exports[mi[0]]
    m = umodel.parse_model_body(p.buf, e["soff"], e["ssize"])
    assert len(m.nodes) == 6
    # Bounds indices (ci pair, field 9/10) are real >=0 hull indices on the solid chain, and the
    # per-side leaf slots (fixed i32, field 14/15) are -1 on solid terminals.
    assert (m.nodes[0].i_collision_bound, m.nodes[0].i_render_bound) == (52, 4)
    assert m.nodes[0].i_leaf == (-1, -1)
    # Only the interior terminal carries the empty leaf 0 (the rest are solid = -1).
    assert m.nodes[5].i_leaf == (-1, 0)
    assert all(n.i_leaf == (-1, -1) for n in m.nodes[:5])


def test_mover_excluded_from_world_csg_but_emitted_as_actor():
    """A Mover (door/elevator/lift) is a DYNAMIC actor: UnrealEd keeps its brush as the Mover's
    OWN private Model and never CSGs it into the world BSP.  The native build must MATCH that —
    a mover is kept OUT of the world-CSG input (else its brush fills the doorway solid and shatters
    empty-space connectivity into spurious zones/leaf-blobs; measured on HK: excluding the movers
    took leaf-blobs 21->2 and zones 24->5), yet it is STILL emitted as a level actor (a mover is a
    real object, not geometry).  Regression for `materialize._in_world_csg`."""
    pytest.importorskip("uedctl_native")
    from uedctl import model as trunk_model
    from uedctl.builders import cube, make_brush_actor

    lvl = trunk_model.Level()
    # A subtracted room (world CSG) + a PlayerStart so the build is valid.
    room = make_brush_actor("Room", cube(400, 400, 300), location=(0.0, 0.0, 0.0), csg="subtract")
    lvl.actors["Room"] = room
    lvl.order.append("Room")
    # A Mover (a small door brush) INSIDE the room — a Mover carries a brush but no CsgOper.
    door = make_brush_actor("Door0", cube(64, 8, 128), location=(0.0, 200.0, 0.0),
                            mover_class="Engine.Mover")
    assert door.brush is not None, "test setup: the mover must carry a brush"
    lvl.actors["Door0"] = door
    lvl.order.append("Door0")
    ps = trunk_model.Actor(name="PS0", cls="Engine.PlayerStart", props=[],
                           location=(0.0, 0.0, 0.0))
    lvl.actors["PS0"] = ps
    lvl.order.append("PS0")

    # The predicate itself: the room brush is world-CSG, the mover is NOT.
    assert materialize._in_world_csg(room, IDX) is True
    assert materialize._in_world_csg(door, IDX) is False

    # The built world model's CSG-brush set contains the room but NOT the mover.
    _m, csg_brushes, _l, _z = materialize._build_level_model(lvl, index=IDX, bake_light=False)
    csg_names = {name for name, _polys in csg_brushes}
    assert "Room" in csg_names, "world brush wrongly dropped from CSG"
    assert "Door0" not in csg_names, "Mover wrongly fed into world CSG (fills doorways solid)"

    # ...but the mover IS still emitted as an actor (brush_actors), independent of CSG selection.
    schema = materialize.default_schema_lookup(lvl)
    actors, brush_actors, _w = materialize._trunk_to_actorspecs(lvl, schema)
    emitted = {a.name for a in actors + brush_actors}
    assert "Door0" in emitted, "Mover must still be emitted as a level actor"
    assert any(a.name == "Door0" for a in brush_actors), \
        "Mover carries a brush, so it is emitted among the brush actors"
    # NB: this asserts the two invariants of the CSG-exclusion change only (out of world CSG /
    # still emitted as an actor).  Whether the mover's OWN private Model carries its door polys is
    # a SEPARATE, pre-existing native-build gap (assemble writes an empty private Model) tracked in
    # board/inbox.md — deliberately NOT asserted here.


def _class_imports(pkg):
    """`{classname: dotted-package-chain}` for every UClass import in a parsed package — the outer
    Package-import chain of each `Class` import IS that class's owning package."""
    nm = pkg.names

    def chain(objref):
        parts = []
        while objref < 0:
            _cp, _cn, pi, on = pkg.imports[-objref - 1]
            parts.append(nm[on])
            objref = pi
        return ".".join(reversed(parts))

    return {nm[on]: chain(pi) for (_cp, cn, pi, on) in pkg.imports if nm[cn] == "Class"}


def _real_game_class_index():
    """The class->package index over the REAL configured Deus Ex install's `.u` code, read straight
    from the user's `~/.uedctl/config.toml` `[games.deusex].paths` — bypassing the autouse
    conftest fixtures that isolate project/home resolution for unit tests.  Returns `{}` (⇒ skip)
    when no install is configured/present, so these engine-fact regressions run in this dev
    environment yet never fail in an install-less CI."""
    import os
    import tomllib
    from uedctl.native.pkgref import build_class_package_index
    override = os.environ.get("UEDCTL_GAME_SYSTEM")
    if override:
        return build_class_package_index([d for d in override.split(os.pathsep) if d])
    cfg = Path.home() / ".uedctl" / "config.toml"
    if not cfg.exists():
        return {}
    try:
        paths = tomllib.loads(cfg.read_text()).get("games", {}).get("deusex", {}).get("paths", "")
        dirs = [d for d in str(paths).split(os.pathsep) if d]
    except Exception:
        return {}
    return build_class_package_index(dirs)


def _real_game_class_dirs():
    """The Deus Ex `.u` search dirs (for a raw collision re-scan), same source as
    `_real_game_class_index`; `[]` when unconfigured."""
    import os
    import tomllib
    override = os.environ.get("UEDCTL_GAME_SYSTEM")
    if override:
        return [d for d in override.split(os.pathsep) if d]
    cfg = Path.home() / ".uedctl" / "config.toml"
    if not cfg.exists():
        return []
    try:
        paths = tomllib.loads(cfg.read_text()).get("games", {}).get("deusex", {}).get("paths", "")
        return [d for d in str(paths).split(os.pathsep) if d]
    except Exception:
        return []


def test_class_package_index_resolves_deusex_classes_to_real_packages():
    """`pkgref.build_class_package_index` maps a BARE actor class to the package that REALLY defines
    it, scanned from the game's `.u` code — the fix for spike section 88 blocker 1, where every
    class defaulted to `Engine` (via a non-existent `uprops.package_of_class`).  A DeusEx-package
    class MUST resolve to `DeusEx`, a genuine Engine class to `Engine`.  Skips when no Deus Ex
    install is configured (no class->package ground truth offline)."""
    idx = _real_game_class_index()
    if "deusexmover" not in idx:
        pytest.skip("no configured Deus Ex install (DeusEx.u) — no class->package ground truth")
    # DeusEx-package classes: must NOT be Engine (the whole bug).
    assert idx["deusexmover"] == "DeusEx"
    assert idx["atm"] == "DeusEx"
    assert idx["alliancetrigger"] == "DeusEx"
    # Genuine Engine classes stay Engine (the castle corpus only exercises these).
    assert idx["playerstart"] == "Engine"
    assert idx["zoneinfo"] == "Engine"


def test_class_names_are_unique_across_the_deusex_package_set():
    """The whole resolver rests on UE1's single global object namespace: a class name is defined in
    exactly ONE package, so `build_class_package_index`'s first-hit `setdefault` can never pick a
    wrong owner (spike section 88).  Re-scan the raw `.u` set and assert no class name is a UClass
    export in two different packages.  Skips with no configured install."""
    from uedctl.native.pkg_write import parse_package
    dirs = _real_game_class_dirs()
    owners: dict[str, set] = {}
    for d in dirs:
        for u in sorted(Path(d).glob("*.u")):
            try:
                p = parse_package(u.read_bytes())
            except Exception:
                continue
            for i, e in enumerate(p.exports):
                if p.class_of_export(i) in (None, "Class"):
                    owners.setdefault(p.names[e["nm"]].casefold(), set()).add(u.stem)
    if "deusexmover" not in owners:
        pytest.skip("no configured Deus Ex install (DeusEx.u)")
    collisions = {c: sorted(pk) for c, pk in owners.items() if len(pk) > 1}
    assert not collisions, f"class name defined in multiple packages (breaks first-hit): {collisions}"


def test_real_deusex_class_imports_as_deusex_not_engine(tmp_path):
    """END-TO-END regression for spike section 88 blocker 1: a materialized level that instantiates
    a DeusEx-package actor by its BARE trunk class (`DeusExMover`) emits `DeusEx.DeusExMover` in its
    import table, NOT the fatal `Engine.DeusExMover` that made the game linker abort loading every
    real level.  The castle/tiny corpus cannot catch this (it only instantiates genuine Engine
    classes), so this synthetic 1-DeusEx-actor build is the required real-class parity check.

    Skips when no Deus Ex install is configured (the resolution has no ground truth to consult)."""
    pytest.importorskip("uedctl_native")
    idx = _real_game_class_index()
    if "deusexmover" not in idx:
        pytest.skip("no configured Deus Ex install (DeusEx.u)")
    from uedctl import model as trunk_model
    from uedctl.builders import cube, make_brush_actor

    lvl = trunk_model.Level()
    # A subtracted room (valid world CSG) + a PlayerStart so the build is valid.
    room = make_brush_actor("Room", cube(400, 400, 300), location=(0.0, 0.0, 0.0), csg="subtract")
    lvl.actors["Room"] = room
    lvl.order.append("Room")
    # A DeusEx-package actor named by its BARE trunk class (exactly how a real level's trunk stores
    # it) — this is the class that used to mis-import as Engine.DeusExMover.
    dxm = trunk_model.Actor(name="Mover0", cls="DeusExMover", props=[], location=(0.0, 100.0, 0.0))
    lvl.actors["Mover0"] = dxm
    lvl.order.append("Mover0")
    ps = trunk_model.Actor(name="PS0", cls="Engine.PlayerStart", props=[], location=(0.0, 0.0, 0.0))
    lvl.actors["PS0"] = ps
    lvl.order.append("PS0")

    out = tmp_path / "dxclass.dx"
    # Pass the real class index explicitly (the autouse fixtures isolate project resolution, so the
    # default lookup would be empty here) — this exercises the whole qualify→import path.
    materialize.run_materialize_native(level=lvl, class_index=IDX, out_path=str(out), overwrite=True,
                                       version=68, no_light=True, class_packages=idx)
    imports = _class_imports(parse_package(out.read_bytes()))
    assert imports.get("DeusExMover") == "DeusEx", \
        f"DeusExMover mis-imported as {imports.get('DeusExMover')!r} (spike §88 blocker 1 regressed)"
    # a genuine Engine class in the same build still resolves to Engine
    assert imports.get("PlayerStart") == "Engine"
