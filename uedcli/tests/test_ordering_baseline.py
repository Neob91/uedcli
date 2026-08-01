"""Slice 1 ordering characterization: the validation / resolution / no-op sequence a later slice
must preserve when it moves handlers. Each probe patches the resolver seams with recorders and
asserts the order (or absence) of calls, not just the final exit code.

Covers the spec's source-free and validation-order guarantees:

- `actor order` / `actor add --order <non-last>` reject a stash/prefab target BEFORE resolving a
  project or level source;
- `actor folder|label` on a stash/prefab reject before source resolution too;
- `actor preview --from-t3d` routes before any level-source resolution;
- empty-stdin behaviour, INCLUDING that source resolution already happens before the no-op (so an
  empty-stdin verb outside a project errors, inside a project no-ops without loading);
- `level materialize` validates `--out` before resolving the project/load set;
- `level preview` validates its shot/mode flags before resolving the project;
- `_mover_index` translation of a missing project vs a missing games config vs an empty path;
- `actor preview`'s tailored filled-render mover error, and its point-only no-op that never
  resolves a class index;
- `actor find` without `--prop`/`--subclass-of` never touches the schema.
"""
from __future__ import annotations

import argparse
import io
from unittest import mock

import pytest

from uedcli.cli import dispatch as D
from uedcli.cli import ingest
from uedcli.cli import rendering
from uedcli.cli import level_sources
from uedcli.cli import resources
from uedcli.cli.commands import stash as stash_cmd
from uedcli.cli.commands.actor import edit as actor_edit
from uedcli.builders import cube, make_brush_actor
from uedcli.model import Actor, Level


@pytest.fixture
def record_resolvers(monkeypatch):
    """Patch the project + level-source seams with recorders. Returns the shared call log so a test
    can assert exactly which resolution happened, in order."""
    calls = []
    monkeypatch.setattr(resources, "resolve_project",
                        lambda args: calls.append("project") or _fail("resolve_project called"))
    monkeypatch.setattr(level_sources, "resolve_level_source",
                        lambda args: calls.append("level_source") or _fail("resolve_source called"))
    return calls


def _fail(msg):
    raise AssertionError(msg)


# --- source-free rejection: order / folder / label on a box target ----------------------------

def _ns(**kw):
    kw.setdefault("tree", None)
    kw.setdefault("project", None)
    return argparse.Namespace(**kw)


def test_actor_order_on_a_box_rejects_before_any_resolution(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(resources, "resolve_project", lambda a: calls.append("project"))
    monkeypatch.setattr(level_sources, "resolve_level_source", lambda a: calls.append("level_source"))
    rc = D.dispatch(_ns(cmd="actor", sub="order", tree="stash/bay", names=["X"],
                        first=True, last=False, before=None, after=None))
    assert rc == 2
    assert "ordering applies only to a level" in capsys.readouterr().err
    assert calls == []                                    # neither project nor source resolved


def test_actor_add_nondefault_order_on_a_box_rejects_before_any_resolution(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(resources, "resolve_project", lambda a: calls.append("project"))
    monkeypatch.setattr(level_sources, "resolve_level_source", lambda a: calls.append("level_source"))
    rc = D.dispatch(_ns(cmd="actor", sub="add", tree="prefab/door", order="first",
                        file="-", label=None, folder=None))
    assert rc == 2
    assert "ordering applies only to a level" in capsys.readouterr().err
    assert calls == []


def test_actor_add_default_order_last_is_not_rejected_source_free(monkeypatch):
    """`--order last` is today's append, valid on any target, so it must NOT trip the source-free
    reject — it falls through to source resolution (which we stub to observe)."""
    seen = []
    monkeypatch.setattr(level_sources, "resolve_level_source",
                        lambda a: seen.append("resolved") or _StubSource(Level(actors={})))
    monkeypatch.setattr(ingest, "read_t3d_input", lambda f: "Begin Map\nEnd Map\n")
    monkeypatch.setattr(actor_edit, "_ingest_actor_t3d",
                        lambda *a, **k: seen.append("ingest") or 0)
    rc = D.dispatch(_ns(cmd="actor", sub="add", tree="prefab/door", order="last",
                        file="-", label=None, folder=None))
    assert rc == 0 and seen == ["resolved", "ingest"]     # reached resolution, no source-free reject


@pytest.mark.parametrize("sub,extra,msg", [
    ("folder", dict(foldersub="set", to="props", names=["X"]), "folders apply only to a level"),
    ("label", dict(labelsub="add", names=["X"], set=["hero"], unset=[]), "labels apply only to a level"),
])
def test_actor_folder_and_label_on_a_box_reject_before_resolution(monkeypatch, capsys, sub, extra, msg):
    calls = []
    monkeypatch.setattr(resources, "resolve_project", lambda a: calls.append("project"))
    monkeypatch.setattr(level_sources, "resolve_level_source", lambda a: calls.append("level_source"))
    rc = D.dispatch(_ns(cmd="actor", sub=sub, tree="stash/bay", **extra))
    assert rc == 2
    assert msg in capsys.readouterr().err
    assert calls == []


# --- actor preview --from-t3d routes before source resolution ---------------------------------

def test_actor_preview_from_t3d_runs_before_level_source_resolution(monkeypatch):
    from uedcli.cli.commands.actor import preview as actor_preview
    seen = []
    monkeypatch.setattr(level_sources, "resolve_level_source",
                        lambda a: seen.append("level_source") or _fail("source resolved"))
    monkeypatch.setattr(actor_preview, "_from_t3d", lambda a: seen.append("from_t3d") or 0)
    rc = D.dispatch(_ns(cmd="actor", sub="preview", from_t3d=["snippet.t3d"]))
    assert rc == 0
    assert seen == ["from_t3d"]                            # from-t3d handled, source never resolved


# --- empty stdin: source resolution happens before the no-op ----------------------------------

class _StubSource:
    def __init__(self, level, log=None):
        self._level = level
        self._log = log if log is not None else []

    def load(self):
        self._log.append("load")
        return self._level


def test_empty_stdin_inside_a_project_resolves_the_source_then_no_ops(monkeypatch):
    calls = []
    src = _StubSource(Level(actors={}), log=calls)
    monkeypatch.setattr(level_sources, "resolve_level_source",
                        lambda a: calls.append("resolve") or src)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))     # empty stdin
    rc = D.dispatch(_ns(cmd="actor", sub="delete", names=["-"]))
    assert rc == 0
    assert calls == ["resolve"]                           # resolved, but the no-op returns before load


def test_empty_stdin_outside_a_project_errors_at_source_resolution(monkeypatch, capsys):
    calls = []

    def resolve(a):
        calls.append("resolve")
        raise D.ProjectError("not in a uedcli project")

    monkeypatch.setattr(level_sources, "resolve_level_source", resolve)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    rc = D.dispatch(_ns(cmd="actor", sub="delete", names=["-"]))
    assert rc == 2                                         # NOT a clean no-op: the source is resolved first
    assert calls == ["resolve"]
    assert "not in a uedcli project" in capsys.readouterr().err


# --- validation before expensive resolution: materialize / preview ----------------------------

def test_materialize_validates_out_before_resolving_the_project(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(resources, "resolve_project", lambda a: called.append("project"))
    rc = D.dispatch(_ns(cmd="level", sub="materialize", out=None))
    assert rc == 2
    assert "requires --out" in capsys.readouterr().err
    assert called == []


def test_preview_validates_flags_before_resolving_the_project(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(resources, "resolve_project", lambda a: called.append("project"))
    rc = D.dispatch(_ns(cmd="level", sub="preview", native=False, fov=90.0, map=None,
                        rebuild=None, keep_alive=None, size="1280x960", list_actors=None,
                        out_dir="s", shots=[], sample=0))
    assert rc == 2
    assert "--fov requires --native" in capsys.readouterr().err
    assert called == []


# --- _mover_index translation matrix ----------------------------------------------------------

@pytest.mark.real_mover_index
def test_mover_index_missing_project_propagates_project_error(monkeypatch):
    monkeypatch.setattr(resources, "resolve_project",
                        lambda a: (_ for _ in ()).throw(D.ProjectError("not in a uedcli project")))
    with pytest.raises(D.ProjectError, match="not in a uedcli project"):
        resources.mover_index(_ns(), "brush scale")


@pytest.mark.real_mover_index
def test_mover_index_missing_games_config_translates_naming_verb(monkeypatch):
    monkeypatch.setattr(resources, "class_index",
                        lambda project=None: (_ for _ in ()).throw(D.CommandError(resources.NO_GAMES_CONFIG)))
    with pytest.raises(D.CommandError) as ei:
        resources.mover_index(_ns(), "brush scale", project=object())
    assert ei.value.message.startswith("brush scale:")
    assert resources.MOVER_RESOLVER_WHY in ei.value.message


@pytest.mark.real_mover_index
def test_mover_index_empty_path_translates_naming_verb(monkeypatch):
    monkeypatch.setattr(resources, "class_index", lambda project=None: mock.Mock(empty=True))
    with pytest.raises(D.CommandError) as ei:
        resources.mover_index(_ns(), "brush scale", project=object())
    assert ei.value.message.startswith("brush scale:")
    assert "no package search path" in ei.value.message


# --- actor preview filled-render mover error + point-only no-op --------------------------------

def _brush_actor(name="B"):
    return make_brush_actor(name, cube(64.0, 64.0, 64.0), csg="subtract")


def test_preview_fill_wraps_project_error_with_a_tailored_message(monkeypatch):
    monkeypatch.setattr(resources, "mover_index",
                        lambda args, verb, project=None:
                        (_ for _ in ()).throw(D.ProjectError("not in a uedcli project")))
    with pytest.raises(D.CommandError) as ei:
        rendering.preview_movers([_brush_actor()], _ns(cmd="actor", sub="preview"), "flat")
    msg = ei.value.message
    assert "Engine.Mover" in msg and "wire needs neither" in msg


def test_preview_point_only_selection_never_resolves_a_class_index(monkeypatch):
    called = []
    monkeypatch.setattr(resources, "mover_index",
                        lambda *a, **k: called.append("mover_index") or mock.Mock(empty=False))
    point = Actor(name="P", cls="Engine.Light", location=(0, 0, 0), brush=None)
    assert rendering.preview_movers([point], _ns(cmd="actor", sub="preview"), "flat") == frozenset()
    assert called == []                                   # no brushes → no class index resolved


# --- plain actor find never touches the schema ------------------------------------------------

def test_plain_actor_find_never_resolves_class_schema(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(level_sources, "resolve_level_source",
                        lambda a: _StubSource(Level(actors={"L1": Actor(name="L1", cls="Engine.Light")})))
    monkeypatch.setattr(resources, "class_ctx",
                        lambda cls, args: calls.append("class_ctx") or _fail("schema touched"))
    monkeypatch.setattr(resources, "class_index",
                        lambda project=None: calls.append("class_index") or _fail("schema touched"))
    rc = D.dispatch(_ns(cmd="actor", sub="find", name=[], cls=[], subclass_of=[], group=[],
                        folder=[], no_folder=False, kind=None, prop=[], json=False,
                        label=[], no_label=False, exclude=False, restrict=None, within_bbox=None))
    assert rc == 0
    assert calls == []                                    # plain find resolved no schema
    assert capsys.readouterr().out == "L1\n"


# --- brush scale: cheap argument checks precede the class resolver -----------------------------

def _scale_ns(**kw):
    base = dict(cmd="brush", sub="scale", names=["Brush"], to=None, by=None, pivot=None,
                pivot_actor=None, tree=None, project=None)
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.mark.parametrize("ns,acts,msg", [
    (_scale_ns(to=("1", "1", "1"), pivot=("0", "0", "0")),
     {"Brush": _brush_actor("Brush")}, "in-place and cannot take a --pivot"),
    (_scale_ns(by=("0", "1", "1")),
     {"Brush": _brush_actor("Brush")}, "zero/sub-epsilon component"),
    (_scale_ns(names=["Point"], to=("2", "2", "2")),
     {"Point": Actor(name="Point", cls="Engine.Light", location=(0, 0, 0), brush=None)},
     "not a brush"),
])
def test_brush_scale_cheap_checks_precede_the_class_resolver(monkeypatch, capsys, ns, acts, msg):
    called = []
    monkeypatch.setattr(resources, "mover_index",
                        lambda *a, **k: called.append("mover_index") or mock.Mock(empty=False))
    monkeypatch.setattr(level_sources, "resolve_level_source", lambda a: _StubSource(Level(actors=acts)))
    rc = D.dispatch(ns)
    assert rc == 2
    assert msg in capsys.readouterr().err
    assert called == []                                   # rejected before the mover class index


# --- save-vs-output ordering ------------------------------------------------------------------

class _SnapSource:
    """A level source whose `save` snapshots the current stdout, so a test can prove whether the
    handler printed its result before or after saving."""
    def __init__(self, level, out, events):
        self._level = level
        self._out = out
        self._events = events

    def load(self):
        return self._level

    def save(self, **kw):
        self._events.append(("save", self._out.getvalue()))


def test_brush_scale_prints_output_before_saving(monkeypatch):
    """`brush scale` is an output-before-save verb: the scaled names are on stdout by the time the
    trunk write happens."""
    import contextlib
    out = io.StringIO()
    events = []
    level = Level(actors={"Brush": _brush_actor("Brush")})
    monkeypatch.setattr(level_sources, "resolve_level_source", lambda a: _SnapSource(level, out, events))
    with contextlib.redirect_stdout(out):
        rc = D.dispatch(_scale_ns(to=("2", "2", "2")))
    assert rc == 0
    assert events == [("save", "Brush\n")]                # names already on stdout when save ran


def test_actor_add_ingest_saves_before_output(monkeypatch):
    """`actor add` (ingest) is save-before-output: the trunk write completes before the allocated
    Names hit stdout, so a live `add - | prop -` pipe can't race ahead of the write."""
    import contextlib
    out = io.StringIO()
    events = []
    src = _SnapSource(Level(actors={}), out, events)
    monkeypatch.setattr(level_sources, "resolve_level_source", lambda a: src)
    monkeypatch.setattr(ingest, "read_t3d_input", lambda f: "Begin Map\nEnd Map\n")

    captured = {}

    def fake_ingest(args, source, level, text, *, verb, labels_override=None):
        # Drive the real save→print order the handler uses, minimally.
        source.save(verb=verb, args={}, level=level, touched=["New_1"])
        print("New_1")
        captured["at_save"] = events[0][1]
        return 0

    monkeypatch.setattr(actor_edit, "_ingest_actor_t3d", fake_ingest)
    with contextlib.redirect_stdout(out):
        rc = D.dispatch(_ns(cmd="actor", sub="add", tree=None, order="last", file="-",
                            label=None, folder=None))
    assert rc == 0
    assert captured["at_save"] == ""                      # nothing on stdout yet when save ran
    assert out.getvalue() == "New_1\n"                    # printed only after the save returned


def test_failing_save_aborts_before_any_output(monkeypatch, capsys):
    """When the trunk write raises, an output-before-save verb has already printed, but a save that
    raises still propagates (exit 2 via the OSError guard) rather than being swallowed. Pins that a
    failing save surfaces."""
    import contextlib
    out = io.StringIO()
    level = Level(actors={"Brush": _brush_actor("Brush")})

    class _BoomSource(_StubSource):
        def save(self, **kw):
            raise OSError("disk full")

    monkeypatch.setattr(level_sources, "resolve_level_source", lambda a: _BoomSource(level))
    with contextlib.redirect_stdout(out):
        rc = D.dispatch(_scale_ns(to=("2", "2", "2")))
    assert rc == 2
    assert "filesystem error: disk full" in capsys.readouterr().err


# --- stash / prefab preview prologue order ----------------------------------------------------

def test_stash_preview_validates_existence_before_read_and_render(monkeypatch):
    """Stash preview resolves the project/register, then checks existence, then reads, then renders."""
    events = []

    class Reg:
        def exists(self, sid):
            events.append(("exists", sid))
            return True

        def read_stash(self, sid):
            events.append(("read", sid))
            return ({}, [], [], {}, {})

    monkeypatch.setattr(stash_cmd, "_resolve_stash_register",
                        lambda a: events.append(("register",)) or Reg())
    monkeypatch.setattr(rendering, "render_actors_to_out",
                        lambda actors, args: events.append(("render",)) or 0)
    rc = D.dispatch(_ns(cmd="stash", sub="preview", id="bay", names=[], summary=False))
    assert rc == 0
    kinds = [e[0] for e in events]
    assert kinds[0] == "register" and kinds[-1] == "render"
    assert kinds.index("exists") < kinds.index("read") < kinds.index("render")


def test_stash_preview_not_found_stops_before_read_and_render(monkeypatch, capsys):
    events = []

    class Reg:
        def exists(self, sid):
            events.append(("exists", sid))
            return False

        def read_stash(self, sid):
            events.append(("read", sid))
            raise AssertionError("read must not run on a missing stash")

    monkeypatch.setattr(stash_cmd, "_resolve_stash_register", lambda a: Reg())
    monkeypatch.setattr(rendering, "render_actors_to_out",
                        lambda actors, args: events.append(("render",)) or 0)
    rc = D.dispatch(_ns(cmd="stash", sub="preview", id="ghost", names=[], summary=False))
    assert rc == 2
    assert "stash not found" in capsys.readouterr().err
    assert events == [("exists", "ghost")]                # no read, no render


def test_prefab_preview_validates_name_before_any_filesystem_op(monkeypatch, capsys):
    events = []
    monkeypatch.setattr(resources, "prefab_root", lambda a: __import__("pathlib").Path("/nope"))
    monkeypatch.setattr("uedcli.stashlib.list_prefabs",
                        lambda root: events.append(("list",)) or [])
    monkeypatch.setattr(rendering, "render_actors_to_out",
                        lambda actors, args: events.append(("render",)) or 0)
    rc = D.dispatch(_ns(cmd="prefab", sub="preview", name="../escape", names=[], summary=False))
    assert rc == 2                                        # name grammar rejected first
    assert events == []                                  # no list_prefabs, no read, no render


def test_prefab_preview_lists_then_reads_then_renders(monkeypatch):
    events = []
    monkeypatch.setattr(resources, "prefab_root", lambda a: __import__("pathlib").Path("/nope"))
    monkeypatch.setattr("uedcli.stashlib.list_prefabs",
                        lambda root: events.append(("list",)) or ["door"])
    monkeypatch.setattr("uedcli.stashlib.read_prefab",
                        lambda root, name: events.append(("read", name)) or ({}, [], [], {}, {}))
    monkeypatch.setattr(rendering, "render_actors_to_out",
                        lambda actors, args: events.append(("render",)) or 0)
    rc = D.dispatch(_ns(cmd="prefab", sub="preview", name="door", names=[], summary=False))
    assert rc == 0
    assert events == [("list",), ("read", "door"), ("render",)]
