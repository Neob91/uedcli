from decimal import Decimal

from uedcli import propedit
from uedcli.effective_props import ScalarProp, StructProp, _resolve_typed_fields
from uedcli.model import Actor
from uedcli.typedprops import ESHEER_AXIS
from uedcli.uprops import SchemaError


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
