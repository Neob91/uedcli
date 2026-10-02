"""Offline tests for `event graph`: the pure eventgraph module + the dispatch verb.

Covers: graph construction (edges on Event==Tag, case-insensitivity, unset-Tag NOT matchable),
each lint category (dangling event / unreachable tag / unreachable mover / cycle), the
self-moving-mover exclusion, and every output mode (text / --dot / --json) through dispatch,
plus the error paths (no project → exit 2)."""
import argparse
import json

from uedcli import eventgraph, trunk
from uedcli.cli import dispatch
from uedcli.model import Actor, Level
from uedcli.tests.conftest import StubClassIndex

IDX = StubClassIndex()          # the offline class resolver `movers.is_mover` needs


def _actor(name, cls, **props):
    """A point actor with the given (key,value) props (order preserved)."""
    return Actor(name=name, cls=cls, props=list(props.items()), location=(0, 0, 0))


# ── pure module: build_graph ──────────────────────────────────────────────────

def test_edge_when_event_matches_tag():
    lv = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="OpenDoor"),
        "Door": _actor("Door", "Engine.Mover", Tag="OpenDoor"),
    })
    g = eventgraph.build_graph(lv, IDX)
    assert [(e.src, e.dst, e.event) for e in g.edges] == [("Trig", "Door", "OpenDoor")]


def test_edge_match_is_case_insensitive():
    lv = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="opendoor"),
        "Door": _actor("Door", "Engine.Mover", Tag="OpenDoor"),
    })
    g = eventgraph.build_graph(lv, IDX)
    assert len(g.edges) == 1


def test_one_event_drives_several_receivers():
    lv = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="Boom"),
        "A": _actor("A", "Engine.Mover", Tag="Boom"),
        "B": _actor("B", "Engine.Light", Tag="Boom"),
    })
    g = eventgraph.build_graph(lv, IDX)
    assert {(e.src, e.dst) for e in g.edges} == {("Trig", "A"), ("Trig", "B")}


def test_unset_tag_is_not_a_matchable_receiver():
    # The load-bearing choice: a class-name-default Tag must NOT create an edge.
    lv = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="Trigger"),  # fires its own class name
        "Other": _actor("Other", "Engine.Trigger"),                 # no explicit Tag
    })
    g = eventgraph.build_graph(lv, IDX)
    assert g.edges == []


def test_empty_tag_value_is_absent():
    lv = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="X"),
        "Door": _actor("Door", "Engine.Mover", Tag="   "),          # whitespace-only = absent
    })
    g = eventgraph.build_graph(lv, IDX)
    assert g.edges == []


def test_node_selection_includes_movers_and_eventing_actors_only():
    lv = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="X"),
        "Door": _actor("Door", "Engine.Mover"),                     # mover, no props → still a node
        "Deco": _actor("Deco", "Engine.Light"),                     # nothing → not a node
    })
    g = eventgraph.build_graph(lv, IDX)
    assert {n.name for n in g.nodes} == {"Trig", "Door"}


def test_no_event_level_is_a_clean_empty_graph():
    lv = Level(actors={"L": _actor("L", "Engine.Light")})
    g = eventgraph.build_graph(lv, IDX)
    assert g.nodes == [] and g.edges == []
    assert eventgraph.lint_graph(g, lv) == []


# ── pure module: lint ─────────────────────────────────────────────────────────

def test_dangling_event_flagged():
    lv = Level(actors={"Trig": _actor("Trig", "Engine.Trigger", Event="Nobody")})
    g = eventgraph.build_graph(lv, IDX)
    kinds = [f.kind for f in eventgraph.lint_graph(g, lv)]
    assert "dangling_event" in kinds


def test_unreachable_tag_flagged_for_non_mover():
    lv = Level(actors={"L": _actor("L", "Engine.Light", Tag="Never")})
    g = eventgraph.build_graph(lv, IDX)
    f = [x for x in eventgraph.lint_graph(g, lv) if x.kind == "unreachable_tag"]
    assert len(f) == 1 and f[0].tag == "Never"


def test_unreachable_mover_flagged_and_not_double_reported_as_tag():
    lv = Level(actors={"Door": _actor("Door", "Engine.Mover", Tag="Never")})
    g = eventgraph.build_graph(lv, IDX)
    kinds = [f.kind for f in eventgraph.lint_graph(g, lv)]
    assert "unreachable_mover" in kinds and "unreachable_tag" not in kinds


def test_self_moving_mover_is_not_unreachable():
    lv = Level(actors={
        "Door": _actor("Door", "Engine.Mover", Tag="Never", InitialState="LoopMove"),
    })
    g = eventgraph.build_graph(lv, IDX)
    assert [f for f in eventgraph.lint_graph(g, lv) if f.kind == "unreachable_mover"] == []


def test_targeted_mover_is_not_flagged():
    lv = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="Go"),
        "Door": _actor("Door", "Engine.Mover", Tag="Go"),
    })
    g = eventgraph.build_graph(lv, IDX)
    kinds = [f.kind for f in eventgraph.lint_graph(g, lv)]
    assert "unreachable_mover" not in kinds and "dangling_event" not in kinds


def test_cycle_detected():
    # A fires B's tag, B fires A's tag → 2-cycle.
    lv = Level(actors={
        "A": _actor("A", "Engine.Trigger", Event="toB", Tag="toA"),
        "B": _actor("B", "Engine.Trigger", Event="toA", Tag="toB"),
    })
    g = eventgraph.build_graph(lv, IDX)
    cyc = [f for f in eventgraph.lint_graph(g, lv) if f.kind == "cycle"]
    assert len(cyc) == 1 and set(cyc[0].actors) == {"A", "B"}


def test_self_cycle_detected():
    lv = Level(actors={"A": _actor("A", "Engine.Trigger", Event="self", Tag="self")})
    g = eventgraph.build_graph(lv, IDX)
    cyc = [f for f in eventgraph.lint_graph(g, lv) if f.kind == "cycle"]
    assert len(cyc) == 1 and cyc[0].actors == ["A"]


def test_three_cycle_message_is_a_real_edge_path():
    # Edges A->B (A.Event=eB == B.Tag), B->C, C->A. The printed path must follow real edges, not a
    # sorted member list (which would claim A->B->C even if the real order were A->C->B).
    lv = Level(actors={
        "A": _actor("A", "Engine.Trigger", Event="eB", Tag="eA"),
        "B": _actor("B", "Engine.Trigger", Event="eC", Tag="eB"),
        "C": _actor("C", "Engine.Trigger", Event="eA", Tag="eC"),
    })
    g = eventgraph.build_graph(lv, IDX)
    edges = {(e.src, e.dst) for e in g.edges}
    cyc = [f for f in eventgraph.lint_graph(g, lv) if f.kind == "cycle"]
    assert len(cyc) == 1
    path = cyc[0].actors
    assert set(path) == {"A", "B", "C"}
    # every consecutive pair (wrapping) is a genuine edge
    closed = path + [path[0]]
    for a, b in zip(closed, closed[1:]):
        assert (a, b) in edges, f"{a}->{b} is not a real edge"


def test_reversed_three_cycle_path_follows_real_edges():
    # Reverse wiring: A->C, C->B, B->A. A naive sort would still print A->B->C->A (wrong direction).
    lv = Level(actors={
        "A": _actor("A", "Engine.Trigger", Event="eC", Tag="eA"),
        "B": _actor("B", "Engine.Trigger", Event="eA", Tag="eB"),
        "C": _actor("C", "Engine.Trigger", Event="eB", Tag="eC"),
    })
    g = eventgraph.build_graph(lv, IDX)
    edges = {(e.src, e.dst) for e in g.edges}
    cyc = [f for f in eventgraph.lint_graph(g, lv) if f.kind == "cycle"]
    assert len(cyc) == 1
    path = cyc[0].actors + [cyc[0].actors[0]]
    for a, b in zip(path, path[1:]):
        assert (a, b) in edges


def test_two_disjoint_cycles_reported_separately():
    lv = Level(actors={
        "A": _actor("A", "Engine.Trigger", Event="tB", Tag="tA"),
        "B": _actor("B", "Engine.Trigger", Event="tA", Tag="tB"),
        "C": _actor("C", "Engine.Trigger", Event="tD", Tag="tC"),
        "D": _actor("D", "Engine.Trigger", Event="tC", Tag="tD"),
    })
    g = eventgraph.build_graph(lv, IDX)
    cyc = [f for f in eventgraph.lint_graph(g, lv) if f.kind == "cycle"]
    assert len(cyc) == 2
    assert {frozenset(f.actors) for f in cyc} == {frozenset({"A", "B"}), frozenset({"C", "D"})}


def test_tagless_mover_is_a_node_but_not_lint_flagged():
    # Documented conservative choice: a tagless mover appears as a NODE but is NOT flagged
    # unreachable (its bump/loop trigger mechanism isn't knowable offline).
    lv = Level(actors={"Door": _actor("Door", "Engine.Mover")})
    g = eventgraph.build_graph(lv, IDX)
    assert [n.name for n in g.nodes] == ["Door"]
    assert eventgraph.lint_graph(g, lv) == []


def test_json_cycle_carries_actors_list():
    lv = Level(actors={"A": _actor("A", "Engine.Trigger", Event="self", Tag="self")})
    g = eventgraph.build_graph(lv, IDX)
    obj = eventgraph.to_json_obj(g, eventgraph.lint_graph(g, lv))
    cyc = [x for x in obj["lint"] if x["kind"] == "cycle"]
    assert cyc and cyc[0]["actors"] == ["A"] and "event" not in cyc[0] and "tag" not in cyc[0]


def test_format_text_empty_when_nodes_but_no_edges():
    lv = Level(actors={"Trig": _actor("Trig", "Engine.Trigger", Event="Nobody")})
    g = eventgraph.build_graph(lv, IDX)
    assert g.nodes and eventgraph.format_text(g) == ""


def test_format_dot_uses_escape_newline_and_escapes_specials():
    # A class ref never contains a quote, but prove _dot_quote escapes them and that the label
    # break is the two-char `\n` escape, not a raw newline byte.
    lv = Level(actors={"Trig": _actor("Trig", 'Weird"Class', Event="X")})
    dot = eventgraph.format_dot(eventgraph.build_graph(lv, IDX))
    assert "\\n(" in dot                       # two-char DOT line-break escape present
    assert "\n(Weird" not in dot               # NOT a raw newline inside the label
    assert 'Weird\\"Class' in dot              # embedded quote escaped


def test_no_spurious_cycle_on_a_dag():
    lv = Level(actors={
        "A": _actor("A", "Engine.Trigger", Event="toB", Tag="start"),
        "B": _actor("B", "Engine.Trigger", Event="toC", Tag="toB"),
        "C": _actor("C", "Engine.Mover", Tag="toC"),
    })
    g = eventgraph.build_graph(lv, IDX)
    assert [f for f in eventgraph.lint_graph(g, lv) if f.kind == "cycle"] == []


# ── formatters ────────────────────────────────────────────────────────────────

def test_format_text_line_shape():
    lv = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="OpenDoor"),
        "Door": _actor("Door", "Engine.Mover", Tag="OpenDoor"),
    })
    g = eventgraph.build_graph(lv, IDX)
    assert eventgraph.format_text(g) == "Trig (Engine.Trigger) --OpenDoor--> Door (Engine.Mover)"


def test_format_dot_has_digraph_nodes_and_edge():
    lv = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="OpenDoor"),
        "Door": _actor("Door", "Engine.Mover", Tag="OpenDoor"),
    })
    dot = eventgraph.format_dot(eventgraph.build_graph(lv, IDX))
    assert dot.startswith("digraph events {")
    assert '"Trig" -> "Door" [label="OpenDoor"];' in dot
    assert '"Door"' in dot and "shape=box" in dot        # mover drawn as a box


def test_to_json_obj_shape():
    lv = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="Nobody"),
    })
    g = eventgraph.build_graph(lv, IDX)
    obj = eventgraph.to_json_obj(g, eventgraph.lint_graph(g, lv))
    assert obj["nodes"][0] == {"name": "Trig", "class": "Engine.Trigger",
                               "event": "Nobody", "tag": None, "is_mover": False}
    assert obj["edges"] == []
    assert obj["lint"][0]["kind"] == "dangling_event" and obj["lint"][0]["actor"] == "Trig"


# ── dispatch: full verb through a project + selected level ────────────────────

def _ns(**kw):
    kw.setdefault("dot", False)
    kw.setdefault("json", False)
    return argparse.Namespace(cmd="event", sub="graph", **kw)


def _project_with_wiring(tmp_path, monkeypatch, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="OpenDoor"),
        "Door": _actor("Door", "Engine.Mover", Tag="OpenDoor"),
        "Lost": _actor("Lost", "Engine.Trigger", Event="Nobody"),
    })
    trunk.write_level(proj / "maps" / name, lvl,
                      {"Trig": "a", "Door": "b", "Lost": "c"})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def test_dispatch_text_prints_wiring_to_stdout_and_lint_to_stderr(tmp_path, monkeypatch, capsys):
    proj = _project_with_wiring(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(project=str(proj)))
    assert rc == 0
    cap = capsys.readouterr()
    assert cap.out.strip() == "Trig (Engine.Trigger) --OpenDoor--> Door (Engine.Mover)"
    assert "dangling_event" in cap.err                   # the Lost trigger fires into the void
    assert "lint finding(s)" in cap.err


def test_dispatch_dot_mode(tmp_path, monkeypatch, capsys):
    proj = _project_with_wiring(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(project=str(proj), dot=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("digraph events {")
    assert '"Trig" -> "Door" [label="OpenDoor"];' in out


def test_dispatch_json_mode_folds_lint_in(tmp_path, monkeypatch, capsys):
    proj = _project_with_wiring(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_ns(project=str(proj), json=True))
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert {n["name"] for n in obj["nodes"]} == {"Trig", "Door", "Lost"}
    assert obj["edges"] == [{"from": "Trig", "to": "Door", "event": "OpenDoor"}]
    assert any(f["kind"] == "dangling_event" for f in obj["lint"])


def test_dispatch_clean_level_exit_zero_no_lint(tmp_path, monkeypatch, capsys):
    proj = tmp_path / "repo"
    (proj / "maps" / "lvl").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={
        "Trig": _actor("Trig", "Engine.Trigger", Event="Go"),
        "Door": _actor("Door", "Engine.Mover", Tag="Go"),
    })
    trunk.write_level(proj / "maps" / "lvl", lvl, {"Trig": "a", "Door": "b"})
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    rc = dispatch.dispatch(_ns(project=str(proj)))
    assert rc == 0
    cap = capsys.readouterr()
    assert cap.out.strip() == "Trig (Engine.Trigger) --Go--> Door (Engine.Mover)"
    assert "0 lint finding(s)" in cap.err


def test_dispatch_no_project_exits_2(tmp_path, monkeypatch):
    monkeypatch.delenv("UEDCLI_PROJECT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert dispatch.dispatch(_ns(project=None)) == 2


def test_dispatch_no_selected_level_exits_2(tmp_path, monkeypatch, capsys):
    # A project with no ambient $UEDCLI_LEVEL → clean exit 2 whose message is the "no level" hint
    # (not merely *some* exit 2 — a regression that started failing for another reason must be caught).
    monkeypatch.delenv("UEDCLI_LEVEL", raising=False)
    proj = tmp_path / "repo"
    (proj / "maps").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    assert dispatch.dispatch(_ns(project=str(proj))) == 2
    assert "no level" in capsys.readouterr().err
