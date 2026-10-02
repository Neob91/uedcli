"""Offline tests for `texframe` — the authored UV frame, the Newell normal, and the actor `PolyFlags`
parse.

Ungated ON PURPOSE: `texframe` needs no Rust extension and no game install (stdlib,
`uedcli.rotation` and `uedcli.builders` only), so these pins must run on a machine with no
`uedcli_native` build, where `test_preview_native.py` skips wholesale.
"""
from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
from decimal import Decimal

import pytest

from uedcli import texframe
from uedcli.builders import _tex_basis
from uedcli.tests.conftest import cube_room, set_prop
from uedcli.texframe import world_uv_frame


def _quad_poly(actor_name="B"):
    """The +X face poly of a unit-ish cube brush, with authored axes."""
    room = cube_room(actor_name, 64, 64)
    return room, room.brush.polys[0]


# ------------------------- UV frames (`unrealed/t3d.md` "The UV convention")


def test_uv_frame_authored_axes_identity_actor():
    actor, poly = _quad_poly()
    poly.origin = (1.0, 2.0, 3.0)
    poly.texture_u = (0.0, 1.0, 0.0)
    poly.texture_v = (0.0, 0.0, -1.0)
    poly.pan = (7, 9)
    base, tu, tv, pan = world_uv_frame(actor, poly)
    assert base == (1.0, 2.0, 3.0)               # Location 0, no PrePivot, no rotation
    assert tu == (0.0, 1.0, 0.0) and tv == (0.0, 0.0, -1.0)
    assert pan == (7.0, 9.0)


def test_uv_frame_rotated_prepivoted_matches_hand_derived():
    actor, poly = _quad_poly()
    actor.location = (Decimal(100), Decimal(200), Decimal(50))
    set_prop(actor, "Rotation", "(Yaw=16384)")   # 90°: x̂→ŷ, ŷ→−x̂ (GMath exact at 90°)
    set_prop(actor, "PrePivot", "(X=10.000000,Y=20.000000,Z=30.000000)")
    poly.origin = (12.0, 24.0, 36.0)
    poly.texture_u = (1.0, 0.0, 0.0)
    poly.texture_v = (0.0, 0.0, 1.0)
    base, tu, tv, pan = world_uv_frame(actor, poly)
    # base = Loc + R·(Origin − PrePivot); R(yaw 90°)·(2,4,6) = (−4,2,6)
    assert base == pytest.approx((96.0, 202.0, 56.0), abs=1e-3)
    assert tu == pytest.approx((0.0, 1.0, 0.0), abs=1e-5)    # x̂ rotates to ŷ
    assert tv == pytest.approx((0.0, 0.0, 1.0), abs=1e-5)    # ẑ unchanged by yaw
    assert pan == (0.0, 0.0)                                  # missing Pan → (0,0)


def test_uv_frame_zero_axes_seed_from_the_STORED_normal_when_it_has_one():
    """Half of the zero/missing-axis fallback: seeded from `poly.normal` when the poly HAS one, even
    where the winding disagrees. That is a deliberate exception to "winding defines the face" and is
    preserved verbatim so this tier and `--native` cannot drift, so it needs its own pin.

    The stored normal is +Z while the winding's Newell normal is +X, and `_tex_basis` returns a
    different pair for each — so seeding from the winding fails this test rather than passing it."""
    actor, poly = _quad_poly()
    actor.location = (Decimal(5), Decimal(6), Decimal(7))
    poly.origin = None
    poly.normal = (0.0, 0.0, 1.0)                # deliberately NOT the winding's +X
    poly.texture_u = (0.0, 0.0, 0.0)             # zero axes → the fallback basis
    poly.texture_v = None
    base, tu, tv, pan = world_uv_frame(actor, poly)
    assert base == (5.0, 6.0, 7.0)               # missing Origin → local zero
    exp_u, exp_v = _tex_basis((0.0, 0.0, 1.0))
    assert _tex_basis((1.0, 0.0, 0.0)) != (exp_u, exp_v)   # the two arms really differ here
    assert tu == pytest.approx(exp_u) and tv == pytest.approx(exp_v)


def test_uv_frame_zero_axes_seed_from_THE_WINDING_when_normal_is_absent():
    """The other half: no stored `Normal` → seed from the unit Newell normal. The winding is reversed
    so Newell is −X, whose `_tex_basis` pair differs from +X's — a fixture whose stored normal and
    winding agree would pass with either arm hard-coded."""
    actor, poly = _quad_poly()
    poly.vertices = list(reversed(poly.vertices))
    poly.normal = None
    poly.texture_u = None
    poly.texture_v = (0.0, 0.0, 0.0)
    _, tu, tv, _ = world_uv_frame(actor, poly)
    exp_u, exp_v = _tex_basis((-1.0, 0.0, 0.0))
    assert _tex_basis((1.0, 0.0, 0.0)) != (exp_u, exp_v)   # reversing the winding is observable
    assert tu == pytest.approx(exp_u) and tv == pytest.approx(exp_v)


def test_uv_frame_unscaled_rotated_is_byte_identical_to_rotation_only():
    """The load-bearing invariant of the scale-aware rewrite: with NO scale, the frame must equal the
    old rotation-only output BIT-FOR-BIT — base `Location + R·(Origin−PrePivot)`, axes `R·axis` (NOT
    the covariant `(L⁻¹)ᵀ`, which differs from `R` at ~1e-7 for a GMath-table R). Every existing
    preview/polyalign golden depends on this, so it is pinned by exact `==`, not `approx`."""
    from uedcli import rotation
    actor, poly = _quad_poly()
    actor.location = (Decimal(100), Decimal(200), Decimal(50))
    set_prop(actor, "Rotation", "(Yaw=9000)")            # non-cardinal, so R⁻¹ᵀ ≠ R numerically
    set_prop(actor, "PrePivot", "(X=10.000000,Y=20.000000,Z=30.000000)")
    poly.origin = (12.0, 24.0, 36.0)
    poly.texture_u = (1.0, 0.0, 0.0)
    poly.texture_v = (0.0, 0.0, 1.0)
    base, tu, tv, _ = world_uv_frame(actor, poly)

    R = rotation.actor_matrix(actor)
    rel = rotation.matvec(R, (12.0 - 10.0, 24.0 - 20.0, 36.0 - 30.0))
    assert base == (100.0 + rel[0], 200.0 + rel[1], 50.0 + rel[2])   # exact, not approx
    assert tu == tuple(rotation.matvec(R, (1.0, 0.0, 0.0)))
    assert tv == tuple(rotation.matvec(R, (0.0, 0.0, 1.0)))


def test_uv_frame_scaled_origin_is_a_point_axes_are_covectors():
    """A scaled brush: the Origin transforms as a POINT by `L` (density stretches with the geometry),
    while `TextureU`/`TextureV` transform as COVECTORS by `(L⁻¹)ᵀ` (magnitude shrinks so texel density
    stays fixed). MainScale X=2 ⇒ base X doubles, world TextureU halves."""
    from uedcli.transform import FScale
    actor, poly = _quad_poly()
    actor.main_scale = FScale(scale=(Decimal(2), Decimal(1), Decimal(1)))
    poly.origin = (10.0, 0.0, 0.0)
    poly.texture_u = (1.0, 0.0, 0.0)
    poly.texture_v = (0.0, 1.0, 0.0)
    poly.pan = (0, 0)
    base, tu, tv, _ = world_uv_frame(actor, poly)
    assert base == pytest.approx((20.0, 0.0, 0.0), abs=1e-9)     # Origin·L (point) — X doubled
    assert tu == pytest.approx((0.5, 0.0, 0.0), abs=1e-9)        # (L⁻¹)ᵀ·U (covector) — X halved
    assert tv == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)


def test_uv_frame_degenerate_scale_raises_naming_the_brush():
    """A zero (degenerate) scale axis makes `L` non-invertible, so the covariant axis map can't be
    built — `world_uv_frame` raises `DegenerateTransformError` naming the brush (→ dispatch exit 2),
    never a bare `ZeroDivisionError`. Guards the mover + `brush poly align` callers (the CSG world path
    already guards this in `brush_marshal`)."""
    from uedcli.transform import DegenerateTransformError, FScale
    actor, poly = _quad_poly("Flat")
    actor.main_scale = FScale(scale=(Decimal(0), Decimal(1), Decimal(1)))
    poly.origin = (1.0, 0.0, 0.0)
    poly.texture_u = (1.0, 0.0, 0.0)
    poly.texture_v = (0.0, 1.0, 0.0)
    with pytest.raises(DegenerateTransformError, match="Flat.*non-invertible"):
        world_uv_frame(actor, poly)


# ------------------------------------------------------------ actor `PolyFlags`


def test_poly_flags_int_parses_or_falls_back_to_zero():
    """The engine ORs an actor's own `PolyFlags` into every one of its polys' flags, and this is the
    parse. Its only other exercise is through `preview_native.build_scene`, which
    `test_preview_native.py` gates behind `importorskip("uedcli_native")` — so on a machine with no
    `cargo` this is the symbol's ONLY coverage."""
    assert texframe.poly_flags_int({"PolyFlags": "2"}) == 2
    assert texframe.poly_flags_int({}) == 0                          # absent key
    assert texframe.poly_flags_int({"PolyFlags": "PF_Masked"}) == 0   # the ValueError arm


# --------------------------------------------------------------- import hygiene


def _imported_modules(path: pathlib.Path) -> set[str]:
    """Every module `path` imports, by name — top-level AND function-local, since `ast` reads the
    source rather than `sys.modules` (which the rest of the suite has already polluted). Relative
    imports resolve to `uedcli.<name>`."""
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(f"uedcli.{node.module}" if node.level else node.module)
            else:                                            # `from . import x`
                out |= {f"uedcli.{a.name}" for a in node.names}
    return out


def test_texframe_source_names_only_stdlib_rotation_and_builders():
    """PINS: the modules `texframe.py`'s OWN source names, top-level and function-local alike.
    GUARANTEES NOTHING TRANSITIVE — a `from .utexture import …` added to `builders.py` leaves this
    green; the subprocess test below is the one that catches that. Kept because it catches the
    converse: a direct import the subprocess test would miss because it is function-local and never
    executed.

    `rotation` and `transform` are REQUIRED, not optional: `world_uv_frame` calls
    `actor_prepivot`/`actor_linear`/`matvec`/`inverse`/`transpose` and, for the degenerate-scale guard,
    `transform.reject_degenerate` (both pure-Python, same no-native/no-game tier). If this fails, move
    the offending import out — do NOT thread the matrices in as parameters, because `world_uv_frame`'s
    signature is what stops this tier and `--native` drifting apart."""
    mods = _imported_modules(pathlib.Path(texframe.__file__))
    # An exact set, so it also excludes the two the plan names: `preview_native` (drags in
    # `uedcli_native` + the texture resolver) and `utexture` (needs a game install). Separate
    # asserts for those two could never fail on their own.
    assert ({m for m in mods if m.split(".")[0] == "uedcli"}
            == {"uedcli.rotation", "uedcli.builders", "uedcli.transform"})
    assert {m.split(".")[0] for m in mods} - {"uedcli"} <= set(sys.stdlib_module_names)


def test_texframe_use_loads_no_native_or_texture_module():
    """PINS, transitively and for real: in a CLEAN interpreter, importing `uedcli.texframe` AND
    running every code path that imports something — `tex_basis_default`, whose `builders` import is
    function-local — leaves neither `uedcli.utexture` (needs a game install) nor `uedcli_native`
    (needs `cargo`) in `sys.modules`, at any depth. So a top-level `from .utexture import …` added to
    `rotation.py` or `builders.py` fails HERE, which the AST test above cannot see. A subprocess is
    required: this suite's own `sys.modules` is long since polluted.

    GUARANTEES NOTHING about `uedcli.preview`, and nothing about an import that exists but is never
    executed; the AST test above covers that half."""
    root = pathlib.Path(texframe.__file__).resolve().parents[1]   # the dir HOLDING the package
    # The child's only route to `uedcli` is that `sys.path` line: `PYTHONPATH` is stripped and no
    # `cwd=` is passed, so the test measures THIS tree and cannot pass on whatever path `bin/test`
    # happens to export.
    probe = (f"import sys; sys.path.insert(0, {str(root)!r});"
             "from uedcli import texframe; texframe.tex_basis_default((1.0, 0.0, 0.0));"
             "print([m for m in ('uedcli.utexture', 'uedcli_native') if m in sys.modules])")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    done = subprocess.run([sys.executable, "-c", probe], env=env, text=True,
                          capture_output=True, check=True)
    assert done.stdout.strip() == "[]", done.stdout
