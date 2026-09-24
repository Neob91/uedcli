from decimal import Decimal

from uedcli import propedit
from uedcli.effective_props import (
    ScalarProp, EnumProp, StructProp, ArrayProp, _resolve_typed_fields, resolve_actor_props)
from uedcli.model import Actor
from uedcli.typedprops import ESHEER_AXIS
from uedcli.uprops import Prop, SchemaError


def make_actor(*, cls="Engine.Actor", props=(), location=None, location_text=None,
               main_scale=None, main_scale_text=None, post_scale=None, post_scale_text=None):
    """A minimal `Actor` for effective-props tests. No such helper exists yet in
    `test_normalize.py` (checked) -- shared here since Tasks 3-5 all construct actors this way."""
    return Actor(
        name="A1", cls=cls, props=list(props),
        location=None if location is None else tuple(Decimal(str(c)) for c in location),
        location_text=location_text,
        main_scale=main_scale, main_scale_text=main_scale_text,
        post_scale=post_scale, post_scale_text=post_scale_text,
    )


def fake_ctx(defaults: dict | None = None, *, schema: dict | None = None,
            schema_raises: bool = False, members_by_name: dict | None = None):
    """A minimal real `propedit.ClassCtx`. Task 3's original shape (`fake_ctx()`/
    `fake_ctx({("location", 0): ...})`, only `.defaults()` ever touched) is unchanged and still
    works positionally. Task 4 adds: `schema` (returned by `.schema()`), `schema_raises` (both
    `.schema()` and `.defaults()` raise `SchemaError` immediately -- a whole-class-unresolvable
    fixture), and `members_by_name` (casefold prop name -> its member `Prop` list; a `StructProperty`
    prop not in this map makes `.members()` raise `SchemaError`, an unresolvable/cross-package
    struct). `.enums()` is never exercised by Task 4's fixtures (none are `ByteProperty`), so its
    loader stays the original "must not be reached" stub."""
    def _unexpected():
        raise AssertionError("this test's fixtures must not touch .enums()")

    def _load_schema():
        if schema_raises:
            raise SchemaError("fake: class schema unresolvable")
        return dict(schema or {})

    def _load_defaults():
        if schema_raises:
            raise SchemaError("fake: class defaults unresolvable")
        return dict(defaults or {})

    def _load_members(prop):
        table = members_by_name or {}
        if prop.name.casefold() in table:
            return table[prop.name.casefold()]
        raise SchemaError(f"fake: no members resolvable for {prop.name!r} (cross-package miss)")

    return propedit.ClassCtx(
        cls="DeusEx.SomeUnresolvableClass" if schema_raises else "Engine.Actor",
        load_schema=_load_schema,
        load_defaults=_load_defaults,
        load_members=_load_members,
        load_enums=lambda prop: _unexpected(),
    )


def array_property_prop() -> Prop:
    return Prop(name="EditPackages", kind="ArrayProperty", array_dim=1, property_flags=0,
               type_ref=0, type_name=None, owner="Engine.Actor")


def pointer_property_prop() -> Prop:
    return Prop(name="VariableMap", kind="PointerProperty", array_dim=1, property_flags=0,
               type_ref=0, type_name=None, owner="Engine.Actor")


def object_property_prop() -> Prop:
    return Prop(name="Owner", kind="ObjectProperty", array_dim=1, property_flags=0,
               type_ref=0, type_name=None, owner="Engine.Actor")


def class_property_prop() -> Prop:
    return Prop(name="AmmoName", kind="ClassProperty", array_dim=1, property_flags=0,
               type_ref=0, type_name=None, owner="Engine.Actor")


def _rotation_member(name: str) -> Prop:
    return Prop(name=name, kind="IntProperty", array_dim=1, property_flags=0, type_ref=0,
               type_name=None, owner="Engine.Actor", category="Movement")


def _object_member(name: str) -> Prop:
    return Prop(name=name, kind="ObjectProperty", array_dim=1, property_flags=0, type_ref=0,
               type_name=None, owner="Engine.Actor", category="Movement")


def rotation_prop() -> Prop:
    return Prop(name="Rotation", kind="StructProperty", array_dim=1, property_flags=0,
               type_ref=999, type_name="Rotator", owner="Engine.Actor", category="Movement")


def struct_array_prop() -> Prop:
    return Prop(name="Corners", kind="StructProperty", array_dim=4, property_flags=0,
               type_ref=999, type_name="Rotator", owner="Engine.Actor", category="Movement")


def unresolvable_struct_prop() -> Prop:
    return Prop(name="BadStruct", kind="StructProperty", array_dim=1, property_flags=0,
               type_ref=999, type_name="SomeCrossPackageStruct", owner="Engine.Actor")


def unresolvable_struct_array_prop() -> Prop:
    return Prop(name="BadCorners", kind="StructProperty", array_dim=4, property_flags=0,
               type_ref=999, type_name="SomeCrossPackageStruct", owner="Engine.Actor")


def test_scalar_prop_shape():
    p = ScalarProp(name="LightRadius", category="Lighting", kind="byte",
                   stored_value="8", default_value="0")
    assert p.kind == "byte"
    assert p.stored_value == "8"

def test_struct_prop_has_no_stored_value_field():
    p = StructProp(name="Rotation", category="Movement", members=[])
    assert not hasattr(p, "stored_value")   # struct variant genuinely has no such field


def test_location_partial_axis_marks_only_stated_explicit():
    actor = make_actor(location=(100, 0, 0), location_text="(X=100.000000)")
    fields = _resolve_typed_fields(actor, fake_ctx(), {})
    loc = next(f for f in fields if f.name == "Location")
    x, y, z = loc.members
    # TypedField.get() renders via _fmt_dec, which trims a whole number to "100" (not "100.000000")
    # -- confirmed against the real propedit/fields.py, not assumed from the brief's literal.
    assert x.stored_value == "100" and x.default_value is not None
    assert y.stored_value is None   # NOT explicit -- omitted from the stated text
    assert z.stored_value is None

def test_location_text_self_invalidated_by_mutation_marks_all_explicit():
    # location_text says (X=100) but .location no longer round-trips to it (a move happened) --
    # normalize._stated_axes's own self-invalidation rule: all three axes read as stated.
    actor = make_actor(location=(200, 0, 0), location_text="(X=100.000000)")
    fields = _resolve_typed_fields(actor, fake_ctx(), {})
    loc = next(f for f in fields if f.name == "Location")
    assert all(m.stored_value is not None for m in loc.members)

def test_sheeraxis_enum_type_self_seeded_into_ctx_by_type():
    ctx_by_type: dict = {}
    _resolve_typed_fields(make_actor(location=(0, 0, 0)), fake_ctx(), ctx_by_type)
    assert ctx_by_type["typedprops.ESheerAxis"] == list(ESHEER_AXIS)


def test_location_unstated_axis_default_is_true_class_default_not_zero():
    # Engine.Camera-shaped class default: Location=(X=0,Y=-300.000000,Z=300.000000). Only X is
    # stated on the actor; Y/Z's default_value must reflect the REAL class default, not the
    # actor's own zero-filled model value for those axes (controller ruling on Discrepancy 3).
    actor = make_actor(location=(100, 0, 0), location_text="(X=100.000000)")
    ctx = fake_ctx({("location", 0): "(X=0.000000,Y=-300.000000,Z=300.000000)"})
    fields = _resolve_typed_fields(actor, ctx, {})
    loc = next(f for f in fields if f.name == "Location")
    x, y, z = loc.members
    assert x.stored_value == "100"
    assert y.stored_value is None and y.default_value == "-300.000000"
    assert z.stored_value is None and z.default_value == "300.000000"


def test_location_no_class_default_falls_back_to_origin_zero():
    actor = make_actor(location=(0, 0, 0))
    fields = _resolve_typed_fields(actor, fake_ctx(), {})
    loc = next(f for f in fields if f.name == "Location")
    assert all(m.default_value == "0" for m in loc.members)


def test_mainscale_unstated_member_default_is_true_class_default():
    # main_scale stays None (== identity), and only SheerAxis is stated in the text -- this
    # round-trips back to identity (no self-invalidation), so Scale/SheerRate read as unstated
    # and must fall back to the TRUE class default, not the actor's own identity value.
    actor = make_actor(main_scale=None, main_scale_text="(SheerAxis=SHEER_ZX)")
    ctx = fake_ctx({
        ("mainscale", 0): "(Scale=(X=2.000000,Y=1.000000,Z=1.000000),"
                          "SheerRate=5.000000,SheerAxis=SHEER_XY)",
    })
    fields = _resolve_typed_fields(actor, ctx, {})
    main = next(f for f in fields if f.name == "MainScale")
    scale = next(m for m in main.members if m.name == "Scale")
    sx, sy, sz = scale.members
    rate = next(m for m in main.members if m.name == "SheerRate")
    axis = next(m for m in main.members if m.name == "SheerAxis")
    assert sx.stored_value is None and sx.default_value == "2.000000"
    assert sy.default_value == "1.000000" and sz.default_value == "1.000000"
    assert rate.default_value == "5.000000"
    assert axis.default_value == "SHEER_XY"


def test_mainscale_no_class_default_falls_back_to_identity():
    actor = make_actor()
    fields = _resolve_typed_fields(actor, fake_ctx(), {})
    main = next(f for f in fields if f.name == "MainScale")
    scale = next(m for m in main.members if m.name == "Scale")
    rate = next(m for m in main.members if m.name == "SheerRate")
    axis = next(m for m in main.members if m.name == "SheerAxis")
    assert all(m.default_value == "1" for m in scale.members)
    assert rate.default_value == "0"
    assert axis.default_value == "SHEER_ZX"


# ── Task 4: resolve_actor_props (generic schema walk) ────────────────────────────────────────────

def test_resolve_actor_props_omits_unknown_stored_prop():
    actor = make_actor(props=[("TotallyFakeProp", "1")])
    ctx = fake_ctx(schema={})   # empty schema -- TotallyFakeProp isn't declared anywhere
    result, _, note = resolve_actor_props(actor, ctx)
    assert not any(p.name == "TotallyFakeProp" for p in result)
    assert note is None


def test_resolve_actor_props_excludes_array_and_pointer_kinds():
    actor = make_actor(props=[])
    ctx = fake_ctx(schema={"editpackages": array_property_prop(),
                          "variablemap": pointer_property_prop()})
    result, _, note = resolve_actor_props(actor, ctx)   # must NOT raise -- the crash this test pins
    # DEVIATION FROM THE BRIEF'S LITERAL `assert result == []` -- see task-4-report.md's "Deviations
    # from the brief" section. `_resolve_typed_fields` (Task 3's real, already-committed code)
    # unconditionally contributes Location/MainScale/PostScale StructProps regardless of schema
    # content (mirrors `effective_all_lines`'s own "typed fields unconditionally included"
    # convention) -- `result` can never be `[]` for ANY actor. The test's real, statable intent
    # (per its own comment -- "the crash this test pins") is that the ArrayProperty/PointerProperty
    # filter keeps those two kinds OUT of the schema-walked result entirely; that is what this
    # assertion checks instead.
    assert not any(p.name in ("EditPackages", "VariableMap") for p in result)
    assert note is None


def test_resolve_actor_props_struct_member_precise():
    # Critical 1 regression pin. The OLD `fake_ctx` shape here (`defaults={("pitch", 0): "4096", ...}`)
    # was VACUOUS: `uprops.resolve_class_defaults` keys a struct-typed default by the STRUCT's own
    # top-level name only (one full struct-literal text per top-level `PropertyTag`, never a
    # per-member key) -- a real `ClassCtx.defaults()` would never produce a `("pitch", 0)` entry, so
    # the old test passed even against the buggy code that looked a member up by its OWN bare name.
    # This fixture instead matches what `resolve_class_defaults`/`render_default_tag` really emit:
    # ONE entry keyed by the struct prop's own name, holding the FULL member-wise struct text (this
    # is DeusEx.Karkian's real live `RotationRate` default, `dev/docs/board`'s own cited motivating
    # case -- `(Pitch=4096,Yaw=30000,Roll=3072)`).
    actor = make_actor(props=[("Rotation", "(Yaw=1234)")])
    ctx = fake_ctx(schema={"rotation": rotation_prop()},
                   defaults={("rotation", 0): "(Pitch=4096,Yaw=30000,Roll=3072)"},
                   members_by_name={"rotation": [_rotation_member("Pitch"),
                                                 _rotation_member("Yaw"),
                                                 _rotation_member("Roll")]})
    result, _, note = resolve_actor_props(actor, ctx)
    rot = next(p for p in result if p.name == "Rotation")
    yaw = next(m for m in rot.members if m.name == "Yaw")
    pitch = next(m for m in rot.members if m.name == "Pitch")
    roll = next(m for m in rot.members if m.name == "Roll")
    assert yaw.stored_value == "1234" and yaw.default_value == "1234"     # stated: default collapses
    assert pitch.stored_value is None and pitch.default_value == "4096"   # unstated: NOT zero
    assert roll.stored_value is None and roll.default_value == "3072"     # unstated: NOT zero
    assert note is None


def test_resolve_actor_props_struct_member_stored_value_is_member_wise_not_bare_name():
    # Critical 1's SECOND, latent defect: a struct member's `stored_value` must resolve through the
    # real member-chain path (the struct's own stated partial-literal text), never a bare top-level
    # name lookup that could coincidentally collide with an unrelated top-level prop of the same
    # spelling. Regression: an actor that ALSO happens to carry a top-level `Yaw=999` line (e.g. a
    # stray/foreign prop) must NOT leak into `Rotation.Yaw`'s own stored_value -- only Rotation's own
    # struct-literal text should ever feed it.
    actor = make_actor(props=[("Rotation", "()"), ("Yaw", "999")])
    ctx = fake_ctx(schema={"rotation": rotation_prop()},
                   defaults={("rotation", 0): "(Pitch=4096,Yaw=30000,Roll=3072)"},
                   members_by_name={"rotation": [_rotation_member("Pitch"),
                                                 _rotation_member("Yaw"),
                                                 _rotation_member("Roll")]})
    result, _, note = resolve_actor_props(actor, ctx)
    rot = next(p for p in result if p.name == "Rotation")
    yaw = next(m for m in rot.members if m.name == "Yaw")
    # Rotation's own text is "()" -- Yaw is not stated THERE, even though a same-named top-level
    # "Yaw" prop line exists on the actor. Must stay None, not "999".
    assert yaw.stored_value is None
    assert yaw.default_value == "30000"
    assert note is None


def test_resolve_actor_props_degrades_on_unresolvable_struct_member():
    # a StructProperty whose MEMBERS can't be resolved (cross-package miss) must NOT crash the
    # whole request -- degrades to an empty members list + a stderr note, same convention as
    # _is_hidden_ed/_actor_radii elsewhere in scene.py. A per-PROPERTY failure (the class itself
    # resolves fine) -- distinct from the next test, a per-CLASS failure.
    actor = make_actor(props=[])
    ctx = fake_ctx(schema={"badstruct": unresolvable_struct_prop()})   # no members_by_name entry
    result, _, note = resolve_actor_props(actor, ctx)
    bad = next(p for p in result if p.name == "BadStruct")
    assert bad.members == []
    assert note is None   # a per-property degrade, not per-class -- no note at this level


def test_resolve_actor_props_degrades_array_of_unresolvable_struct_to_array_prop():
    # Minor 5, the ARRAY counterpart of the test above: a STATIC ARRAY of an unresolvable struct
    # type must degrade to a real ArrayProp (kind="array", elements=[]), preserving its true wire
    # kind -- never a relabeled StructProp that silently flips `kind` to "struct". `element_kind`
    # is always "struct" here: SchemaError in this degrade path can only come from `ctx.members()`,
    # which `_resolve_one`/`zero_value` only ever call for a StructProperty-kind prop, so whichever
    # prop's resolution failed to reach here was necessarily a struct.
    actor = make_actor(props=[])
    ctx = fake_ctx(schema={"badcorners": unresolvable_struct_array_prop()})   # no members_by_name entry
    result, _, note = resolve_actor_props(actor, ctx)
    bad = next(p for p in result if p.name == "BadCorners")
    assert isinstance(bad, ArrayProp)
    assert bad.kind == "array"
    assert bad.elements == []
    assert bad.element_kind == "struct"
    assert note is None   # a per-property degrade, not per-class -- no note at this level


def test_resolve_actor_props_degrades_on_unresolvable_class():
    # the CLASS itself can't be resolved at all (ctx.schema() or ctx.defaults() raises
    # SchemaError). Must degrade to (empty props, empty enum dict, a real note) -- never crash the
    # whole payload, matching _is_hidden_ed's exact convention.
    actor = make_actor(props=[], cls="DeusEx.SomeUnresolvableClass")
    ctx = fake_ctx(schema_raises=True)   # .schema() (and .defaults()) both raise SchemaError
    result, enums, note = resolve_actor_props(actor, ctx)
    assert result == []
    assert enums == {}
    assert note is not None and "DeusEx.SomeUnresolvableClass" in note


def test_resolve_actor_props_static_array_is_index_precise():
    # Not one of the plan's 5 mandated cases, but array_dim > 1 is otherwise completely
    # unexercised by them -- a minimal sanity check that the array branch resolves per-slot,
    # not just once for the whole array (the crash class this task also exists to prevent).
    ammo = Prop(name="AmmoCount", kind="IntProperty", array_dim=3, property_flags=0,
               type_ref=0, type_name=None, owner="Engine.Actor", category="Ammo")
    actor = make_actor(props=[("AmmoCount", "10"), ("AmmoCount(2)", "30")])
    ctx = fake_ctx(schema={"ammocount": ammo},
                   defaults={("ammocount", 0): "0", ("ammocount", 1): "0", ("ammocount", 2): "0"})
    result, _, note = resolve_actor_props(actor, ctx)
    arr = next(p for p in result if p.name == "AmmoCount")
    assert arr.kind == "array" and arr.element_kind == "int"
    assert [e.stored_value for e in arr.elements] == ["10", None, "30"]
    assert note is None


# ── task-4 review fixes: static array of structs, Object/Class-kind exclusion ───────────────────

def test_resolve_actor_props_struct_array_resolves_as_array_of_structs():
    # Finding 1: a static array of structs (`prop.kind == "StructProperty"` AND `prop.array_dim > 1`,
    # e.g. `var Rotator Corners[4]`) must resolve as an ArrayProp of 4 StructProp elements -- never
    # as ONE StructProp whose "members" are the struct type's own fields read off the
    # array-declared prop (the bug: the StructProperty check used to run BEFORE the array_dim check).
    actor = make_actor(props=[("Corners", "(Yaw=1)"), ("Corners(2)", "(Yaw=2)")])
    ctx = fake_ctx(schema={"corners": struct_array_prop()},
                   members_by_name={"corners": [_rotation_member("Pitch"),
                                               _rotation_member("Yaw"),
                                               _rotation_member("Roll")]})
    result, _, note = resolve_actor_props(actor, ctx)
    arr = next(p for p in result if p.name == "Corners")
    assert arr.kind == "array"
    assert arr.element_kind == "struct"   # NOT "string" -- the residual _scalar_kind(prop) bug
    assert len(arr.elements) == 4
    for el in arr.elements:
        assert el.kind == "struct"
        assert {m.name for m in el.members} == {"Pitch", "Yaw", "Roll"}
    yaw0 = next(m for m in arr.elements[0].members if m.name == "Yaw")
    yaw1 = next(m for m in arr.elements[1].members if m.name == "Yaw")
    yaw2 = next(m for m in arr.elements[2].members if m.name == "Yaw")
    assert yaw0.stored_value == "1"
    assert yaw1.stored_value is None   # not stated for this element
    assert yaw2.stored_value == "2"
    assert note is None


def test_resolve_actor_props_excludes_object_and_class_kinds():
    # Finding 2, top-level half: spec.md excludes ObjectProperty/ClassProperty from scope the same
    # way as ArrayProperty/PointerProperty -- the top-level filter used to only name the latter two.
    actor = make_actor(props=[])
    ctx = fake_ctx(schema={"owner": object_property_prop(),
                          "ammoname": class_property_prop()})
    result, _, note = resolve_actor_props(actor, ctx)
    assert not any(p.name in ("Owner", "AmmoName") for p in result)
    assert note is None


def test_resolve_actor_props_excludes_nested_object_property_struct_member():
    # Finding 2, recursion half: the exclusion must apply inside _resolve_one's OWN recursion (a
    # struct member), not just the top-level loop -- a struct member of an excluded kind used to
    # fall through to the catch-all ScalarProp(kind="string") branch one level deep, silently
    # mislabeled instead of omitted.
    actor = make_actor(props=[])
    ctx = fake_ctx(schema={"rotation": rotation_prop()},
                   members_by_name={"rotation": [_rotation_member("Pitch"),
                                                 _object_member("Owner"),
                                                 _rotation_member("Yaw")]})
    result, _, note = resolve_actor_props(actor, ctx)
    rot = next(p for p in result if p.name == "Rotation")
    assert {m.name for m in rot.members} == {"Pitch", "Yaw"}   # Owner (ObjectProperty) excluded
    assert not any(m.name == "Owner" for m in rot.members)
    assert note is None
