"""Exercises the REAL bodies the autouse `_stub_author_validation` no-ops elsewhere:
`utexture.TextureResolver.exists`, the `class list`/`class show` dispatch handler, and the
`_validate_ingest_actors` ingest gate driven through `actor add`. A fake substrate (an injected
`ClassIndex` + a fake `TextureResolver`) stands in for the gitignored v68 install.
"""
import argparse
import io

import pytest

from uedctl import classindex, config, dispatch, trunk, uprops, utexture
from uedctl.classindex import ClassIndex
from uedctl.model import Actor, Level
from uedctl.uprops import Prop


# --------------------------------------------------------------------------- TextureResolver.exists
def _texpkg(entries):
    """A minimally-fabricated `utexture.Package` with the given `(name, group|None)` Texture exports
    (import 0 = the "Texture" class, so `cls=-1` marks a texture export)."""
    names = ["Texture", "None"]
    imports = [(0, 0, 0, 0)]                              # import[-1] → ObjectName idx 0 = "Texture"

    def nidx(s):
        if s not in names:
            names.append(s)
        return names.index(s)

    exports = []
    for name, group in entries:
        outer = 0
        if group is not None:
            imports.append((0, 0, 0, nidx(group)))       # a group import
            outer = -len(imports)                        # negative ref to that import
        exports.append({"cls": -1, "nm": nidx(name), "outer": outer, "soff": 0, "ssize": 0})
    return utexture.Package(version=68, names=names, imports=imports, exports=exports, buf=b"")


def _resolver(**pkgs):
    r = utexture.TextureResolver([])
    for stem, pkg in pkgs.items():
        r._by_stem[stem.casefold()] = f"{stem}.utx"
        r._pkg_cache[stem.casefold()] = pkg
    return r


def test_texture_exists_qualified_and_missing():
    r = _resolver(CoreTex=_texpkg([("Stone", None), ("Metal", None)]))
    assert r.exists("CoreTex.Stone")
    assert r.exists("coretex.stone")                     # case-insensitive
    assert not r.exists("CoreTex.Nope")                  # unknown name in a known package
    assert not r.exists("Nope.Stone")                    # unknown package
    assert not r.exists("A.B.C.D")                       # over-dotted → miss


def test_texture_exists_group_and_bare_any_package():
    r = _resolver(CoreTex=_texpkg([("Stone", "Rock")]),
                  DecoTex=_texpkg([("Vase", None)]))
    assert r.exists("CoreTex.Rock.Stone")                # 3-part group match
    assert r.exists("CoreTex.Stone")                     # group ignored — 2-part still matches
    assert r.exists("Vase")                              # bare → exists in ANY package
    assert not r.exists("Nothing")                       # bare, in no package


def test_texture_exists_is_existence_not_decodability():
    # `buf=b""` means these exports have NO decodable mip/palette — resolve() would return None, but
    # exists() must still say True (a real non-P8/undecodable texture must never false-reject).
    r = _resolver(Weird=_texpkg([("RGBA7Tex", None)]))
    assert r.exists("Weird.RGBA7Tex")
    assert r.resolve("Weird.RGBA7Tex") is None           # ...and decode genuinely fails


def test_texture_exists_is_cached():
    pkg = _texpkg([("Stone", None)])
    r = _resolver(CoreTex=pkg)
    assert r.exists("CoreTex.Stone")
    r._pkg_cache["coretex"] = _texpkg([])                # swap out the package
    assert r.exists("CoreTex.Stone")                     # cached True, not re-scanned


# --------------------------------------------------------------------------- fake class substrate
def _fake_index():
    idx = ClassIndex(_paths={"core": "x", "engine": "x", "deco": "x"},
                     _stems={"core": "Core", "engine": "Engine", "deco": "Deco"})
    idx._all = ["Core.Object", "Engine.Actor", "Engine.Light", "Engine.Brush",
                "Engine.Decoration", "Deco.Vase"]
    idx._ancestry = {                                          # every chain roots at Core.Object,
        "core.object": ["Core.Object"],                        # consistent with _children below
        "engine.actor": ["Engine.Actor", "Core.Object"],
        "engine.light": ["Engine.Light", "Engine.Actor", "Core.Object"],
        "engine.brush": ["Engine.Brush", "Engine.Actor", "Core.Object"],
        "engine.decoration": ["Engine.Decoration", "Engine.Actor", "Core.Object"],
        "deco.vase": ["Deco.Vase", "Engine.Decoration", "Engine.Actor", "Core.Object"],
    }
    idx._abstract = {"core.object": True, "engine.actor": True, "engine.decoration": True,
                     "engine.light": False, "engine.brush": False, "deco.vase": False}
    idx._cmaps = {"core": {"object": 1},
                  "engine": {"actor": 1, "light": 2, "brush": 3, "decoration": 4},
                  "deco": {"vase": 1}}
    idx._children = {"core.object": ["Engine.Actor"],           # Core.Object is Engine.Actor's parent
                     "engine.actor": ["Engine.Brush", "Engine.Decoration", "Engine.Light"],
                     "engine.decoration": ["Deco.Vase"]}        # for the class-list tree
    return idx


class _FakeResolver:
    """A TextureResolver stand-in: only `CoreTex.Stone`/bare `Stone` exist."""
    def __init__(self, _files):
        pass

    def exists(self, ref):
        return ref.split(".")[-1].casefold() == "stone"


@pytest.fixture
def substrate(monkeypatch):
    """Inject the fake class index + texture resolver + a non-empty package path."""
    monkeypatch.setattr(ClassIndex, "from_project",
                        classmethod(lambda cls, project, user_config: _fake_index()))
    monkeypatch.setattr(config, "composed_search_files", lambda project, user_config: [("x.utx", "base")])
    monkeypatch.setattr(config, "load_user_config", lambda: object())
    monkeypatch.setattr(utexture, "TextureResolver", _FakeResolver)


def _project(tmp_path, monkeypatch, actors=None):
    proj = tmp_path / "repo"
    (proj / "maps" / "lvl").mkdir(parents=True)
    (proj / "uedctl.toml").write_text('game = "deusex"\n')
    trunk.write_level(proj / "maps" / "lvl", Level(actors=actors or {}),
                      {n: "m" for n in (actors or {})})
    monkeypatch.setenv("UEDCTL_LEVEL", "lvl")
    return proj


# --------------------------------------------------------------------------- class list/show handler
def test_class_list_default_is_an_indented_tree(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    out = _run_class(monkeypatch, capsys, proj, sub="list")
    assert out.splitlines()[0] == "Engine.Actor *"       # root at top, abstract-marked
    assert "\n  Engine.Light" in out                     # direct child, one indent, no abstract mark
    assert "\n  Engine.Decoration *" in out              # abstract child
    assert "\n    Deco.Vase" in out                      # grandchild, deeper indent


def test_class_list_tree_reroots_with_subclass_of(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    out = _run_class(monkeypatch, capsys, proj, sub="list", subclass_of="Engine.Decoration")
    assert out.splitlines()[0] == "Engine.Decoration *"  # rerooted
    assert "\n  Deco.Vase" in out
    assert "Engine.Light" not in out                     # outside the subtree


def test_class_list_tree_depth_collapses_frontier(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    out = _run_class(monkeypatch, capsys, proj, sub="list", depth=1)
    assert out.splitlines()[0] == "Engine.Actor *"       # root
    assert "\n  Engine.Decoration * (1)" in out          # frontier node: abstract-marked + (N) hidden kids
    assert "\n  Engine.Light" in out and "* (1)" not in out.split("Engine.Light")[1][:6]  # leaf, no count
    assert "Deco.Vase" not in out                         # depth 1 = children only; grandchild collapsed away


def test_class_list_tree_depth_all_expands_with_no_collapse(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    out = _run_class(monkeypatch, capsys, proj, sub="list", depth=float("inf"))   # --depth all
    assert "Deco.Vase" in out                             # full depth reached (grandchild shown)
    assert "(1)" not in out and "(2)" not in out          # NO (N) collapse anywhere at --depth all


def test_class_list_tree_include_non_actor_reroots_at_core_object(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    out = _run_class(monkeypatch, capsys, proj, sub="list", include_non_actor=True)
    assert out.splitlines()[0] == "Core.Object *"         # --include-non-actor roots the tree at Core.Object
    assert "\n  Engine.Actor *" in out                    # Engine.Actor now a child, one indent
    assert "Deco.Vase" in out                             # small tree fits the budget in full


def test_class_list_tree_leaf_root_is_a_single_line(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    out = _run_class(monkeypatch, capsys, proj, sub="list", subclass_of="Engine.Light")
    assert out.splitlines() == ["Engine.Light"]           # a childless root renders as itself alone


def test_class_list_tree_package_prunes_to_reaching_branches(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    out = _run_class(monkeypatch, capsys, proj, sub="list", package="Deco")
    assert "Deco.Vase" in out                             # the in-package leaf...
    assert "Engine.Decoration" in out                     # ...kept via its reaching ancestor branch
    assert "Engine.Light" not in out and "Engine.Brush" not in out   # off-branch classes pruned


def test_class_list_tree_package_with_no_matches_hints(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)                # Core's only class (Core.Object) is ABOVE the
    rc, cap = _run_class_cap(monkeypatch, capsys, proj, sub="list", package="Core")  # Engine.Actor root
    assert rc == 0
    assert cap.out.splitlines() == ["Engine.Actor *"]     # nothing under the root is in Core → root only
    assert "no classes under Engine.Actor are in package Core" in cap.err


def test_class_list_flat_is_the_pipeable_list(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    lines = _run_class(monkeypatch, capsys, proj, sub="list", flat=True).split()
    assert "Engine.Light" in lines and "Engine.Decoration" in lines   # flat categories (depth-1)
    assert "Deco.Vase" not in lines and "Engine.Actor" not in lines
    # --flat drill / every-class dump / --package / error path (the flat list_classes logic)
    assert _run_class(monkeypatch, capsys, proj, sub="list", flat=True,
                      subclass_of="Engine.Decoration").split() == ["Deco.Vase"]
    # the faithful "every class" dump: --subclass-of Core.Object --include-abstract (see migration map)
    assert "Engine.Actor" in _run_class(monkeypatch, capsys, proj, sub="list", flat=True,
                                        subclass_of="Core.Object", include_abstract=True).split()
    rc, err = _run_class_rc(monkeypatch, capsys, proj, sub="list", flat=True, subclass_of="Engine.Bogus")
    assert rc == 2 and "unknown --subclass-of class" in err


def test_class_list_flat_include_non_actor_reaches_actor_from_core_object(tmp_path, monkeypatch, capsys):
    # dispatch → list_classes wiring for --include-non-actor in --flat mode (reroots at Core.Object).
    proj = _project(tmp_path, monkeypatch)
    lines = _run_class(monkeypatch, capsys, proj, sub="list", flat=True,
                       include_non_actor=True, depth=float("inf")).split()
    assert "Engine.Actor" in lines and "Deco.Vase" in lines   # every class below Core.Object, any depth
    assert "Core.Object" not in lines                         # the root itself is skipped (d==0)


def test_class_list_include_abstract_errors_where_it_has_no_effect(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    # tree (no --flat): --include-abstract can't act → HARD ERROR, exit 2 (not a silent no-op / warning)
    rc, err = _run_class_rc(monkeypatch, capsys, proj, sub="list", include_abstract=True)
    assert rc == 2 and "not valid here" in err
    # --flat --subclass-of drill: it genuinely acts → exit 0, and the abstract base is kept
    out = _run_class(monkeypatch, capsys, proj, sub="list", flat=True,
                     subclass_of="Engine.Decoration", include_abstract=True)
    assert "Engine.Decoration" in out.split()  # abstract base now listed
    # --flat --subclass-of BUT with --depth (browse already unfiltered) → can't act → error again
    rc3, err3 = _run_class_rc(monkeypatch, capsys, proj, sub="list", flat=True,
                              subclass_of="Engine.Decoration", depth=1, include_abstract=True)
    assert rc3 == 2 and "not valid here" in err3


def test_class_list_legacy_all_errors_with_split_pointer(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    rc, err = _run_class_rc(monkeypatch, capsys, proj, sub="list", legacy_all=True)
    assert rc == 2 and "--all was split" in err
    assert "--include-non-actor" in err and "--include-abstract" in err and "--depth all" in err


def test_class_show_legacy_all_errors_with_rename_pointer(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    rc, err = _run_class_rc(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light", legacy_all=True)
    assert rc == 2 and "--all was renamed" in err and "--depth all" in err


def _prop(name, owner, kind="ByteProperty", category=None):
    return Prop(name=name, kind=kind, array_dim=1, property_flags=0, type_ref=0,
                type_name=None, owner=owner, category=category)


def _show_setup(monkeypatch, union):
    # The `_cache=None` param is kept in the stub signature only to match resolve_class_properties'
    # real signature; `class show` no longer seeds it (the seed was dropped 2026-07-20 so the prop
    # walk uses the persistent schema cache). Nothing else needs stubbing: every class fact the
    # header prints comes off the fake index below.
    monkeypatch.setattr(uprops, "resolve_class_properties",
                        lambda fqcn, resolver, _cache=None: union)


def test_class_show_default_own_by_category_with_inherited_counts(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    union = [_prop("LightBrightness", "Engine.Light", category="Lighting"),   # OWN, editable
             _prop("LE1", "Engine.Actor", category="Lighting"),               # inherited, same category
             _prop("LE2", "Engine.Actor", category="Lighting"),               # inherited, same category
             _prop("Location", "Engine.Actor", kind="StructProperty", category="Movement"),  # cat has no own
             _prop("iInternal", "Engine.Light", category=None)]               # own but non-editable → hidden
    _show_setup(monkeypatch, union)
    out = _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light")
    assert "Lighting:" in out and "LightBrightness" in out                    # own prop shown in its group
    assert "(+2 inherited, from 1 superclass)" in out                         # same-category inherited COUNTED
    assert "LE1" not in out and "LE2" not in out                              # ...but not listed
    assert "iInternal" not in out                                            # non-editable var hidden
    assert "Movement:" not in out and "Location" not in out                  # entirely-inherited → collapsed
    assert "(+1 inherited, in 1 more category: Movement)" in out             # the collapsed tail


def test_class_show_budgets_own_categories(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    union = [_prop(f"P{i}", "Engine.Light", category=f"Cat{i}") for i in range(40)]  # 40 own categories
    _show_setup(monkeypatch, union)
    out = _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light")
    assert "Cat0:" in out                                  # first own category shown
    assert "more own categories hidden:" in out            # trailer now LISTS the hidden names...
    assert "Cat39:" not in out and "Cat39" in out          # ...so a budget-hidden category is named


def test_class_show_depth_all_expands_with_fqcn_tags(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    union = [_prop("Own", "Engine.Light", category="Lighting"),
             _prop("Location", "Engine.Actor", kind="StructProperty", category="Movement")]
    _show_setup(monkeypatch, union)                       # chain (fake) = Engine.Light -> Engine.Actor
    out = _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light", depth=float("inf"))
    assert "Lighting:" in out and "Own: ByteProperty" in out                 # own prop, UNTAGGED
    assert "Location: StructProperty   ← Engine.Actor" in out                # inherited, FQCN-TAGGED
    assert "inherited," not in out                                          # not the collapsed-count view


def test_class_show_depth_limits_superclasses(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    union = [_prop("Own", "Engine.Light", category="Lighting"),
             _prop("Location", "Engine.Actor", category="Movement")]     # hop 1 (Engine.Actor)
    _show_setup(monkeypatch, union)
    out = _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light",
                     depth=0)                            # depth 0 = own only
    assert "Own: ByteProperty" in out
    assert "Location" not in out                          # the hop-1 superclass prop is excluded
    assert "1 more superclass level" in out              # ...and noted, with --depth to see it


# ---------------------------------------------------------------- class show --category (spec 2026-07-18)
def _cat_union():
    """Editable props spanning Lighting (own + inherited), Movement (inherited only), and the
    `var()` pseudo-category `Actor` — over the fake chain Engine.Light -> Engine.Actor."""
    return [_prop("LightBrightness", "Engine.Light", category="Lighting"),   # own, hop 0
            _prop("LightType", "Engine.Actor", category="Lighting"),         # inherited, hop 1
            _prop("Location", "Engine.Actor", kind="StructProperty", category="Movement"),  # inh, hop 1
            _prop("Tag", "Engine.Actor", category="Actor")]                  # var() pseudo-category


def test_class_show_category_filters_and_expands(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    _show_setup(monkeypatch, _cat_union())
    out = _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light", categories=["Lighting"])
    assert "Lighting:" in out                                                 # only the wanted section...
    assert "Movement:" not in out and "Actor:" not in out                    # ...others absent
    assert "LightBrightness: ByteProperty" in out                            # own prop, UNTAGGED
    assert "LightType: ByteProperty   ← Engine.Actor" in out                 # inherited, FQCN-TAGGED (expanded)
    assert "inherited," not in out                                          # not the collapsed-count view


def test_class_show_category_is_case_insensitive_and_or_combined(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    _show_setup(monkeypatch, _cat_union())
    out = _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light",
                     categories=["movement", "lighting"])                    # lowercase, two values
    assert "Movement:" in out and "Lighting:" in out                         # canonical headers, OR-combined
    assert "Actor:" not in out
    # the motivating case: an entirely-INHERITED category shows its PROPS (expanded), not a count
    assert "Location: StructProperty   ← Engine.Actor" in out
    assert "more superclass level" not in out            # default --category depth is unlimited → no trailer


def test_class_show_depth_all_with_category_equals_category(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    _show_setup(monkeypatch, _cat_union())
    only = _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light", categories=["Lighting"])
    both = _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light",
                      categories=["Lighting"], depth=float("inf"))           # --depth all is subsumed
    assert only == both


def test_class_show_category_depth_clips_and_scopes_trailer(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    _show_setup(monkeypatch, _cat_union())
    out0 = _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light",
                      categories=["Lighting"], depth=0)                       # own Lighting only
    assert "LightBrightness" in out0 and "LightType" not in out0
    assert "1 more superclass level" in out0 and "--depth all" in out0       # trailer counts only Lighting's
    out1 = _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light",
                      categories=["Lighting"], depth=1)                       # adds the parent's
    assert "LightType" in out1 and "more superclass level" not in out1


def test_class_show_category_unknown_names_first_bad(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    _show_setup(monkeypatch, _cat_union())
    rc, cap = _run_class_cap(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light",
                             categories=["Bogus"])
    assert rc == 2 and "no category 'Bogus' on Engine.Light" in cap.err
    assert "available: Actor, Lighting, Movement" in cap.err                 # sorted, the class's categories
    assert cap.out == ""                                                     # rejected filter → nothing on stdout
    rc, cap = _run_class_cap(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light",
                             categories=["Lighting", "Nope"])                 # good then bad → first bad named
    assert rc == 2 and "no category 'Nope'" in cap.err
    assert "Lighting:" not in cap.out                                       # all-or-nothing: nothing printed


def test_class_show_category_no_editable_categories(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    _show_setup(monkeypatch, [_prop("iHidden", "Engine.Light", category=None)])   # only non-editable var
    rc, err = _run_class_rc(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light",
                            categories=["Lighting"])
    assert rc == 2 and "class Engine.Light has no editable categories" in err


def test_class_show_errors_when_an_ancestor_package_is_unreadable(tmp_path, monkeypatch, capsys):
    # An unreadable/missing ANCESTOR package is a HARD error naming that package — there is no
    # own-only degrade (which would print a truncated prop set as if it were complete; the stderr
    # note scrolls away). `direction.md` "No silent half-answers" / decisions.md 2026-07-24 21:58.
    proj = _project(tmp_path, monkeypatch)
    def _boom(fqcn, resolver, _cache=None):
        raise uprops.SchemaError("package 'Engine' not found on the schema search path")
    monkeypatch.setattr(uprops, "resolve_class_properties", _boom)
    monkeypatch.setattr(uprops, "own_class_properties",   # must NOT be consulted — no fallback
                        lambda pkg, cname, owner_fqcn: pytest.fail("own-only degrade fired"))
    for kw in ({}, {"categories": ["Lighting"]}, {"depth": float("inf")}):   # every render mode errors
        rc, cap = _run_class_cap(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light", **kw)
        assert rc == 2, kw
        assert "cannot read schema for Engine.Light" in cap.err and "'Engine'" in cap.err
        assert cap.out == "", kw                          # nothing partial on stdout


def test_class_show_prop_walk_uses_the_schema_cache_not_a_seed(tmp_path, monkeypatch, capsys):
    # The super chain (idx.ancestry) and the property walk must stay consistent, but consistency now
    # comes from BOTH reading the version-consistent persistent schema cache — not from seeding a shared
    # full-`Package` load. The seed was dropped (2026-07-20) so `class show`'s prop walk hits the warm
    # schema cache (the cache-ON path). Assert resolve_class_properties is called WITHOUT a seeded
    # `_cache`, so it takes that cache path instead of the seed-forced live decode.
    proj = _project(tmp_path, monkeypatch)
    seen = {}
    def _spy(fqcn, resolver, _cache=None):
        seen["called"] = True
        seen["cache"] = _cache
        return [_prop("X", "Engine.Light", category="Lighting")]
    monkeypatch.setattr(uprops, "resolve_class_properties", _spy)
    _run_class(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Light")   # chain = Light -> Actor
    assert seen.get("called"), "resolve_class_properties was not called"
    assert seen["cache"] is None, "prop walk must not seed _cache — it should use the schema cache"


def test_class_show_unknown_exits_2(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    rc, err = _run_class_rc(monkeypatch, capsys, proj, sub="show", fqcn="Engine.Nope")
    assert rc == 2 and "unknown class" in err


def test_class_list_empty_index_errors(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(ClassIndex, "from_project",
                        classmethod(lambda cls, p, u: ClassIndex(_paths={}, _stems={})))
    monkeypatch.setattr(config, "load_user_config", lambda: object())
    rc = dispatch.dispatch(argparse.Namespace(cmd="class", sub="list", project=str(proj),
                                              package=None, subclass_of=None, legacy_all=False))
    assert rc == 2
    assert "no package search path" in capsys.readouterr().err


def _run_class(monkeypatch, capsys, proj, **kw):
    rc, cap = _run_class_cap(monkeypatch, capsys, proj, **kw)
    assert rc == 0, cap.err
    return cap.out


def _run_class_rc(monkeypatch, capsys, proj, **kw):
    rc, cap = _run_class_cap(monkeypatch, capsys, proj, **kw)
    return rc, cap.err


def _run_class_cap(monkeypatch, capsys, proj, **kw):
    monkeypatch.setattr(ClassIndex, "from_project",
                        classmethod(lambda cls, p, u: _fake_index()))
    monkeypatch.setattr(config, "load_user_config", lambda: object())
    ns_kw = dict(cmd="class", project=str(proj), package=None, subclass_of=None,
                 include_non_actor=False, include_abstract=False, legacy_all=False,
                 flat=False, depth=None, categories=[], fqcn=None)
    ns_kw.update(kw)
    rc = dispatch.dispatch(argparse.Namespace(**ns_kw))
    return rc, capsys.readouterr()                        # capture ONCE (out + err together)


# --------------------------------------------------------------------------- real ingest gate
@pytest.mark.real_validation
def test_actor_add_qualifies_bare_class_to_fqcn(tmp_path, monkeypatch, substrate):
    proj = _project(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin",
                        io.StringIO('Begin Actor Class=Light Name=L\n    Name="L"\nEnd Actor\n'))
    rc = dispatch.dispatch(argparse.Namespace(cmd="actor", sub="add", project=str(proj), file="-"))
    assert rc == 0
    stored, _ = trunk.read_level(proj / "maps" / "lvl")
    assert [a.cls for a in stored.actors.values()] == ["Engine.Light"]   # bare → FQCN in the trunk


@pytest.mark.real_validation
def test_actor_add_unknown_class_exits_2_and_stores_nothing(tmp_path, monkeypatch, substrate):
    proj = _project(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin",
                        io.StringIO('Begin Actor Class=Bogus Name=X\n    Name="X"\nEnd Actor\n'))
    rc = dispatch.dispatch(argparse.Namespace(cmd="actor", sub="add", project=str(proj), file="-"))
    assert rc == 2
    stored, _ = trunk.read_level(proj / "maps" / "lvl")
    assert stored.actors == {}


@pytest.mark.real_validation
def test_actor_add_brush_texture_validated(tmp_path, monkeypatch, substrate):
    from uedctl.builders import cube, make_brush_actor
    from uedctl.emit import emit_actor_t3d
    proj = _project(tmp_path, monkeypatch)
    a = make_brush_actor("Wall", cube(64, 64, 64), location=(0, 0, 0), csg="add",
                         group=None, poly_flags=0)
    for p in a.brush.polys:
        p.texture = "CoreTex.Granite"                    # NOT in the fake resolver → reject
    monkeypatch.setattr("sys.stdin", io.StringIO(emit_actor_t3d(a)))
    rc = dispatch.dispatch(argparse.Namespace(cmd="actor", sub="add", project=str(proj), file="-"))
    assert rc == 2
    assert trunk.read_level(proj / "maps" / "lvl")[0].actors == {}
    # a real texture passes
    for p in a.brush.polys:
        p.texture = "CoreTex.Stone"
    monkeypatch.setattr("sys.stdin", io.StringIO(emit_actor_t3d(a)))
    rc = dispatch.dispatch(argparse.Namespace(cmd="actor", sub="add", project=str(proj), file="-"))
    assert rc == 0


@pytest.mark.real_validation
def test_no_package_path_message_is_canonical(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "composed_search_files", lambda project, user_config: [])
    monkeypatch.setattr(config, "load_user_config", lambda: object())
    monkeypatch.setattr("sys.stdin",
                        io.StringIO('Begin Actor Class=Light Name=L\n    Name="L"\nEnd Actor\n'))
    rc = dispatch.dispatch(argparse.Namespace(cmd="actor", sub="add", project=str(proj), file="-"))
    assert rc == 2
    assert "no package search path" in capsys.readouterr().err
