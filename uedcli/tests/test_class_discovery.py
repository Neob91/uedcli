"""Offline class discovery + qualify-and-validate on ingest
(spec in board item `offline-class-discovery-qualify-and-validate`).

The `ClassIndex` byte-level readers (`uprops.class_is_abstract`, the TextBuffer decode, `iter_classes`)
are live-verified against the real v68 `.u`; here we test the offline LOGIC by injecting the index's
caches directly (no `.u` on disk needed), plus the pure `abstract_from_source` parser and the
`requalify_classes_to_loaded` H3 reconciler.
"""
import pytest

from uedcli import schema_cache
from uedcli.classindex import ClassIndex, ClassRefError
from uedcli.model import Actor
from uedcli.uprops import abstract_from_source


# --------------------------------------------------------------------------- abstract_from_source
@pytest.mark.parametrize("src, expected", [
    ("class Foo extends Bar abstract;", True),
    ("class Foo extends Bar;", False),
    ("class Pawn extends Actor\n\tabstract\n\tnative;", True),                 # multi-line decl
    ("//===\n// Foo.\n//===\nclass Foo extends Bar\n\tabstract;", True),       # comment header
    ("class Foo extends Bar; // this abstract comment must not count", False), # kw only after ';'
    ("/* abstract */ class Foo extends Bar;", False),                          # kw in block comment
    ("class AbstractBase extends Object;", False),                            # *Abstract* NAME, no kw
    ("// no class here at all", None),
    (None, None),
])
def test_abstract_from_source(src, expected):
    assert abstract_from_source(src) is expected


# --------------------------------------------------------------------------- --depth value parsing
def test_depth_value_parses_ints_and_all_and_rejects_bad():
    """`class list`/`class show` --depth accepts a non-negative int or case-insensitive `all` (→ inf);
    a negative or non-numeric token is a clean ArgumentTypeError naming it (decision 2026-07-18)."""
    import argparse
    import math
    from uedcli.cli import depth_value
    assert depth_value("0") == 0 and depth_value("5") == 5
    assert depth_value("all") == math.inf and depth_value("  ALL ") == math.inf
    for bad in ("-1", "foo", "3.5", ""):
        with pytest.raises(argparse.ArgumentTypeError):
            depth_value(bad)


# --------------------------------------------------------------------------- injected ClassIndex
def _index() -> ClassIndex:
    """A fully cache-injected ClassIndex — every query answers from the injected caches, so NO `.u`
    is loaded. Mirrors a small substrate: Engine (Actor tree) + Core + a game package `Deco`."""
    idx = ClassIndex(_paths={"engine": "x", "core": "x", "deco": "x", "other": "x"},
                     _stems={"engine": "Engine", "core": "Core", "deco": "Deco", "other": "Other"})
    idx._all = ["Engine.Actor", "Engine.Light", "Engine.Decoration", "Engine.Mover",
                "Engine.ElevatorMover", "Engine.Brush", "Core.Object", "Deco.Vase",
                "Deco.Widget", "Other.Widget"]
    idx._ancestry = {
        "core.object": ["Core.Object"],
        "engine.actor": ["Engine.Actor", "Core.Object"],
        "engine.light": ["Engine.Light", "Engine.Actor", "Core.Object"],
        "engine.decoration": ["Engine.Decoration", "Engine.Actor", "Core.Object"],
        "engine.mover": ["Engine.Mover", "Engine.Brush", "Engine.Actor", "Core.Object"],
        "engine.elevatormover": ["Engine.ElevatorMover", "Engine.Mover", "Engine.Brush",
                                 "Engine.Actor", "Core.Object"],
        "engine.brush": ["Engine.Brush", "Engine.Actor", "Core.Object"],
        "deco.vase": ["Deco.Vase", "Engine.Decoration", "Engine.Actor", "Core.Object"],
        "deco.widget": ["Deco.Widget", "Engine.Actor", "Core.Object"],
        "other.widget": ["Other.Widget", "Engine.Actor", "Core.Object"],
    }
    idx._abstract = {
        "engine.actor": True, "engine.decoration": True, "core.object": True,
        "engine.mover": True,           # abstract base mover
        "engine.light": False, "engine.elevatormover": False, "engine.brush": False,
        "deco.vase": False, "deco.widget": False, "other.widget": False,
    }
    idx._cmaps = {
        "engine": {"actor": 1, "light": 2, "decoration": 3, "mover": 4, "elevatormover": 5,
                   "brush": 6},
        "core": {"object": 1},
        "deco": {"vase": 1, "widget": 2},
        "other": {"widget": 1},
    }
    return idx


def test_class_exists():
    idx = _index()
    assert idx.class_exists("Engine.Light")
    assert idx.class_exists("engine.light")          # case-insensitive
    assert not idx.class_exists("Engine.Bogus")
    assert not idx.class_exists("Nope.Light")
    assert not idx.class_exists("Light")             # bare is not an existence key


def _disc_schema(package_name, super_refs):
    """A discovery-only PackageSchema (own_props=None) to inject into `idx._schemas` — mirrors what
    `ClassIndex._schema` caches. `ancestry` reads its `super_ref_for` (the cached disc super ref) now,
    so tests seed super refs here instead of monkeypatching the live `super_fqcn_by_index` decode."""
    return schema_cache.PackageSchema(
        package_name=package_name, class_list=tuple(super_refs), cmap={c: i + 1 for i, c in enumerate(super_refs)},
        super_refs=super_refs, abstract={c: None for c in super_refs}, own_props=None)


def test_ancestry_parse_error_truncation_is_surfaced(capsys):
    # A corrupt/out-of-range super ref (a malformed package, or a torn concurrent read) truncates the
    # ancestry SILENTLY by default — that silent drop is what made a `class show` super chain vanish
    # with no trace (2026-07-18). It must now emit a diagnosable stderr note. The `""` sentinel is what
    # the schema cache stores for an un-decodable super, and `super_ref_for` re-raises it (spec §6).
    idx = ClassIndex(_paths={"engine": "x"}, _stems={"engine": "Engine"})
    idx._schemas = {"engine": _disc_schema("Engine", {"foo": ""})}   # corrupt super ref → re-raise
    chain = idx.ancestry("Engine.Foo")
    assert chain == ["Engine.Foo"]                        # truncated at the error
    err = capsys.readouterr().err
    assert "super chain of Engine.Foo truncated" in err and "corrupt/out-of-range super ref" in err


def test_ancestry_genuine_root_is_silent(capsys):
    # A real root (super ref None) is NOT corruption — it must stay silent (no false note).
    idx = ClassIndex(_paths={"engine": "x"}, _stems={"engine": "Engine"})
    idx._schemas = {"engine": _disc_schema("Engine", {"object": None})}
    assert idx.ancestry("Engine.Object") == ["Engine.Object"]
    assert "truncated" not in capsys.readouterr().err


def test_qualify_bare_unique_and_unknown():
    idx = _index()
    assert idx._qualify_bare("Light") == "Engine.Light"
    assert idx._qualify_bare("vase") == "Deco.Vase"  # case-insensitive
    with pytest.raises(ClassRefError):
        idx._qualify_bare("TotallyBogus")


def test_qualify_bare_ambiguity_prefers_engine_then_defers():
    idx = _index()
    # Widget is in Deco AND Other (both game packages) — no Engine/Core winner → LEAVE BARE (defer to
    # live), so ingest is never stricter than the build.
    assert idx._qualify_bare("Widget") is None
    # add an Engine.Widget → the Engine candidate wins deterministically.
    idx._bare = None                                 # force rebuild
    idx._all = idx._all + ["Engine.Widget"]
    idx._cmaps["engine"]["widget"] = 7
    assert idx._qualify_bare("Widget") == "Engine.Widget"


def test_qualify_and_validate_mutates_bare_and_rejects_unknown():
    idx = _index()
    a = Actor(name="L", cls="Light", location=(0, 0, 0), props=[], brush=None)
    idx.qualify_and_validate([a])
    assert a.cls == "Engine.Light"                   # qualified in place
    b = Actor(name="B", cls="Engine.Bogus", location=(0, 0, 0), props=[], brush=None)
    with pytest.raises(ClassRefError):
        idx.qualify_and_validate([b])
    # a qualified, real class passes untouched
    c = Actor(name="C", cls="Deco.Vase", location=(0, 0, 0), props=[], brush=None)
    idx.qualify_and_validate([c])
    assert c.cls == "Deco.Vase"


def test_list_classes_default_is_the_category_view():
    # DEFAULT = the direct Engine.Actor children (categories), abstract branch-points INCLUDED,
    # deeper classes and the Actor root itself excluded. (Engine.Mover extends Brush → depth 2, so it
    # is NOT a top-level category — matches real DX.)
    got = _index().list_classes()
    for cat in ("Engine.Light", "Engine.Brush", "Engine.Decoration"):
        assert cat in got                            # direct children (incl. abstract Decoration)
    for deep_or_root in ("Deco.Vase", "Engine.Mover", "Engine.ElevatorMover",
                         "Engine.Actor", "Core.Object"):
        assert deep_or_root not in got               # depth≥2 leaves, the root, non-Actor


def test_list_classes_isa_drills_to_placeable_leaves():
    idx = _index()
    assert idx.list_classes(subclass_of="Engine.Mover") == ["Engine.ElevatorMover"]   # concrete leaf (base abstract)
    assert idx.list_classes(subclass_of="Engine.Decoration") == ["Deco.Vase"]         # deep placeable leaf
    movers_all = idx.list_classes(subclass_of="Engine.Mover", include_abstract=True)  # keeps the abstract base
    assert "Engine.Mover" in movers_all and "Engine.ElevatorMover" in movers_all


def test_list_classes_depth_is_a_structural_browse():
    idx = _index()
    # --depth 2 from Engine.Actor: direct children (Light d1) AND their children (Mover d2), no
    # placeable filter; ElevatorMover (d3) is beyond depth 2.
    d2 = idx.list_classes(depth=2)
    assert "Engine.Light" in d2 and "Engine.Mover" in d2
    assert "Engine.ElevatorMover" not in d2
    # --depth 1 == the category default
    assert set(idx.list_classes(depth=1)) == set(idx.list_classes())


def test_list_classes_package_lists_all_placeable_in_it():
    idx = _index()
    assert "Deco.Vase" in idx.list_classes(package="Deco")   # deep, but --package lifts the depth-1 default
    assert "Engine.Light" not in idx.list_classes(package="Deco")
    with pytest.raises(ClassRefError):
        idx.list_classes(subclass_of="Engine.Bogus")
    with pytest.raises(ClassRefError):
        idx.list_classes(package="NoSuchPkg")


def test_list_classes_every_class_dump_includes_abstract_and_root():
    # The faithful "every class incl. the root" dump (old bare `--all`): subclass_of=Core.Object +
    # include_abstract drops the placeable filter; passing subclass_of disables the d==0 root-skip so
    # Core.Object itself is listed. (Decision 2026-07-18: the `--all` split; there is no unrooted path.)
    got = _index().list_classes(subclass_of="Core.Object", include_abstract=True)
    assert "Engine.Actor" in got and "Core.Object" in got and "Engine.Decoration" in got


def test_list_classes_include_non_actor_reroots_at_core_object():
    idx = _index()
    # `--include-non-actor` reroots the default at Core.Object; the default depth-1 view shows its
    # direct children (here just Engine.Actor). The root Core.Object is EXCLUDED by the d==0 root-skip
    # (as Engine.Actor is in the default Actor view).
    top = idx.list_classes(include_non_actor=True)
    assert "Engine.Actor" in top and "Core.Object" not in top
    # `--depth all` (math.inf) then reaches every non-root class, abstract included (unfiltered browse).
    deep = idx.list_classes(include_non_actor=True, depth=float("inf"))
    assert "Engine.Light" in deep and "Deco.Vase" in deep and "Engine.Decoration" in deep
    assert "Core.Object" not in deep


def test_list_classes_depth_all_expands_fully():
    idx = _index()
    # --depth all == unlimited: every Actor descendant at any depth (structural browse, unfiltered).
    alld = idx.list_classes(depth=float("inf"))
    assert {"Engine.Light", "Engine.Mover", "Engine.ElevatorMover", "Deco.Vase"} <= set(alld)
    assert "Core.Object" not in alld and "Engine.Actor" not in alld   # root + its own root excluded


# --------------------------------------------------------------------------- H3 reconciliation
def test_requalify_classes_to_loaded_reconciles_bare_and_qualified():
    from uedcli.qualify import requalify_classes_to_loaded
    from uedcli.model import Level
    bare = Actor(name="A", cls="Light", location=(0, 0, 0), props=[], brush=None)
    already = Actor(name="B", cls="Engine.Light", location=(0, 0, 0), props=[], brush=None)
    collide = Actor(name="C", cls="Widget", location=(0, 0, 0), props=[], brush=None)
    lvl = Level(actors={"A": bare, "B": already, "C": collide}, order=["A", "B", "C"])
    loaded = {"Light": {"Engine.Light"}, "Widget": {"Deco.Widget", "Other.Widget"}}
    requalify_classes_to_loaded(lvl, loaded)
    assert bare.cls == "Engine.Light"                # bare → live pick
    assert already.cls == "Engine.Light"             # already-FQCN → RE-qualified to the live pick
    assert collide.cls == "Widget"                   # 2+ candidates → left unchanged (conservative)


# --------------------------------------------------------------------------- dispatch wiring
# These OVERRIDE the autouse `_stub_author_validation` (same monkeypatch instance, last write wins)
# to prove the ingest gate is actually wired into `actor add` / the generators.
def _project_with_level(tmp_path, monkeypatch, actors=None):
    from uedcli import trunk
    from uedcli.model import Level
    proj = tmp_path / "repo"
    (proj / "maps" / "lvl").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors=actors or {})
    trunk.write_level(proj / "maps" / "lvl", lvl, {n: "m" for n in (actors or {})})
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    return proj


def _builder_plus_light_t3d() -> str:
    """A clean red-builder-brush (bare `Class=Brush`, inner model name `Brush`, no CsgOper) + a bare
    `Class=Light` — the exact `MAP EXPORT`-style input where qualifying before the builder filter
    would misfire."""
    from uedcli.builders import cube, make_brush_actor
    from uedcli.emit import emit_map
    builder = make_brush_actor("Brush", cube(64, 64, 64), location=(0, 0, 0), csg="add",
                               group=None, poly_flags=0)
    builder.cls = "Brush"
    builder.brush.model_name = "Brush"                       # the builder signature
    builder.props = [(k, v) for k, v in builder.props if k != "CsgOper"]
    light = Actor(name="MyLight", cls="Light", location=(10, 20, 30), props=[], brush=None)
    return emit_map([builder, light])


def test_actor_add_validates_the_filtered_set_after_builder_filter(tmp_path, monkeypatch):
    """The gate runs AFTER `is_builder_brush` filtering (qualifying `Brush`→`Engine.Brush` first
    would let the transient builder brush escape the filter) — the reviewer's ordering constraint."""
    import argparse
    import io
    from uedcli import dispatch, trunk
    from uedcli.normalize import is_builder_brush
    proj = _project_with_level(tmp_path, monkeypatch)
    seen: list = []
    monkeypatch.setattr(dispatch, "_validate_ingest_actors",
                        lambda actors, args: seen.append(list(actors)))
    monkeypatch.setattr("sys.stdin", io.StringIO(_builder_plus_light_t3d()))
    rc = dispatch.dispatch(argparse.Namespace(cmd="actor", sub="add", project=str(proj), file="-"))
    assert rc == 0
    assert len(seen) == 1
    validated = seen[0]
    assert [a.cls for a in validated] == ["Light"]           # ONLY the light — builder was filtered
    assert not any(is_builder_brush(a) for a in validated)
    stored, _ = trunk.read_level(proj / "maps" / "lvl")
    assert not any(is_builder_brush(a) for a in stored.actors.values())
    assert any(a.cls == "Light" for a in stored.actors.values())


def test_actor_add_rejecting_validator_exits_2_and_stores_nothing(tmp_path, monkeypatch):
    import argparse
    import io
    from uedcli import dispatch, trunk
    proj = _project_with_level(tmp_path, monkeypatch)
    monkeypatch.setattr(dispatch, "_validate_ingest_actors",
                        lambda actors, args: (_ for _ in ()).throw(
                            dispatch._SelectionExit("unknown class: Foo.Bogus")))
    monkeypatch.setattr("sys.stdin",
                        io.StringIO('Begin Actor Class=Bogus Name=X\n    Name="X"\nEnd Actor\n'))
    rc = dispatch.dispatch(argparse.Namespace(cmd="actor", sub="add", project=str(proj), file="-"))
    assert rc == 2
    stored, _ = trunk.read_level(proj / "maps" / "lvl")
    assert stored.actors == {}                        # all-or-nothing: nothing written


def test_actor_build_generator_invokes_validation(tmp_path, monkeypatch, capsys):
    import argparse
    from uedcli import dispatch
    monkeypatch.setattr(dispatch, "_validate_ingest_actors",
                        lambda actors, args: (_ for _ in ()).throw(
                            dispatch._SelectionExit("unknown class: Engine.Bogus")))
    rc = dispatch.dispatch(argparse.Namespace(
        cmd="actor", sub="build", project=str(tmp_path), aclass="Engine.Bogus",
        at=(0, 0, 0), base_name=None, prop=[]))
    assert rc == 2
    cap = capsys.readouterr()                         # capture ONCE (a second read is drained → vacuous)
    assert "unknown class" in cap.err
    assert cap.out == ""                              # nothing emitted on rejection


def test_class_list_without_games_config_is_clean_exit_2(tmp_path, capsys):
    """Absent `~/.uedcli/config.toml` (the autouse home isolation guarantees an empty home) must be
    a clean 'no per-user games config' exit 2 on `class list` — never the raw
    `AttributeError: 'NoneType' … .games` traceback a cold review reproduced here (2026-07-18)."""
    import argparse
    from uedcli import dispatch
    proj = tmp_path / "repo"
    proj.mkdir()
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    rc = dispatch.dispatch(argparse.Namespace(
        cmd="class", sub="list", project=str(proj), package=None, subclass_of=None, legacy_all=False))
    assert rc == 2
    cap = capsys.readouterr()
    assert "no per-user games config" in cap.err
    assert "Traceback" not in cap.err


def test_package_path_seam_without_games_config_raises_clean(tmp_path):
    """`_package_path_or_exit` (the seam every author-time ingest validation goes through) raises
    the canonical no-games-config `_SelectionExit` when `~/.uedcli/config.toml` is absent — the
    generator/`actor add` twin of the `class list` regression above."""
    import argparse
    import pytest as _pytest
    from uedcli import dispatch
    proj = tmp_path / "repo"
    proj.mkdir()
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    with _pytest.raises(dispatch._SelectionExit, match="no per-user games config"):
        dispatch._package_path_or_exit(argparse.Namespace(project=str(proj)))
