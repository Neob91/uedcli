"""The path pass (`native/paths.py`) and its config: offline, a fake graph builder, the committed
UED22 `PATHS DEFINE` golden `pathlab-define.dx` as the byte oracle (spec §7.2/§7.4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from uedcli import config
from uedcli.classdefaults import ClassDefaults
from uedcli.classindex import ClassIndex
from uedcli.native import paths
from uedcli.native.unbuilt import serialization_rank_resolver

_ROOT = Path(__file__).resolve().parents[2]
_UED22 = _ROOT / "uned" / "UED22"
_GOLDEN = _ROOT / "dev/docs/spikes/2026-09-05-pathing-build-re/evidence/pathlab-define.dx"

pytestmark = pytest.mark.skipif(not (_UED22 / "Engine.u").is_file(),
                                reason="committed UED22/Engine.u not present")


def _resolver(name: str) -> str | None:
    p = _UED22 / f"{name}.u"
    return str(p) if p.is_file() else None


@pytest.fixture
def env():
    paths_ = {p.stem.casefold(): str(p) for p in _UED22.glob("*.u")}
    index = ClassIndex(_paths=paths_, _stems={k: Path(v).stem for k, v in paths_.items()})
    return dict(index=index, defaults=ClassDefaults(_resolver),
                rank_for=serialization_rank_resolver([str(_UED22)]))


def _builder_returning(graph):
    calls = []

    def fake(model_body, movers, navs, zones, level_zone, preset_args):
        calls.append(dict(model_body=model_body, movers=movers, navs=navs, zones=zones,
                          level_zone=level_zone, preset=preset_args))
        return graph
    return fake, calls


# --- config -------------------------------------------------------------------------------------

def _user_config(tmp_path, body: str):
    home = tmp_path / "home"
    home.mkdir(parents=True)
    (home / "config.toml").write_text(body)
    return str(home / "config.toml")


def test_config_accepts_the_three_presets_and_rejects_an_unknown_one(tmp_path):
    for v in config.PATHING_PRESETS:
        cfg = config.load_user_config(_user_config(
            tmp_path / v, f'[games.dx]\npaths = "/x"\npathing = "{v}"\n'))
        assert cfg.games["dx"].pathing == v
    with pytest.raises(config.ConfigError) as ei:
        config.load_user_config(_user_config(
            tmp_path / "bad", '[games.dx]\npaths = "/x"\npathing = "ut-436"\n'))
    msg = str(ei.value)
    assert "[games.dx]" in msg and "'ut-436'" in msg and "deusex-1112fm, ued22-469, none" in msg


def test_a_missing_pathing_key_is_refused_only_at_the_use_site(tmp_path):
    cfg = config.load_user_config(_user_config(tmp_path, '[games.dx]\npaths = "/x"\n'))
    sub = cfg.games["dx"]
    assert sub.pathing is None                              # loads fine: other verbs keep working
    with pytest.raises(config.ConfigError) as ei:
        config.require_pathing(sub, verb="level materialize")
    assert "[games.dx].pathing" in str(ei.value) and "deusex-1112fm, ued22-469, none" in str(ei.value)
    assert config.require_pathing(config.Substrate(name="dx", paths="/x", pathing="none"),
                                  verb="x") == "none"


# --- the pass -----------------------------------------------------------------------------------

def test_none_returns_the_input_unchanged(env, monkeypatch):
    monkeypatch.setattr(paths, "graph_builder", lambda *a: pytest.fail("builder must not run"))
    data = _GOLDEN.read_bytes()
    assert paths.apply_path_pass(data, pathing="none", **env) is data


def test_strip_then_splice_the_original_graph_is_byte_identical(env, monkeypatch):
    """Read the golden's graph, strip it (an empty graph), feed the original back: the output must
    equal the golden byte for byte -- the read, the tag encoding (16-int arrays, array-index byte,
    bool/object forms), the serialization order, the ULevel splice and the re-lay all exact."""
    original = _GOLDEN.read_bytes()
    graph = paths.read_path_graph(original, index=env["index"], defaults=env["defaults"])
    assert len(graph.specs) == 281 and len(graph.nodes) == 40 and graph.nav_list_head != -1

    monkeypatch.setattr(paths, "graph_builder", _builder_returning(paths.empty_graph(40))[0])
    stripped = paths.apply_path_pass(original, pathing="ued22-469", **env)
    assert len(stripped) < len(original)
    bare = paths.read_path_graph(stripped, index=env["index"], defaults=env["defaults"])
    assert bare.specs == () and bare.nav_list_head == -1
    assert all(n.next_nav == -1 and set(n.paths) == {-1} for n in bare.nodes)

    fake, calls = _builder_returning(graph)
    monkeypatch.setattr(paths, "graph_builder", fake)
    rebuilt = paths.apply_path_pass(stripped, pathing="deusex-1112fm", **env)
    assert rebuilt == original
    # what reached the builder: the world Model body, 40 navs in roster order, the preset
    (call,) = calls
    assert len(call["navs"]) == 40 and call["navs"][0][1] == "navigationpoint"
    assert any(n[1] == "playerstart" for n in call["navs"])
    assert call["preset"]["prune_compare"] == "f64-strict" and "name" not in call["preset"]
    assert call["level_zone"][0] == 0


def test_a_column_shaped_native_graph_marshals_to_the_python_graph():
    """The Rust `PathGraphOut` is column-oriented (one list per field, indexed by nav)."""
    from types import SimpleNamespace
    e = [-1] * 16
    out = SimpleNamespace(specs=[(100, 0, 1, 18, 40, 1, False)], paths=[[0] + e[1:], e],
                          upstream=[e, [0] + e[1:]], pruned_paths=[e, e], vis_no_reach=[e, e],
                          next_nav=[-1, 0], residue=[(10000000, 0, 0, False, -1, -1, -1)] * 2,
                          nav_list_head=1, num_pruned=0)
    g = paths.graph_from_native(out)
    assert g.specs[0] == paths.SpecOut(distance=100, start=0, end=1, radius=18, height=40, flags=1,
                                       pruned=0)
    assert g.nodes[0].paths[0] == 0 and g.nodes[1].upstream[0] == 0 and g.nodes[1].next_nav == 0
    assert g.nodes[0].residue.visited_weight == 10000000 and g.nav_list_head == 1


def test_ulevel_body_outside_the_reachspecs_run_is_preserved(env, monkeypatch):
    """The Actors array, FURL, ModelRef, TimeSeconds/FirstDeleted/the 16 refs/TravelInfo are the
    original bytes; only the ReachSpecs run changes size."""
    from uedcli import upackage
    original = _GOLDEN.read_bytes()
    monkeypatch.setattr(paths, "graph_builder", _builder_returning(paths.empty_graph(40))[0])
    stripped = paths.apply_path_pass(original, pathing="ued22-469", **env)
    for data in (original, stripped):
        pkg = upackage.parse_package_bytes(data, where="x")
        lv = paths._read_level(pkg)
        e = pkg.exports[lv.export]
        body = data[e["soff"]:e["soff"] + e["ssize"]]
        s0, s1 = (o - e["soff"] for o in lv.specs_span)
        if data is original:
            head, tail = body[:s0], body[s1:]
        else:
            assert body[:s0] == head and body[s1:] == tail and body[s0:s1] == b"\x00"


def test_a_graph_naming_a_nav_index_off_the_roster_is_an_error(env, monkeypatch):
    g = paths.empty_graph(40)
    bad = paths.PathGraph(specs=(paths.SpecOut(distance=1, start=0, end=40, radius=1, height=1,
                                               flags=1, pruned=0),), nodes=g.nodes,
                          nav_list_head=-1)
    monkeypatch.setattr(paths, "graph_builder", _builder_returning(bad)[0])
    with pytest.raises(paths.PathPassError, match="nav index 0/40 out of range"):
        paths.apply_path_pass(_GOLDEN.read_bytes(), pathing="ued22-469", **env)


def test_a_missing_native_symbol_is_a_named_error(env, monkeypatch):
    import types
    monkeypatch.setitem(__import__("sys").modules, "uedcli_native", types.SimpleNamespace())
    monkeypatch.setattr(paths, "graph_builder", paths._native_build_path_graph)
    with pytest.raises(paths.PathPassError, match="build_path_graph"):
        paths.apply_path_pass(_GOLDEN.read_bytes(), pathing="ued22-469", **env)


def test_presets_carry_the_decoded_constants():
    from uedcli.native import pathrules
    dx, ued = pathrules.preset("deusex-1112fm"), pathrules.preset("ued22-469")
    assert (dx.radius_start, dx.radius_cap, dx.height_cap) == (12, 115, 79)
    assert (ued.radius_start, ued.radius_cap, ued.height_cap) == (18, 70, 70)
    assert dx.jump_fall_limit == 350 and ued.jump_fall_limit is None
    assert (dx.bot_only_radius, ued.bot_only_radius) == (12, 24)
    assert dx.residue and not ued.residue and ued.skip_deleted and not dx.skip_deleted
    assert (dx.size_rounding, ued.size_rounding) == ("trunc", "round")
    assert set(dx.as_args()) == set(ued.as_args()) and "skip_deleted" not in dx.as_args()
    with pytest.raises(ValueError, match="none"):
        pathrules.preset("none")
