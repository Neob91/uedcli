"""`brush relation measure|find|set` — cross-brush geometric relationships (plane, footprint,
deltas). `measure`/`find` are pure queries (no mutation); `set` translates a brush's Location.
Model-side, no editor. See dev/docs/superpowers/specs/2026-09-05-brush-relation-family-design.md."""
import sys
from decimal import Decimal

from ...targets import resolve_target_names
from ...errors import CommandError
from .... import query, relation


def run(args, src) -> int:
    if args.relationsub == "measure":
        return _measure(args, src)
    if args.relationsub == "find":
        return _find(args, src)
    if args.relationsub == "set":
        return _set(args, src)
    raise CommandError(f"unimplemented brush relation sub-verb: {args.relationsub}")


def _measure(args, src) -> int:
    top = None if args.top == "all" else args.top
    level = src.load()
    try:
        report = relation.compute_pair(level, args.ref, args.target,
                                        top=top, allow_self=args.allow_self)
    except relation.RelationError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(relation.format_report(report))
    return 0


def _default_candidates(level, ref_name: str, allow_self: bool) -> list:
    return sorted(
        name for name, actor in level.actors.items()
        if actor.brush is not None and (allow_self or name != ref_name)
    )


def _find(args, src) -> int:
    top = None if args.top == "all" else args.top
    level = src.load()
    try:
        ref_name, _, _ = relation._resolve_measure_selector(level, args.relative_to)
    except relation.RelationError as e:
        print(str(e), file=sys.stderr)
        return 2

    if not args.candidates:                            # no names, no '-': every other brush
        candidate_names = _default_candidates(level, ref_name, args.allow_self)
    else:
        raw = resolve_target_names(args.candidates)     # `-` → stdin
        if not raw:
            return 0                                    # '-' with empty stdin: clean no-op
        candidate_names = []
        seen: set = set()
        for tok in raw:
            bname = tok.split(":", 1)[0]
            try:
                canonical = query.resolve_actor_name(level, bname)
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            if canonical == ref_name and not args.allow_self:
                print(f"brush relation find: candidate {canonical!r} is the reference's own "
                      f"brush — pass --allow-self to include it", file=sys.stderr)
                return 2
            actor = level.actors[canonical]
            if actor.brush is None:
                print(f"skipping non-brush actor: {canonical}", file=sys.stderr)
                continue
            if canonical not in seen:
                seen.add(canonical)
                candidate_names.append(canonical)

    try:
        matches = relation.find_candidates(
            level, args.relative_to, candidate_names,
            max_gap=args.max_gap, min_gap=args.min_gap,
            footprint=args.footprint, plane=args.plane, top=top,
        )
    except relation.RelationError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.json:
        import json
        rows = [{
            "ref": m.pair.brush_a, "ref_poly": m.pair.poly_a,
            "candidate": m.candidate, "poly": m.poly,
            "plane": m.pair.plane.plane,
            "normal_ref": list(m.pair.plane.normal_a),
            "normal_candidate": list(m.pair.plane.normal_b),
            "distance": m.pair.plane.distance,
            "footprint_2d": m.pair.footprint_2d,
            "deltas": {"centroid_u": m.pair.deltas.centroid_u, "centroid_v": m.pair.deltas.centroid_v,
                       "edge_u_label": m.pair.deltas.edge_u_label, "edge_u": m.pair.deltas.edge_u,
                       "edge_v_label": m.pair.deltas.edge_v_label, "edge_v": m.pair.deltas.edge_v},
        } for m in matches]
        print(json.dumps(rows, indent=2))
    else:
        for m in matches:
            print(f"{m.candidate}:{m.poly}")
        for m in matches:
            print(f"{m.pair.brush_a}:{m.pair.poly_a} <-> {m.candidate}:{m.poly}  "
                  f"plane={m.pair.plane.plane} "
                  f"gap={relation._fmt(abs(m.pair.plane.distance))} "
                  f"footprint={m.pair.footprint_2d}", file=sys.stderr)
    return 0


def _set(args, src) -> int:
    raw = list(dict.fromkeys(resolve_target_names(args.target)))   # dedup exact repeats
    if not raw:
        return 0                                        # '-' with empty stdin: clean no-op
    level = src.load()
    edge_u = None
    if args.edge_u_min is not None:
        edge_u = ("min", args.edge_u_min)
    elif args.edge_u_max is not None:
        edge_u = ("max", args.edge_u_max)
    edge_v = None
    if args.edge_v_min is not None:
        edge_v = ("min", args.edge_v_min)
    elif args.edge_v_max is not None:
        edge_v = ("max", args.edge_v_max)

    # Pass 1: resolve + compute every target's move, no mutation, no printing -- a bad target
    # anywhere in the set leaves nothing mutated/saved/printed (all-or-nothing, matching
    # surface.apply_move/apply_rotate's pre-pass convention).
    planned = []
    seen_targets: set = set()
    for target_token in raw:
        try:
            target_name, ref_name, move = relation.compute_set_translation(
                level, target_token, args.relative_to,
                gap=args.gap, centroid_u=args.centroid_u, centroid_v=args.centroid_v,
                edge_u=edge_u, edge_v=edge_v,
            )
        except relation.RelationError as e:
            print(str(e), file=sys.stderr)
            return 2
        if target_name in seen_targets:
            print(f"brush relation set: target brush {target_name!r} named by more than one "
                  f"token — each move is computed against its original position, so applying "
                  f"both would silently compound", file=sys.stderr)
            return 2
        seen_targets.add(target_name)
        planned.append((target_name, move))

    # Pass 2: every target validated -- mutate, save once, then print.
    touched = []
    for target_name, move in planned:
        actor = level.actors[target_name]
        loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
        actor.location = tuple(loc[i] + Decimal(str(move[i])) for i in range(3))
        if target_name not in touched:
            touched.append(target_name)
    src.save(verb="relation-set", args={"target": raw, "relative_to": args.relative_to},
             level=level, touched=touched)
    for target_name in touched:
        print(target_name)
    print(f"moved {len(touched)} brush(es) relative to {args.relative_to}", file=sys.stderr)
    return 0
