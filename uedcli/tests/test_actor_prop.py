"""actor prop set|unset|get — the subcommand surface (spec in board item `materialize-post-verify-fails-when-the-trunk`).

Each test seeds an in-memory Level, patches the trunk seam (`_resolve_level_source`) and the four
schema seams (`_class_schema`/`_class_defaults`/`_struct_members`/`_enum_names`), invokes
`dispatch._dispatch`, and asserts on the captured `src.save(...)`, the mutated model, or the
printed output. Offline — the schema/defaults are hand-built fixtures, so no v68 install is
needed. The pure grammar/planner internals are covered in `test_propedit.py`; these are the
verb-level contracts (§11).
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest

from uedcli.cli import dispatch as dispatch_mod
from uedcli.model import Actor, Level
from uedcli.uprops import Prop


def _prop(name, kind, *, array_dim=1, enum=(), type_ref=0, type_name=None):
    return Prop(name=name, kind=kind, array_dim=array_dim, property_flags=0, type_ref=type_ref,
                type_name=type_name, owner="Engine.Actor", enum_value_names=tuple(enum))


_VECTOR_MEMBERS = [_prop("X", "FloatProperty"), _prop("Y", "FloatProperty"),
                   _prop("Z", "FloatProperty")]
_ROTATOR_MEMBERS = [_prop("Pitch", "IntProperty"), _prop("Yaw", "IntProperty"),
                    _prop("Roll", "IntProperty")]

_SCHEMA = {
    "group": _prop("Group", "NameProperty"),
    "tag": _prop("Tag", "NameProperty"),
    "lightbrightness": _prop("LightBrightness", "ByteProperty"),
    "lightperiod": _prop("LightPeriod", "ByteProperty"),
    "csgoper": _prop("CsgOper", "ByteProperty",
                     enum=("CSG_Active", "CSG_Add", "CSG_Subtract", "CSG_Intersect",
                           "CSG_Deintersect"), type_ref=1),
    "rotation": _prop("Rotation", "StructProperty", type_ref=2, type_name="Rotator"),
    "velocity": _prop("Velocity", "StructProperty", type_ref=3, type_name="Vector"),
    "location": _prop("Location", "StructProperty", type_ref=3, type_name="Vector"),
    "multiskins": _prop("MultiSkins", "ObjectProperty", array_dim=8),
    "mainscale": _prop("MainScale", "StructProperty", type_ref=4, type_name="Scale"),
    "bselected": _prop("bSelected", "BoolProperty"),      # a computed prop that IS in the schema
    "bhidden": _prop("bHidden", "BoolProperty"),
    "mass": _prop("Mass", "FloatProperty"),
    # A struct with a STRING member, so a member value can legitimately contain a comma
    # (`(Text="a,b",Count=1)`) — the quoted-comma regression below.
    "note": _prop("Note", "StructProperty", type_ref=5, type_name="NoteS"),
}

# Effective class defaults (what `_class_defaults` would decode from the .u).
_DEFAULTS = {
    ("lightbrightness", 0): "64",
    ("lightperiod", 0): "32",
    ("rotation", 0): "(Pitch=4096)",
    ("mass", 0): "100",
    ("bhidden", 0): "True",
    ("csgoper", 0): "CSG_Active",
}


_NOTE_MEMBERS = [_prop("Text", "StrProperty"), _prop("Count", "IntProperty")]


def _members_for(prop):
    if (prop.type_name or "").casefold() == "vector":
        return list(_VECTOR_MEMBERS)
    if (prop.type_name or "").casefold() == "rotator":
        return list(_ROTATOR_MEMBERS)
    if (prop.type_name or "").casefold() == "notes":
        return list(_NOTE_MEMBERS)
    return []


def _level(*, props=None, location=None):
    a = Actor(name="Widget0", cls="Engine.Brush", location=location, props=list(props or []))
    lv = Level()
    lv.actors["Widget0"] = a
    lv.order = ["Widget0"]
    return lv


def _run(level, propsub, tokens=(), *, kv=False, schema=None, defaults=None):
    """Invoke `actor prop <propsub>` against `level` with every seam mocked. Returns
    (rc, saved_kwargs|None, actor)."""
    args = SimpleNamespace(cmd="actor", sub="prop", propsub=propsub, name="widget0",
                           tokens=list(tokens), kv=kv)
    src = mock.Mock()
    src.load.return_value = level
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.resolve_project",
                       side_effect=dispatch_mod.ProjectError("no project")), \
            mock.patch("uedcli.cli.resources.class_schema",
                       lambda cls, project=None: dict(schema or _SCHEMA)), \
            mock.patch("uedcli.cli.resources.class_defaults",
                       lambda cls, project=None: dict(defaults if defaults is not None
                                                      else _DEFAULTS)), \
            mock.patch("uedcli.cli.resources.struct_members",
                       lambda p, project=None: _members_for(p)), \
            mock.patch("uedcli.cli.resources.enum_names",
                       lambda p, project=None: p.enum_value_names):
        rc = dispatch_mod._dispatch(args)
    saved = src.save.call_args.kwargs if src.save.called else None
    return rc, saved, level.actors["Widget0"]


# ── set: whole values ────────────────────────────────────────────────────────────


def test_set_replaces_and_records_one_mutation():
    level = _level(props=[("Group", "cells"), ("Tag", "old")])
    rc, saved, actor = _run(level, "set", ["Group=walls"])
    assert rc == 0
    assert saved == {
        "verb": "prop",
        "args": {"name": "Widget0", "propsub": "set", "tokens": ["Group=walls"]},
        "level": level,
        "touched": ["Widget0"],
    }
    assert actor.props == [("Group", "walls"), ("Tag", "old")]


def test_set_stores_canonical_casing_case_insensitively():
    level = _level(props=[("Group", "cells")])
    rc, _saved, actor = _run(level, "set", ["gRoUp=walls"])
    assert rc == 0
    assert actor.props == [("Group", "walls")]


def test_set_enum_name_and_in_range_ordinal_accepted():
    level = _level()
    rc, _s, actor = _run(level, "set", ["CsgOper=CSG_Subtract"])
    assert rc == 0
    rc2, _s, actor = _run(level, "set", ["CsgOper=2"])
    assert rc2 == 0


def test_set_enum_bad_value_and_out_of_range_ordinal_error(capsys):
    level = _level(props=[("Tag", "keep")])
    rc, saved, actor = _run(level, "set", ["CsgOper=CSG_Bogus"])
    assert rc == 2 and saved is None
    assert "CSG_Add" in capsys.readouterr().err          # message lists the valid values
    rc2, saved2, _a = _run(level, "set", ["CsgOper=9"])
    assert rc2 == 2 and saved2 is None
    assert actor.props == [("Tag", "keep")]              # untouched


def test_set_bool_numeric_forms_ok_bad_value_errors():
    level = _level()
    assert _run(level, "set", ["bHidden=1"])[0] == 0
    assert _run(level, "set", ["bHidden=perhaps"])[0] == 2


def test_set_byte_non_numeric_errors():
    assert _run(_level(), "set", ["LightBrightness=bright"])[0] == 2


def test_set_comma_sugar_on_vector_and_verbatim_on_name_prop():
    level = _level()
    rc, _s, actor = _run(level, "set", ["Velocity=4,5,-17"])
    assert rc == 0
    assert ("Velocity", "(X=4,Y=5,Z=-17)") in actor.props
    # ruling R1: a comma value on a NON-Vector/Rotator prop stays plain verbatim text
    rc2, _s, actor = _run(level, "set", ["Group=cells,ambers"])
    assert rc2 == 0
    assert ("Group", "cells,ambers") in actor.props


def test_set_comma_sugar_wrong_arity_errors(capsys):
    rc, _s, _a = _run(_level(), "set", ["Velocity=4,5"])
    assert rc == 2
    assert "3 components" in capsys.readouterr().err


def test_set_token_without_equals_errors():
    assert _run(_level(), "set", ["Group"])[0] == 2


# ── set: arrays ──────────────────────────────────────────────────────────────────


def test_set_array_element_via_dot_stores_paren_spelling():
    level = _level(props=[("MultiSkins(2)", "old")])
    rc, _s, actor = _run(level, "set", ["MultiSkins.2=Texture'T.New'", "multiskins.5=X"])
    assert rc == 0
    assert ("MultiSkins(2)", "Texture'T.New'") in actor.props
    assert ("MultiSkins(5)", "X") in actor.props


def test_set_array_tuple_replaces_whole_array():
    level = _level(props=[("MultiSkins(2)", "old"), ("Tag", "keep")])
    rc, _s, actor = _run(level, "set", ["MultiSkins=(0=A,5=B)"])
    assert rc == 0
    stored = [p for p in actor.props if p[0].startswith("MultiSkins")]
    assert stored == [("MultiSkins(0)", "A"), ("MultiSkins(5)", "B")]   # element 2 cleared
    assert ("Tag", "keep") in actor.props


def test_set_array_tuple_corners_error():
    level = _level()
    assert _run(level, "set", ["MultiSkins=()"])[0] == 2                # empty tuple
    assert _run(level, "set", ["MultiSkins=(9=A)"])[0] == 2             # out of bounds
    assert _run(level, "set", ["MultiSkins=(1=A,1=B)"])[0] == 2         # repeated index
    assert _run(level, "set", ["MultiSkins=Texture'T.X'"])[0] == 2      # non-tuple whole value


def test_set_paren_index_spelling_rejected_with_dot_hint(capsys):
    rc, _s, _a = _run(_level(), "set", ["MultiSkins(2)=X"])
    assert rc == 2
    assert "MultiSkins.2" in capsys.readouterr().err


def test_set_array_index_out_of_bounds_and_negative_error():
    assert _run(_level(), "set", ["MultiSkins.8=X"])[0] == 2
    assert _run(_level(), "set", ["MultiSkins.-1=X"])[0] == 2


# ── set: struct members ──────────────────────────────────────────────────────────


def test_set_member_preserves_stored_siblings():
    level = _level(props=[("Rotation", "(Pitch=1,Yaw=2)")])
    rc, _s, actor = _run(level, "set", ["Rotation.Yaw=8192"])
    assert rc == 0
    assert ("Rotation", "(Pitch=1,Yaw=8192)") in actor.props


def test_set_member_on_unset_prop_bases_on_class_default():
    # Rotation's class default is (Pitch=4096): the member edit must NOT zero Pitch (§3.1 +
    # the 2026-07-18 partial-value probe — unmentioned members mean the class default). The
    # base is the FULL effective default (default merged over zero — every member explicit,
    # store-explicit per ruling round-4 Q3).
    level = _level()
    rc, _s, actor = _run(level, "set", ["Rotation.Yaw=8192"])
    assert rc == 0
    assert ("Rotation", "(Pitch=4096,Yaw=8192,Roll=0)") in actor.props


def test_set_member_unknown_member_errors(capsys):
    rc, _s, _a = _run(_level(), "set", ["Rotation.Q=1"])
    assert rc == 2
    assert "Pitch" in capsys.readouterr().err            # names the valid members


def test_set_member_on_non_struct_errors():
    assert _run(_level(), "set", ["Mass.X=1"])[0] == 2


def test_set_member_value_validated_by_member_type():
    assert _run(_level(), "set", ["Rotation.Yaw=fast"])[0] == 2


# ── set: conflicts + atomicity + warnings ────────────────────────────────────────


def test_set_overlapping_tokens_error():
    level = _level()
    assert _run(level, "set", ["Group=a", "group=b"])[0] == 2           # same key twice
    assert _run(level, "set", ["Rotation=(Yaw=1)", "Rotation.Pitch=2"])[0] == 2   # whole+member


def test_set_is_atomic_across_tokens():
    level = _level(props=[("Group", "cells")])
    rc, saved, actor = _run(level, "set", ["Group=walls", "CsgOper=CSG_Bogus"])
    assert rc == 2 and saved is None
    assert actor.props == [("Group", "cells")]           # first token NOT applied


def test_set_warns_on_computed_but_scale_is_a_typed_field(capsys):
    # bSelected still warns (computed/won't-persist); MainScale is now a first-class TYPED field
    # (spec §10) so it routes to `actor.main_scale` and no longer warns "scale not applied".
    level = _level()
    rc, _s, actor = _run(level, "set", ["bSelected=True", "MainScale.Scale.X=2"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "computed" in err and "scale is not applied" not in err
    assert ("bSelected", "True") in actor.props
    from decimal import Decimal
    assert actor.main_scale is not None and actor.main_scale.scale[0] == Decimal(2)


def test_hard_rejects_apply_to_all_subcommands(capsys):
    level = _level(props=[("KeyPos(1)", "(X=1)")])
    for propsub, tokens in (("set", ["Name=Z"]), ("set", ["KeyNum=1"]),
                            ("set", ["KeyRot.1=(Yaw=1)"]), ("unset", ["Brush"]),
                            ("get", ["KeyPos.1"])):
        rc, saved, _a = _run(level, propsub, tokens)
        assert rc == 2 and saved is None, (propsub, tokens)
        assert "mover key" in capsys.readouterr().err


# NumKeys came OFF the hard-reject list (spec 2026-07-20): it is a first-class settable count,
# routed through the same bounded 2..8 / omit-when-2 setter `mover key count` uses.
_NUMKEYS_SCHEMA = dict(_SCHEMA, numkeys=_prop("NumKeys", "IntProperty"))


def test_set_numkeys_is_accepted_and_bounded_naming_the_value(capsys):
    level = _level()
    rc, saved, actor = _run(level, "set", ["NumKeys=4"], schema=_NUMKEYS_SCHEMA)
    assert rc == 0 and saved is not None
    assert actor.props == [("NumKeys", "4")]
    capsys.readouterr()                               # discard the success run's stdout/stderr
    rc2, saved2, _a = _run(_level(), "set", ["NumKeys=9"], schema=_NUMKEYS_SCHEMA)
    assert rc2 == 2 and saved2 is None
    assert capsys.readouterr().err == "NumKeys must be 2..8, got 9\n"


def test_set_numkeys_omits_at_the_default_of_two():
    level = _level(props=[("NumKeys", "5")])
    rc, _s, actor = _run(level, "set", ["NumKeys=2"], schema=_NUMKEYS_SCHEMA)
    assert rc == 0
    assert actor.props == []                          # 2 is the editor default — line dropped


def test_set_numkeys_non_integer_value_errors_cleanly(capsys):
    # A non-integer NumKeys is caught before the bounds check — a clean named error, no traceback.
    rc, saved, _a = _run(_level(), "set", ["NumKeys=abc"], schema=_NUMKEYS_SCHEMA)
    assert rc == 2 and saved is None
    assert capsys.readouterr().err == "NumKeys=abc: expected an integer\n"


def test_set_numkeys_on_a_class_without_it_is_rejected_by_schema(capsys):
    # A non-mover has no NumKeys in its schema → the ordinary unknown-property rejection.
    rc, saved, _a = _run(_level(), "set", ["NumKeys=4"])          # default _SCHEMA lacks numkeys
    assert rc == 2 and saved is None
    assert "Engine.Brush" in capsys.readouterr().err


def test_unknown_property_errors_naming_class(capsys):
    rc, _s, _a = _run(_level(), "set", ["Bogus=1"])
    assert rc == 2
    assert "Engine.Brush" in capsys.readouterr().err


def test_schema_error_surfaces_cleanly(capsys):
    from uedcli.uprops import SchemaError
    level = _level()
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="set", name="widget0",
                           tokens=["Group=x"], kv=False)
    src = mock.Mock()
    src.load.return_value = level
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.resolve_project",
                       side_effect=dispatch_mod.ProjectError("no project")), \
            mock.patch("uedcli.cli.resources.class_schema",
                       side_effect=SchemaError("package Engine not found")):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2 and not src.save.called
    assert "Engine" in capsys.readouterr().err


def test_hard_reject_never_resolves_the_schema():
    level = _level()
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="set", name="widget0",
                           tokens=["Name=Zed"], kv=False)
    src = mock.Mock()
    src.load.return_value = level
    schema = mock.Mock(side_effect=AssertionError("schema must not be resolved"))
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.resolve_project",
                       side_effect=dispatch_mod.ProjectError("no project")), \
            mock.patch("uedcli.cli.resources.class_schema", schema):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    assert not schema.called


# ── typed Location (ruling R2 + §6) ──────────────────────────────────────────────


def test_set_location_partial_struct_zero_fills():
    level = _level(location=(Decimal(9), Decimal(9), Decimal(9)))
    rc, _s, actor = _run(level, "set", ["Location=(X=1)"])
    assert rc == 0
    assert actor.location == (Decimal(1), Decimal(0), Decimal(0))


def test_set_location_comma_form_requires_all_components():
    level = _level()
    assert _run(level, "set", ["Location=1,2,3"])[0] == 0
    assert level.actors["Widget0"].location == (Decimal(1), Decimal(2), Decimal(3))
    assert _run(level, "set", ["Location=1,2"])[0] == 2


def test_set_location_member_bases_on_current():
    level = _level(location=(Decimal(4), Decimal(5), Decimal(6)))
    rc, _s, actor = _run(level, "set", ["Location.Y=50"])
    assert rc == 0
    assert actor.location == (Decimal(4), Decimal(50), Decimal(6))


def test_unset_location_member_zeroes_axis_and_whole_resets_origin():
    level = _level(location=(Decimal(4), Decimal(5), Decimal(6)))
    rc, _s, actor = _run(level, "unset", ["Location.Y"])
    assert rc == 0
    assert actor.location == (Decimal(4), Decimal(0), Decimal(6))
    rc2, _s, actor = _run(level, "unset", ["Location"])
    assert rc2 == 0
    assert actor.location is None


def test_typed_location_never_resolves_the_schema():
    level = _level()
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="set", name="widget0",
                           tokens=["Location=1,2,3"], kv=False)
    src = mock.Mock()
    src.load.return_value = level
    schema = mock.Mock(side_effect=AssertionError("schema must not be resolved"))
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.resolve_project",
                       side_effect=dispatch_mod.ProjectError("no project")), \
            mock.patch("uedcli.cli.resources.class_schema", schema):
        rc = dispatch_mod._dispatch(args)
    assert rc == 0
    assert not schema.called


def test_location_unknown_axis_errors():
    assert _run(_level(), "set", ["Location.Q=1"])[0] == 2


# ── unset ────────────────────────────────────────────────────────────────────────


def test_unset_whole_scalar_and_silent_on_absent():
    level = _level(props=[("Group", "cells")])
    rc, _s, actor = _run(level, "unset", ["Group", "Tag"])   # Tag not stored → silent
    assert rc == 0
    assert actor.props == []


def test_unset_whole_array_clears_every_element():
    level = _level(props=[("MultiSkins(0)", "A"), ("MultiSkins(5)", "B"), ("Tag", "keep")])
    rc, _s, actor = _run(level, "unset", ["MultiSkins"])
    assert rc == 0
    assert actor.props == [("Tag", "keep")]


def test_unset_single_element():
    level = _level(props=[("MultiSkins(0)", "A"), ("MultiSkins(5)", "B")])
    rc, _s, actor = _run(level, "unset", ["MultiSkins.5"])
    assert rc == 0
    assert actor.props == [("MultiSkins(0)", "A")]


def test_unset_member_removes_it_and_last_member_removes_line():
    level = _level(props=[("Rotation", "(Pitch=1,Yaw=2)")])
    rc, _s, actor = _run(level, "unset", ["Rotation.Pitch"])
    assert rc == 0
    assert ("Rotation", "(Yaw=2)") in actor.props
    rc2, _s, actor = _run(level, "unset", ["Rotation.Yaw"])
    assert rc2 == 0
    assert actor.props == []


def test_unset_token_with_value_errors():
    assert _run(_level(), "unset", ["Group=x"])[0] == 2


# ── get: keyed (effective view) ──────────────────────────────────────────────────


def test_get_stored_default_and_zero(capsys):
    level = _level(props=[("Group", "cells")])
    rc, saved, _a = _run(level, "get", ["Group", "LightBrightness", "Mass", "Tag"])
    assert rc == 0 and saved is None                     # a read never saves
    out = capsys.readouterr().out.splitlines()
    assert out == ["cells", "64", "100", "None"]         # stored / default / default / zero


def test_get_kv_mode_prints_canonical_keys(capsys):
    level = _level(props=[("Group", "cells")])
    rc, _s, _a = _run(level, "get", ["group", "lightbrightness"], kv=True)
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["Group=cells", "LightBrightness=64"]


def test_get_enum_renders_name_for_stored_ordinal(capsys):
    level = _level(props=[("CsgOper", "2")])
    rc, _s, _a = _run(level, "get", ["CsgOper"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "CSG_Subtract"


def test_get_whole_array_one_line_full_dim(capsys):
    level = _level(props=[("MultiSkins(2)", "Texture'T.Skin'")])
    rc, _s, _a = _run(level, "get", ["MultiSkins"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == ("(0=None,1=None,2=Texture'T.Skin',3=None,4=None,5=None,6=None,7=None)")


def test_get_array_element_bare(capsys):
    level = _level(props=[("MultiSkins(2)", "Texture'T.Skin'")])
    rc, _s, _a = _run(level, "get", ["MultiSkins.2", "MultiSkins.3"])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["Texture'T.Skin'", "None"]


def test_get_struct_full_form_fills_unmentioned_members_from_default(capsys):
    # stored partial (Yaw=8192); Rotation default (Pitch=4096) → the probe semantics fill
    # Pitch from the class default, Roll from zero.
    level = _level(props=[("Rotation", "(Yaw=8192)")])
    rc, _s, _a = _run(level, "get", ["Rotation"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "(Pitch=4096,Yaw=8192,Roll=0)"


def test_get_struct_member_falls_through_stored_then_default(capsys):
    level = _level(props=[("Rotation", "(Yaw=8192)")])
    rc, _s, _a = _run(level, "get", ["Rotation.Yaw", "Rotation.Pitch"])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["8192", "4096"]


def test_get_struct_member_with_a_quoted_comma_in_a_sibling(capsys):
    # Regression: the struct-text splitter used to split on ANY depth-0 comma, so the comma inside
    # `Text="a,b"` broke the literal into bogus members and every read/write of the struct failed.
    level = _level(props=[("Note", '(Text="a,b",Count=1)')])
    rc, _s, _a = _run(level, "get", ["Note.Count", "Note.Text"])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["1", '"a,b"']


def test_set_struct_member_preserves_a_quoted_comma_sibling():
    level = _level(props=[("Note", '(Text="a,b",Count=1)')])
    rc, _s, actor = _run(level, "set", ["Note.Count=7"])
    assert rc == 0
    assert dict(actor.props)["Note"] == '(Text="a,b",Count=7)'


def test_get_unset_struct_prints_class_default(capsys):
    # §4: a struct key prints the FULL member form — the sparse default (Pitch=4096) merges
    # over the zero struct (review M5: the default text alone is not the promised full form).
    rc, _s, _a = _run(_level(), "get", ["Rotation"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "(Pitch=4096,Yaw=0,Roll=0)"


def test_get_location_and_axis(capsys):
    level = _level(location=(Decimal(4), Decimal(5), Decimal("-17")))
    rc, _s, _a = _run(level, "get", ["Location", "Location.Z"])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["(X=4,Y=5,Z=-17)", "-17"]


def test_get_duplicate_keys_allowed_line_per_key(capsys):
    level = _level(props=[("Group", "cells")])
    rc, _s, _a = _run(level, "get", ["Group", "Group"])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["cells", "cells"]


def test_get_validates_all_keys_before_output(capsys):
    level = _level(props=[("Group", "cells")])
    rc, _s, _a = _run(level, "get", ["Group", "Bogus"])
    assert rc == 2
    cap = capsys.readouterr()
    assert cap.out == ""                                 # nothing printed before the error
    assert "Bogus" in cap.err


def test_get_bool_default_and_zero(capsys):
    rc, _s, _a = _run(_level(), "get", ["bHidden", "bSelected"])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["True", "False"]


# ── get: dump-all (stored view) ──────────────────────────────────────────────────


def test_dump_all_location_first_stored_order_dot_spelling(capsys):
    level = _level(props=[("Group", "cells"), ("MultiSkins(2)", "X"), ("Rotation", "(Yaw=1)")],
                   location=(Decimal(1), Decimal(2), Decimal(3)))
    rc, _s, _a = _run(level, "get", [])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == [
        "Location=(X=1,Y=2,Z=3)",
        "Group=cells",
        "MultiSkins.2=X",                                # dot-canonical, value verbatim
        "Rotation=(Yaw=1)",                              # STORED view: partial stays partial
    ]


def test_dump_all_skips_mover_bookkeeping_and_errors_on_alien(capsys):
    level = _level(props=[("KeyPos(1)", "(X=1)"), ("Group", "cells")])
    rc, _s, _a = _run(level, "get", [])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["Location=(X=0,Y=0,Z=0)", "Group=cells"]
    level2 = _level(props=[("WeirdProp", "1")])
    rc2, _s, _a = _run(level2, "get", [])
    assert rc2 == 2                                      # ruling R4: hard error
    assert "WeirdProp" in capsys.readouterr().err


def test_dump_all_kv_flag_is_legal_noop(capsys):
    level = _level(props=[("Group", "cells")])
    rc, _s, _a = _run(level, "get", [], kv=True)
    assert rc == 0
    assert "Group=cells" in capsys.readouterr().out


# ── actor resolution ─────────────────────────────────────────────────────────────


def test_unknown_actor_errors(capsys):
    level = _level()
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="get", name="nosuch",
                           tokens=[], kv=False)
    src = mock.Mock()
    src.load.return_value = level
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    assert "Actor not found: nosuch" in capsys.readouterr().err


# ── review-gate regressions (build reviews A/B/C, 2026-07-18) ────────────────────


def _nest_fixtures():
    """A struct with a NESTED struct member and a MEMBER static array (review findings A2/B6:
    real DX has both — Scale{Vector,…}, NearbyProjectileList.List[8])."""
    nest = _prop("Nest", "StructProperty", type_ref=9, type_name="NestS")
    marks = _prop("Marks", "ByteProperty", array_dim=4)
    inner = _prop("Inner", "StructProperty", type_ref=3, type_name="Vector")
    rate = _prop("Rate", "FloatProperty")
    schema = dict(_SCHEMA)
    schema["nest"] = nest
    members = {"nests": [inner, rate, marks]}

    def members_for(p):
        if (p.type_name or "").casefold() in members:
            return list(members[(p.type_name or "").casefold()])
        return _members_for(p)
    defaults = dict(_DEFAULTS)
    defaults[("nest", 0)] = "(Inner=(X=1,Y=1,Z=1),Rate=0.5,Marks(0)=7)"
    return schema, members_for, defaults


def _run_nest(level, propsub, tokens=(), *, kv=False):
    schema, members_for, defaults = _nest_fixtures()
    args = SimpleNamespace(cmd="actor", sub="prop", propsub=propsub, name="widget0",
                           tokens=list(tokens), kv=kv)
    src = mock.Mock()
    src.load.return_value = level
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.resolve_project",
                       side_effect=dispatch_mod.ProjectError("no project")), \
            mock.patch("uedcli.cli.resources.class_schema", lambda cls, project=None: dict(schema)), \
            mock.patch("uedcli.cli.resources.class_defaults",
                       lambda cls, project=None: dict(defaults)), \
            mock.patch("uedcli.cli.resources.struct_members",
                       lambda p, project=None: members_for(p)), \
            mock.patch("uedcli.cli.resources.enum_names",
                       lambda p, project=None: p.enum_value_names):
        rc = dispatch_mod._dispatch(args)
    return rc, level.actors["Widget0"]


def test_nonfinite_and_out_of_range_numbers_rejected(capsys):
    # review B1/B2: nan/inf passed Decimal() and tracebacked later; 1e999 ballooned the trunk
    level = _level()
    for tok in ("Location.X=nan", "Location.X=inf", "Location=(X=snan)", "Location=1e999,0,0",
                "Mass=nan", "Mass=1e999"):
        rc, saved, _a = _run(level, "set", [tok])
        assert rc == 2 and saved is None, tok
        assert "Traceback" not in capsys.readouterr().err


def test_duplicate_stored_lines_set_edits_winner_unset_removes_all():
    # review A5/B5: T3D import is last-wins; set must edit the winner and drop shadowed dups
    level = _level(props=[("Tag", "one"), ("Tag", "two")])
    rc, _s, actor = _run(level, "set", ["Tag=nine"])
    assert rc == 0
    assert actor.props == [("Tag", "nine")]
    level2 = _level(props=[("Tag", "one"), ("Tag", "two")])
    rc2, _s, actor2 = _run(level2, "unset", ["Tag"])
    assert rc2 == 0
    assert actor2.props == []


def test_unindexed_array_line_is_element_zero(capsys):
    # review A4: a bare `MultiSkins=X` stored line is element 0 (T3D semantics)
    level = _level(props=[("MultiSkins", "Texture'T.A'")])
    rc, _s, actor = _run(level, "set", ["MultiSkins.0=Texture'T.B'"])
    assert rc == 0
    assert actor.props == [("MultiSkins(0)", "Texture'T.B'")]      # no duplicate line
    level2 = _level(props=[("MultiSkins", "Texture'T.A'")])
    rc2, _s, actor2 = _run(level2, "unset", ["MultiSkins.0"])
    assert rc2 == 0 and actor2.props == []
    level3 = _level(props=[("MultiSkins", "Texture'T.A'")])
    rc3, _a3 = _run_nest(level3, "get", [])[0], None
    del rc3, _a3
    rc4, _s, _a = _run(level3, "get", [])
    assert rc4 == 0
    assert "MultiSkins.0=Texture'T.A'" in capsys.readouterr().out  # dump-all round-trippable


def test_member_array_paths_set_get_roundtrip(capsys):
    # review B6: struct members that are static arrays (Nest.Marks.1 ↔ Marks(1)= in the text)
    level = _level()
    rc, actor = _run_nest(level, "set", ["Nest.Marks.1=9"])
    assert rc == 0
    stored = dict(actor.props)["Nest"]
    assert "Marks(1)=9" in stored and "Inner=(X=1,Y=1,Z=1)" in stored
    capsys.readouterr()                                   # drain `set`'s producer name-line
    rc2, _a = _run_nest(level, "get", ["Nest.Marks.1", "Nest.Marks.0", "Nest.Marks"], kv=False)
    assert rc2 == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "9"
    assert out[1] == "7"                                  # default element preserved
    assert out[2] == "(0=7,1=9,2=0,3=0)"                  # whole member array as a tuple


def test_nested_struct_member_falls_through_to_default(capsys):
    # review A2: a stored partial NESTED member must not zero its siblings — merge recursively
    level = _level(props=[("Nest", "(Inner=(X=2))")])
    rc, _a = _run_nest(level, "get", ["Nest.Inner.Y", "Nest"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "1"                                  # default member survives
    assert out[1] == "(Inner=(X=2,Y=1,Z=1),Rate=0.5,Marks(0)=7,Marks(1)=0,Marks(2)=0,Marks(3)=0)"


def test_member_unset_noop_leaves_stored_line_untouched():
    # review A8: a silent-success member unset must not rewrite (or re-normalize) the line
    level = _level(props=[("Rotation", '"(Yaw=8192)"')])
    rc, _s, actor = _run(level, "unset", ["Rotation.Pitch"])
    assert rc == 0
    assert actor.props == [("Rotation", '"(Yaw=8192)"')]  # byte-identical, quotes and all


def test_quote_stripping_only_wrapping_pairs():
    # review B10: only a WRAPPING quote pair strips — inner/unmatched quotes survive
    level = _level()
    rc, _s, actor = _run(level, "set", ['Tag="a" and "b"'])
    assert rc == 0
    assert ('Tag', '"a" and "b"') in actor.props


def test_paren_with_path_still_gets_dot_hint(capsys):
    # review A9/B7: `MultiSkins(2).X` must earn the dot-form hint too
    rc, _s, _a = _run(_level(), "set", ["MultiSkins(2)=Q"])
    assert rc == 2
    assert "MultiSkins.2" in capsys.readouterr().err
    rc2, _s, _a = _run(_level(), "get", ["Velocity(0).X"])
    assert rc2 == 2
    assert "Velocity.0.X" in capsys.readouterr().err


def test_kv_roundtrip_reproduces_effective_state(capsys):
    # review C M4 / spec §4 "round-trip clean": get --kv fed back into set reproduces the
    # effective state (including struct + array + typed Location forms)
    level = _level(props=[("Rotation", "(Yaw=8192)"), ("MultiSkins(2)", "Texture'T.S'"),
                          ("CsgOper", "2")],
                   location=(Decimal(4), Decimal(5), Decimal(6)))
    keys = ["Rotation", "MultiSkins", "CsgOper", "Location", "Mass"]
    rc, _s, _a = _run(level, "get", keys, kv=True)
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    level2 = _level()
    rc2, _s, _a2 = _run(level2, "set", lines)
    assert rc2 == 0
    capsys.readouterr()                                   # drain `set`'s producer name-line
    rc3, _s, _a = _run(level2, "get", keys, kv=True)
    assert rc3 == 0
    assert capsys.readouterr().out.splitlines() == lines


def test_prop_set_prints_touched_name_to_stdout(capsys):
    # producer follow-up (2026-07-19): set emits the touched canonical name to stdout, summary → stderr
    rc, _s, _a = _run(_level(), "set", ["Group=walls"])
    assert rc == 0
    cap = capsys.readouterr()
    assert cap.out == "Widget0\n" and "set on 1 actor(s)" in cap.err


def test_prop_unset_prints_touched_name_to_stdout(capsys):
    rc, _s, _a = _run(_level(props=[("Group", "walls")]), "unset", ["Group"])
    assert rc == 0
    cap = capsys.readouterr()
    assert cap.out == "Widget0\n" and "unset on 1 actor(s)" in cap.err


def test_empty_string_value_stores_and_prints_empty_line(capsys):
    # spec §2.1/§2.3: KEY= is a legal empty string; bare-mode get prints an empty line
    level = _level()
    rc, _s, actor = _run(level, "set", ["Tag="])
    assert rc == 0
    assert ("Tag", "") in actor.props
    capsys.readouterr()                                   # drain `set`'s producer name-line
    rc2, _s, _a = _run(level, "get", ["Tag"])
    assert rc2 == 0
    assert capsys.readouterr().out == "\n"


def test_get_location_never_resolves_schema():
    # review C L7c: the §2.4 laziness holds for READS too
    level = _level(location=(Decimal(1), Decimal(2), Decimal(3)))
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="get", name="widget0",
                           tokens=["Location", "Location.X"], kv=False)
    src = mock.Mock()
    src.load.return_value = level
    schema = mock.Mock(side_effect=AssertionError("schema must not be resolved"))
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.resolve_project",
                       side_effect=dispatch_mod.ProjectError("no project")), \
            mock.patch("uedcli.cli.resources.class_schema", schema):
        rc = dispatch_mod._dispatch(args)
    assert rc == 0
    assert not schema.called


def test_comma_sugar_non_numeric_component_errors(capsys):
    rc, _s, _a = _run(_level(), "set", ["Velocity=1,two,3"])
    assert rc == 2
    assert "number" in capsys.readouterr().err
