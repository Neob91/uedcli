"""Pins for `uscript.ordering` — UED22 `SavePackage` table ordering, RE'd from `core.dll`.

Export order is reproduced byte-exact vs real UCC compiles (no docker needed — pure model). The
name/import COUNT keys are pinned via their tier structure; the within-tier order needs the engine's
global FName/GObjObjects index (see `ordering.py`) and is not asserted here.
"""
from __future__ import annotations

from uedcli.uscript.global_index import default_global_index
from uedcli.uscript.ordering import ObjInput, msvc_qsort, order_exports, order_package


def _expands_object(cls: str, members: list[tuple[str, str]], defaults: set[str]):
    """Build the object graph + creation order for `class <cls> expands Object;` with `members`
    (name, property-class) and a set of member names carrying a default value."""
    objs = [ObjInput(name="ScriptText", class_name="TextBuffer", outer=cls, in_package=True,
                     name_refs=("None",))]
    for i, (mn, pc) in enumerate(members):
        nxt = (members[i + 1][0],) if i + 1 < len(members) else ()
        # Each declared property contributes its own name once (empirically count 1 per property,
        # independent of a default — the class CDO's tagged-property serialization) plus the body's
        # None terminator + None category (non-editable var).
        objs.append(ObjInput(name=mn, class_name=pc, outer=cls, in_package=True,
                             name_refs=(mn, "None", "None"), obj_refs=nxt))
    child = (members[0][0],) if members else ()
    # A default value does NOT add to a member NAME's count (empirically every member name is
    # count 1); `defaults` only affects the member's *value* bytes, not table ordering.
    _ = defaults
    nrefs = (cls, cls, "Core", "System", "None")
    orefs = ("Object", "ScriptText", *child, cls, "Object", "Object")
    objs.append(ObjInput(name=cls, class_name="Class", outer=None, in_package=True,
                        name_refs=nrefs, obj_refs=orefs))
    ptypes = list(dict.fromkeys(pc for _, pc in members))
    for n, c, o in [("Core", "Package", None), ("Object", "Class", "Core"),
                    ("Class", "Class", "Core"), ("TextBuffer", "Class", "Core")]:
        objs.append(ObjInput(name=n, class_name=c, outer=o, in_package=False))
    for pc in ptypes:
        objs.append(ObjInput(name=pc, class_name="Class", outer="Core", in_package=False))
    creation = [cls, "ScriptText", *(m for m, _ in members)]
    return objs, creation


def test_export_order_usc_hello():
    objs, creation = _expands_object("UscHello", [], set())
    assert order_exports(objs, creation) == ["ScriptText", "UscHello"]


def test_export_order_usc_vars():
    objs, creation = _expands_object(
        "UscVars", [("Alpha", "IntProperty"), ("Beta", "FloatProperty"), ("Gamma", "StrProperty")],
        {"Alpha", "Beta"})
    assert order_exports(objs, creation) == ["ScriptText", "Alpha", "Beta", "Gamma", "UscVars"]


def test_export_order_members_follow_declaration():
    objs, creation = _expands_object(
        "Q4", [("wun", "IntProperty"), ("two", "IntProperty"),
               ("tre", "IntProperty"), ("For", "IntProperty")], set())
    # ScriptText first, class last, members in declaration order between (UCC-verified).
    assert order_exports(objs, creation) == ["ScriptText", "wun", "two", "tre", "For", "Q4"]


def test_name_count_tiers():
    """The name sort key is a reference count; these tiers reproduce every sampled UCC package:
    None (highest) > class (2) > {member names, Core, System} (1) > stock import names (0)."""
    objs, creation = _expands_object(
        "UscVars", [("Alpha", "IntProperty"), ("Beta", "FloatProperty"), ("Gamma", "StrProperty")],
        {"Alpha", "Beta"})
    k = order_package(objs, creation).name_key
    assert k["None"] > k["UscVars"] > k["Core"]
    assert k["UscVars"] == 2
    assert k["Alpha"] == k["Beta"] == k["Gamma"] == k["Core"] == k["System"] == 1
    for stock in ("Class", "Object", "Package", "TextBuffer", "ScriptText", "IntProperty"):
        assert k.get(stock, 0) == 0


def test_import_order_reproduces_ucc():
    """The corpus-reconstructed object order reproduces both goldens' IMPORT table byte-exact.
    Imports are all stock objects, so one global order suffices (unlike names — see below)."""
    gi = default_global_index()
    hello = order_package(*_expands_object("UscHello", [], set()), gi)
    assert hello.imports == ["Core", "Object", "TextBuffer", "Class"]
    vars_ = order_package(*_expands_object(
        "UscVars", [("Alpha", "IntProperty"), ("Beta", "FloatProperty"), ("Gamma", "StrProperty")],
        {"Alpha", "Beta"}), gi)
    assert vars_.imports == ["Core", "Object", "FloatProperty", "IntProperty", "Class", "TextBuffer",
                             "StrProperty"]


def test_name_order_member_free_reproduces_ucc():
    """A member-free class (UscHello) reproduces its NAME table byte-exact from the stock name order.
    Member-bearing classes do NOT (member FNames interleave with stock by property type, not a static
    table — see `global_index.py`), so only the member-free case is pinned."""
    hello = order_package(*_expands_object("UscHello", [], set()), default_global_index())
    assert hello.names == ["None", "UscHello", "Core", "System", "Class", "TextBuffer",
                           "ScriptText", "Package", "Object"]


def test_msvc_qsort_equal_key_permutation():
    """The CRT shortsort maps an all-equal creation order to this fixed rotation — the reason a
    plain member class exports as [ScriptText, members…, class]."""
    got = msvc_qsort(["Class", "ScriptText", "a", "b", "c"], lambda x, y: 0)
    assert got == ["ScriptText", "a", "b", "c", "Class"]
