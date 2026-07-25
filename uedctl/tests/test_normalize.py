from uedctl.model import parse_t3d, Actor
from uedctl.normalize import normalize_level, canonical_actor_t3d, COMPUTED_PROPS
from uedctl.tests.conftest import StubDefaults, read_fixture


def _level(text):
    return parse_t3d("Begin Map\n" + text + "\nEnd Map")


def test_strips_computed_props():
    lvl = _level(
        "Begin Actor Class=Light Name=L1\n"
        "    LightBrightness=200\n"
        "    AIProfile(0)=12.5\n"
        "    Location=(X=1.0,Y=2.0,Z=3.0)\n"
        '    Name="L1"\n'
        "End Actor"
    )
    normalize_level(lvl)
    keys = [k for k, _ in lvl.actors["L1"].props]
    assert "AIProfile(0)" not in keys
    assert "LightBrightness" in keys


def test_excludes_builder_brush():
    # The builder brush exports with its reserved inner model `Begin Brush Name=Brush` and no
    # CsgOper (Task 4a spike); that's what is_builder_brush keys on, not the actor Name.
    lvl = _level(
        "Begin Actor Class=Brush Name=Brush0\n"
        "    Begin Brush Name=Brush\n       Begin PolyList\n       End PolyList\n    End Brush\n"
        "    Brush=Model'MyLevel.Brush'\n    Name=\"Brush0\"\nEnd Actor\n"
        "Begin Actor Class=Light Name=L1\n    Name=\"L1\"\nEnd Actor"
    )
    normalize_level(lvl)
    assert "Brush0" not in lvl.actors      # the red builder brush is transient
    assert "L1" in lvl.actors


def test_canonical_actor_t3d_is_stable():
    a = parse_t3d(
        "Begin Map\nBegin Actor Class=Light Name=L1\n"
        "    TimeSeconds=99.0\n    LightBrightness=200\n"
        '    Name="L1"\nEnd Actor\nEnd Map'
    ).actors["L1"]
    out1 = canonical_actor_t3d(a)
    out2 = canonical_actor_t3d(a)
    assert out1 == out2
    assert "TimeSeconds" not in out1


def test_canonical_actor_t3d_strips_timeseconds():
    a = parse_t3d(
        "Begin Map\nBegin Actor Class=Light Name=L1\n"
        "    TimeSeconds=99.0\n    LightBrightness=200\n"
        '    Name="L1"\nEnd Actor\nEnd Map'
    ).actors["L1"]
    out = canonical_actor_t3d(a)
    assert "TimeSeconds" not in out
    assert "LightBrightness" in out


def test_computed_props_set_contains_expected():
    assert "TimeSeconds" in COMPUTED_PROPS
    assert "Summary" in COMPUTED_PROPS
    assert "Region" in COMPUTED_PROPS


def test_stable_actor_ordering():
    lvl = _level(
        "Begin Actor Class=Light Name=ZLight\n    Name=\"ZLight\"\nEnd Actor\n"
        "Begin Actor Class=Light Name=ALight\n    Name=\"ALight\"\nEnd Actor"
    )
    normalize_level(lvl)
    assert list(lvl.actors.keys()) == ["ALight", "ZLight"]


from uedctl.normalize import canonical_level_hash, level_order, normalize_level
from uedctl.model import parse_t3d


_L = ("Begin Map\n"
      "Begin Actor Class=Light Name=L1\n    Name=\"L1\"\nEnd Actor\n"
      "Begin Actor Class=Light Name=L2\n    Name=\"L2\"\nEnd Actor\nEnd Map")
_L_SWAPPED = ("Begin Map\n"
              "Begin Actor Class=Light Name=L2\n    Name=\"L2\"\nEnd Actor\n"
              "Begin Actor Class=Light Name=L1\n    Name=\"L1\"\nEnd Actor\nEnd Map")

_TWO_BRUSHES = (
    "Begin Map\n"
    "Begin Actor Class=Brush Name=B_first\n"
    "    Begin Brush Name=Model0\n       Begin PolyList\n       End PolyList\n    End Brush\n"
    "    Brush=Model'MyLevel.Model0'\n    Name=\"B_first\"\nEnd Actor\n"
    "Begin Actor Class=Light Name=Lamp\n    Name=\"Lamp\"\nEnd Actor\n"
    "Begin Actor Class=Brush Name=B_second\n"
    "    Begin Brush Name=Model1\n       Begin PolyList\n       End PolyList\n    End Brush\n"
    "    Brush=Model'MyLevel.Model1'\n    Name=\"B_second\"\nEnd Actor\nEnd Map")


def test_canonical_level_hash_is_order_dependent():
    a, b = parse_t3d(_L), parse_t3d(_L_SWAPPED)
    a.order, b.order = level_order(a), level_order(b)
    assert canonical_level_hash(a) != canonical_level_hash(b)


def test_canonical_level_hash_is_stable():
    a, b = parse_t3d(_L), parse_t3d(_L)
    a.order, b.order = level_order(a), level_order(b)
    assert canonical_level_hash(a) == canonical_level_hash(b)


def test_canonical_level_hash_differs_on_authored_change():
    a = parse_t3d("Begin Map\nBegin Actor Class=Light Name=L1\n"
                  "    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n    Name=\"L1\"\nEnd Actor\nEnd Map")
    b = parse_t3d("Begin Map\nBegin Actor Class=Light Name=L1\n"
                  "    Location=(X=64.000000,Y=0.000000,Z=0.000000)\n    Name=\"L1\"\nEnd Actor\nEnd Map")
    a.order, b.order = level_order(a), level_order(b)
    assert canonical_level_hash(a) != canonical_level_hash(b)


def test_level_order_lists_all_actors_in_export_order():
    assert level_order(parse_t3d(_TWO_BRUSHES)) == ["B_first", "Lamp", "B_second"]


def _levelinfo_named(name):
    # A level whose singleton LevelInfo has the given actor Name, plus one plain actor.
    lv = parse_t3d(f"Begin Map\n"
                   f"Begin Actor Class=Engine.LevelInfo Name={name}\n    Name=\"{name}\"\nEnd Actor\n"
                   f"Begin Actor Class=Engine.Light Name=L1\n    Name=\"L1\"\nEnd Actor\nEnd Map")
    lv.order = level_order(lv)
    return lv


def test_compare_view_ignores_the_levelinfo_singleton_name():
    # The LevelInfo actor Name is engine-managed, not authored: a trunk 'LevelInfo_4dosan'
    # re-exports as the editor's 'LevelInfo0' (confirmed live 2026-07-14), so the two must COMPARE
    # equal or every materialize post-verify fails. Both the actor map and the order must ignore
    # it (the name is in both).
    from uedctl.normalize import compare_view
    d = StubDefaults()
    assert (compare_view(_levelinfo_named("LevelInfo_4dosan"), defaults=d)
            == compare_view(_levelinfo_named("LevelInfo0"), defaults=d))


def test_the_identity_hash_does_NOT_ignore_the_levelinfo_singleton_name():
    # ...but the HASH does NOT, deliberately. It is the preview build-cache key
    # (`preview_game.materialized_dx`), so every equivalence folded into it is a chance to serve a
    # cached map for a level it was not built from. Being stricter than the compare only ever costs
    # a rebuild; being looser serves the wrong map.
    assert (canonical_level_hash(_levelinfo_named("LevelInfo_4dosan"))
            != canonical_level_hash(_levelinfo_named("LevelInfo0")))


def _f32_level(zval):
    from uedctl.model import Actor, Brush, Level, Polygon
    from decimal import Decimal
    a = Actor(name="B", cls="Engine.Brush")
    a.brush = Brush(model_name="Model0",
                    polys=[Polygon(texture="T", origin=(Decimal("43.552099"),
                                                        Decimal("43.552099"), Decimal(zval)))])
    lv = Level(actors={"B": a}); lv.order = ["B"]
    return lv


def test_compare_view_quantizes_coords_to_float32():
    # A rotated brush's Origin at full decimal precision (43.552099) and its editor float32
    # round-trip (43.552097) must compare IDENTICALLY -- else every non-grid brush fails
    # post-verify (confirmed live 2026-07-14). A grid coord is untouched.
    # The reduction lives in the COMPARE path, NOT canonical_actor_t3d (which is also the
    # trunk/import emit -- see the faithfulness test below).
    from uedctl.normalize import compare_view
    d = StubDefaults()
    assert compare_view(_f32_level("-18.333333"), defaults=d) == \
           compare_view(_f32_level("-18.333332"), defaults=d)


def test_the_identity_hash_does_NOT_quantize_coords_to_float32():
    # Same rationale as the LevelInfo case: the cache key stays byte-exact on the authored trunk.
    assert canonical_level_hash(_f32_level("-18.333333")) != \
           canonical_level_hash(_f32_level("-18.333332"))


def test_compare_view_ignores_the_recomputed_poly_normal():
    # The importer recomputes a poly's Normal from vertex winding and ignores the authored one
    # (unrealed/t3d.md), so a level's authored normal and its re-export differ STRUCTURALLY. The
    # COMPARE must ignore it -- two levels with identical vertices but different authored normals
    # compare IDENTICALLY.
    from uedctl.normalize import compare_view
    from uedctl.model import Actor, Brush, Level, Polygon
    from decimal import Decimal
    verts = [(Decimal("0"), Decimal("0"), Decimal("0")), (Decimal("64"), Decimal("0"), Decimal("0")),
             (Decimal("64"), Decimal("64"), Decimal("0"))]

    def _lvl(nz):
        a = Actor(name="B", cls="Engine.Brush")
        a.brush = Brush(model_name="Model0",
                        polys=[Polygon(texture="T", normal=(Decimal("0"), Decimal("0"), Decimal(nz)),
                                       vertices=list(verts))])
        lv = Level(actors={"B": a}); lv.order = ["B"]
        return lv
    d = StubDefaults()
    assert compare_view(_lvl("1"), defaults=d) == compare_view(_lvl("-1"), defaults=d)


def test_canonical_actor_t3d_stays_faithful_for_trunk_and_import():
    # Finding 1 (cold review 2026-07-14): canonical_actor_t3d is ALSO the durable trunk-write
    # (trunk.dump_actor_body) AND the editor/game import payload (apply._materialize `result`).
    # It must therefore keep authored geometry INTACT -- NOT float32-round coords and NOT drop the
    # poly Normal -- or it silently corrupts the git-tracked trunk and the import. Only the
    # hash/compare copy gets those reductions.
    from uedctl.normalize import canonical_actor_t3d
    from uedctl.model import Actor, Brush, Polygon
    from decimal import Decimal
    a = Actor(name="B", cls="Brush")
    a.brush = Brush(model_name="Model0",
                    polys=[Polygon(texture="T", origin=(Decimal("43.552099"), Decimal("0"), Decimal("0")),
                                   normal=(Decimal("0"), Decimal("0"), Decimal("1")),
                                   vertices=[(Decimal("64"), Decimal("-128"), Decimal("0"))])])
    out = canonical_actor_t3d(a)
    assert "Normal" in out                          # Normal PRESERVED (faithful for trunk/import)
    assert "+00043.552099" in out                   # FULL precision preserved, not float32 ...097
    assert "+00064.000000" in out and "-00128.000000" in out       # integers exact


def test_canonical_level_hash_still_distinguishes_a_real_actor_rename():
    # Only the LevelInfo singleton's name is noise; a NON-LevelInfo actor's name is real content.
    a = _levelinfo_named("LevelInfo0")
    b = parse_t3d("Begin Map\n"
                  "Begin Actor Class=Engine.LevelInfo Name=LevelInfo0\n    Name=\"LevelInfo0\"\nEnd Actor\n"
                  "Begin Actor Class=Light Name=L_RENAMED\n    Name=\"L_RENAMED\"\nEnd Actor\nEnd Map")
    b.order = level_order(b)
    assert canonical_level_hash(a) != canonical_level_hash(b)


_WITH_BUILDER_BRUSH = (
    "Begin Map\n"
    "Begin Actor Class=Brush Name=Brush0\n"
    "    Begin Brush Name=Brush\n       Begin PolyList\n       End PolyList\n    End Brush\n"
    "    Brush=Model'MyLevel.Brush'\n    Name=\"Brush0\"\nEnd Actor\n"
    "Begin Actor Class=Light Name=L1\n    Name=\"L1\"\nEnd Actor\nEnd Map")


_CONTENT_BRUSH0 = (
    "Begin Map\n"
    "Begin Actor Class=Brush Name=Brush0\n"
    "    CsgOper=CSG_Add\n"
    "    Begin Brush Name=Model5\n       Begin PolyList\n       End PolyList\n    End Brush\n"
    "    Brush=Model'MyLevel.Model5'\n    Name=\"Brush0\"\nEnd Actor\n"
    "Begin Actor Class=Light Name=L1\n    Name=\"L1\"\nEnd Actor\nEnd Map")


def test_is_builder_brush_true_for_brush0_with_no_csgoper():
    from uedctl.normalize import is_builder_brush
    lv = parse_t3d(_WITH_BUILDER_BRUSH)
    assert is_builder_brush(lv.actors["Brush0"]) is True


def test_is_builder_brush_false_for_brush0_with_explicit_csgoper():
    from uedctl.normalize import is_builder_brush
    lv = parse_t3d(_CONTENT_BRUSH0)
    assert is_builder_brush(lv.actors["Brush0"]) is False


def test_level_order_excludes_the_builder_brush():
    assert level_order(parse_t3d(_WITH_BUILDER_BRUSH)) == ["L1"]


def test_level_order_and_normalize_keep_a_content_brush_named_brush0():
    lv = parse_t3d(_CONTENT_BRUSH0)
    assert level_order(lv) == ["Brush0", "L1"]
    normalize_level(lv)
    assert "Brush0" in lv.actors and "L1" in lv.actors


def test_level_order_set_equals_normalized_content_set():
    lv = parse_t3d(_WITH_BUILDER_BRUSH)
    order = level_order(lv)
    normalize_level(lv)
    assert set(order) == set(lv.actors)


_BUILDER_BRUSH1 = (
    "Begin Map\n"
    "Begin Actor Class=Brush Name=Brush1\n"
    "    Begin Brush Name=Brush\n       Begin PolyList\n       End PolyList\n    End Brush\n"
    "    Brush=Model'MyLevel.Brush'\n    Name=\"Brush1\"\nEnd Actor\n"
    "Begin Actor Class=Light Name=L1\n    Name=\"L1\"\nEnd Actor\nEnd Map")


def test_is_builder_brush_true_for_brush1_fresh_editor_name():
    # Task 4a: a fresh editor numbers the builder brush Brush1 (not Brush0). The model-name
    # + no-CsgOper predicate must still strip it; a Name=="Brush0" rule would NOT.
    from uedctl.normalize import is_builder_brush
    lv = parse_t3d(_BUILDER_BRUSH1)
    assert is_builder_brush(lv.actors["Brush1"]) is True


def test_level_order_excludes_a_brush1_builder_brush():
    assert level_order(parse_t3d(_BUILDER_BRUSH1)) == ["L1"]


def test_is_builder_brush_false_for_a_content_model_named_brush_actor():
    # A content brush keeps an explicit CsgOper even if it happened to be Brush-named; the
    # CsgOper check excludes it regardless of model name.
    from uedctl.normalize import is_builder_brush
    lv = parse_t3d(
        "Begin Map\nBegin Actor Class=Brush Name=Brush2\n    CsgOper=CSG_Subtract\n"
        "    Begin Brush Name=Brush\n       Begin PolyList\n       End PolyList\n    End Brush\n"
        "    Brush=Model'MyLevel.Brush'\n    Name=\"Brush2\"\nEnd Actor\nEnd Map")
    assert is_builder_brush(lv.actors["Brush2"]) is False


# --- store-centric pivot: LevelInfo strips + M2 self-ref canonicalization ---
from uedctl.model import parse_t3d as _parse_t3d
from uedctl.normalize import (normalize_actor as _normalize_actor,
                              canonicalize_self_refs, canonical_actor_t3d as _canon)


def test_it_strips_levelinfo_runtime_list_heads():
    lv = _parse_t3d(
        "Begin Map\nBegin Actor Class=LevelInfo Name=LevelInfo0\n"
        "    Title=\"X\"\n    NavigationPointList=PathNode'MyLevel.PathNode0'\n"
        "    PawnList=Pawn'MyLevel.Pawn3'\n    Name=\"LevelInfo0\"\nEnd Actor\nEnd Map")
    a = lv.actors["LevelInfo0"]
    _normalize_actor(a)
    keys = {k for k, _ in a.props}
    assert "NavigationPointList" not in keys and "PawnList" not in keys
    assert "Title" in keys


def test_it_strips_the_navigation_point_runtime_links():
    # next/prevNavigationPoint are the per-actor halves of the SAME PATHS DEFINE-rebuilt graph
    # NavigationPointList/PawnList are the per-level heads of -- never survive a fresh MAP NEW +
    # FULL RE-IMPORT (materialize.py never runs a paths build).
    lv = _parse_t3d(
        "Begin Map\nBegin Actor Class=Teleporter Name=Teleporter0\n"
        "    URL=\"19_multiport\"\n"
        "    nextNavigationPoint=PlayerStart'MyLevel.PlayerStart0'\n"
        "    prevNavigationPoint=PlayerStart'MyLevel.PlayerStart1'\n"
        "    Name=\"Teleporter0\"\nEnd Actor\nEnd Map")
    a = lv.actors["Teleporter0"]
    _normalize_actor(a)
    keys = {k for k, _ in a.props}
    assert "nextNavigationPoint" not in keys and "prevNavigationPoint" not in keys
    assert "URL" in keys


def test_it_strips_level_and_bselected():
    # Level=/bSelected= are editor-import/session artifacts, never authored content -- a
    # freshly model-side-created actor never has them (2026-06-21, debugging a
    # never-before-materialized actor's first apply).
    lv = _parse_t3d(
        "Begin Map\nBegin Actor Class=Brush Name=B1\n"
        "    Level=LevelInfo'MyLevel.LevelInfo0'\n    bSelected=True\n"
        "    CsgOper=CSG_Add\n    Name=\"B1\"\nEnd Actor\nEnd Map")
    a = lv.actors["B1"]
    _normalize_actor(a)
    keys = {k for k, _ in a.props}
    assert not ({"Level", "bSelected"} & keys)
    assert "CsgOper" in keys


def test_normalize_actor_never_strips_a_tag_from_the_trunk():
    # The editor's default-stamp (an unset Tag comes back as the bare class name) is dropped on the
    # COMPARE VIEW only -- see the typed-compare tests below. It must NOT be dropped here:
    # normalize_actor feeds canonical_actor_t3d, i.e. the git-tracked trunk AND the MAP IMPORT
    # payload, and for the 5 TNM classes that default `Tag` (TNM.Trestkon = 'Player') deleting a
    # `Tag=Trestkon` silently re-imports the actor tagged `Player`, breaking its event wiring.
    lv = _parse_t3d(
        "Begin Map\nBegin Actor Class=Brush Name=B1\n"
        "    Tag=Brush\n    CsgOper=CSG_Add\n    Name=\"B1\"\nEnd Actor\nEnd Map")
    a = lv.actors["B1"]
    _normalize_actor(a)
    assert ("Tag", "Brush") in a.props


def test_it_keeps_a_genuinely_authored_tag():
    # A Tag that does NOT match the bare class name is real authored content (e.g.
    # tests/fixtures/add_light.t3d's Tag=SpikeProbe on a Light actor) -- stripping it
    # unconditionally would silently erase real data on the next record_mutation/session seed
    # (GPT-5.4 review, 2026-06-21, caught an earlier version of this fix doing exactly that).
    lv = _parse_t3d(
        "Begin Map\nBegin Actor Class=Light Name=L1\n"
        "    Tag=SpikeProbe\n    Name=\"L1\"\nEnd Actor\nEnd Map")
    a = lv.actors["L1"]
    _normalize_actor(a)
    assert ("Tag", "SpikeProbe") in a.props


def test_it_keeps_a_tag_matching_a_DIFFERENT_actors_class():
    # The default-stamp check is scoped to THIS actor's own class -- a Tag that happens to equal
    # some other class name entirely is still real content, not a coincidental default-stamp.
    lv = _parse_t3d(
        "Begin Map\nBegin Actor Class=Light Name=L1\n"
        "    Tag=Brush\n    Name=\"L1\"\nEnd Actor\nEnd Map")
    a = lv.actors["L1"]
    _normalize_actor(a)
    assert ("Tag", "Brush") in a.props


def test_normalize_actor_keeps_an_all_zero_location_in_the_trunk():
    # THE `Engine.Camera` BUG (2026-07-25). normalize_actor used to clear an all-zero Location to
    # None -- into canonical_actor_t3d, i.e. into the trunk AND the MAP IMPORT payload. An omitted
    # Location does not re-import as the origin: it re-imports as the CLASS DEFAULT, and
    # `Engine.Camera` defaults `(X=-500,Y=-300,Z=300)`, so a camera authored at the origin was
    # silently built 655 uu away -- and the post-verify PASSED, because both compare sides had
    # dropped the same line. The compare-side equivalence now lives in the typed compare, which
    # resolves an omitted property to the real class default.
    from decimal import Decimal
    lv = _parse_t3d(
        "Begin Map\nBegin Actor Class=Engine.Camera Name=Cam1\n"
        "    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n    Name=\"Cam1\"\nEnd Actor\nEnd Map")
    a = lv.actors["Cam1"]
    assert a.location == (Decimal(0), Decimal(0), Decimal(0))
    _normalize_actor(a)
    assert a.location == (Decimal(0), Decimal(0), Decimal(0))
    # And it must reach the EMITTED form -- the trunk file and the import payload, not just the
    # parsed field.
    assert "Location=(X=0.000000,Y=0.000000,Z=0.000000)" in canonical_actor_t3d(a)


def test_it_leaves_a_nonzero_location_untouched():
    from decimal import Decimal
    lv = _parse_t3d(
        "Begin Map\nBegin Actor Class=Brush Name=B1\n"
        "    Location=(X=10.000000,Y=0.000000,Z=0.000000)\n    Name=\"B1\"\nEnd Actor\nEnd Map")
    a = lv.actors["B1"]
    _normalize_actor(a)
    assert a.location == (Decimal(10), Decimal(0), Decimal(0))


def test_it_canonicalizes_the_self_ref_package_stem_to_mylevel():
    txt = ("Begin Actor Class=LevelInfo Name=LevelInfo0\n"
           "    Level=LevelInfo'spike13.LevelInfo0'\n"
           "    Name=\"LevelInfo0\"\nEnd Actor\n")
    out = canonicalize_self_refs(txt)
    assert "MyLevel.LevelInfo0" in out and "spike13." not in out


def test_it_canonicalizes_brush_model_self_ref():
    txt = ("Begin Actor Class=Brush Name=RoomBrush\n"
           "    Brush=Model'mymap.Model7'\n    Name=\"RoomBrush\"\nEnd Actor\n")
    assert "MyLevel.Model7" in canonicalize_self_refs(txt)


def test_it_canonicalizes_a_deusexlevelinfo_self_ref():
    txt = "    Level=DeusExLevelInfo'20_train.DeusExLevelInfo0'\n"
    out = canonicalize_self_refs(txt)
    assert "MyLevel.DeusExLevelInfo0" in out and "20_train." not in out


def test_it_leaves_foreign_package_refs_alone():
    txt = "    DefaultTexture=Texture'Engine.DefaultTexture'\n"
    assert canonicalize_self_refs(txt) == txt


def test_canonical_actor_t3d_applies_self_ref_canonicalization():
    a = _parse_t3d("Begin Map\nBegin Actor Class=Brush Name=B\n"
                   "    Brush=Model'ondisk.Model1'\n    Name=\"B\"\nEnd Actor\nEnd Map").actors["B"]
    assert "MyLevel.Model1" in _canon(a)


def test_it_strips_editor_derived_basepos_baserot_but_keeps_keyframes():
    from uedctl.normalize import normalize_actor
    t3d = (
        "Begin Map\nBegin Actor Class=Mover Name=Door1\n"
        "    BasePos=(Z=100.000000)\n    BaseRot=(Yaw=8192)\n"
        "    OldLocation=(Z=100.000000)\n"
        "    KeyPos(1)=(Z=256.000000)\n    KeyRot(1)=(Yaw=16384)\n"
        "    MultiSkins(2)=Texture'Pkg.Skin'\n    AIProfile(0)=830\n"
        '    Name="Door1"\nEnd Actor\nEnd Map\n'
    )
    actor = parse_t3d(t3d).actors["Door1"]
    normalize_actor(actor)
    keys = {k for k, _ in actor.props}
    assert "BasePos" not in keys and "BaseRot" not in keys and "OldLocation" not in keys
    assert "AIProfile(0)" not in keys          # stripped by the AIProfile prefix rule
    assert "KeyPos(1)" in keys and "KeyRot(1)" in keys and "MultiSkins(2)" in keys


def test_authored_mover_hashes_equal_to_its_editor_reexported_form():
    authored = parse_t3d(
        "Begin Map\nBegin Actor Class=Engine.Mover Name=M\n"
        "    Location=(Z=100.000000)\n    KeyPos(1)=(Z=256.000000)\n"
        '    Name="M"\nEnd Actor\nEnd Map\n').actors["M"]
    reexported = parse_t3d(
        "Begin Map\nBegin Actor Class=Engine.Mover Name=M\n"
        "    BasePos=(Z=100.000000)\n    OldLocation=(Z=100.000000)\n"
        "    Location=(Z=100.000000)\n    KeyPos(1)=(Z=256.000000)\n"
        '    Name="M"\nEnd Actor\nEnd Map\n').actors["M"]
    assert canonical_actor_t3d(authored) == canonical_actor_t3d(reexported)


# --- mover Saved* sentinels: engine-stamped by AMover::PostLoad (spike 2026-07-25) -------------
#
# `AMover::PostLoad()` overwrites SavedPos/SavedRot with a fixed "not saved yet" sentinel on EVERY
# load of a Mover object, unconditionally, before any code can read what the map file stored. So a
# uedctl-authored mover (which omits both) and the map it materializes into (which comes back
# carrying the sentinel) MUST compare equal, or `level materialize` refuses to write every mover
# map. See dev/docs/spikes/2026-07-25-mover-savedpos-savedrot-engine-stamped/findings.md.

_SAVED_POS = "(X=-12345.000000,Y=-12345.000000,Z=-12345.000000)"
_SAVED_ROT = "(Pitch=123,Yaw=456,Roll=789)"


def _mover_level(*, stamped: bool):
    """A one-mover level; `stamped` adds exactly what the editor's re-export carries back."""
    from uedctl.normalize import level_order
    extra = (f"    SavedPos={_SAVED_POS}\n    SavedRot={_SAVED_ROT}\n"
             "    BasePos=(Z=100.000000)\n    BaseRot=(Yaw=8192)\n") if stamped else ""
    lv = parse_t3d(
        "Begin Map\nBegin Actor Class=Engine.Mover Name=Door\n"
        f"{extra}"
        "    Location=(X=0.000000,Y=0.000000,Z=100.000000)\n    Rotation=(Yaw=8192)\n"
        "    KeyPos(1)=(Z=256.000000)\n"
        '    Name="Door"\nEnd Actor\nEnd Map\n')
    lv.order = level_order(lv)
    return lv


def test_it_strips_the_engine_stamped_mover_saved_sentinels():
    from uedctl.normalize import normalize_actor
    actor = _mover_level(stamped=True).actors["Door"]
    normalize_actor(actor)
    keys = {k for k, _ in actor.props}
    assert "SavedPos" not in keys and "SavedRot" not in keys
    assert "KeyPos(1)" in keys                    # authored keyframes are untouched


def test_a_trunk_mover_compares_equal_to_its_editor_reexport_carrying_the_saved_sentinels():
    """THE regression for the materialize abort: the trunk omits SavedPos/SavedRot, the rebuilt
    map's re-export carries the sentinels, and the H3 post-verify must see NO difference."""
    from uedctl.normalize import compare_view
    d = StubDefaults(schema={"Engine.Mover": {"SavedPos": "struct:X=float,Y=float,Z=float",
                                              "SavedRot": "struct:Pitch=int,Yaw=int,Roll=int",
                                              "BasePos": "struct:X=float,Y=float,Z=float",
                                              "BaseRot": "struct:Pitch=int,Yaw=int,Roll=int"}})
    assert (compare_view(_mover_level(stamped=True), defaults=d)
            == compare_view(_mover_level(stamped=False), defaults=d))


def test_savedtrigger_is_deliberately_NOT_treated_as_computed():
    """`AMover::PostLoad` does not touch `SavedTrigger`, and it appears zero times in the whole
    committed export corpus — so it is left alone under the same "no unverified-symbol guesses"
    rule that keeps `OldRot` out. This test exists so adding it becomes a deliberate act with
    evidence attached, not a drive-by."""
    from uedctl.normalize import is_computed_key
    assert not is_computed_key("SavedTrigger")


# --- is_computed_key: case-insensitive (decision 2026-06-26 12:41 UTC) -----------------------

def test_it_detects_computed_keys_case_insensitively():
    from uedctl.normalize import is_computed_key
    for k in ("Region", "region", "REGION", "OldLocation", "oldlocation", "bSelected"):
        assert is_computed_key(k), k


def test_it_detects_the_aiprofile_prefix_case_insensitively():
    from uedctl.normalize import is_computed_key
    assert is_computed_key("AIProfile(0)")
    assert is_computed_key("aiprofile(3)")


def test_it_does_not_flag_authored_props_as_computed():
    from uedctl.normalize import is_computed_key
    for k in ("LightBrightness", "Tag", "PrePivot", "Rotation", "CsgOper", "PolyFlags", "Group",
              # `bDynamicLightMover` and the `KeyPos[]`/`KeyRot[]` arrays were flagged as possibly
              # editor-injected too when the mover `Saved*` bug was reported. A live materialize of
              # a mover carrying `NumKeys=3`, `KeyPos(1)` and `bDynamicLightMover=True` re-exported
              # all three VERBATIM (spike 2026-07-25 §5), so they are authored content — stripping
              # them would silently erase a mover's animation. (`KeyRot(1)` is `KeyPos`'s symmetric
              # counterpart, covered by the same emit/parse path.)
              "bDynamicLightMover", "KeyPos(1)", "KeyRot(1)", "NumKeys"):
        assert not is_computed_key(k), k


def test_no_computed_prop_case_collides_with_a_plausibly_authored_prop():
    # Guard the global case-fold change: a folded COMPUTED_PROPS member must not equal a folded
    # real authored prop (which would silently strip authored content).
    from uedctl.normalize import COMPUTED_PROPS
    authored = {"LightBrightness", "LightRadius", "LightHue", "Tag", "PrePivot", "Rotation",
                "CsgOper", "PolyFlags", "Group", "Event", "Physics", "Mass", "Skin"}
    folded_computed = {c.casefold() for c in COMPUTED_PROPS}
    collisions = {a for a in authored if a.casefold() in folded_computed}
    assert collisions == set(), collisions




# ═══ The TYPED compare: two actors are equal iff they IMPORT TO THE SAME OBJECT ═══════════════
#
# UnrealEd's export is member-precise default-diffing: it omits a whole property equal to the class
# default and omits a struct member equal to the default member (`unrealed/t3d.md`). uedctl's
# producers write everything explicitly. So the built map's re-export and the trunk it was built
# from state the SAME values in DIFFERENT TEXT. The compare therefore resolves each property to its
# EFFECTIVE TYPED VALUE — the stored value if present, else the class default, decoded by the
# declared type — instead of canonicalizing text (decision 2026-07-25: typed values dissolve the
# spelling problem rather than tolerating it).

from uedctl.normalize import compare_view


def _one_actor_level(body, cls="Engine.Light", name="A1"):
    lv = parse_t3d(f"Begin Map\nBegin Actor Class={cls} Name={name}\n{body}"
                   f'    Name="{name}"\nEnd Actor\nEnd Map\n')
    lv.order = level_order(lv)
    return lv


def _same(a_body, b_body, *, cls, defaults):
    """Whether two spellings of one actor compare EQUAL through the post-verify's own view."""
    return (compare_view(_one_actor_level(a_body, cls=cls), defaults=defaults)
            == compare_view(_one_actor_level(b_body, cls=cls), defaults=defaults))


_ROT = "struct:Pitch=int,Yaw=int,Roll=int"
_VEC = "struct:X=float,Y=float,Z=float"


# --- FRotator: member-wise against the CLASS default -------------------------------------------

_START = StubDefaults(schema={"Engine.PlayerStart": {"Rotation": _ROT}})


def test_a_yaw_only_actor_compares_equal_to_its_editor_reexport():
    """THE ORIGINAL REPORTED BUG. `--rotate 0,16384,0` writes `(Pitch=0,Yaw=16384,Roll=0)`; UnrealEd
    re-exports `(Yaw=16384)`, omitting the members equal to the default member. Typed, both decode
    to the same rotator, so they are simply the same value."""
    assert _same("    Rotation=(Pitch=0,Yaw=16384,Roll=0)\n", "    Rotation=(Yaw=16384)\n",
                 cls="Engine.PlayerStart", defaults=_START)


def test_an_explicit_all_zero_rotation_compares_equal_to_an_absent_one():
    """The editor omits the line entirely when the rotator matches the (zero) class default."""
    assert _same("    Rotation=(Pitch=0,Yaw=0,Roll=0)\n", "",
                 cls="Engine.PlayerStart", defaults=_START)


def test_a_different_rotation_still_fails_the_compare():
    """NEGATIVE CONTROL: expansion must not collapse a real difference."""
    assert not _same("    Rotation=(Yaw=16384)\n", "    Rotation=(Yaw=8192)\n",
                     cls="Engine.PlayerStart", defaults=_START)


def test_over_range_rotation_components_are_never_reduced_mod_65536():
    """REGRESSION GUARD against decoding a component through `rotation.parse_frotator`'s `% 65536`.
    UnrealEd stores an FRotator field VERBATIM — `Yaw=-131072`, `-65536` and `-81920` all occur in
    the committed retail corpus (live-probed 2026-07-25,
    `dev/docs/spikes/2026-07-25-frotator-import-normalization/findings.md`). `-131072 % 65536 == 0`,
    so a mod-reducing decode would make an over-range rotator compare EQUAL to an unrotated actor —
    a false pass on a wrong map — as well as rewriting 20,109 of the corpus's 23,960 components."""
    for over in ("(Yaw=-131072)", "(Yaw=-65536)", "(Yaw=65536)", "(Yaw=-81920)"):
        assert not _same(f"    Rotation={over}\n", "", cls="Engine.PlayerStart", defaults=_START), over
        assert _same(f"    Rotation={over}\n", f"    Rotation={over.replace(')', ',Pitch=0,Roll=0)')}\n",
                     cls="Engine.PlayerStart", defaults=_START), over


def test_the_compare_is_case_insensitive_on_the_property_key():
    """FName semantics, matching `is_computed_key` — a hand-edited or imported `rotation=` must
    compare as `Rotation`, or it silently aborts materialize."""
    assert _same("    rotation=(Yaw=16384)\n", "    Rotation=(Pitch=0,Yaw=16384,Roll=0)\n",
                 cls="Engine.PlayerStart", defaults=_START)


def test_a_partial_struct_expands_against_ITS_OWN_class_default_not_zero():
    """THE GENERALIZED MEMBER-DIFF (it used to exist for `Rotation` only). 228 classes default
    `RotationRate` non-zero — `DeusEx.Rat` is `(Pitch=4096,Yaw=65530,Roll=3072)` — so the editor's
    `RotationRate=(Yaw=1234)` means Pitch=4096/Roll=3072, NOT zero. Expanding member-wise from the
    class default makes it equal to the full authored spelling and UNEQUAL to a zero-filled one."""
    d = StubDefaults({"DeusEx.Rat": {("rotationrate", 0): "(Pitch=4096,Yaw=65530,Roll=3072)"}},
                     schema={"DeusEx.Rat": {"RotationRate": _ROT}})
    assert _same("    RotationRate=(Yaw=1234)\n",
                 "    RotationRate=(Pitch=4096,Yaw=1234,Roll=3072)\n", cls="DeusEx.Rat", defaults=d)
    assert not _same("    RotationRate=(Yaw=1234)\n",
                     "    RotationRate=(Pitch=0,Yaw=1234,Roll=0)\n", cls="DeusEx.Rat", defaults=d)


def test_an_unrecognized_struct_member_is_kept_rather_than_guessed_at():
    """A member the schema does not know is compared verbatim rather than dropped, so it can never
    be silently ignored (which would make two different actors compare equal)."""
    assert not _same("    Rotation=(Bogus=3)\n", "    Rotation=(Bogus=4)\n",
                     cls="Engine.PlayerStart", defaults=_START)
    assert _same("    Rotation=(Bogus=3)\n", "    Rotation=(Bogus=3)\n",
                 cls="Engine.PlayerStart", defaults=_START)


# --- whole properties equal to the class default ------------------------------------------------

def test_a_property_equal_to_the_class_default_compares_equal_to_an_omitted_line():
    """The five default-equal properties measured in this repo's own trunks (`uedctl/maps/*`). The
    editor omits every one of them on re-export, so before the default-aware compare each aborted
    `level materialize` with nothing written. `StayOpenTime` is the TYPED case that a text compare
    could not solve: the trunk stores `4.0`, the class default renders `4`."""
    cases = [
        ("DeusEx.DeusExMover", "MoverGlideType", "MV_GlideByTime", "MV_GlideByTime",
         "enum:MV_MoveByTime,MV_GlideByTime"),
        ("DeusEx.DeusExMover", "StayOpenTime", "4.0", "4", "float"),
        ("Engine.Light", "LightPeriod", "32", "32", "byte"),
        ("Engine.Spotlight", "LightEffect", "LE_Spotlight", "LE_Spotlight",
         "enum:LE_None,LE_TorchWaver,LE_Spotlight"),
        ("Engine.AmbientSound", "SoundRadius", "64", "64", "byte"),
    ]
    for cls, key, stored, default, kind in cases:
        d = StubDefaults({cls: {(key.casefold(), 0): default}}, schema={cls: {key: kind}})
        assert _same(f"    {key}={stored}\n", "", cls=cls, defaults=d), f"{cls}.{key}={stored}"


def test_a_property_that_differs_from_the_class_default_still_fails():
    """NEGATIVE CONTROL — `Engine.AmbientSound` defaults `SoundRadius=64`, so 64 compares equal to
    an omitted line but 65 must not, or a genuinely wrong map passes the post-verify."""
    d = StubDefaults({"Engine.AmbientSound": {("soundradius", 0): "64"}},
                     schema={"Engine.AmbientSound": {"SoundRadius": "byte"}})
    assert not _same("    SoundRadius=65\n", "", cls="Engine.AmbientSound", defaults=d)
    assert not _same("    SoundRadius=65\n", "    SoundRadius=64\n",
                     cls="Engine.AmbientSound", defaults=d)


def test_an_enum_compares_by_ordinal_so_a_name_and_a_number_are_one_value():
    """`uprops` renders a whole-property enum default as its NAME but a struct-MEMBER enum as its
    raw ordinal (`_decode_struct_bin_at`), and T3D always writes the name. Normalizing to the
    ordinal is what makes the two forms one value."""
    d = StubDefaults({"Engine.Light": {("lighteffect", 0): "2"}},
                     schema={"Engine.Light": {"LightEffect": "enum:LE_None,LE_TorchWaver,LE_Spotlight"}})
    assert _same("    LightEffect=LE_Spotlight\n", "", cls="Engine.Light", defaults=d)
    assert not _same("    LightEffect=LE_TorchWaver\n", "", cls="Engine.Light", defaults=d)


# --- zero-valued SCALARS: the type's zero comes from the SCHEMA, never from the text ------------

def test_an_explicit_zero_scalar_compares_equal_to_an_omitted_line():
    """`actor prop set X LightRadius=0` followed by `level materialize` used to ABORT: the editor
    omits `LightRadius=0` (it equals the class default) while the trunk states it, and the old
    text-canonicalizing compare deliberately refused to drop a zero SCALAR because it could not
    tell a zero byte from a string that reads `0`. Typed, `LightRadius` is a ByteProperty whose
    zero is the integer 0, so the two are the same value."""
    d = StubDefaults(schema={"Engine.Light": {"LightRadius": "byte"}})
    assert _same("    LightRadius=0\n", "", cls="Engine.Light", defaults=d)
    assert not _same("    LightRadius=1\n", "", cls="Engine.Light", defaults=d)


def test_a_false_bool_compares_equal_to_an_omitted_line_but_only_where_the_class_agrees():
    """Same rule for bools — and the guard: `Engine.Light` defaults `bHidden=True`, so an explicit
    `bHidden=False` there is a REAL difference from the omitted line, not a spelling of it."""
    plain = StubDefaults(schema={"Engine.Brush": {"bHidden": "bool"}})
    assert _same("    bHidden=False\n", "", cls="Engine.Brush", defaults=plain)
    hidden = StubDefaults({"Engine.Light": {("bhidden", 0): "True"}},
                          schema={"Engine.Light": {"bHidden": "bool"}})
    assert not _same("    bHidden=False\n", "", cls="Engine.Light", defaults=hidden)


def test_a_STRING_property_that_reads_zero_is_not_the_zero_of_its_type():
    """THE FALSE-PASS GUARD that kept zero-scalars out of the old text-based compare. `parse_t3d`
    discards quoting, so `Title="0"` and `Title=0` are the same text in the model — but a
    StrProperty's zero is the EMPTY string, so an explicit `0` must still differ from an omitted
    line. Only the declared type can tell those apart; the text never could."""
    d = StubDefaults(schema={"Engine.LevelInfo": {"Title": "string"}})
    assert not _same('    Title="0"\n', "", cls="Engine.LevelInfo", defaults=d)
    assert _same('    Title=""\n', "", cls="Engine.LevelInfo", defaults=d)


def test_an_untyped_property_is_never_matched_against_an_invented_zero():
    """NO FABRICATED DEFAULTS. With no declared type and no class default there is no zero to
    compare against, so an explicit value can never compare equal to an omitted one — the compare
    fails loudly instead of guessing (which is how a wrong map would pass)."""
    assert not _same("    Mystery=0\n", "", cls="Engine.Light", defaults=StubDefaults())


# --- Location: an omitted axis means the class DEFAULT member, not zero -------------------------

_CAMERA = StubDefaults(
    {"Engine.Camera": {("location", 0): "(X=-500,Y=-300,Z=300)"}},
    schema={"Engine.Camera": {"Location": _VEC}})


def test_an_editor_export_that_omits_an_axis_compares_as_the_class_default_not_zero():
    """DEFECT 2. `Engine.Camera` defaults `Location=(X=-500,Y=-300,Z=300)`, so the editor writes
    `Location=(X=100,Y=200)` for a camera at `(100,200,300)` — the Z is omitted because it equals
    the default member. `parse_t3d` zero-fills the triple for the geometry consumers, so the
    compare must read the omission from the verbatim text side-channel and expand it against the
    class default. Reading it as Z=0 silently drops 300 uu."""
    editor = _one_actor_level("    Location=(X=100.000000,Y=200.000000)\n", cls="Engine.Camera")
    trunk = _one_actor_level("    Location=(X=100.000000,Y=200.000000,Z=300.000000)\n",
                             cls="Engine.Camera")
    at_zero = _one_actor_level("    Location=(X=100.000000,Y=200.000000,Z=0.000000)\n",
                               cls="Engine.Camera")
    assert compare_view(editor, defaults=_CAMERA) == compare_view(trunk, defaults=_CAMERA)
    assert compare_view(editor, defaults=_CAMERA) != compare_view(at_zero, defaults=_CAMERA)


def test_sub_grid_coordinate_NOISE_in_a_location_compares_equal_to_the_snapped_trunk_value():
    """REGRESSION (cold review, 2026-07-25). The trunk emit snaps a coordinate within `CLEAN_EPS`
    (0.001) of an integer onto it — `emit.clean`, applied when the value was WRITTEN — while the
    editor re-exports its own float32 value verbatim (`Y=7215.999512`). Both compare sides must pass
    through the same snap, or every actor the editor nudged sub-grid aborts the post-verify with
    nothing written. Measured on a real retail export before the fix: 49 of 5125 actors."""
    noisy = _one_actor_level("    Location=(X=100.000000,Y=7215.999512,Z=-4832.000977)\n")
    snapped = _one_actor_level("    Location=(X=100.000000,Y=7216.000000,Z=-4832.000000)\n")
    d = StubDefaults(schema={"Engine.Light": {"Location": _VEC}})
    assert compare_view(noisy, defaults=d) == compare_view(snapped, defaults=d)
    # ...but a REAL sub-unit difference (past CLEAN_EPS) still fails.
    off = _one_actor_level("    Location=(X=100.000000,Y=7215.900000,Z=-4832.000000)\n")
    assert compare_view(off, defaults=d) != compare_view(snapped, defaults=d)


def test_a_model_typed_property_is_typed_the_SAME_WAY_whether_stated_or_omitted():
    """REGRESSION (cold review, 2026-07-25). `Location`/`MainScale`/`PostScale` are parsed out of the
    property list into typed model fields, so the compare re-renders them from the model. If the
    STATING side got the model's layout while the OMITTING side (which goes through
    `ClassInfo.typed_default`) got "no schema entry" → `ABSENT`, the two could never be equal and
    that actor's post-verify would be permanently unpassable. Both go through `ClassInfo.field`."""
    d = StubDefaults()                             # a class with NO schema entries at all
    assert _same("    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n", "",
                 cls="Engine.Light", defaults=d)
    assert _same("    MainScale=(Scale=(X=1.000000,Y=1.000000,Z=1.000000),SheerRate=0.000000,"
                 "SheerAxis=SHEER_ZX)\n", "    MainScale=(SheerAxis=SHEER_ZX)\n",
                 cls="Engine.Brush", defaults=d)
    info = d.for_class("Engine.Light")
    assert info.field("location").members and info.field("mainscale").members


def test_a_camera_at_its_class_default_compares_equal_to_an_export_that_omits_the_line():
    """The editor omits a property equal to the class default, so its re-export of a camera sitting
    at `(-500,-300,300)` carries NO `Location=` line at all. The trunk carries the explicit value
    (it must — see the trunk test below), and the two have to compare EQUAL or `level materialize`
    aborts on the post-verify with nothing written."""
    assert _same("    Location=(X=-500.000000,Y=-300.000000,Z=300.000000)\n", "",
                 cls="Engine.Camera", defaults=_CAMERA)


def test_a_camera_at_the_origin_does_NOT_compare_equal_to_one_at_its_default():
    """THE NEGATIVE CONTROL for the same case: the origin is not the Camera default, so the two must
    stay distinguishable — otherwise the compare would pass on a map built 655 uu off."""
    assert not _same("    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n", "",
                     cls="Engine.Camera", defaults=_CAMERA)


def test_a_camera_authored_at_the_origin_keeps_its_location_in_the_durable_emit():
    """`canonical_actor_t3d` is the git-tracked trunk AND the `MAP IMPORT` payload. An omitted
    `Location` re-imports as the CLASS DEFAULT, so dropping an all-zero one built the camera 655 uu
    away — and post-verify passed, because both sides had dropped the same line (2026-07-25)."""
    a = _one_actor_level("    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n",
                         cls="Engine.Camera").actors["A1"]
    assert "Location=(X=0.000000,Y=0.000000,Z=0.000000)" in canonical_actor_t3d(a)


def test_a_moved_actor_stops_trusting_the_axes_its_source_stated():
    """THE SELF-INVALIDATION RULE. `Actor.location_text` records which axes the source stated, and
    is trusted only while it still parses back to the current `location`. After a move the two
    disagree and the actor compares with all three axes stated — which is right, because the write
    path emits all three. Without this, moving a partially-stated actor would silently keep reading
    the old omitted axis from the class default.

    KNOWN NARROW LIMIT: a move that lands EXACTLY on the zero-filled triple (`--to 100,200,0` here)
    still parses back equal, so the omitted axis keeps reading as the class default. That case can
    only ever produce a spurious ABORT, never a false pass — the built map would carry the moved
    value, the editor would then state it explicitly, and the two sides disagree loudly. Filed with
    the ingest remnant on `board/inbox.md`."""
    from decimal import Decimal as D
    moved = _one_actor_level("    Location=(X=100.000000,Y=200.000000)\n", cls="Engine.Camera")
    moved.actors["A1"].location = (D(100), D(200), D(50))         # what `actor move` writes
    at_50 = _one_actor_level("    Location=(X=100.000000,Y=200.000000,Z=50.000000)\n",
                             cls="Engine.Camera")
    assert compare_view(moved, defaults=_CAMERA) == compare_view(at_50, defaults=_CAMERA)


def test_the_location_text_side_channel_is_never_emitted():
    """It is a compare-side record of the SOURCE spelling, not authored content: it must not reach
    the trunk, the import payload, `actor show`, or the identity hash."""
    a = _one_actor_level("    Location=(X=100.000000,Y=200.000000)\n",
                         cls="Engine.Camera").actors["A1"]
    assert a.location_text == "(X=100.000000,Y=200.000000)"
    assert "Location=(X=100.000000,Y=200.000000,Z=0.000000)" in canonical_actor_t3d(a)


# --- the injectivity guard: absent is NOT the same as an authored zero --------------------------

_LAVA = StubDefaults({"TNM.LavaSpitter": {("rotation", 0): "(Pitch=16384,Yaw=0,Roll=0)"}},
                     schema={"TNM.LavaSpitter": {"Rotation": _ROT}})


def test_lavaspitter_expands_a_partial_rotation_against_its_non_zero_default():
    """`TNM.LavaSpitter` is the only one of 1346 actor classes that defaults `Rotation`
    (`(Pitch=16384,Yaw=0,Roll=0)`). An actor authored level — `(Pitch=0,Yaw=0,Roll=0)` — and the
    editor's re-export of it — `(Pitch=0)`, Yaw/Roll omitted because they equal the default
    members — are the same rotator."""
    assert _same("    Rotation=(Pitch=0,Yaw=0,Roll=0)\n", "    Rotation=(Pitch=0)\n",
                 cls="TNM.LavaSpitter", defaults=_LAVA)


def test_a_lavaspitter_zero_rotation_is_not_the_same_level_as_one_with_no_rotation():
    """THE FALSE-PASS GUARD. For that class "rotator explicitly zero" and "no rotator" are DIFFERENT
    levels: the first is level, the second is pitched 90°. Neither the identity hash (the preview
    build-cache key — collapsing them would serve the wrong map) nor the compare may equate them."""
    explicit = _one_actor_level("    Rotation=(Pitch=0)\n", cls="TNM.LavaSpitter")
    absent = _one_actor_level("", cls="TNM.LavaSpitter")
    assert canonical_level_hash(explicit) != canonical_level_hash(absent)
    assert compare_view(explicit, defaults=_LAVA) != compare_view(absent, defaults=_LAVA)


# --- the editor's Tag default-stamp -------------------------------------------------------------

def test_the_editor_tag_default_stamp_is_dropped_from_the_compare():
    """An actor that never had an explicit `Tag` comes back from the editor stamped with its own
    bare class name (`Tag=Brush` on a Brush). That stamp exists only on the built map's side, so
    leaving it in would fail post-verify for every uedctl-created actor."""
    d = StubDefaults(schema={"Engine.Brush": {"Tag": "name"}})
    assert _same("    Tag=Brush\n", "", cls="Engine.Brush", defaults=d)


def test_a_tag_is_kept_when_the_class_actually_defaults_tag():
    """THE SAFETY GUARD. `TNM.Trestkon` defaults `Tag='Player'` (5 TNM classes default `Tag`), so it
    never gets the class-name stamp — `Tag=Trestkon` there is authored event-wiring content.
    Dropping it would let a map whose Tag the engine replaced with `Player` pass post-verify."""
    d = StubDefaults({"TNM.Trestkon": {("tag", 0): "Player"}},
                     schema={"TNM.Trestkon": {"Tag": "name"}})
    assert not _same("    Tag=Trestkon\n", "", cls="TNM.Trestkon", defaults=d)
    assert _same("    Tag=Player\n", "", cls="TNM.Trestkon", defaults=d)      # default-equal


def test_a_tag_that_is_not_the_class_name_is_always_kept():
    d = StubDefaults(schema={"Engine.Light": {"Tag": "name"}})
    assert not _same("    Tag=SpikeProbe\n", "", cls="Engine.Light", defaults=d)


# --- structs that are entirely at their default -------------------------------------------------

def test_an_all_zero_struct_compares_equal_to_an_omitted_line():
    """`transform.bake` and `actor prop set PrePivot=0,0,0` write all three axes; the editor omits
    the line, because every member equals the (zero) default member."""
    d = StubDefaults(schema={"Engine.Brush": {"PrePivot": _VEC}})
    assert _same("    PrePivot=(X=0.000000,Y=0.000000,Z=0.000000)\n", "",
                 cls="Engine.Brush", defaults=d)


def test_an_all_zero_struct_SURVIVES_where_the_class_defaults_it_non_zero():
    """THE NEGATIVE CONTROL. 17 classes default `PrePivot` non-zero (`DeusEx.Chandelier` =
    `(X=0,Y=0,Z=20.48)`). There an authored all-zero PrePivot is NOT the default — the editor
    exports it, and equating them would let a map whose chandelier hangs 20 uu off pass."""
    d = StubDefaults({"DeusEx.Chandelier": {("prepivot", 0): "(X=0,Y=0,Z=20.48)"}},
                     schema={"DeusEx.Chandelier": {"PrePivot": _VEC}})
    assert not _same("    PrePivot=(X=0.000000,Y=0.000000,Z=0.000000)\n", "",
                     cls="DeusEx.Chandelier", defaults=d)


def test_an_indexed_property_expands_against_its_OWN_array_index_default():
    """A static-array element's key is the literal `KeyPos(1)`, whose default lives at
    `("keypos", 1)`. Using index 0's default for every element would make each element look
    un-defaulted — and an all-zero element of a class that defaults it NON-zero would then compare
    equal to an omitted one (a false pass)."""
    d = StubDefaults({"Engine.Mover": {("keypos", 1): "(X=0,Y=0,Z=128)",
                                       ("keypos", 2): "(X=0,Y=0,Z=0)"}},
                     schema={"Engine.Mover": {"KeyPos": _VEC}})
    # index 1 defaults NON-zero: an authored all-zero element is real content, not the default
    assert not _same("    KeyPos(1)=(X=0.000000,Y=0.000000,Z=0.000000)\n", "",
                     cls="Engine.Mover", defaults=d)
    # ...and the editor's PARTIAL spelling of that same default expands to it member-wise
    assert _same("    KeyPos(1)=(Z=128.000000)\n", "", cls="Engine.Mover", defaults=d)
    # index 2 defaults zero: an all-zero element there IS the default
    assert _same("    KeyPos(2)=(X=0.000000,Y=0.000000,Z=0.000000)\n", "",
                 cls="Engine.Mover", defaults=d)


def test_a_partially_stated_scale_compares_equal_to_its_fully_stated_form():
    """The editor writes `MainScale=(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)` — Y/Z/SheerRate
    omitted because they equal the identity members `transform.parse_fscale` fills in. The model
    holds the complete FScale either way, so the two spellings are one value."""
    d = StubDefaults()          # no schema: the model's own FScale layout is the fallback
    assert _same("    MainScale=(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)\n",
                 "    MainScale=(Scale=(X=-1.000000,Y=1.000000,Z=1.000000),"
                 "SheerRate=0.000000,SheerAxis=SHEER_ZX)\n", cls="Engine.Brush", defaults=d)


# --- the whole-level invariants -----------------------------------------------------------------

def test_the_compare_never_mutates_the_level_it_reads():
    """If the compare ever reduced the level in place, the very next trunk save would write the
    reduced actor — i.e. `level materialize` would silently delete authored properties from the
    git-tracked source as a side effect of verifying the build."""
    lv = _one_actor_level("    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n"
                          "    Rotation=(Pitch=0,Yaw=0,Roll=0)\n    Tag=Light\n")
    before = {n: canonical_actor_t3d(a) for n, a in lv.actors.items()}
    compare_view(lv, defaults=StubDefaults())
    assert {n: canonical_actor_t3d(a) for n, a in lv.actors.items()} == before
    assert "Rotation=(Pitch=0,Yaw=0,Roll=0)" in before["A1"] and "Tag=Light" in before["A1"]


def test_canonical_actor_t3d_is_identical_with_and_without_a_resolver():
    """THE INVARIANT. `canonical_actor_t3d` is the durable git-tracked trunk emit AND the
    `MAP IMPORT` payload AND `actor show`. Its bytes must NEVER depend on which packages happen to
    be installed — the typed expansion is compare-only. There is no way to pass it a resolver, and
    this pins it: the same actor emits identically whether or not class defaults are resolvable
    (here: a level whose every property EQUALS a class default it is never told about)."""
    lv = _one_actor_level("    SoundRadius=64\n    LightPeriod=32\n", cls="Engine.AmbientSound")
    a = lv.actors["A1"]
    emitted = canonical_actor_t3d(a)
    assert "SoundRadius=64" in emitted and "LightPeriod=32" in emitted
    compare_view(lv, defaults=StubDefaults(
        {"Engine.AmbientSound": {("soundradius", 0): "64", ("lightperiod", 0): "32"}},
        schema={"Engine.AmbientSound": {"SoundRadius": "byte", "LightPeriod": "byte"}}))
    assert canonical_actor_t3d(a) == emitted


def _golden_level():
    """The committed editor-exported golden, with its BARE classes qualified — exactly what
    `qualify.requalify_classes_to_loaded` does against the live editor before the compare runs (a
    bare class has no resolvable schema, by design: no fallback)."""
    lv = _parse_t3d(read_fixture("level_small.t3d"))
    lv.order = level_order(lv)
    normalize_level(lv)
    for a in lv.actors.values():
        if "." not in a.cls:
            a.cls = f"Engine.{a.cls}"
    return lv


def test_the_committed_editor_golden_survives_its_own_round_trip_byte_for_byte():
    """THE END-TO-END MATERIALIZE INVARIANT, on a real `MAP EXPORT`: re-emitting the editor's own
    export through `canonical_actor_t3d` (the trunk write + import payload) and re-parsing it must
    compare EQUAL to the original — otherwise materializing a level captured from the editor would
    abort on its own post-verify. Run with NO class defaults supplied, the strictest form: every
    property must survive on its own merits, with nothing folded away."""
    lv = _golden_level()
    reemitted = _parse_t3d("Begin Map\n"
                           + "\n".join(canonical_actor_t3d(a) for a in lv.actors.values())
                           + "\nEnd Map\n")
    reemitted.order = list(lv.order)
    d = StubDefaults()
    assert len(lv.actors) > 5                     # the fixture really did carry actors
    assert compare_view(reemitted, defaults=d) == compare_view(lv, defaults=d)


def test_the_trunk_t3d_is_byte_identical_after_a_hash_and_compare_pass():
    """Trunk byte-purity end to end: hashing a level and comparing it must leave every actor's
    `actor.t3d` body untouched, byte for byte."""
    lv = _golden_level()
    before = {n: canonical_actor_t3d(a) for n, a in lv.actors.items()}
    canonical_level_hash(lv)
    compare_view(lv, defaults=StubDefaults())
    assert {n: canonical_actor_t3d(a) for n, a in lv.actors.items()} == before


def test_two_actors_that_canonicalize_to_one_name_are_REFUSED_not_silently_merged():
    """The compare view is a dict keyed by the canonical name, and `_levelinfo_rename` aliases the
    LevelInfo singleton onto the fixed sentinel `LevelInfo`. A non-LevelInfo actor literally named
    `LevelInfo` therefore collides — and a dict would let one body overwrite the other, making the
    post-verify blind to EVERY change in that actor (a false pass on a wrong map). It must fail
    loudly instead. (Cold review, 2026-07-25.)"""
    import pytest
    lv = parse_t3d(
        "Begin Map\n"
        "Begin Actor Class=Engine.LevelInfo Name=LevelInfo_zzz\n    Name=\"LevelInfo_zzz\"\nEnd Actor\n"
        "Begin Actor Class=Engine.Light Name=LevelInfo\n    LightBrightness=64\n"
        '    Name="LevelInfo"\nEnd Actor\nEnd Map')
    lv.order = level_order(lv)
    with pytest.raises(ValueError, match="canonicalize to the name"):
        compare_view(lv, defaults=StubDefaults())


def test_an_unresolvable_class_names_the_actor_and_never_falls_back_to_zero():
    """No silent half-answers, and no fabricated defaults: a bare/unresolvable class fails the
    compare with the ACTOR named, rather than being compared against an assumed-zero default."""
    import pytest
    from uedctl.uprops import SchemaError
    lv = _one_actor_level("", cls="Camera", name="Cam1")
    with pytest.raises(SchemaError, match="cannot verify actor 'Cam1'"):
        compare_view(lv, defaults=StubDefaults())


def test_the_compare_resolves_each_DISTINCT_class_exactly_once():
    """PERF GUARD. Class resolution is the expensive half (~0.2 s cold per class: a package load, a
    Super-chain walk, a defaults decode, struct/enum layouts), so it is memoized per class over one
    shared package map. A level has 5-60 distinct classes across hundreds of actors; resolving
    per-ACTOR instead would turn a ~1 s verify into a ~2 min one."""
    d = StubDefaults()
    body = "".join(
        f'Begin Actor Class=Engine.{cls} Name=A{i}\n    Name="A{i}"\nEnd Actor\n'
        for i, cls in enumerate(["Light"] * 5 + ["Brush"] * 5 + ["PlayerStart"] * 5))
    lv = parse_t3d("Begin Map\n" + body + "End Map\n")
    lv.order = level_order(lv)
    compare_view(lv, defaults=d)
    compare_view(lv, defaults=d)                  # both compare sides share the memo
    assert d.resolutions == 3                     # three DISTINCT classes, 30 actor views
