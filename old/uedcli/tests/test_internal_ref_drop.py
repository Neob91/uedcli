"""`_internal_ref`: a top-level intra-level object ref whose target this build omits is DROPPED
(reset to class default), not emitted as `Base=None`.

The editor's MAP IMPORT resets an unresolvable `MyLevel.X` object ref to the class default and, that
default being None, does not serialize it. Native must omit the prop too -- emitting a default-valued
tag the editor drops is a byte divergence (Island ThugMale5.Base, N=10..12).
"""
from uedcli.native.actor_write import PT_INT, PT_OBJECT, Prop, StructValue
from uedcli.native.assemble import ObjRef
from uedcli.native.props import ImportRef
from uedcli.native.unbuilt import _internal_ref


def _base(target="LevelInfo0"):
    return Prop("Base", PT_OBJECT, ImportRef("LevelInfo", f"MyLevel.{target}"))


def test_top_level_ref_dropped_when_target_absent():
    warns = []
    assert _internal_ref(_base(), present=set(), owner="ThugMale5", warnings=warns) is None
    assert warns and "dropped" in warns[0]


def test_top_level_ref_kept_as_objref_when_target_present():
    p = _internal_ref(_base(), present={"LevelInfo0"}, owner="ThugMale5", warnings=[])
    assert p is not None and isinstance(p.value, ObjRef) and p.value.name == "LevelInfo0"


def test_non_object_ref_never_dropped():
    p = Prop("MaxRange", PT_INT, 1000)
    assert _internal_ref(p, present=set(), owner="X", warnings=[]) is p


def test_struct_member_ref_resets_but_prop_kept():
    # An internal ref INSIDE a struct is reset to 0 by recursion; the prop itself survives (the
    # editor resets the struct to spawn state, it does not drop the whole property).
    sv = StructValue("PointRegion", [Prop("Zone", PT_OBJECT, ImportRef("LevelInfo", "MyLevel.LevelInfo0"))])
    p = Prop("Region", PT_OBJECT, sv, struct_name="PointRegion")
    out = _internal_ref(p, present=set(), owner="X", warnings=[])
    assert out is p and out.value.members[0].value == 0
