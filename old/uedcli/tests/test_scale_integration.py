"""Live `brush apply-transform` / scale parity on the dx-lum-uned substrate (integration, gated).

Deselected by default (pytest.ini: addopts = -m "not integration"). Run with:
    pytest uedcli/tests/test_scale_integration.py -m integration -v

The offline bake (`transform.bake`) must reproduce the editor's own `ACTOR APPLYTRANSFORM` to 0-diff
(spec §8). For a corpus of scaled / sheared / mirrored / rotated brushes — including PostScale and
Main+Post combos — this: IMPORTADDs the brush, `SELECTNAME` + `ACTOR APPLYTRANSFORM` (the editor
bakes it), `MAP EXPORT`s the result, and asserts the editor's baked world vertices match
`transform.bake(actor)`'s. It also asserts `emit_fscale` byte-matches the editor's re-export of an
un-baked scaled brush. Grounding: dev/docs/spikes/2026-06-25-scale-transform-mechanics.md; the
complex-brush (16-gon / staircase) and all-SheerAxis extension:
dev/docs/spikes/2026-08-04-sheer-bake-byte-parity/spike.md.
"""
import re
import subprocess
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

import pytest

from uedcli import rotation as R, transform as T
from uedcli.builders import cube, cylinder, make_brush_actor, staircase
from uedcli.emit import emit_map
from uedcli.model import Brush, parse_t3d

pytestmark = pytest.mark.integration

CONTAINER = "dx-lum-uned"
PARITY_TOL = 1e-4
D = Decimal

_ALL_AXES = ("SHEER_XY", "SHEER_XZ", "SHEER_YX", "SHEER_YZ", "SHEER_ZX", "SHEER_ZY")


@dataclass(frozen=True)
class Case:
    """One differential case: a builder brush plus the scale-field mutation to apply to its actor."""
    make_brush: Callable[[], Brush]
    setup: Callable[[object], None]


def _cube() -> Brush:
    return cube(128, 64, 32, texture="DefaultTexture")


def _cyl16() -> Brush:
    # 16-gon prism: 16 side quads + tiled caps → many non-axis-aligned faces (bad-matrix bait).
    return cylinder(128, 48, sides=16, texture="DefaultTexture")


def _stair() -> Brush:
    # One non-convex brush, 6 steps: 2 + 4*6 = 26 faces at assorted orientations.
    return staircase(6, 32, 16, 96, texture="DefaultTexture")


def _set_main(fs: T.FScale) -> Callable[[object], None]:
    return lambda a: setattr(a, "main_scale", fs)


def _sheer_main(axis: str, rate: str) -> Callable[[object], None]:
    return lambda a: setattr(a, "main_scale", T.FScale((D(1), D(1), D(1)), D(rate), axis))


def _sheer_post(axis: str, rate: str) -> Callable[[object], None]:
    return lambda a: setattr(a, "post_scale", T.FScale((D(1), D(1), D(1)), D(rate), axis))


def _sheer_and_prop(axis: str, rate: str, prop: tuple[str, str]) -> Callable[[object], None]:
    def setup(a):
        a.main_scale = T.FScale((D(1), D(1), D(1)), D(rate), axis)
        a.props.append(prop)
    return setup


# name -> Case. The cube block is the original spec §8 corpus; the cylinder/staircase and combo
# blocks below extend it to COMPLEX multi-poly brushes and every SheerAxis (spike
# 2026-08-04-sheer-bake-byte-parity).
_CASES: dict[str, Case] = {
    "main_x2": Case(_cube, _set_main(T.FScale((D(2), D(1), D(1))))),
    "main_uniform2": Case(_cube, _set_main(T.FScale((D(2), D(2), D(2))))),
    "mirror_x": Case(_cube, _set_main(T.FScale((D(-1), D(1), D(1))))),
    "main_x2_yaw90": Case(_cube, lambda a: (setattr(a, "main_scale", T.FScale((D(2), D(1), D(1)))),
                                            a.props.append(("Rotation", "(Yaw=16384)")))),
    "post_x2_yaw90": Case(_cube, lambda a: (setattr(a, "post_scale", T.FScale((D(2), D(1), D(1)))),
                                            a.props.append(("Rotation", "(Yaw=16384)")))),
    "sheer_xy_03": Case(_cube, _sheer_main("SHEER_XY", "0.3")),
    "main_x2_prepivot": Case(_cube, lambda a: (setattr(a, "main_scale", T.FScale((D(2), D(1), D(1)))),
                                               a.props.append(("PrePivot", "(X=16.000000)")))),
    "main_post_yaw": Case(_cube, lambda a: (setattr(a, "main_scale", T.FScale((D(2), D(1), D(1)))),
                                            setattr(a, "post_scale", T.FScale((D(1), D(3), D(1)))),
                                            a.props.append(("Rotation", "(Yaw=8192)")))),
    # All six SheerAxis pairs on a 16-gon and a staircase — the shapes most likely to expose a bad
    # sheer matrix/order (non-axis-aligned faces). Rate 0.3 → sheer_coeff k = 0.25.
    **{f"cyl_{ax.split('_')[1].lower()}": Case(_cyl16, _sheer_main(ax, "0.3")) for ax in _ALL_AXES},
    **{f"stair_{ax.split('_')[1].lower()}": Case(_stair, _sheer_main(ax, "0.3")) for ax in _ALL_AXES},
    # sheer × non-uniform Scale — nails the Sheer·Scale ORDER (the gap the scale work flagged).
    "cyl_sheer_scale": Case(_cyl16, _set_main(T.FScale((D(2), D(3), D(1)), D("0.3"), "SHEER_XY"))),
    "stair_sheer_scale": Case(_stair, _set_main(T.FScale((D(2), D(3), D(1)), D("0.3"), "SHEER_YZ"))),
    # sheer × Rotation (yaw), sheer × PrePivot, and PostScale-sheer vs MainScale-sheer.
    "cyl_sheer_yaw": Case(_cyl16, _sheer_and_prop("SHEER_XY", "0.3", ("Rotation", "(Yaw=8192)"))),
    "cyl_sheer_prepivot": Case(_cyl16,
                               _sheer_and_prop("SHEER_XY", "0.3", ("PrePivot", "(X=16.000000)"))),
    "cyl_sheer_post": Case(_cyl16, _sheer_post("SHEER_XY", "0.3")),
    # sheer_coeff snap boundaries: deadzone |r|≤0.05 → k=0 (scaled to keep a real transform), and the
    # ~0.6 notch → k=0.5.
    "cyl_sheer_deadzone": Case(_cyl16, _set_main(T.FScale((D(2), D(1), D(1)), D("0.05"), "SHEER_XY"))),
    "cyl_sheer_notch": Case(_cyl16, _sheer_main("SHEER_XY", "0.6")),
}


@pytest.fixture(scope="module")
def driver():
    from uedcli.driver import Driver
    return Driver(container=CONTAINER)


def _cpath(tag: str) -> str:
    return f"/work/scaleit_{tag}_{uuid.uuid4().hex}.t3d"


def _write(path: str, content: str) -> None:
    subprocess.run(["docker", "exec", "-i", CONTAINER, "tee", path],
                   input=content, text=True, capture_output=True, check=True)


def _read(path: str) -> str:
    return subprocess.run(["docker", "exec", CONTAINER, "cat", path],
                          text=True, capture_output=True, check=True).stdout


def _world_verts(t3d: str) -> list[tuple[float, float, float]]:
    seen = set()
    for line in t3d.splitlines():
        m = re.match(r"\s*Vertex\s+([-+0-9.]+),([-+0-9.]+),([-+0-9.]+)", line)
        if m:
            seen.add(tuple(round(float(x), 6) for x in m.groups()))
    return sorted(seen)


def _worst(pred, obs) -> float:
    if not pred or not obs:
        return float("inf")
    return max(min(max(abs(p[i] - o[i]) for i in range(3)) for p in pred) for o in obs)


@pytest.mark.parametrize("name", sorted(_CASES))
def test_offline_bake_matches_editor_applytransform(driver, name):
    case = _CASES[name]
    a = make_brush_actor("ScaleIT", case.make_brush(), location=(D(0), D(0), D(0)))
    case.setup(a)
    baked_offline = T.bake(a)
    predicted = sorted({tuple(round(c, 6) for c in w) for w in R.world_vertices(baked_offline)})

    ipath, opath = _cpath(name + "_in"), _cpath(name + "_out")
    _write(ipath, emit_map([a]))
    driver.map_new()
    driver.set_grid(1, 1, 1)
    driver.map_importadd(ipath)
    driver.selectname("ScaleIT")
    driver.exec("ACTOR APPLYTRANSFORM")
    driver.map_export(opath)
    editor_actor = parse_t3d(_read(opath)).actors.get("ScaleIT")
    assert editor_actor is not None and editor_actor.brush is not None
    editor = sorted({tuple(round(c, 6) for c in w) for w in R.world_vertices(editor_actor)})

    assert len(editor) == len(predicted), f"{name}: {len(editor)} vs {len(predicted)} corners"
    err = max(_worst(predicted, editor), _worst(editor, predicted))
    assert err <= PARITY_TOL, f"{name}: offline bake vs editor APPLYTRANSFORM worst {err:.6f}uu"
    # fields reset to identity by the editor too
    assert editor_actor.main_scale is None or editor_actor.main_scale.is_identity()
    assert editor_actor.post_scale is None or editor_actor.post_scale.is_identity()


@pytest.mark.parametrize("name", sorted(_CASES))
def test_emission_byte_matches_editor_reexport(driver, name):
    """An un-baked scaled brush's MainScale/PostScale must re-export byte-identically (H3)."""
    case = _CASES[name]
    a = make_brush_actor("ScaleEmit", case.make_brush(), location=(D(0), D(0), D(0)))
    case.setup(a)
    ipath, opath = _cpath(name + "_ein"), _cpath(name + "_eout")
    _write(ipath, emit_map([a]))
    driver.map_new()
    driver.map_importadd(ipath)
    driver.map_export(opath)
    raw = _read(opath)
    for field, fs in (("MainScale", a.main_scale), ("PostScale", a.post_scale)):
        if fs is not None and not fs.is_identity():
            assert f"{field}={T.emit_fscale(fs)}" in raw, (name, field)
