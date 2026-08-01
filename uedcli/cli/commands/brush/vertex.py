"""`brush vertex list|move` — welded-corner query and move-only edit (add/delete are illegal: they
would break the closed solid). Pure, model-side (no editor).

`list` reads the trunk level the route resolved; `move` selects corners by world coordinate, moves
every poly-vertex sharing each, and writes the trunk back. This module uses the model-side
`emit`/`query`/`rotation`/`vertex` services and `cli.errors`; it never imports another command
family or the router.
"""
from __future__ import annotations

import sys

from ...errors import CommandError
from .... import emit, query, rotation
from ....geometry import validate_brush


def _num_coord_component(value):
    """A reported coordinate as a JSON number — `emit.num_coord` is the one definition, shared with
    `query.list_mover_keys`."""
    return emit.num_coord(value)


def run(args, src) -> int:
    """Route one `brush vertex` subverb against the trunk source the route already resolved."""
    if args.vsub == "list":
        return _list(args, src)
    if args.vsub == "move":
        return _move(args, src)
    raise CommandError(f"unimplemented brush vertex sub-verb: {args.vsub}")


def _list(args, src) -> int:
    level = src.load()
    try:
        canonical = query.resolve_actor_name(level, args.name)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        import json
        rows = []
        for r in query.list_vertices(level.actors[canonical]):
            # `clean` first: these are DERIVED world coords, so they carry the GMath rotator
            # noise. Without it `--json` reports 228.000006 where the text table and
            # `actor bbox --json` both report 228 — the machine-readable output being the noisy
            # one is exactly what rationale/reported-coordinates.md rejects.
            c = [emit.clean(v) for v in r["coord"]]
            rows.append({"coord": {"x": _num_coord_component(c[0]),
                                   "y": _num_coord_component(c[1]),
                                   "z": _num_coord_component(c[2])},
                         "polys": r["polys"], "nrefs": r["nrefs"]})
        print(json.dumps({"actor": canonical, "vertices": rows}, indent=2))
    else:
        print(query.format_vertices(level.actors[canonical], canonical))
    return 0


def _move(args, src) -> int:
    from .... import vertex as vertexmod
    level = src.load()
    try:
        canonical = query.resolve_actor_name(level, args.name)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    actor = level.actors[canonical]
    if actor.brush is None:
        print(f"{canonical} is not a brush", file=sys.stderr)
        return 2
    # --at/--to are world positions → local via `Rᵀ·(world − Location) + PrePivot` (the inverse
    # of `vertex list`'s forward transform, so a coord copied from there round-trips). --by is a
    # world delta → local via `Rᵀ·delta` (rotation only). For a rotated brush the corner match
    # relies on emit.clean snapping the float-inverted coord to its grid corner.
    local_at = [rotation.world_to_local_point(actor, at) for at in args.at]
    if args.to is not None:
        local_to = rotation.world_to_local_point(actor, args.to)
        actor.brush = vertexmod.move_vertices(actor.brush, local_at, to=local_to)
    else:
        actor.brush = vertexmod.move_vertices(
            actor.brush, local_at, by=rotation.world_to_local_delta(actor, args.by))
    validate_brush(actor.brush)
    rec_args = {"name": canonical, "at": [[str(c) for c in at] for at in args.at]}
    if args.to is not None:
        rec_args["to"] = [str(c) for c in args.to]
    else:
        rec_args["by"] = [str(c) for c in args.by]
    src.save(verb="vertex-move", args=rec_args,
                    level=level, touched=[canonical])
    return 0
