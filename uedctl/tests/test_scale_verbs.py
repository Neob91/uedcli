"""Dispatch-level tests for `brush scale` / `brush apply-transform` / `actor rotate --to`
(spec 2026-07-18-scale-support §3/§7). Pure model-side — the trunk seam is mocked, so each verb's
transform + guards + save record are asserted with no editor."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from uedctl import dispatch as dispatch_mod, rotation as R, transform as T
from uedctl.builders import cube, make_brush_actor
from uedctl.model import Actor, Level

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
    with mock.patch("uedctl.dispatch._resolve_level_source", return_value=src):
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
        raise dispatch_mod._SelectionExit(f"{verb}: no games config found (~/.uedctl/config.toml)")
    monkeypatch.setattr(dispatch_mod, "_mover_index", _no_resolver)
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
        raise dispatch_mod._SelectionExit(f"{verb}: no games config found (~/.uedctl/config.toml)")
    monkeypatch.setattr(dispatch_mod, "_mover_index", _no_resolver)
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
