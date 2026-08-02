"""Brush whole-actor edits and CSG/clip set filters: `scale`, `apply-transform`, `replace`
(source-consuming, model-side) and `intersect`/`deintersect`/`clip` (stateless filters over a piped
brush set).

`scale`/`apply-transform`/`replace` transform the trunk level the route resolved and write it back;
`intersect`/`deintersect` consume T3D on stdin and emit one merged brush/mover actor to stdout, and
`clip` clips every brush in a piped set by one world plane and emits them to stdout — all three touch
neither trunk nor stash. This module uses `cli.generators`/`cli.ingest`/`cli.resources`/
`cli.targets` and the model-side services (`brushcsg`/`movers`/`transform`/`clip`/`query`/`rotation`/
`emit`); it never imports another command family or the router.
"""
from __future__ import annotations

import sys
from decimal import Decimal

from ... import generators, ingest, resources
from ... import targets as target_names
from ...errors import CommandError
from .... import emit, propedit, query, rotation
from ....geometry import GeometryError, validate_brush
from ....model import parse_t3d_actors
from ....normalize import is_builder_brush
from ....uprops import SchemaError


def _fmt_coord_component(value) -> str:
    """A reported coordinate as a tidy string — `emit.fmt_coord` is the one definition, shared with
    `stashlib.format_summary` and `query._coord_component` so they cannot drift apart."""
    return emit.fmt_coord(value)


def merge(args) -> int:
    """`brush intersect` / `brush deintersect` — CSG-merge a piped brush SET into ONE brush.

    A generator in the `brush build` mould: consumes T3D on stdin, produces one brush (or Mover)
    actor T3D on stdout, touches neither trunk nor stash.  The merge itself is
    `brushcsg.merge` -> `uedcli_native.intersect_brushset` (the decoded `bspBrushCSG` intersect
    tail); everything here is CLI shape — flag validation, placement, and the shared generator
    post-steps (`--prop`/`--rotate`/`--folder`/`--label`) that `brush build` also applies.
    """
    from .... import brushcsg
    from ....emit import emit_actor_t3d
    from ....model import parse_t3d

    verb = args.sub
    deintersect = verb == "deintersect"
    mover_class = getattr(args, "mover_class", None)
    if mover_class is not None:
        parts = mover_class.split(".")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise CommandError(
                f"brush {verb}: --mover-class must be Package.Name, got: {mover_class!r}")
        if args.csg is not None:
            raise CommandError(f"brush {verb}: --csg is invalid with --mover-class "
                                 "(a mover does not participate in world CSG)")
        # `--solidity` is rejected outright on a mover — ALL values, `solid` included. A mover keeps
        # the SOURCE per-face solidity of the welded set, and that is always correct: a semisolid
        # face collides exactly like a solid one (only `nonsolid` is walk-through — collision spike
        # §3), so there is nothing to "scrub" and no reason to override. Actor-level solidity
        # (`semisolid`/`nonsolid`) is meaningless on a mover (it has no part in world CSG). Set a
        # mover's collision via --prop if you ever need to. (Earlier this special-cased `--solidity
        # solid` as a "cure" for a supposed semisolid-door-walk-through trap — that trap was a myth;
        # semisolid blocks.)
        if args.solidity is not None:
            raise CommandError(
                f"brush {verb}: --solidity is invalid with --mover-class — a mover keeps the SOURCE "
                "per-face solidity of the welded set (a semisolid face blocks just like solid; only "
                "nonsolid is walk-through), so there is nothing to override. Set a mover's collision "
                "via --prop if needed.")
    try:
        origin = brushcsg.parse_anchor_spec(args.origin, flag="--origin", allow_keep=True)
        pivot_spec = brushcsg.parse_anchor_spec(args.pivot, flag="--pivot", allow_keep=False)
    except brushcsg.BrushCsgError as e:
        raise CommandError(f"brush {verb}: {e}") from None
    # `--origin keep` is the RAW faithful form (Location=0, world-space verts) — it exists to diff
    # against an editor export, so it is incompatible with any placement (which would double-apply).
    if origin == "keep":
        if args.at is not None:
            raise CommandError(
                f"brush {verb}: --at is invalid with --origin keep — `keep` emits the result at its "
                "absolute carved position (Location=0, world vertices), so placing it would "
                "translate it twice. Drop --origin keep to place the result")
        if pivot_spec is not None:
            raise CommandError(
                f"brush {verb}: --pivot is invalid with --origin keep — `keep` emits the raw form "
                "with no local origin to pivot about")

    text = ingest.read_t3d_input(args.set)
    if not text.strip():
        return 0                                          # empty stdin: clean no-op (exit 0)
    # `parse_t3d_actors` (NOT `parse_t3d`): the Name-keyed dict drops all but the LAST of each
    # duplicate group, and duplicates are the NORMAL case here — every `brush build cube` emits
    # `Name=Cube`, so the canonical composition (two generator outputs concatenated into one pipe)
    # feeds two identically-named actors and the additive would silently vanish. Keeping an ordered
    # list also makes STDIN ORDER (= the CSG order, load-bearing for a mixed add/subtract set)
    # explicit rather than incidental to dict insertion. Builder brushes are dropped as on every
    # other T3D ingest path: a `MAP EXPORT`-derived stream carries the transient red brush, and
    # `_oper_of` would otherwise merge it as an additive.
    actors = [a for a in parse_t3d_actors(text) if not is_builder_brush(a)]
    if not actors:
        raise CommandError(
            f"brush {verb}: stdin held no brush actors — this reads a T3D SNIPPET (the output of "
            f"`actor show` / `stash show` / `brush build`), not the newline-separated NAME list "
            f"that `actor find` prints and the mutating verbs take")

    try:
        brushcsg.check_all_csg_brushes(actors, verb=verb,
                                       index=resources.mover_index(args, f"brush {verb}"))
        brushcsg.check_guards(actors, deintersect=deintersect)
        brushcsg.check_unscaled(actors)
        n = len(actors)
        print(f"brush {verb}: merging {n} brush{'' if n == 1 else 'es'}", file=sys.stderr)
        pairs = brushcsg.merge(actors, deintersect=deintersect)
    except brushcsg.BrushCsgError as e:
        raise CommandError(str(e)) from None
    polys = [p for p, _src in pairs]
    if not polys:
        raise CommandError(
            f"brush {verb}: the merge produced no faces — the set encloses no "
            f"{'void' if deintersect else 'solid'} against "
            f"{'a solid' if deintersect else 'an empty'} background")

    # A disjoint result stays ONE actor (there is deliberately no --split, decision 2026-07-24
    # 18:12); say so, since a caller wanting independent movers must re-run per subset.
    ncomp = brushcsg.component_count(polys)
    if ncomp > 1:
        print(f"brush {verb}: the result has {ncomp} DISCONNECTED components, emitted as one "
              f"actor — run the verb on each subset separately for independently movable pieces",
              file=sys.stderr)

    # `--texture` RETEXTURES the whole result. Without this the merge is faithful-only: each face
    # keeps the texture of the source face it was cut from (Phase-2 caps inherit the surrounding
    # brushes' surfaces), which is right by default but leaves no way to skin the welded brush —
    # and a door plug cut out of wall geometry comes out wearing the wall.
    if getattr(args, "texture", None):
        for p in polys:
            p.texture = args.texture
    poly_flags = brushcsg.apply_solidity(polys, args.solidity)
    if origin == "keep":
        location, prepivot = (Decimal(0), Decimal(0), Decimal(0)), (0, 0, 0)
    else:
        lo, hi = brushcsg.result_bounds(polys)
        anchor = brushcsg.resolve_anchor(origin, lo, hi)
        pivot = brushcsg.resolve_anchor(pivot_spec, lo, hi) if pivot_spec is not None else anchor
        location, prepivot = brushcsg.recenter(polys, anchor=anchor, pivot=pivot)
        if args.at is not None:
            location = tuple(args.at)                     # place the result's pivot at --at

    if mover_class is not None:
        name = args.base_name or mover_class.rsplit(".", 1)[-1]
    else:
        name = args.base_name or verb.capitalize()
    actor = brushcsg.make_result_actor(
        polys, name=name, location=location, prepivot=prepivot,
        csg=args.csg or "add", poly_flags=poly_flags, mover_class=mover_class)

    # The shared generator post-steps, in `brush build`'s order: --prop (schema-validated) first,
    # then --rotate (so it wins over a --prop Rotation=…), then the folder/label carriers.
    prop_tokens = getattr(args, "prop", None) or []
    if prop_tokens:
        try:
            ptoks = [propedit.parse_token(t, expect_value=True) for t in prop_tokens]
            plan = propedit.plan_edit(actor, ptoks, "set", resources.class_ctx(actor.cls, args),
                                      propedit.TYPED_FIELDS)
        except propedit.PropEditError as e:
            raise CommandError(f"brush {verb}: {e}") from None
        except SchemaError as e:
            raise CommandError(f"brush {verb}: {e}") from None
        actor.props = plan.props
        for attr, val in plan.typed_updates.items():
            setattr(actor, attr, val)
    generators.apply_generator_rotate([actor], getattr(args, "rotate", None))
    generators.apply_generator_org([actor], args)
    ingest.validate_ingest_actors([actor], args)
    sys.stdout.write(emit_actor_t3d(actor))
    return 0


def clip(args) -> int:
    """`brush clip` — clip every brush in a piped T3D SET by one world plane, keeping one half.

    A stateless filter in the `brush intersect`/`deintersect` mould: reads a brush T3D snippet on
    stdin (`-`) or a FILE, clips each brush actor by the same world plane, emits the clipped actors
    to stdout, touching neither trunk nor stash. The plane is mapped into EACH actor's own local
    frame (`rotation.world_to_local_*`) from the `Location`/`Rotation`/`PrePivot` the snippet
    carries, so it is as rotation-aware as a placed edit. To clip a PLACED actor, compose with
    `replace`: `actor show X | brush clip - … | brush replace X -`.
    """
    from .... import clip as clipmod
    from ....emit import emit_actor_t3d

    has_plane = args.plane is not None
    has_axis = args.axis is not None or args.offset is not None
    if has_plane and has_axis:
        print("brush clip: give EITHER --plane PX,PY,PZ NX,NY,NZ OR --axis AXIS --offset N, "
              "not both", file=sys.stderr)
        return 2
    if has_plane:
        point, normal = args.plane                # two X,Y,Z triples
    elif args.axis is not None and args.offset is not None:
        point, normal = clipmod.axis_plane(args.axis, args.offset)
    else:
        print("brush clip needs --axis AXIS --offset N, or --plane PX,PY,PZ NX,NY,NZ",
              file=sys.stderr)
        return 2

    text = ingest.read_t3d_input(args.set)
    if not text.strip():
        return 0                                  # empty stdin: clean no-op (exit 0)
    actors = [a for a in parse_t3d_actors(text) if not is_builder_brush(a)]
    if not actors:
        raise CommandError(
            "brush clip: stdin held no brush actors — this reads a T3D SNIPPET (the output of "
            "`actor show` / `stash show` / `brush build`), not the newline-separated NAME list that "
            "`actor find` prints and the mutating verbs take")
    nonbrush = [a.name for a in actors if a.brush is None]
    if nonbrush:
        print(f"brush clip: not a brush: {', '.join(nonbrush)} — clip transforms brush geometry; a "
              f"point actor has none. Narrow the pipe with `actor find --kind brush`",
              file=sys.stderr)
        return 2

    keep_negative = args.keep == "below"          # below = opposite the normal (orientation kept)
    # All-or-nothing across the set: a plane that DISCARDS a whole brush fails the run naming every
    # such brush and writes nothing; a plane that MISSES a brush interior passes it through with a
    # stderr note. Both decisions are made over the whole set before any stdout, so a later discard
    # cannot leave a half-written result or a stale "unchanged" note on a run that exits 2.
    discarded: list[str] = []
    whole: list[str] = []
    for actor in actors:
        # The plane is world-space; map it into this brush's LOCAL frame (vertices are local). For a
        # rotated/scaled brush this clips the local PolyList by the pulled-back plane and preserves
        # the Rotation/scale fields, so it materializes as the intended world clip.
        local_point = rotation.world_to_local_point(actor, point)
        local_normal = rotation.world_to_local_normal(actor, normal)
        kind = clipmod.classify_clip(actor.brush, local_point, local_normal,
                                     keep_negative=keep_negative)
        if kind == "empty":
            discarded.append(actor.name)
            continue
        if kind == "whole":
            whole.append(actor.name)
            continue
        try:
            actor.brush = clipmod.clip_brush(actor.brush, local_point, local_normal,
                                             keep_negative=keep_negative)
            validate_brush(actor.brush)
        except GeometryError as e:
            raise CommandError(f"brush clip: {actor.name}: {e}") from None
    if discarded:
        raise CommandError(
            f"brush clip: plane discards the whole brush for: {', '.join(discarded)} — the clip "
            f"would remove every face (nothing kept on the --keep {args.keep} side)")
    for name in whole:
        print(f"brush clip: plane did not intersect brush {name} — emitted unchanged",
              file=sys.stderr)
    for actor in actors:
        sys.stdout.write(emit_actor_t3d(actor))
    return 0


def run(args, src) -> int:
    """Route one source-consuming brush edit (`scale`, `apply-transform`, `replace`) against
    the trunk source the route already resolved."""
    if args.sub == "scale":
        return _scale(args, src)
    if args.sub == "apply-transform":
        return _apply_transform(args, src)
    if args.sub == "replace":
        return _replace(args, src)
    raise CommandError(f"unimplemented brush edit sub-verb: {args.sub}")


def _scale(args, src) -> int:
    from .... import movers, transform
    raw = target_names.resolve_target_names(args.names)          # `-` → names from stdin
    if not raw:
        return 0
    level = src.load()
    try:
        resolved = query.resolve_actor_names(level, raw)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    names = list(dict.fromkeys(resolved))            # dedupe: scaling twice would double-apply
    # `brush` verb (renamed from `actor scale`): MainScale is a brush-family property, so reject a
    # non-brush (point) actor up front, all-or-nothing — like the other brush verbs.
    nonbrush = [n for n in names if level.actors[n].brush is None]
    if nonbrush:
        print(f"brush scale: not a brush: {', '.join(nonbrush)} — MainScale is a brush property "
              f"(a mesh scales via DrawScale, e.g. `actor prop set … DrawScale=…`)",
              file=sys.stderr)
        return 2
    targets = [level.actors[n] for n in names]
    factors = args.to if args.to is not None else args.by
    # Disallow a zero / sub-epsilon scale factor — it collapses the brush to a plane and makes the
    # transform non-invertible (spec §7). Named exit-2, never a downstream crash.
    for c in factors:
        if abs(Decimal(c)) < transform.SCALE_EPS:
            print(f"brush scale: scale factor {tuple(str(x) for x in factors)} has a "
                  f"zero/sub-epsilon component — refusing (would collapse the brush)",
                  file=sys.stderr)
            return 2
    uniform = factors[0] == factors[1] == factors[2]
    # `--to` is an ABSOLUTE, IN-PLACE MainScale target (Location never moves), so a pivot is
    # meaningless with it (spec §4). This is one of the cheap argument checks, so it belongs
    # ABOVE the resolver — otherwise `brush scale --to … --pivot …` with no games config blames
    # the missing config instead of the conflicting flags the user actually typed.
    if args.to is not None and (args.pivot is not None or args.pivot_actor is not None):
        print("brush scale --to is in-place and cannot take a --pivot/--pivot-actor",
              file=sys.stderr)
        return 2
    # Same reason: `--pivot-actor` names an actor in the ALREADY-LOADED level, so resolving it is
    # as cheap as the checks above — and a typo'd pivot name must say `Actor not found: …`, not
    # blame a missing games config.
    default_loc = resources.default_location_for(args)          # ONE closure = one memo (see rotate)
    pivot_actor_loc = None
    if args.pivot_actor is not None:
        try:
            pivot_canonical = query.resolve_actor_name(level, args.pivot_actor)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        # The named actor's EFFECTIVE Location — see the same note on `actor rotate --by`.
        pa = level.actors[pivot_canonical]
        pivot_actor_loc = rotation.actor_own_pivot(
            pa, None if pa.location is not None else default_loc(pa))
    # AFTER every cheap argument check above (so a bad factor, a flag conflict or an unknown
    # pivot actor reports itself, not a missing resolver) and once per invocation, not per actor.
    mover_index = resources.mover_index(args, "brush scale")
    if args.to is not None:
        for actor in targets:
            cur = rotation.actor_main_scale(actor)
            actor.main_scale = transform.FScale(tuple(Decimal(c) for c in args.to),
                                                cur.sheer_rate, cur.sheer_axis)
            if movers.is_mover(actor, mover_index):
                print(f"warning: {actor.name} is a Mover — its keyframe travel (KeyPos/KeyRot) "
                      f"does not scale with the brush", file=sys.stderr)
            if not rotation.actor_post_scale(actor).is_identity():
                print(f"warning: {actor.name} has a non-identity PostScale — the previewed world "
                      f"scale is PostScale*MainScale, not {tuple(str(c) for c in args.to)}",
                      file=sys.stderr)
            if actor.brush is not None:
                validate_brush(actor.brush)
        for name in names:                           # PRODUCER: scaled names to stdout (feed `| verb -`)
            print(name)
        print(f"scaled {len(targets)} actor(s) to "
              f"{','.join(_fmt_coord_component(c) for c in args.to)}", file=sys.stderr)
        src.save(verb="scale", args={"names": names, "to": [str(c) for c in args.to]},
                 level=level, touched=names)
        return 0
    # RELATIVE (--by): multiply MainScale per-axis AND orbit each Location component-wise about
    # the pivot (`Loc' = P + S∘(Loc−P)` — NOT the rotation orbit; spec §10).
    if args.pivot is not None:
        pivot = args.pivot
    elif pivot_actor_loc is not None:                # resolved above, BEFORE the class resolver
        pivot = pivot_actor_loc
    else:
        pivot = rotation.best_grid_pivot(targets, default_loc)
    S = tuple(Decimal(c) for c in args.by)
    for actor in targets:
        # Same EFFECTIVE Location the pivot resolved — see the note in `actor rotate --by`.
        loc = rotation.actor_own_pivot(
            actor, None if actor.location is not None else default_loc(actor))
        actor.location = tuple(pivot[i] + (loc[i] - pivot[i]) * S[i] for i in range(3))
        cur = rotation.actor_main_scale(actor)
        actor.main_scale = transform.FScale(
            tuple(Decimal(cur.scale[i]) * S[i] for i in range(3)), cur.sheer_rate, cur.sheer_axis)
        if movers.is_mover(actor, mover_index):
            print(f"warning: {actor.name} is a Mover — its keyframe travel (KeyPos/KeyRot) does "
                  f"not scale with the brush", file=sys.stderr)
        if not uniform and not rotation.is_identity_uu(rotation.actor_rotation_uu(actor)):
            print(f"warning: {actor.name} is rotated and scaled non-uniformly about a world "
                  f"pivot — MainScale is pre-rotation, so the world pivot orbit is inexact "
                  f"(consider apply-transform first)", file=sys.stderr)
        if actor.brush is not None:
            validate_brush(actor.brush)
    for name in names:                               # PRODUCER: scaled names to stdout (feed `| verb -`)
        print(name)
    print(f"scaled {len(targets)} actor(s) about "
          f"{','.join(_fmt_coord_component(c) for c in pivot)}", file=sys.stderr)
    src.save(verb="scale",
             args={"names": names, "by": [str(c) for c in args.by],
                   "pivot": [str(c) for c in pivot]},
             level=level, touched=names)
    return 0


def _apply_transform(args, src) -> int:
    from .... import movers, transform
    raw = target_names.resolve_target_names(args.names)
    if not raw:
        return 0
    level = src.load()
    try:
        resolved = query.resolve_actor_names(level, raw)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    names = list(dict.fromkeys(resolved))
    targets = [(n, level.actors[n]) for n in names]
    # `brush` verb (renamed from `actor apply-transform`): the bake folds into the PolyList, so a
    # non-brush (point) actor has nothing to bake — reject up front, all-or-nothing.
    nonbrush = [n for n, a in targets if a.brush is None]
    if nonbrush:
        print(f"brush apply-transform: not a brush: {', '.join(nonbrush)} — the bake folds the "
              f"transform into brush vertices; a point actor has none", file=sys.stderr)
        return 2
    # Guards all-or-nothing (spec §7): a Mover bake rewrites PrePivot (= the swing axis) and
    # desyncs KeyPos/KeyRot — reject before mutating anything.
    mover_index = resources.mover_index(args, "brush apply-transform")
    movers_hit = [n for n, a in targets if movers.is_mover(a, mover_index)]
    if movers_hit:
        print(f"brush apply-transform: refusing to bake Mover(s) {', '.join(movers_hit)} — a "
              f"bake rewrites PrePivot (the swing axis) and desyncs keyframe travel (deferred "
              f"in v1); scale/rotate a mover in place instead", file=sys.stderr)
        return 2
    for n, a in targets:
        if not rotation.actor_post_scale(a).is_identity():
            print(f"warning: {n} has a non-identity PostScale — baking it is DESTRUCTIVE and "
                  f"IRREVERSIBLE (v1 has no PostScale-authoring verb to reconstruct it)",
                  file=sys.stderr)
    for n, a in targets:
        baked = transform.bake(a, lock_textures=args.lock_textures)
        if baked.brush is not None:
            validate_brush(baked.brush)
        level.actors[n] = baked
    for name in names:                               # PRODUCER: baked names to stdout (feed `| verb -`)
        print(name)
    print(f"baked {len(targets)} actor(s)", file=sys.stderr)
    src.save(verb="apply-transform",
             args={"names": names, "lock_textures": bool(args.lock_textures)},
             level=level, touched=names)
    return 0


def _replace(args, src) -> int:
    # In-place SHAPE SWAP: take ONLY the incoming PolyList; keep the target's Name, order_value
    # (CSG rank), Group, CsgOper, PolyFlags, Rotation, AND its old Location/PrePivot. The incoming
    # shape's own Location/PrePivot/Name are ignored (decisions 2026-07-18; supersedes `brush
    # resize`). `-` is the SOLE shape source (the `build → add -` T3D-snippet stdin convention).
    if args.shape != "-":
        print("brush replace: the shape argument must be `-` (read a T3D snippet from stdin, "
              "e.g. `brush build cube … | brush replace NAME -`)", file=sys.stderr)
        return 2
    text = sys.stdin.read()
    if not text.strip():
        return 0                                       # empty stdin: clean no-op, exit 0
    # parse_t3d_actors (NOT parse_t3d) + drop the transient builder brush, exactly like `actor
    # add -`. A generator brush carries an explicit CsgOper so it is NOT filtered.
    incoming = [a for a in parse_t3d_actors(text)
                if a.brush is not None and not is_builder_brush(a)]
    if not incoming:
        print("brush replace: no brush geometry found in the T3D input (nothing to swap in)",
              file=sys.stderr)
        return 2
    if len(incoming) > 1:
        print(f"brush replace: stdin has {len(incoming)} brush actors, expected exactly one "
              f"(a single-shape swap is unambiguous; pipe one `brush build <shape>`)",
              file=sys.stderr)
        return 2
    level = src.load()
    try:
        canonical = query.resolve_actor_name(level, args.name)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    target = level.actors[canonical]
    if target.brush is None:
        print(f"{canonical} is not a brush", file=sys.stderr)
        return 2
    # Swap the polys only — keep the target Brush object so its model_name stays `Model_<name>`
    # (matches the actor's `Brush=` prop) and every other actor field (Location/PrePivot/props)
    # is untouched. validate_brush rejects degenerate incoming geometry before the write.
    target.brush.polys = incoming[0].brush.polys
    validate_brush(target.brush)
    src.save(verb="replace", args={"name": canonical}, level=level, touched=[canonical])
    return 0
