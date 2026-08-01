"""Dispatch-level tests for `brush scale` / `brush apply-transform` / `actor rotate --to`
(spec 2026-07-18-scale-support §3/§7). Pure model-side — the trunk seam is mocked, so each verb's
transform + guards + save record are asserted with no editor."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from uedcli import rotation as R, transform as T
from uedcli.cli import dispatch as dispatch_mod
from uedcli.cli import resources
from uedcli.builders import cube, make_brush_actor
from uedcli.model import Actor, Level

D = Decimal


def _fake_src(level):
    src = mock.Mock()
    src.load.return_value = level
    return src


def _level(*actors) -> Level:
    lv = Level()
    for a in actors:
        lv.actors[a.name] = a
        lv.order.append(a.name)
    return lv


def _run(args, level):
    src = _fake_src(level)
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    saved = src.save.call_args.kwargs["level"] if src.save.call_args else None
    return rc, saved


def _scale_args(names, *, to=None, by=None, pivot=None, pivot_actor=None):
    return SimpleNamespace(cmd="brush", sub="scale", names=names, to=to, by=by,
                           pivot=pivot, pivot_actor=pivot_actor, tree=None, container="c")


# ── brush scale --to (absolute, in place) ───────────────────────────────────────────────────────

def test_scale_to_sets_mainscale_in_place():
    a = make_brush_actor("C", cube(64, 64, 64), location=(D(100), D(0), D(0)))
    rc, saved = _run(_scale_args(["C"], to=(D(2), D(1), D(1))), _level(a))
    assert rc == 0
    out = saved.actors["C"]
    assert out.main_scale.scale == (D(2), D(1), D(1))
    assert out.location == (D(100), D(0), D(0))          # in place — Location never moves


def test_scale_to_rejects_a_pivot():
    a = make_brush_actor("C", cube(64, 64, 64))
    rc, _ = _run(_scale_args(["C"], to=(D(2), D(1), D(1)), pivot=(D(0), D(0), D(0))), _level(a))
    assert rc == 2


def test_scale_to_reports_the_pivot_conflict_before_it_needs_a_class_resolver(capsys, monkeypatch):
    """A flag conflict must report ITSELF. `brush scale` builds a mover class resolver (a project +
    the games config) and the mutual-exclusion check used to sit BELOW that, so `--to … --pivot …`
    on a machine with no games config blamed the missing config for the user's typo."""
    def _no_resolver(args, verb, project=None):
        raise dispatch_mod.CommandError(f"{verb}: no games config found (~/.uedcli/config.toml)")
    monkeypatch.setattr(resources, "mover_index", _no_resolver)
    a = make_brush_actor("C", cube(64, 64, 64))
    rc, _ = _run(_scale_args(["C"], to=(D(2), D(1), D(1)), pivot=(D(0), D(0), D(0))), _level(a))
    assert rc == 2
    err = capsys.readouterr().err
    assert "cannot take a --pivot/--pivot-actor" in err
    assert "games config" not in err


def test_scale_by_reports_an_unknown_pivot_actor_before_it_needs_a_class_resolver(capsys,
                                                                                 monkeypatch):
    """The twin of the check above: `--pivot-actor` names an actor in the already-loaded level, so a
    typo must say so rather than blaming the games config the verb happens to need later."""
    def _no_resolver(args, verb, project=None):
        raise dispatch_mod.CommandError(f"{verb}: no games config found (~/.uedcli/config.toml)")
    monkeypatch.setattr(resources, "mover_index", _no_resolver)
    a = make_brush_actor("C", cube(64, 64, 64))
    rc, _ = _run(_scale_args(["C"], by=(D(2), D(1), D(1)), pivot_actor="Typo"), _level(a))
    assert rc == 2
    err = capsys.readouterr().err
    assert "Typo" in err
    assert "games config" not in err


# ── brush scale --by (relative, orbits Location) ────────────────────────────────────────────────

def test_scale_by_multiplies_and_orbits_location():
    a = make_brush_actor("C", cube(64, 64, 64), location=(D(100), D(0), D(0)))
    rc, saved = _run(_scale_args(["C"], by=(D(2), D(1), D(1)), pivot=(D(0), D(0), D(0))), _level(a))
    assert rc == 0
    out = saved.actors["C"]
    assert out.main_scale.scale == (D(2), D(1), D(1))
    assert out.location == (D(200), D(0), D(0))          # Loc' = P + S∘(Loc−P), P=0 → 2·100


def test_scale_by_composes_onto_an_existing_scale():
    a = make_brush_actor("C", cube(64, 64, 64))
    a.main_scale = T.FScale((D(2), D(1), D(1)))
    rc, saved = _run(_scale_args(["C"], by=(D(2), D(1), D(1))), _level(a))
    assert rc == 0 and saved.actors["C"].main_scale.scale == (D(4), D(1), D(1))


def test_mirror_is_scale_by_negative_one():
    a = make_brush_actor("C", cube(64, 64, 64))
    rc, saved = _run(_scale_args(["C"], by=(D(-1), D(1), D(1))), _level(a))
    assert rc == 0 and saved.actors["C"].main_scale.scale[0] == D(-1)


# ── guards ──────────────────────────────────────────────────────────────────────────────────────

def test_scale_zero_factor_exits_2():
    a = make_brush_actor("C", cube(64, 64, 64))
    rc, saved = _run(_scale_args(["C"], to=(D(0), D(1), D(1))), _level(a))
    assert rc == 2 and saved is None


def test_scale_sub_epsilon_factor_exits_2():
    a = make_brush_actor("C", cube(64, 64, 64))
    rc, _ = _run(_scale_args(["C"], by=(D("0.00001"), D(1), D(1))), _level(a))
    assert rc == 2


def test_scale_on_a_mover_warns_but_proceeds(capsys):
    a = make_brush_actor("Lift", cube(64, 64, 64), mover_class="Engine.Mover")
    rc, saved = _run(_scale_args(["Lift"], to=(D(2), D(1), D(1))), _level(a))
    assert rc == 0 and saved.actors["Lift"].main_scale.scale[0] == D(2)
    assert "Mover" in capsys.readouterr().err


def test_scale_nonuniform_by_pivot_on_rotated_brush_warns(capsys):
    a = make_brush_actor("C", cube(64, 64, 64), location=(D(50), D(0), D(0)))
    a.props += [("Rotation", "(Yaw=8192)")]             # 45°
    rc, _ = _run(_scale_args(["C"], by=(D(2), D(1), D(1)), pivot=(D(0), D(0), D(0))), _level(a))
    assert rc == 0
    assert "rotated" in capsys.readouterr().err


# ── brush apply-transform ────────────────────────────────────────────────────────────────────────

def _axf_args(names, *, lock_textures=True):
    return SimpleNamespace(cmd="brush", sub="apply-transform", names=names,
                           lock_textures=lock_textures, tree=None, container="c")


def _point(name="Lamp"):
    return Actor(name=name, cls="Engine.Light", location=(D(0), D(0), D(0)))   # brush is None


def test_brush_scale_rejects_a_point_actor(capsys):
    # the brush-only guard (rename 2026-07-20): MainScale is a brush property → a Light is rejected,
    # all-or-nothing, before any mutation
    rc, saved = _run(_scale_args(["Lamp"], to=(D(2), D(2), D(2))), _level(_point()))
    assert rc == 2
    assert saved is None                                  # nothing saved
    assert "not a brush: Lamp" in capsys.readouterr().err


def test_brush_scale_rejects_a_mixed_set_all_or_nothing(capsys):
    # a set with one point actor is rejected WHOLE — the brush is not scaled either
    brush = make_brush_actor("C", cube(64, 64, 64))
    rc, saved = _run(_scale_args(["C", "Lamp"], to=(D(2), D(2), D(2))), _level(brush, _point()))
    assert rc == 2 and saved is None


def test_brush_apply_transform_rejects_a_point_actor(capsys):
    rc, saved = _run(_axf_args(["Lamp"]), _level(_point()))
    assert rc == 2 and saved is None
    assert "not a brush: Lamp" in capsys.readouterr().err


def test_apply_transform_bakes_and_resets_fields():
    a = make_brush_actor("C", cube(64, 64, 64), location=(D(100), D(0), D(0)))
    a.main_scale = T.FScale((D(2), D(1), D(1)))
    before = sorted({round(w[0], 3) for w in R.world_vertices(a)})
    rc, saved = _run(_axf_args(["C"]), _level(a))
    assert rc == 0
    out = saved.actors["C"]
    assert out.main_scale.is_identity()
    assert sorted({round(w[0], 3) for w in R.world_vertices(out)}) == before


def test_apply_transform_rejects_a_mover():
    a = make_brush_actor("Lift", cube(64, 64, 64), mover_class="Engine.Mover")
    a.main_scale = T.FScale((D(2), D(1), D(1)))
    rc, saved = _run(_axf_args(["Lift"]), _level(a))
    assert rc == 2 and saved is None


def test_apply_transform_warns_on_postscale(capsys):
    a = make_brush_actor("C", cube(64, 64, 64))
    a.post_scale = T.FScale((D(2), D(1), D(1)))
    rc, _ = _run(_axf_args(["C"]), _level(a))
    assert rc == 0
    assert "PostScale" in capsys.readouterr().err


# ── actor rotate --to (absolute, in place) ───────────────────────────────────────────────────────

def test_rotate_to_sets_the_field_in_place():
    a = make_brush_actor("C", cube(64, 64, 64), location=(D(64), D(0), D(0)))
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["C"], to=(D(0), D(16384), D(0)),
                           by=None, pivot=None, pivot_actor=None, tree=None, container="c")
    rc, saved = _run(args, _level(a))
    assert rc == 0
    out = saved.actors["C"]
    assert out.location == (D(64), D(0), D(0))           # in place — Location never moves
    assert any(k == "Rotation" and "Yaw=16384" in v for k, v in out.props)


def test_rotate_to_zero_writes_the_rotator_not_an_omission():
    """THE `TNM.LavaSpitter` BUG (2026-07-25). `--to 0,0,0` used to DELETE the `Rotation` prop, on
    the reasoning that "identity means unrotated". It does not: an omitted property re-imports as
    the CLASS DEFAULT, and `TNM.LavaSpitter` defaults `Rotation=(Pitch=16384,Yaw=0,Roll=0)` (the
    only one of 1346 actor classes that defaults `Rotation`), so `--to 0,0,0` on one built it
    PITCHED 90° — and the post-verify passed, because both compare sides had dropped the same
    line. The explicit zero rotator is what the editor itself accepts and re-exports away."""
    a = Actor(name="Spitter", cls="TNM.LavaSpitter", location=(D(0), D(0), D(0)))
    a.props = [("Rotation", "(Pitch=8192,Yaw=0,Roll=0)")]
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["Spitter"], to=(D(0), D(0), D(0)),
                           by=None, pivot=None, pivot_actor=None, tree=None, container="c")
    rc, saved = _run(args, _level(a))
    assert rc == 0
    assert ("Rotation", "(Pitch=0,Yaw=0,Roll=0)") in saved.actors["Spitter"].props


def test_rotate_by_composing_to_zero_writes_the_rotator_too():
    """The orbit path (`--by`) had the same "don't write a spurious Rotation=(0,0,0)" shortcut, so
    rotating a LavaSpitter back to identity dropped the prop and pitched it 90°."""
    a = Actor(name="Spitter", cls="TNM.LavaSpitter", location=(D(64), D(0), D(0)))
    a.props = [("Rotation", "(Pitch=0,Yaw=16384,Roll=0)")]
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["Spitter"], to=None,
                           by=(D(0), D(-16384), D(0)), pivot=(D(0), D(0), D(0)), pivot_actor=None,
                           tree=None, container="c")
    rc, saved = _run(args, _level(a))
    assert rc == 0
    assert ("Rotation", "(Pitch=0,Yaw=0,Roll=0)") in saved.actors["Spitter"].props


def test_rotate_to_rejects_a_pivot():
    a = make_brush_actor("C", cube(64, 64, 64))
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["C"], to=(D(0), D(16384), D(0)),
                           by=None, pivot=(D(0), D(0), D(0)), pivot_actor=None, tree=None,
                           container="c")
    rc, _ = _run(args, _level(a))
    assert rc == 2


def test_rotate_warns_on_nonuniform_postscale_brush(capsys):
    # spec §7: rotating a non-uniform PostScale brush warps it (inherent UE1) → warn, exit 0.
    a = make_brush_actor("C", cube(64, 64, 64), location=(D(64), D(0), D(0)))
    a.post_scale = T.FScale((D(2), D(1), D(1)))
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["C"], to=None,
                           by=(D(0), D(90), D(0)), pivot=(D(0), D(0), D(0)), pivot_actor=None,
                           tree=None, container="c")
    rc, _ = _run(args, _level(a))
    assert rc == 0
    assert "non-uniform PostScale" in capsys.readouterr().err


def test_uniform_postscale_rotate_does_not_warp_warn(capsys):
    a = make_brush_actor("C", cube(64, 64, 64), location=(D(64), D(0), D(0)))
    a.post_scale = T.FScale((D(2), D(2), D(2)))        # uniform → rotates cleanly, no warn
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["C"], to=None,
                           by=(D(0), D(90), D(0)), pivot=(D(0), D(0), D(0)), pivot_actor=None,
                           tree=None, container="c")
    rc, _ = _run(args, _level(a))
    assert rc == 0 and "non-uniform PostScale" not in capsys.readouterr().err


# ── the default pivot, end to end through dispatch ──────────────────────────────────────────────
# (build-review finding #6, 2026-07-26: the unit tests pinned `best_grid_pivot` but nothing asserted
# what a user actually sees — that the verbs leave a lone actor where it was.)

def _never_resolver(actor):
    """Must not be called — the actor states a Location (see test_rotate_pivot._never)."""
    raise AssertionError(f"class schema consulted for {actor.name!r}, which states a Location")


def _bounds(actor):
    wv = R.world_vertices(actor)
    return (tuple(min(w[i] for w in wv) for i in range(3)),
            tuple(max(w[i] for w in wv) for i in range(3)))


def _offset_cube(side, shift):
    """A cube whose LOCAL verts are shifted off the origin, so its Location is NOT its bbox centre —
    the only shape that can tell the own-Location rule apart from a bbox-centre rule."""
    c = cube(side, side, side)
    for p in c.polys:
        p.vertices = [(x + shift, y + shift, z + shift) for x, y, z in p.vertices]
    return c


def test_rotate_by_pivots_on_a_members_location_not_the_bbox_centre():
    """THE distinguishing case (build-review round 2, finding #5). A generator cube's Location is its
    own bbox centre, so a symmetric brush cannot separate the rules — both answer the same point, and
    a test built on one passes against either implementation. Shifting the local verts by +64 puts the
    centre at 1064 while the Location stays 1000, so the superseded centre rule and the own-Location
    rule differ by 64 uu."""
    a = make_brush_actor("C", _offset_cube(128, 64.0), location=(D(1000), D(0), D(0)))
    assert R.best_grid_pivot([a], _never_resolver) == (D(1000), D(0), D(0))     # NOT the centre (1064, 64, 64)
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["C"], to=None,
                           by=(D(0), D(32768), D(0)), pivot=None, pivot_actor=None,
                           tree=None, container="c")
    rc, saved = _run(args, _level(a))
    assert rc == 0
    # Pivoting on its own Location leaves Location exactly put; a centre pivot would have moved it.
    assert tuple(saved.actors["C"].location) == (D(1000), D(0), D(0))


def test_rotate_by_leaves_a_lone_brush_where_it_was():
    """The default pivot is the actor's own Location, so a 180° flip is in place: same bounds, to
    within the GMath rotator noise the table cannot avoid."""
    a = make_brush_actor("C", cube(128, 4, 128), location=(D(1056), D(228), D(112)))
    before = _bounds(a)
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["C"], to=None,
                           by=(D(0), D(32768), D(0)), pivot=None, pivot_actor=None,
                           tree=None, container="c")
    rc, saved = _run(args, _level(a))
    assert rc == 0
    after = _bounds(saved.actors["C"])
    for side in (0, 1):
        for i in range(3):
            assert abs(after[side][i] - before[side][i]) < 1e-3, f"{after} moved from {before}"


def test_mirror_leaves_a_lone_brush_where_it_was():
    """`brush scale --by -1,1,1` is the documented un-mirror lever; it shares the same default pivot,
    so a symmetric brush mirrors in place instead of reflecting across a corner and landing a full
    width away."""
    a = make_brush_actor("C", cube(128, 64, 32), location=(D(512), D(256), D(64)))
    before = _bounds(a)
    rc, saved = _run(_scale_args(["C"], by=(D(-1), D(1), D(1))), _level(a))
    assert rc == 0
    after = _bounds(saved.actors["C"])
    for side in (0, 1):
        for i in range(3):
            assert abs(after[side][i] - before[side][i]) < 1e-3, f"{after} moved from {before}"


def test_an_unstated_location_orbits_from_its_CLASS_default_not_zero():
    """The orbit must read the same EFFECTIVE Location the pivot does. `Engine.Camera` states no
    Location and defaults it to (-500,-300,300), so it pivots about its own position and must NOT
    move; with the orbit assuming zero it landed at (-800,200,0) — the assume-zero bug half-fixed."""
    a = Actor(name="Cam1", cls="Engine.Camera", location=None)
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["Cam1"], to=None,
                           by=(D(0), D(16384), D(0)), pivot=None, pivot_actor=None,
                           tree=None, container="c", project=None)
    with mock.patch.object(resources, "default_location_for",
                           return_value=lambda fq: (D(-500), D(-300), D(300))):
        rc, saved = _run(args, _level(a))
    assert rc == 0
    assert tuple(saved.actors["Cam1"].location) == (D(-500), D(-300), D(300))


# ── the class-default seam itself (build review round 3: nothing executed it) ────────────────────

def test_a_rotate_whose_actors_all_state_a_location_never_needs_a_project():
    """The seam must stay LAZY. Resolving the project eagerly made an ordinary offline rotate demand
    a resolvable project — contradicting the promise that it stays offline, and turning 25 tests red.
    Nothing here mocks `_default_location_for`: the real closure runs and must not touch the project."""
    a = make_brush_actor("C", cube(64, 64, 64), location=(D(100), D(0), D(0)))
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["C"], to=None,
                           by=(D(0), D(16384), D(0)), pivot=None, pivot_actor=None,
                           tree=None, container="c", project="/nonexistent/not-a-project")
    rc, saved = _run(args, _level(a))
    assert rc == 0 and saved is not None


def test_the_class_default_lookup_is_memoized_per_class():
    """`_class_defaults` costs ~50 ms per class (250 ms for a DeusExMover) and builds a fresh package
    map each call, while BOTH the pivot scan and the orbit ask for every actor — so an unmemoized
    lookup is 2N resolutions. Measured before the memo: 500 Location-less actors took 59.9 s against
    1.07 s with Locations stated. `test_normalize.py`'s PERF GUARD says the same: per-ACTOR
    resolution turns a ~1 s job into a ~2 min one."""
    calls = []

    def _fake_defaults(cls, project=None):
        calls.append(cls)
        return {("location", 0): "(X=-500,Y=-300,Z=300)"}

    actors = [Actor(name=f"Cam{i}", cls="Engine.Camera", location=None) for i in range(20)]
    args = SimpleNamespace(cmd="actor", sub="rotate", names=[a.name for a in actors], to=None,
                           by=(D(0), D(16384), D(0)), pivot=None, pivot_actor=None,
                           tree=None, container="c", project=None)
    with mock.patch.object(resources, "class_defaults", _fake_defaults), \
            mock.patch.object(resources, "resolve_project", lambda a: None):
        rc, _ = _run(args, _level(*actors))
    assert rc == 0
    assert calls == ["Engine.Camera"], f"resolved {len(calls)}x for 20 actors of ONE class"
