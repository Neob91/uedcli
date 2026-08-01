"""`brush build <shape>` — a STATELESS generator: writes brush/mover-actor T3D to stdout, no editor,
no level. Also owns the swept-generator advisories and the shared positive-dimension guard.

No source is resolved (nothing is loaded or saved); `--prop`/`--texture` may resolve the project's
class schema and texture path through `cli.resources` when they need it. This module uses
`cli.generators`/`cli.ingest`/`cli.resources` and the `builders`/`propedit`/`emit`/`rotation`
services; it never imports another command family or the router.
"""
from __future__ import annotations

import math
import sys

from ... import generators, ingest, resources
from ...errors import CommandError
from .... import propedit, rotation
from ....uprops import SchemaError


# ── the ONE positive-dimension guard shared by every `brush build` shape ──────────────────────
#
# A negative or zero LENGTH silently produces self-overlapping, inside-out geometry: before this
# guard, `brush build staircase --depth -32` exited 0 and emitted a brush whose steps ran backwards
# through each other, surfacing much later as an incomprehensible BSP failure. Rejecting it at the
# front door is one table and one message shape — never a copy-pasted check per verb.
#
# PLUG-IN POINT for a NEW `brush build <shape>`: add ONE row — `"<shape>": {"--flag": "dest", …}`,
# mapping each of the shape's dimension FLAGS (as the user spells them) to its argparse dest. That
# is the whole integration. `test_every_builder_shape_declares_its_positive_dimensions` enumerates
# the real parser and FAILS unless every FLOAT flag of every shape is either listed here or named
# in that test's explicit non-dimension allow-list (the angles below) — so a new shape cannot
# quietly ship a dimension outside this guard, including one that merely has a default.
#
# Deliberately NOT listed: COUNTS (`--steps`, `--sides`, `--segments`) and ANGLES
# (`--angle-per-step`, `--angle`). Their real constraint is tighter than "> 0" — >= 1 step, >= 3
# sides, a sweep under a half turn — and lives next to the geometry reason for it (in `builders.py`
# for the parametric shapes, in `_revolve_sweep`/the spiral branch for the ones checked in unreal
# rotation units before conversion), where the message can name the actual rule. None of them is a
# float flag any more, so none needs an exemption in the test's allow-list either.
_POSITIVE_BUILD_DIMS: dict[str, dict[str, str]] = {
    "cube":      {"--width": "width", "--breadth": "breadth", "--height": "height"},
    "cylinder":  {"--height": "height", "--radius": "radius"},
    "cone":      {"--height": "height", "--radius": "radius"},
    "sheet":     {"--width": "width", "--height": "height"},
    "staircase": {"--depth": "depth", "--rise": "rise", "--breadth": "breadth"},
    "spiral":    {"--inner-radius": "inner_radius", "--step-width": "step_width", "--rise": "rise"},
    "extrude":   {"--depth": "depth"},
    # `revolve` has no float dimension flag at all: its radii ARE the profile's own `u`
    # coordinates, guarded by the stricter "every point strictly off the axis (u > 0)" rule in
    # `_revolve_sweep`, and `--angle`/`--segments` are an angle and a count (see the note above).
    # The row still has to exist — the plug-in-point test requires one per shape.
    "revolve":   {},
}


def _check_positive_build_dims(shape, args) -> None:
    """Reject a non-positive builder dimension BEFORE any geometry is generated. One message shape
    across every builder verb, naming the offending flag and its value (clean exit 2, never a
    traceback). Flags are checked in the table's order, so the message is deterministic when a
    caller passes several bad values at once."""
    for flag, dest in _POSITIVE_BUILD_DIMS.get(shape, {}).items():
        value = getattr(args, dest, None)
        # `not (finite and > 0)` rather than `<= 0`: NaN compares False against EVERYTHING, so a
        # `<= 0` test waves `--width nan` through to fail later as an unrelated-looking geometry
        # error naming no flag. inf is rejected for the same reason (it builds unbounded vertices).
        if value is not None and not (math.isfinite(value) and value > 0):
            raise CommandError(
                f"brush build {shape}: {flag} must be greater than 0, got {value}")


def _align_offset_degrees(args) -> float:
    """`--align-to-side` → the cross-section offset the builder takes, in degrees.

    Half a segment (`180/sides`) turns a FACE rather than a vertex toward the axes, so an n-gon
    pillar sits flush against an axis-aligned wall instead of meeting it on a corner. It is a bool
    at the CLI because that is the only documented use, because any other angle is whole-actor
    placement (`--rotate`), and because a half segment is not exactly representable in unreal
    rotation units for most side counts (a 3-gon's 60° is 10922.67 uu)."""
    return 180.0 / args.sides if getattr(args, "align_to_side", False) else 0.0


def _profile_points(shape: str, args):
    """Parse and validate a swept generator's `--point U,V` profile, in ONE fixed order, before any
    geometry exists: token parse → arity → cleanup (weld + drop collinear) → simple-ring test →
    winding normalization. Returns the cleaned, counter-clockwise ring.

    Every failure is a clean exit 2 naming the offending value. `profile.ProfileError` already
    subclasses `GeometryError` (which `dispatch()` catches without a traceback); it is re-raised as
    `CommandError` here so the message carries the usual `brush build <shape>:` prefix rather than
    the generic "invalid brush geometry" one."""
    from .... import profile as profile2d
    tokens = getattr(args, "point", None) or []
    try:
        points = [profile2d.parse_point(t) for t in tokens]
        if len(points) < 3:
            raise profile2d.ProfileError(
                f"a profile needs at least 3 points, got {len(points)}")
        ring = profile2d.clean_profile(points)      # welds + drops collinear; re-checks the arity
        profile2d.check_simple(ring)
        return profile2d.normalize_winding(ring)
    except profile2d.ProfileError as e:
        raise CommandError(f"brush build {shape}: {e}") from None


def _revolve_sweep(args, points) -> tuple[float, int]:
    """Validate `brush build revolve`'s sweep and return `(degrees, segments)`.

    Checked in this fixed order, each failure a clean exit 2 naming the flag AND the value the user
    typed: `--angle` range → the `--segments` default → `--segments` range → the closed-turn
    minimum → the per-facet angle → the strictly-off-axis profile rule.

    Three things here are load-bearing:

    - **The closed-turn minimum is tested BEFORE the per-facet angle**, not after — see the comment
      at that check. A full turn in 1 or 2 segments trips both rules, and `65536/2` is exactly the
      32768 the facet rule rejects, so ordering them the other way would make the closed-turn rule
      unreachable and report the generic facet message for a mistake that has a specific one.

    - **The range check is on the RAW integer, before any conversion**, and the conversion is a
      plain `uu * 360/65536`. `rotation.uu_field`/`uu_to_deg` must NEVER be used: they wrap mod
      65536 because they parse an FRotator *field*, which is inherently modular — but a sweep
      MAGNITUDE is not, and `uu_to_deg(65536)` is `0.0`, so routing a closed full turn through them
      would silently collapse it to a zero sweep.
    - **The `--segments` default is spelled `floor(x + 0.5)`, not `round()`**, which is banker's
      rounding and would make the tie cases surprising.
    """
    angle = args.angle
    if not (0 < angle <= 65536):
        raise CommandError(
            f"brush build revolve: --angle must satisfy 0 < angle <= 65536 unreal rotation units "
            f"(65536 = a full turn), got {angle}")
    segments = args.segments
    if segments is None:
        segments = max(1, math.floor(angle / 4096 + 0.5))   # one facet per 22.5°, UED's own density
    if segments < 1:
        raise CommandError(
            f"brush build revolve: --segments must be at least 1, got {segments}")
    # The closed-turn minimum is tested BEFORE the per-facet rule even though a full turn in 1 or 2
    # segments trips both: its message is the specific one for that mistake, and testing it second
    # would make this rule unreachable (65536/2 is exactly the 32768 the facet rule rejects).
    if angle == 65536 and segments < 3:
        raise CommandError(
            f"brush build revolve: a closed full turn (--angle 65536) needs at least 3 "
            f"--segments, got {segments} — with fewer, the far ring welds onto the near ring and "
            f"every side quad collapses")
    if angle / segments >= 32768:
        raise CommandError(
            f"brush build revolve: --angle {angle} over --segments {segments} is "
            f"{angle / segments:g} uu per facet; a facet of 32768 uu (180°) or more is flat — it "
            f"maps every profile point to its mirror image, giving a zero-volume solid")
    for i, (u, v) in enumerate(points):
        if u <= 0:
            raise CommandError(
                f"brush build revolve: every profile point must sit strictly on the POSITIVE-u "
                f"side of the revolve axis (the line u=0), got point {i} at ({u},{v}) — mirror "
                f"the profile's u values to bulge the other way")
    return angle * 360.0 / 65536.0, segments


def _build_brushes(builders, shape, args):
    """Dispatch `brush build <shape>` to its generator. Returns a Brush or a list of
    Brush (single-element list for convex primitives; staircase → one non-convex
    Brush; extrude and revolve → one swept brush each, non-convex whenever the profile is;
    spiral → a central column plus one wedge tread per step, a list of len > 1). The dispatch
    caller emits one actor per Brush, so the `len(list) > 1` branch stays live for the spiral."""
    _check_positive_build_dims(shape, args)
    if shape == "cube":
        return [builders.cube(args.width, args.breadth, args.height, args.texture)]
    # `--align-to-side` is a BOOL at the CLI and half a segment in DEGREES at the builder: the
    # builders stay a degrees-valued internal API (four direct callers produce editor-blessed
    # parity goldens from angles that are not half-segments at all — decisions.md 2026-07-25 02:30
    # UTC, D11), while the user-facing surface is UU or a bool, never degrees.
    if shape == "cylinder":
        return [builders.cylinder(args.height, args.radius, args.sides, args.texture,
                                  angle_offset=_align_offset_degrees(args))]
    if shape == "cone":
        return [builders.cone(args.height, args.radius, args.sides, args.texture,
                              angle_offset=_align_offset_degrees(args))]
    if shape == "sheet":
        return [builders.sheet(args.width, args.height, args.plane, args.texture,
                               extra_flags=getattr(args, "flags", None))]
    if shape == "staircase":
        return builders.staircase(args.steps, args.depth, args.rise, args.breadth, args.texture)
    if shape == "spiral":
        # The USER-FACING range check, in the units the user typed and naming the flag they typed,
        # BEFORE any conversion (decisions.md 2026-07-25 02:30 UTC, D12). `builders` keeps its own
        # guard for its non-CLI callers, in degrees and naming the parameter.
        per_step = args.angle_per_step
        if not (0 < per_step < 32768):
            raise CommandError(
                f"brush build spiral: --angle-per-step must satisfy 0 < angle < 32768 unreal "
                f"rotation units (32768 = a half turn), got {per_step}")
        return builders.spiral_staircase(args.steps, args.inner_radius, args.step_width,
                                         args.rise, per_step * 360.0 / 65536.0, args.texture)
    if shape == "extrude":
        return [builders.extrude(_profile_points(shape, args), args.depth, args.axis,
                                 args.texture)]
    if shape == "revolve":
        points = _profile_points(shape, args)
        degrees, segments = _revolve_sweep(args, points)
        return [builders.revolve(points, degrees, segments, args.axis, args.texture)]
    raise ValueError(f"unknown builder shape {shape!r}")


# The two stderr ADVISORIES of the swept generators. Both are gated on the shape, so no existing
# verb changes behaviour: `brush build cylinder --radius 48` has inherently fractional ring
# vertices and a green test asserting it says nothing (`test_generators.py`), and a 16-step
# staircase already emits 66 faces. Whether the poly budget should also cover those shapes is an
# open question filed on `board/inbox/` rather than decided here.
_SWEPT_SHAPES = frozenset({"extrude", "revolve"})
_POLY_BUDGET = 64


def _advise_swept_brush(shape: str, actors, *, mover_class, poly_flags: int) -> None:
    """Print the swept generators' two advisories to STDERR — stdout stays a clean T3D snippet and
    the exit status is unaffected (these report a legitimate build, not a half-answer).

    1. **Off-grid + solid.** A revolve is off the integer grid by construction (every vertex away
       from `θ=0` lands on `radius·cos/sin θ`) and uedcli deliberately preserves genuine fractions.
       An off-grid *solid* brush throws its BSP partition planes off-grid too, landing faces inside
       the engine's `SplitWithPlane`/`RemoveColinears` tolerance bands — slivers, T-junctions,
       dropped faces, holes. The prescribed mitigation is `--solidity semisolid`, which receives
       cuts but emits no world-splitting planes. Gated on non-mover as well as on solidity: a mover
       REJECTS `--solidity`, so it always lands on the solid flag value (0) while never
       partitioning the world.
    2. **Poly budget.** A 16-segment revolve of an 8-point profile is 128 swept faces plus caps —
       a lot of BSP for one brush.
    """
    if shape not in _SWEPT_SHAPES:
        return
    for actor in actors:
        if actor.brush is None:
            continue
        if (mover_class is None and poly_flags == 0
                and any(generators.offgrid_flags(rotation.world_vertices(actor)))):
            print(f"warning: brush build {shape}: {actor.name} has vertices off the integer grid "
                  f"AND is solid — an off-grid solid throws its BSP splitting planes off-grid too "
                  f"(slivers, T-junctions, holes in the built map). Consider --solidity semisolid "
                  f"where this is detail rather than structure, or author on-grid points",
                  file=sys.stderr)
        faces = len(actor.brush.polys)
        if faces > _POLY_BUDGET:
            caps = sum(1 for p in actor.brush.polys if p.item == "Cap")
            print(f"warning: brush build {shape}: {actor.name} has {faces} faces "
                  f"({faces - caps} swept + {caps} cap) — a heavy brush for the BSP; consider a "
                  f"simpler profile, fewer --segments, or --solidity semisolid so it does not "
                  f"partition the world", file=sys.stderr)


def run(args) -> int:
    """`brush build <shape>` — build a parametric shape and write its actor T3D to stdout. Stateless:
    no level is loaded or saved. `--prop`/`--rotate`/`--folder`/`--label` apply the same generator
    post-steps as `actor build`; `--mover-class` makes a Mover of the shape."""
    from .... import builders
    from ....emit import emit_actor_t3d
    shape = args.shape
    mover_class = getattr(args, "mover_class", None)
    if mover_class is not None:
        parts = mover_class.split(".")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise CommandError(
                f"brush build: --mover-class must be Package.Name, got: {mover_class!r}")
        if args.csg is not None:
            raise CommandError("brush build: --csg is invalid with --mover-class "
                                 "(a mover does not participate in world CSG)")
        if args.solidity is not None:
            raise CommandError("brush build: --solidity is invalid with --mover-class "
                                 "(a mover's collision is not CSG solidity — set actor "
                                 "collision flags via --prop)")
    brush_or_list = _build_brushes(builders, shape, args)
    at = tuple(args.at) if args.at else (0.0, 0.0, 0.0)
    if mover_class is not None:
        name_template = args.base_name or mover_class.rsplit(".", 1)[-1]   # ElevatorMover/Mover
    else:
        name_template = args.base_name or shape.capitalize()
    poly_flags = builders.SOLIDITY_FLAGS.get(args.solidity or "solid", 0)
    csg = args.csg or "add"
    # Group is no longer a dedicated brush-build flag (ditched 2026-07-24 17:04) — set it via
    # --prop Group=<name>, applied below; so make_brush_actor gets group=None.
    if isinstance(brush_or_list, list) and len(brush_or_list) > 1:
        actors = [
            builders.make_brush_actor(f"{name_template}{k}", b, location=at, csg=csg,
                                      group=None, poly_flags=poly_flags,
                                      mover_class=mover_class)
            for k, b in enumerate(brush_or_list)
        ]
    else:
        b = brush_or_list[0] if isinstance(brush_or_list, list) else brush_or_list
        actors = [builders.make_brush_actor(name_template, b, location=at, csg=csg,
                                            group=None, poly_flags=poly_flags,
                                            mover_class=mover_class)]
    # --prop (M3): schema-validated actor properties, same grammar/validation as `actor build
    # --prop`, applied to EVERY emitted brush/mover actor (composing onto its generator props:
    # CsgOper/PolyFlags/Group/Brush). The way to set open-ended mover config (MoverEncroachType,
    # Tag/Event, collision flags) at birth. Grammar errors surface before schema resolution.
    prop_tokens = getattr(args, "prop", None) or []
    if prop_tokens:
        try:
            ptoks = [propedit.parse_token(t, expect_value=True) for t in prop_tokens]
        except propedit.PropEditError as e:
            raise CommandError(f"brush build: {e}") from None
        ctxs: dict[str, propedit.ClassCtx] = {}
        for a in actors:
            ctx = ctxs.setdefault(a.cls.casefold(), resources.class_ctx(a.cls, args))
            try:
                plan = propedit.plan_edit(a, ptoks, "set", ctx, propedit.TYPED_FIELDS)
            except propedit.PropEditError as e:
                raise CommandError(f"brush build: {e}") from None
            except SchemaError as e:
                raise CommandError(f"brush build: {e}") from None
            a.props = plan.props
            for attr, val in plan.typed_updates.items():
                setattr(a, attr, val)
    # Feature 7: --rotate SETS the Rotation field absolutely on every emitted actor (identity
    # base ⇒ no add-vs-override ambiguity); warns off-grid. No-op when the flag is absent.
    # (After --prop so --rotate wins over a --prop Rotation=…, matching actor build.)
    generators.apply_generator_rotate(actors, getattr(args, "rotate", None))
    # AFTER --rotate, so rotation-induced off-grid geometry counts too. `generators.apply_generator_rotate`
    # emits its own rotation-specific warning; both may print, and they report different causes.
    _advise_swept_brush(shape, actors, mover_class=mover_class, poly_flags=poly_flags)
    generators.apply_generator_org(actors, args)             # --folder/--label → sidecar carriers
    # Author-time gate: existence-validate the class (Engine.Brush or --mover-class) + the
    # --texture ref, if any, before emitting the T3D.
    ingest.validate_ingest_actors(actors, args)
    for a in actors:
        sys.stdout.write(emit_actor_t3d(a))
    return 0
