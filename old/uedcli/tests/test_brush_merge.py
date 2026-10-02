"""`brush intersect` / `brush deintersect` — the OFFLINE gate.

Two layers:

* **Golden parity** — the native merge vs the committed `fixtures/intersect/*.t3d`, which were
  captured from the live UnrealEd (`test_integration_intersect_oracle.py` regenerates them).  No
  editor and no container is touched here; the fixtures ARE the oracle.
* **CLI behaviour** — the guards, the flag matrix, and the §6b placement construction.
"""
from __future__ import annotations

import argparse
from decimal import Decimal

import pytest

from uedcli import brushcsg, builders
from uedcli.cli.dispatch import dispatch
from uedcli.model import parse_t3d
from uedcli.tests import intersect_cases
from uedcli.tests.merge_compare import (assert_same_faces, load_golden,
                                        load_golden_text, native_faces,
                                        native_links, oracle_links)

uedcli_native = pytest.importorskip("uedcli_native")


# --------------------------------------------------------------------------------------------
# Golden parity
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("case_id", sorted(intersect_cases.CASES))
def test_native_merge_matches_the_committed_editor_golden(case_id):
    """EVERY case matches the live editor, face for face. Two of them only do so because of a
    specific fix, and both would regress silently:

    * `c_semisolid_additive` needs a SEMISOLID brush to actually reach the world tree, which it did
      not before `build_geometry_bspcsg` learned to clear `NF_IsNew` after the repartition (the
      whole rebuilt tree read as non-CSG, so every Pass-2 detail face classified `F_INSIDE` and was
      dropped). Without that, the merge returns ZERO faces here — and `level materialize` silently
      loses every detail brush.
    * `h_leading_additive_deintersect` needs `deintersect`'s DISTANT seed-subtract, without which
      the set's leading `CSG_Add` meets a node-less world and takes the core's convex-world-shell
      seed path, leaving the additive punched out of the plug (22 polys against the editor's 6).
    """
    assert_same_faces(native_faces(case_id), load_golden(case_id),
                      what=f"{case_id}: native vs the committed editor golden")


# --------------------------------------------------------------------------------------------
# CLI behaviour
# --------------------------------------------------------------------------------------------

def _args(sub, **over):
    d = dict(cmd="brush", sub=sub, set="-", at=None, base_name=None, csg=None, solidity=None,
             folder=None, label=[], texture=None, mover_class=None, prop=[], rotate=None,
             origin="center", pivot=None, project=None)
    d.update(over)
    return argparse.Namespace(**d)


def _t3d(*actors) -> str:
    from uedcli.emit import emit_actor_t3d
    return "".join(emit_actor_t3d(a) for a in actors)


def _cube(name, csg="add", size=(128, 128, 128), at=(0, 0, 0), **props):
    b = builders.translate_brush(builders.cube(*size), *at)
    a = builders.make_brush_actor(name, b, csg=csg)
    for k, v in props.items():
        a.props = [p for p in a.props if p[0] != k] + [(k, v)]
    return a


def _run(sub, stdin_text, monkeypatch, capsys, **over):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    rc = dispatch(_args(sub, **over))
    return rc, capsys.readouterr()


def test_empty_stdin_is_a_clean_noop(monkeypatch, capsys):
    rc, cap = _run("intersect", "", monkeypatch, capsys)
    assert rc == 0
    assert cap.out == ""


def test_intersect_without_an_additive_points_at_deintersect(monkeypatch, capsys):
    rc, cap = _run("intersect", _t3d(_cube("A", csg="subtract")), monkeypatch, capsys)
    assert rc == 2
    assert "no additive brush" in cap.err and "deintersect" in cap.err


def test_deintersect_without_a_subtractive_points_at_intersect(monkeypatch, capsys):
    rc, cap = _run("deintersect", _t3d(_cube("A", csg="add")), monkeypatch, capsys)
    assert rc == 2
    assert "no subtractive brush" in cap.err and "intersect" in cap.err


def test_a_non_brush_in_the_set_is_refused_not_silently_skipped(monkeypatch, capsys):
    """`dev/docs/direction/conventions.md` "No silent half-answers": dropping it and warning would hand back a merge that
    is quietly missing a piece, and the warning scrolls away."""
    blob = _t3d(_cube("A")) + 'Begin Actor Class=Light Name=L1\n    Name="L1"\nEnd Actor\n'
    rc, cap = _run("intersect", blob, monkeypatch, capsys)
    assert rc == 2
    assert "L1" in cap.err and "not a brush actor" in cap.err


def test_a_mover_in_the_set_is_refused(monkeypatch, capsys):
    mover = builders.make_brush_actor("Door", builders.cube(64, 64, 64),
                                      mover_class="Engine.Mover")
    rc, cap = _run("intersect", _t3d(_cube("A"), mover), monkeypatch, capsys)
    assert rc == 2
    assert "Door" in cap.err and "Mover" in cap.err


def test_a_scaled_source_brush_now_builds_at_its_scaled_size(monkeypatch, capsys):
    """A scaled source brush now MERGES (was exit-2): its linear map `L` bakes into `rot` with the
    `scale` tuple left identity, so the `build_geometry_bspcsg` world build inside `intersect_brushset`
    applies it — no core change.  The merged brush spans the SCALED extent (a 128³ cube at MainScale
    X=2 reaches x=±128, not the unit ±64)."""
    from uedcli.transform import FScale
    a = _cube("Scaled", size=(128, 128, 128))
    a.main_scale = FScale(scale=(Decimal(2), Decimal(1), Decimal(1)))
    rc, cap = _run("intersect", _t3d(a), monkeypatch, capsys)
    assert rc == 0, cap.err
    polys = next(iter(parse_t3d(cap.out).actors.values())).brush.polys
    xs = {float(v[0]) for p in polys for v in p.vertices}
    assert max(xs) == pytest.approx(128.0) and min(xs) == pytest.approx(-128.0), \
        f"scaled cube must reach x=±128 (unit ±64 × MainScale.x=2); got x in [{min(xs)},{max(xs)}]"


def test_a_degenerate_scaled_source_brush_exits_2_naming_it(monkeypatch, capsys):
    """A zero/degenerate scale axis makes `L` singular — the marshaller refuses with a named
    `BrushCsgError` (exit 2), never a traceback."""
    from uedcli.transform import FScale
    a = _cube("Flat")
    a.post_scale = FScale(scale=(Decimal(0), Decimal(1), Decimal(1)))
    rc, cap = _run("intersect", _t3d(a), monkeypatch, capsys)
    assert rc == 2
    assert "Flat" in cap.err and "non-invertible" in cap.err


def test_a_mirrored_source_brush_builds_a_closed_solid(monkeypatch, capsys):
    """A mirrored source brush (`det L < 0`) merges into a closed box: the marshaller pre-reverses each
    ring so the post-`L` winding stays outward-CCW (a subtract would otherwise build inside-out)."""
    from uedcli.transform import FScale
    a = _cube("Mir", size=(128, 128, 128))
    a.post_scale = FScale(scale=(Decimal(-1), Decimal(1), Decimal(1)))       # one mirror axis
    rc, cap = _run("intersect", _t3d(a), monkeypatch, capsys)
    assert rc == 0, cap.err
    polys = next(iter(parse_t3d(cap.out).actors.values())).brush.polys
    normals = {tuple(round(float(c)) for c in p.normal) for p in polys}
    assert len(normals) == 6, f"a mirrored cube must merge to a closed 6-normal box; got {normals}"


def test_intersect_of_a_block_with_a_notch_carves_the_notch(monkeypatch, capsys):
    """The whole point of the verb: the merged brush is block-MINUS-notch, one actor."""
    blob = _t3d(_cube("Block", size=(256, 256, 128)),
                _cube("Notch", csg="subtract", size=(64, 64, 256), at=(96, 0, 0)))
    rc, cap = _run("intersect", blob, monkeypatch, capsys)
    assert rc == 0
    level = parse_t3d(cap.out)
    assert len(level.actors) == 1
    polys = next(iter(level.actors.values())).brush.polys
    # The notch spans x in [64,128]: the top face must stop at x=64, and the carve introduces
    # faces the plain block never had (a plain box is 6 polys).
    assert len(polys) > 6
    xs = {float(v[0]) for p in polys for v in p.vertices}
    assert 64.0 in xs, "the notch's near wall (x=64) is missing — nothing was carved"


def test_deintersect_of_a_doorway_yields_the_plug(monkeypatch, capsys):
    rc, cap = _run("deintersect", _t3d(_cube("Doorway", csg="subtract", size=(96, 32, 224))),
                   monkeypatch, capsys)
    assert rc == 0
    polys = next(iter(parse_t3d(cap.out).actors.values())).brush.polys
    assert len(polys) == 6                                   # a box-shaped plug
    normals = {tuple(round(float(c)) for c in p.normal) for p in polys}
    assert len(normals) == 6, f"the plug must be a closed box, got normals {normals}"


def test_default_origin_recenters_and_at_places_the_pivot(monkeypatch, capsys):
    """§6b: `world = Location + R·(v - PrePivot)`, so the pivot point maps to `Location`."""
    blob = _t3d(_cube("Doorway", csg="subtract", size=(96, 32, 224), at=(2048, 512, 112)))
    rc, cap = _run("deintersect", blob, monkeypatch, capsys, at=(Decimal(4096), Decimal(2048),
                                                                Decimal(128)))
    assert rc == 0
    actor = next(iter(parse_t3d(cap.out).actors.values()))
    assert tuple(float(c) for c in actor.location) == (4096.0, 2048.0, 128.0)
    # Re-centred: the local vertices straddle the origin (half-extents of the 96x32x224 doorway).
    xs = [float(v[0]) for p in actor.brush.polys for v in p.vertices]
    assert min(xs) == -48.0 and max(xs) == 48.0


def test_pivot_min_writes_prepivot_and_preserves_world_position(monkeypatch, capsys):
    blob = _t3d(_cube("Doorway", csg="subtract", size=(96, 32, 224)))
    rc, cap = _run("deintersect", blob, monkeypatch, capsys, pivot="min")
    assert rc == 0
    actor = next(iter(parse_t3d(cap.out).actors.values()))
    pre = dict(actor.props)["PrePivot"]
    # fmt_loc form, matching Location on the same actor (not a bare Decimal repr).
    assert pre == "(X=-48.000000,Y=-16.000000,Z=-112.000000)"   # P - anchor = min - centre
    # Location = P = the min corner in WORLD space; at rest the geometry must land back where it
    # was carved: world = Location + (v_local - PrePivot).
    loc = [float(c) for c in actor.location]
    pp = (-48.0, -16.0, -112.0)
    world_x = [loc[0] + float(v[0]) - pp[0] for p in actor.brush.polys for v in p.vertices]
    assert min(world_x) == -48.0 and max(world_x) == 48.0    # the doorway's own world extent


def test_origin_keep_emits_the_raw_world_form(monkeypatch, capsys):
    blob = _t3d(_cube("Doorway", csg="subtract", size=(96, 32, 224), at=(2048, 512, 112)))
    rc, cap = _run("deintersect", blob, monkeypatch, capsys, origin="keep")
    assert rc == 0
    actor = next(iter(parse_t3d(cap.out).actors.values()))
    assert tuple(float(c) for c in actor.location) == (0.0, 0.0, 0.0)
    xs = [float(v[0]) for p in actor.brush.polys for v in p.vertices]
    assert min(xs) == 2000.0 and max(xs) == 2096.0           # absolute world verts, not rebased


def test_origin_keep_rejects_at(monkeypatch, capsys):
    rc, cap = _run("deintersect", _t3d(_cube("D", csg="subtract")), monkeypatch, capsys,
                   origin="keep", at=(Decimal(1), Decimal(2), Decimal(3)))
    assert rc == 2
    assert "--at is invalid with --origin keep" in cap.err


def test_bad_origin_spec_is_a_clean_error(monkeypatch, capsys):
    rc, cap = _run("intersect", _t3d(_cube("A")), monkeypatch, capsys, origin="middle")
    assert rc == 2
    assert "--origin" in cap.err and "middle" in cap.err


def test_solidity_solid_clears_the_solidity_bits_on_every_face(monkeypatch, capsys):
    rc, cap = _run("intersect", _t3d(_cube("A", size=(256, 256, 128))), monkeypatch, capsys,
                   solidity="solid")
    assert rc == 0
    polys = next(iter(parse_t3d(cap.out).actors.values())).brush.polys
    assert polys and all((p.flags or 0) & brushcsg.SOLIDITY_BITS == 0 for p in polys)


def test_solidity_nonsolid_sets_the_actor_level_flag(monkeypatch, capsys):
    rc, cap = _run("intersect", _t3d(_cube("A", size=(256, 256, 128))), monkeypatch, capsys,
                   solidity="nonsolid")
    assert rc == 0
    actor = next(iter(parse_t3d(cap.out).actors.values()))
    assert dict(actor.props)["PolyFlags"] == str(builders.SOLIDITY_FLAGS["nonsolid"])


def test_mover_class_emits_a_mover_with_no_csgoper(monkeypatch, capsys):
    rc, cap = _run("deintersect", _t3d(_cube("D", csg="subtract")), monkeypatch, capsys,
                   mover_class="Engine.Mover")
    assert rc == 0
    assert "Class=Engine.Mover" in cap.out and "CsgOper" not in cap.out


def test_mover_class_rejects_csg_and_ALL_solidity(monkeypatch, capsys):
    """A mover rejects `--csg` and EVERY `--solidity` value, `solid` included: it keeps the SOURCE
    per-face solidity of the welded set, which is always right (a semisolid face blocks just like a
    solid one — only nonsolid is walk-through), so there is nothing to override. Accepting
    `--solidity solid` used to be justified as a 'cure' for a semisolid-door-walk-through trap; that
    trap was a myth, and allowing the flag was a footgun."""
    for flag, val in (("csg", "add"), ("solidity", "solid"),
                      ("solidity", "semisolid"), ("solidity", "nonsolid")):
        rc, cap = _run("deintersect", _t3d(_cube("D", csg="subtract")), monkeypatch, capsys,
                       mover_class="Engine.Mover", **{flag: val})
        assert rc == 2
        assert f"--{flag}" in cap.err and "invalid with --mover-class" in cap.err


def test_texture_retextures_every_result_face(monkeypatch, capsys):
    rc, cap = _run("intersect", _t3d(_cube("A", size=(256, 256, 128))), monkeypatch, capsys,
                   texture="Coretex.Metal.Metal6")
    assert rc == 0
    polys = next(iter(parse_t3d(cap.out).actors.values())).brush.polys
    assert polys and all(p.texture == "Coretex.Metal.Metal6" for p in polys)


def test_duplicate_names_in_the_piped_set_are_all_merged(monkeypatch, capsys):
    """Two generator outputs concatenated both carry `Name=Cube`; a Name-keyed parse would drop the
    first, silently turning an add+subtract set into a subtract-only one."""
    blob = _t3d(_cube("Cube", size=(256, 256, 128)),
                _cube("Cube", csg="subtract", size=(64, 64, 256), at=(96, 0, 0)))
    rc, cap = _run("intersect", blob, monkeypatch, capsys)
    assert rc == 0, cap.err
    assert "merging 2 brushes" in cap.err
    xs = {float(v[0]) for p in next(iter(parse_t3d(cap.out).actors.values())).brush.polys
          for v in p.vertices}
    assert 64.0 in xs, "the subtractive twin was dropped — the notch was not carved"


def test_a_name_list_on_stdin_is_refused_not_a_silent_noop(monkeypatch, capsys):
    """The two stdin conventions are easy to confuse; feeding the name-list form must say so."""
    rc, cap = _run("intersect", "Brush0\nBrush1\n", monkeypatch, capsys)
    assert rc == 2
    assert "T3D SNIPPET" in cap.err


def test_csg_subtract_stamps_the_result(monkeypatch, capsys):
    rc, cap = _run("intersect", _t3d(_cube("A")), monkeypatch, capsys, csg="subtract")
    assert rc == 0
    assert "CsgOper=CSG_Subtract" in cap.out


def test_folder_and_label_ride_the_wire_as_carriers(monkeypatch, capsys):
    rc, cap = _run("intersect", _t3d(_cube("A")), monkeypatch, capsys,
                   folder="castle.door", label=["hero", "lighting"])
    assert rc == 0
    assert "uedcli-folder: castle.door" in cap.out
    assert "uedcli-labels:" in cap.out and "hero" in cap.out


def test_a_disjoint_result_warns_but_stays_one_actor(monkeypatch, capsys):
    """There is deliberately no --split (decision 2026-07-24 18:12)."""
    blob = _t3d(_cube("Near", size=(128, 128, 128)),
                _cube("Far", size=(128, 128, 128), at=(1024, 0, 0)))
    rc, cap = _run("intersect", blob, monkeypatch, capsys)
    assert rc == 0
    assert len(parse_t3d(cap.out).actors) == 1
    assert "2 DISCONNECTED components" in cap.err


def test_stdin_order_is_the_csg_order_and_is_never_sorted(monkeypatch, capsys):
    """A mixed set is order-dependent: subtract-then-add leaves the block WHOLE (the carve hits
    empty space first), add-then-subtract carves it.  Sorting by Name would silently pick one."""
    block = _cube("Z_block", size=(256, 256, 128))
    notch = _cube("A_notch", csg="subtract", size=(64, 64, 256), at=(96, 0, 0))

    rc1, cap1 = _run("intersect", _t3d(block, notch), monkeypatch, capsys)
    rc2, cap2 = _run("intersect", _t3d(notch, block), monkeypatch, capsys)
    assert rc1 == 0 and rc2 == 0
    carved = next(iter(parse_t3d(cap1.out).actors.values())).brush.polys
    whole = next(iter(parse_t3d(cap2.out).actors.values())).brush.polys

    # add-then-subtract: the notch (x in [64,128]) is CARVED, so its near wall exists at x=64.
    carved_xs = {float(v[0]) for p in carved for v in p.vertices}
    assert 64.0 in carved_xs, "authoring order did not carve the notch"
    assert len(carved) == 14

    # subtract-then-add: the carve lands on empty space first and is a no-op, so the block comes
    # back WHOLE — a plain 6-face box with no x=64 wall anywhere.
    whole_xs = {float(v[0]) for p in whole for v in p.vertices}
    assert len(whole) == 6, f"reversed order should yield the plain block, got {len(whole)} polys"
    assert 64.0 not in whole_xs, "reversed order still carved — stdin order was not honoured"


# --------------------------------------------------------------------------------------------
# The §3 flag rule, end to end
# --------------------------------------------------------------------------------------------

def test_flag_rule_an_additive_source_keeps_its_solidity_in_the_result():
    """Spec §3, the whole reason this feature was investigated: poly flags are decided at CSG time
    and baked into the result faces. A face cut from a SEMISOLID additive stays semisolid (which is
    exactly what a glass-paned door wants — a semisolid face still blocks, only nonsolid is
    walk-through), while faces from a solid additive come out clean. The rule is emergent from the
    merge (LOOP-1's `NotPolyFlags`), never re-derived afterwards, so this pins it where a regression
    would actually show.

    This also guards the `NF_IsNew`-after-repartition fix: before it, a semisolid brush never
    reached the world at all and this returned ZERO semisolid faces.
    """
    pairs = brushcsg.merge(intersect_cases.build_actors("c_semisolid_additive"),
                           deintersect=False)
    by_src = {}
    for poly, src in pairs:
        by_src.setdefault(src.name if src else None, set()).add(poly.flags & brushcsg.SOLIDITY_BITS)
    assert by_src["Semi"] == {0x20}, "the semisolid additive's faces lost PF_Semisolid"
    assert by_src["Solid"] == {0}, "the solid additive's faces picked up a solidity bit"


def test_solidity_solid_scrubs_the_semisolid_inheritance(monkeypatch, capsys):
    """The documented cure for the trap above."""
    blob = _t3d(*intersect_cases.build_actors("c_semisolid_additive"))
    rc, cap = _run("intersect", blob, monkeypatch, capsys, solidity="solid")
    assert rc == 0
    polys = next(iter(parse_t3d(cap.out).actors.values())).brush.polys
    assert polys and all((p.flags or 0) & brushcsg.SOLIDITY_BITS == 0 for p in polys)


def test_editor_internal_poly_flag_bits_never_reach_the_output():
    """`PF_EdProcessed` (0x40000000) / `PF_EdCut` (0x80000000) are CSG scratch state; a real editor
    export carries them. They must never land in the trunk (`POLY_FLAG_MASK`)."""
    actors = intersect_cases.build_actors("a_add_with_notch")
    for a in actors:
        for p in a.brush.polys:
            p.flags = (p.flags or 0) | 0x40000000 | 0x100        # keep a real bit alongside
    pairs = brushcsg.merge(actors, deintersect=False)
    assert pairs
    for poly, _src in pairs:
        assert poly.flags & 0xC0000000 == 0, f"editor-internal bits leaked: {poly.flags:#x}"


def test_origin_keep_rejects_pivot(monkeypatch, capsys):
    rc, cap = _run("deintersect", _t3d(_cube("D", csg="subtract")), monkeypatch, capsys,
                   origin="keep", pivot="min")
    assert rc == 2
    assert "--pivot is invalid with --origin keep" in cap.err


# --------------------------------------------------------------------------------------------
# Result ORDER + surf-share links
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("case_id", ["a_add_with_notch", "b_doorway_plug", "k_overlapping_adds"])
def test_result_face_order_and_surf_links_match_the_editor(case_id):
    """The face-SET comparison above is order-blind, so on its own it pins neither the Phase-1/
    Phase-2 traversal order nor the finalize `iLink` renumber (the two-pass surf-share regroup at
    `0x35c44`/`0x35cb1`). Both are real output: `iLink` is what makes coplanar result faces share a
    surface, so getting it wrong silently un-groups a retexture.

    NOTE the links are read off the FFI tuple, not the emitted T3D. `Link` is COMPUTED BSP output,
    not authored state — the engine re-derives it in `bspValidateBrush` from geometry + texture +
    axes + flags, and it is "never authored, ignored on import" (`unrealed/t3d.md`), so `emit_actor`
    deliberately never writes it. The core still has to get it right (it is what groups result faces
    onto one surf during the build), which is what this pins.
    """
    got = native_links(case_id)
    want = oracle_links(load_golden_text(case_id))
    assert want, f"{case_id}: the golden carries no Link= values to compare against"
    assert got == want, (
        f"{case_id}: surf-share links differ\n  native: {got}\n  golden: {want}\n"
        "(a mismatch means either the result face ORDER or the finalize renumber diverged)")
