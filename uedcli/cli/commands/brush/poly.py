"""`brush poly list|set|pan|rotate|scale|find|align` — per-surface (polygon) query and edit. Pure,
model-side (no editor).

The query verbs read the trunk level the route resolved; the mutators transform it and write it
back. `set`/`pan`/`rotate`/`scale` print the faces they touched as `BRUSH:idx` selectors (stdout) so
a per-face pipe stays exact. This module uses `cli.resources`/`cli.targets` and the model-side
`surface`/`polyalign`/`query`/`utexture` services; it never imports another command family or the
router.
"""
from __future__ import annotations

import sys

from ... import resources
from ... import targets as target_names
from ...errors import CommandError
from .... import query


def _print_poly_selectors(level, targets: list[str], touched: list[str], past_tense: str) -> int:
    """The stdout/stderr contract shared by every PER-FACE mutator (`brush poly set|pan|rotate|
    scale`): the faces it touched go to **stdout** as `BRUSH:idx` selectors, one per line, and a
    human summary to **stderr** so a pipe stays clean.

    Per-FACE selectors, not touched brush NAMES: a bare brush name means *all* of that brush's
    polys, so piping one into a second per-face verb would silently widen the set from the three
    faces that were edited to the brush's twelve. The pairs come from `surface.resolve_targets` —
    the same resolution the mutator itself used, so the printed set is exactly the mutated set,
    canonically cased, expanded and deduped (`wall:all` in, `Wall:0 … Wall:5` out). Echoing the
    caller's own tokens back would fail all three of those.

    `touched` stays the brush-name list the model returns: that is the session-store `save(touched=…)`
    currency, where widening to a whole brush is harmless. Returns 0, so a caller can `return` it."""
    from .... import surface
    pairs = surface.resolve_targets(level, targets)
    for brush_name, idx in pairs:
        print(f"{brush_name}:{idx}")
    print(f"{past_tense} {len(pairs)} face(s) across {len(touched)} brush(es)", file=sys.stderr)
    return 0


def _validate_texture_ref(ref: str, args) -> None:
    """Existence-validate a single texture ref (for `brush poly set --texture`), exit 2 (clean) if
    it names no Texture on the path or the path is empty."""
    if ref is None:
        return
    _project, _user_config, files = resources.package_path_or_exit(args)
    from .... import utexture
    if not utexture.TextureResolver(files).exists(ref):
        raise CommandError(f"texture not found: {ref} — no Texture of that name on the package "
                             f"path (author-time validation)")


def run(args, src) -> int:
    """Route one `brush poly` subverb against the trunk source the route already resolved."""
    if args.polysub == "list":
        return _list(args, src)
    if args.polysub == "set":
        return _set(args, src)
    if args.polysub == "pan":
        return _pan(args, src)
    if args.polysub == "rotate":
        return _rotate(args, src)
    if args.polysub == "scale":
        return _scale(args, src)
    if args.polysub == "find":
        return _find(args, src)
    if args.polysub == "align":
        return _align(args, src)
    raise CommandError(f"unimplemented brush poly sub-verb: {args.polysub}")


def _list(args, src) -> int:
    level = src.load()
    try:
        canonical = query.resolve_actor_name(level, args.name)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        import json
        print(json.dumps({"actor": canonical,
                          "polys": query.list_polys(level.actors[canonical])}, indent=2))
    else:
        print(query.format_polys(level.actors[canonical], canonical))
    return 0


def _set(args, src) -> int:
    from .... import surface
    targets = target_names.resolve_target_names(args.targets)    # `-` → stdin (BRUSH:idx lines from poly find)
    if not targets:
        return 0                                      # empty stdin / no targets: clean no-op
    _validate_texture_ref(args.texture, args)       # author-time: reject a fabricated ref
    level = src.load()
    try:
        touched = surface.apply_surface_edit(
            level, targets, texture_ref=args.texture,
            add_flags=args.add_flags, remove_flags=args.remove_flags)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    rec_args: dict = {"targets": targets}
    if args.texture is not None:
        rec_args["texture"] = args.texture
    if args.add_flags:
        rec_args["add_flags"] = args.add_flags
    if args.remove_flags:
        rec_args["remove_flags"] = args.remove_flags
    src.save(verb="poly-set", args=rec_args, level=level, touched=touched)
    return _print_poly_selectors(level, targets, touched, "set")


def _pan(args, src) -> int:
    from .... import surface
    targets = target_names.resolve_target_names(args.targets)
    if not targets:
        return 0
    level = src.load()
    try:
        touched = surface.apply_pan(level, targets, pan_to=args.pan_to, pan_by=args.pan_by)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    rec_args = {"targets": targets}
    if args.pan_to is not None:
        rec_args["pan_to"] = [str(c) for c in args.pan_to]
    if args.pan_by is not None:
        rec_args["pan_by"] = [str(c) for c in args.pan_by]
    src.save(verb="poly-pan", args=rec_args, level=level, touched=touched)
    return _print_poly_selectors(level, targets, touched, "panned")


def _rotate(args, src) -> int:
    from .... import surface
    targets = target_names.resolve_target_names(args.targets)
    if not targets:
        return 0
    level = src.load()
    try:
        touched = surface.apply_rotate(level, targets, by_uu=args.by)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    src.save(verb="poly-rotate", args={"targets": targets, "by": str(args.by)},
             level=level, touched=touched)
    return _print_poly_selectors(level, targets, touched, "rotated")


def _scale(args, src) -> int:
    from .... import surface
    targets = target_names.resolve_target_names(args.targets)
    if not targets:
        return 0
    level = src.load()
    try:
        touched = surface.apply_scale(level, targets, by=args.by)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    src.save(verb="poly-scale", args={"targets": targets, "by": [str(c) for c in args.by]},
             level=level, touched=touched)
    return _print_poly_selectors(level, targets, touched, "scaled")


def _find(args, src) -> int:
    from .... import polyalign
    facing = getattr(args, "facing", None)
    valid_facing = {"+X", "-X", "+Y", "-Y", "+Z", "-Z", "slant"}
    if facing is not None and facing not in valid_facing:
        print(f"brush poly find --facing: invalid value {facing!r} "
              f"(expected one of {', '.join(sorted(valid_facing))})", file=sys.stderr)
        return 2
    level = src.load()
    try:
        canonical = query.resolve_actor_name(level, args.name)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    actor = level.actors[canonical]
    try:
        idxs = polyalign.find_faces(actor, canonical, item=args.item,
                                    facing=facing, texture=args.texture)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        import json
        rows = []
        for i in idxs:
            p = actor.brush.polys[i]
            wv = polyalign._world_verts(actor, p)
            rows.append({"brush": canonical, "poly": i, "item": p.item,
                         "facing": query._poly_facing(wv) if len(wv) >= 3 else None,
                         "texture": p.texture})
        print(json.dumps(rows, indent=2))
    else:
        for i in idxs:
            print(f"{canonical}:{i}")
    print(f"{len(idxs)} face(s) matched", file=sys.stderr)
    return 0


def _align(args, src) -> int:
    from .... import polyalign
    tokens = target_names.resolve_target_names(args.targets)     # `-` → stdin (bare names or BRUSH:idx lines)
    if not tokens:
        return 0                                      # empty stdin / no targets: clean no-op
    level = src.load()
    try:
        touched = polyalign.align(level, tokens, args.mode,
                                  fresh_frame=args.fresh_frame,
                                  fit_perimeter=args.fit_perimeter)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if not touched:
        return 0
    for name in touched:
        print(name)
    print(f"aligned {len(tokens)} face target(s) across {len(touched)} brush(es) "
          f"({args.mode})", file=sys.stderr)
    src.save(verb="poly-align", args={"mode": args.mode}, level=level, touched=touched)
    return 0
