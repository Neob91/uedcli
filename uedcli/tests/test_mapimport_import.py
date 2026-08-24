"""End-to-end native map import: a compiled `.dx` → `MAP EXPORT`-shaped T3D → a parsed level.

These run entirely OFFLINE — no editor, no container, no game install — because both halves they
need are committed:

* `uedcli/tests/fixtures/map_import_bounds/*.dx` — three real UnrealEd `MAP SAVE` outputs from one
  live editor session over the same two-brush fixture (a subtractive room plus an additive pillar).
  Genuine editor output, so the decoder faces a real compiled map's byte layout.
* `uned/UED22/*.u` — the compiled class packages, needed for every property's declared TYPE and each
  class's DEFAULT values (which is how a struct's unchanged members get dropped).

They prove the decoder reads a real compiled map and produces text that parses back into the expected
level, actors, geometry and value forms. They do NOT prove byte agreement with the official
exporter's output — that needs the retail maps plus the UnrealEd container, and is tracked as
outstanding on `dev/docs/board/inbox/`.

Spec: board item `level-import-native-editor-less-dx-unr-t3d`. Format evidence:
`dev/docs/unrealed/package-format.md`, `dev/docs/unrealed/t3d.md`.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from uedcli import mapimport, model, normalize
from uedcli.classindex import ClassIndex
from uedcli.upackage import load_package

_ROOT = Path(__file__).resolve().parent.parent.parent
_UED22 = _ROOT / "uned" / "UED22"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map_import_bounds"

pytestmark = pytest.mark.skipif(
    not (_UED22 / "Engine.u").is_file(),
    reason="committed UED22/Engine.u not present (the decode needs class schemas + defaults)")


def _resolver(name: str) -> str | None:
    p = _UED22 / f"{name}.u"
    return str(p) if p.is_file() else None


def _class_index() -> ClassIndex:
    paths = {p.stem.casefold(): str(p) for p in _UED22.glob("*.u")}
    return ClassIndex(_paths=paths, _stems={k: Path(v).stem for k, v in paths.items()})


def _import_text(stem: str) -> str:
    dx = _FIXTURES / f"{stem}.dx"
    pkg = load_package(str(dx), name=dx.stem)
    return mapimport.import_map(pkg, _class_index(),
                                mapimport.ImportSchema(resolver=_resolver))


@pytest.fixture(scope="module")
def paste_text() -> str:
    """`paste.dx` decoded to T3D. Module-scoped: resolving every class's schema and defaults out of
    the compiled packages is the expensive part, and it is identical for every test here."""
    return _import_text("paste")


# ── the whole pipeline ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("stem", ["paste", "import", "importadd"])
def test_every_committed_editor_map_decodes_and_parses_back(stem):
    """Each committed editor-built map decodes to text that `model.parse_t3d` ingests.

    This is the broadest single check in the file: it exercises the container parse, the actor
    ordering, the StateFrame skip, every property value form the three maps happen to contain, and
    the brush geometry decode — and then requires the result to be text uedcli's own parser
    accepts. A decode that produced plausible-looking but malformed T3D fails here.
    """
    text = _import_text(stem)

    assert text.startswith("Begin Map\n") and text.endswith("End Map\n")
    level = model.parse_t3d(text)
    assert level.actors, f"{stem}.dx decoded to a level with no actors"
    # Actors[0] is the LevelInfo singleton on every UE1 map — proves the order array was read in
    # alignment rather than by luck.
    assert next(iter(level.actors.values())).cls == "LevelInfo"


def test_paste_decodes_to_its_known_actor_set_in_actors_array_order(paste_text):
    """`paste.dx`'s decoded actors, in order, are exactly what the map holds.

    The order is not the export-table order — it is read from the level object's own `Actors`
    array, which is the CSG precedence the map was built with. `paste.dx`'s export table
    interleaves its cameras and models differently from this list, so a decoder that fell back on
    export order would produce a visibly different sequence.
    """
    level = model.parse_t3d(paste_text)

    assert list(level.actors) == [
        "LevelInfo0", "Brush1",
        "Camera6", "Camera7", "Camera8", "Camera9", "Camera10", "Camera11",
        "ProbeRoom", "ProbePillar",
    ]


def test_import_is_a_stable_round_trip_through_serialized_text(paste_text):
    """Decoded text → level → re-emitted text → level again is a FIXED POINT.

    Why this matters. The decoder's output is not an end in itself: it is fed to `parse_t3d` and
    then written to the durable tree through `canonical_actor_t3d`, the same emitter every other
    uedcli write path uses. If the decode emitted a form that survives parsing but re-emits
    differently, an imported tree would change on its first unrelated edit and every diff after the
    import would be noise.

    Compared through the re-emitted text of the SECOND generation onward, not against the decoder's
    own output: the decoder writes what the editor writes, while `canonical_actor_t3d` writes
    uedcli's canonical form, and those two legitimately differ in layout. What must be stable is
    the canonical form.
    """
    first = model.parse_t3d(paste_text)
    once = {n: normalize.canonical_actor_t3d(a) for n, a in first.actors.items()}

    second = model.parse_t3d("Begin Map\n" + "\n".join(once.values()) + "\nEnd Map\n")
    twice = {n: normalize.canonical_actor_t3d(a) for n, a in second.actors.items()}

    assert twice == once


# ── the editor's scratch objects (owner ruling, 2026-07-27) ──────────────────────────────────

def test_the_builder_brush_and_viewport_cameras_are_dropped(paste_text):
    """Import keeps level CONTENT and discards the editor's own apparatus.

    A saved map is the editor's workspace, so it carries the red builder brush (the scratch shape a
    designer works with) and one `Camera` actor per open editor viewport. `paste.dx` holds one of
    the former and six of the latter; none of the seven is level content. Keeping them would put
    editing tools into the durable tree, and rebuilding a map from that tree would collide the
    imported builder brush with the fresh one the editor makes for itself.

    The cameras are recognisable as apparatus in the decoded text itself — they carry the editor's
    own `Tag=U2Viewport1`, `Tag=MeshBrowser` and so on.
    """
    level = model.parse_t3d(paste_text)

    dropped = mapimport.drop_editor_scratch(level)

    assert sorted(dropped) == sorted(
        ["Brush1", "Camera6", "Camera7", "Camera8", "Camera9", "Camera10", "Camera11"])
    assert list(level.actors) == ["LevelInfo0", "ProbeRoom", "ProbePillar"]
    assert level.order == [n for n in level.order if n in level.actors]


def test_the_drop_is_independent_of_class_qualification(paste_text):
    """The scratch drop fires whether the class is stored short or fully qualified.

    `is_builder_brush` matches the BARE class name (`(a.cls or '').rsplit('.', 1)[-1]`), so a builder
    brush is dropped whether its class is `Brush` or `Engine.Brush`; the camera check already strips
    qualification itself. So `drop_editor_scratch` no longer depends on running before import's
    class-qualification rewrite. This pins that qualification-independence: qualify FIRST, then assert
    both are still dropped.
    """
    level = model.parse_t3d(paste_text)
    for a in level.actors.values():                    # simulate qualify_and_validate's rewrite
        if a.cls in ("Brush", "Camera", "LevelInfo"):
            a.cls = f"Engine.{a.cls}"

    dropped = mapimport.drop_editor_scratch(level)

    assert "Brush1" in dropped and "Brush1" not in level.actors
    assert "Camera6" in dropped


def test_dropping_scratch_is_a_no_op_on_a_level_that_has_none():
    """A level with no builder brush and no cameras loses nothing, and reports nothing dropped."""
    a = model.Actor(name="Light0", cls="Light")
    level = model.Level(actors={"Light0": a}, order=["Light0"])

    assert mapimport.drop_editor_scratch(level) == []
    assert list(level.actors) == ["Light0"]


# ── brush geometry, on real editor output ────────────────────────────────────────────────────

def test_named_faces_survive_the_decode_including_the_default_label(paste_text):
    """Every authored face label reaches the T3D, `OUTSIDE` included.

    `OUTSIDE` is the editor's own default face label and it sits at name-table index 0 in these
    maps. A decoder that treats index 0 as "no label" drops it silently — no error, no short
    count, just a map whose faces have quietly lost their names. This asserts on the real editor
    output rather than a synthetic package, which is how the defect was originally spotted.
    (`uedcli/tests/test_mapimport_geometry.py` pins the underlying name-table rule directly.)
    """
    assert "Item=OUTSIDE" in paste_text

    level = model.parse_t3d(paste_text)
    room = level.actors["ProbeRoom"]
    assert room.brush is not None and room.brush.polys, "the subtractive room lost its geometry"
    assert {p.item for p in room.brush.polys} == {"OUTSIDE"}


def test_a_content_brush_keeps_its_full_polygon_list(paste_text):
    """The subtractive room decodes as a closed six-sided box with its texture axes intact."""
    level = model.parse_t3d(paste_text)
    room = level.actors["ProbeRoom"]

    assert len(room.brush.polys) == 6
    assert all(len(p.vertices) == 4 for p in room.brush.polys)
    # Six axis-aligned faces ⇒ six distinct unit normals.
    assert len({tuple(p.normal) for p in room.brush.polys}) == 6


def test_the_brush_reference_follows_its_geometry_block(paste_text):
    """`Brush=Model'…'` is written AFTER the inline geometry, matching `emit.emit_actor`.

    An actor that binds its model before the model is defined imports with no usable bound and
    cannot be selected in the editor, so the ordering is load-bearing rather than cosmetic.
    """
    block = paste_text.split("Begin Actor Class=Brush Name=ProbeRoom")[1].split("End Actor")[0]

    assert block.index("Begin Brush ") < block.index("Brush=Model'")


# ── the value forms the editor writes (`T3D_STYLE`) ──────────────────────────────────────────

def test_floats_are_written_at_six_decimals(paste_text):
    """`MAP EXPORT` writes every float at six decimal places, including integral ones.

    uedcli's ordinary CLI rendering trims `24.000000` to `24`, which is friendlier to read but does
    not match the editor. Import deliberately uses the editor's spelling so an imported tree is
    textually comparable with an editor export of the same map.
    """
    assert "OldLocation=(X=-500.000000,Y=-300.000000,Z=300.000000)" in paste_text


def test_a_byte_valued_struct_member_is_written_as_its_enum_name(paste_text):
    """A struct member that is an enumerated byte is written by NAME, not as a number.

    `MainScale`'s `SheerAxis` member holds the byte 5, which the editor writes as `SHEER_ZX`. The
    same value under uedcli's ordinary rendering comes out as `5`, and a tree carrying `5` would
    not match an editor export.
    """
    assert "MainScale=(SheerAxis=SHEER_ZX)" in paste_text
    assert "SheerAxis=5" not in paste_text


def test_struct_members_equal_to_the_class_default_are_dropped(paste_text):
    """A struct writes only the members that DIFFER from the class's default for that property.

    This is the editor's own rule and it is why a rotated actor exports as `Rotation=(Yaw=8192)`
    rather than spelling out all three angles. Note the default is not always zero: `MainScale`
    defaults to a scale of 1 on each axis with `SheerAxis=SHEER_ZX`, and here every member EXCEPT
    the sheer axis matches that default and is therefore absent — which is only correct if the
    comparison is against the real class default rather than against zero.
    """
    assert "MainScale=(SheerAxis=SHEER_ZX)" in paste_text
    assert "MainScale=(X=1.000000" not in paste_text

    # `Region` keeps only the members that actually differ, and differs between actors: the
    # builder brush sits in zone 1, the LevelInfo carries the unset leaf index.
    assert "Region=(Zone=LevelInfo'paste.LevelInfo0',iLeaf=-1)" in paste_text
    assert "Region=(Zone=LevelInfo'paste.LevelInfo0',ZoneNumber=1)" in paste_text


@pytest.mark.parametrize("scale,expected", [
    # A mirrored brush — the case real editor output covers. Only the axis that changed is stated.
    ((-1.0, 1.0, 1.0), "(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)"),
    ((-1.0, 2.0, 1.0), "(Scale=(X=-1.000000,Y=2.000000),SheerAxis=SHEER_ZX)"),
    # Nothing inside the nested struct differs → the whole nested member disappears.
    ((1.0, 1.0, 1.0), "(SheerAxis=SHEER_ZX)"),
])
def test_the_member_drop_recurses_into_a_NESTED_struct(scale, expected):
    """A struct inside a struct keeps only ITS OWN differing members.

    `MainScale` is a struct whose first member `Scale` is itself a struct (an X/Y/Z vector). When a
    brush is mirrored on one axis, the editor writes `MainScale=(Scale=(X=-1.000000),SheerAxis=
    SHEER_ZX)` — the nested vector states the one axis that changed and drops the two that still
    match the class default of 1. Real editor output committed at
    `uedcli/tests/fixtures/level_small.t3d` contains exactly that line.

    Why this needs its own test. Comparing a nested struct as one already-joined string can only
    keep or drop the whole of it, which yields `Scale=(X=-1.000000,Y=1.000000,Z=1.000000)` — still
    semantically correct (an unstated member is filled from the class default) but NOT what the
    editor writes, so an imported tree would differ textually from an export of the same map and the
    fidelity comparison against the official exporter would fail on any scaled brush. None of the
    committed map fixtures happens to contain a scaled brush, which is why the case is built here
    rather than read out of one.
    """
    import struct as _struct

    from uedcli.upackage import PT_STRUCT, Package, PropertyTag

    pkg = Package(name="T", version=68, names=["None"], imports=[], exports=[], buf=b"")
    raw = _struct.pack("<ffff", *scale, 0.0) + bytes([5])       # Scale, SheerRate=0, SheerAxis=5
    tag = PropertyTag(name="MainScale", ptype=PT_STRUCT, struct_name="Scale", array_index=0,
                      bool_value=None, raw=raw)

    rendered = mapimport.render_prop(pkg, tag, "Engine.Brush",
                                     schema=mapimport.ImportSchema(resolver=_resolver))

    assert rendered == [("MainScale", expected)]


def test_names_and_strings_are_quoted_and_object_refs_are_typed(paste_text):
    """The three reference-ish value forms all take the shapes `MAP EXPORT` uses."""
    assert 'Tag="LevelInfo"' in paste_text                       # a name, quoted
    assert "Level=LevelInfo'paste.LevelInfo0'" in paste_text      # an object ref, Class'Pkg.Name'
    assert "CsgOper=CSG_Subtract" in paste_text                   # a plain enum byte, unquoted


def test_a_property_equal_to_a_non_zero_class_default_is_omitted_entirely(paste_text):
    """A whole property is absent when its value matches the class default, even a non-zero one.

    Every `Camera` in `paste.dx` sits at the class's default location, which is NOT the origin —
    `Engine.Camera` defaults `Location=(X=-500,Y=-300,Z=300)`. The compiled map therefore stores no
    `Location` tag for them at all, and the decode must not invent one: writing `Location=(0,0,0)`
    for an omitted property would move every such actor 655 units on re-import.
    """
    camera = paste_text.split("Begin Actor Class=Camera Name=Camera6")[1].split("End Actor")[0]

    # Match the property LINE, not the bare substring — `OldLocation=` contains it.
    assert "\n    Location=" not in camera
    # …while the separate, genuinely-stored `OldLocation` DOES carry that same default triple,
    # which is what makes the omission above meaningful rather than an artefact of an empty actor.
    assert "OldLocation=(X=-500.000000,Y=-300.000000,Z=300.000000)" in camera


# ── integrity gates ──────────────────────────────────────────────────────────────────────────

def test_a_file_that_is_not_a_map_is_a_named_error(tmp_path):
    """A package with no level object is rejected by name, not by traceback."""
    from uedcli.upackage import SchemaError

    engine = load_package(str(_UED22 / "Engine.u"), name="Engine")
    with pytest.raises(SchemaError, match=r"expected exactly one Engine\.Level"):
        mapimport.import_map(engine, _class_index(),
                             mapimport.ImportSchema(resolver=_resolver))
