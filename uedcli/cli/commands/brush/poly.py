"""`brush poly list|set|pan|rotate|scale|move|find|align` — per-surface (polygon) query and edit.
Pure, model-side (no editor).

The query verbs read the trunk level the route resolved; the mutators transform it and write it
back. `set`/`pan`/`rotate`/`scale`/`align` print the faces they touched as `BRUSH:idx` selectors
(stdout) so a per-face pipe stays exact. This module uses `cli.resources`/`cli.targets` and the model-side
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
    if args.polysub == "move":
        return _move(args, src)
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
    to = getattr(args, "to", None)
    # `--to` needs a texture's pixel size; `--by` is pure math and stays project-independent.
    resolve_dims = resources.texture_dims_resolver(args) if to is not None else None
    level = src.load()
    try:
        touched = surface.apply_scale(level, targets, by=args.by, to=to, resolve_dims=resolve_dims)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    rec_args = {"targets": targets}
    if args.by is not None:
        rec_args["by"] = [str(c) for c in args.by]
    if to is not None:
        rec_args["to"] = [str(c) for c in to]
    src.save(verb="poly-scale", args=rec_args, level=level, touched=touched)
    return _print_poly_selectors(level, targets, touched, "scaled")


def _move(args, src) -> int:
    from .... import surface
    targets = target_names.resolve_target_names(args.targets)
    if not targets:
        return 0
    level = src.load()
    try:
        touched = surface.apply_move(level, targets, by=args.by)
    except ValueError as e:                          # incl. GeometryError (a non-planar neighbour)
        print(str(e), file=sys.stderr)
        return 2
    src.save(verb="poly-move", args={"targets": targets, "by": [str(c) for c in args.by]},
             level=level, touched=touched)
    return _print_poly_selectors(level, targets, touched, "moved")


def _find(args, src) -> int:
    from .... import facing_spec, polyalign
    try:
        spec = facing_spec.parse_facing_spec(args.facing) if args.facing is not None else None
    except ValueError as e:
        print(str(e), file=sys.stderr)                # malformed --facing → clean exit 2, naming it
        return 2
    raw = target_names.resolve_target_names(args.names)   # `-` → stdin (bare names or BRUSH:idx lines)
    if not raw:
        return 0                                      # empty stdin / no targets: clean no-op
    level = src.load()
    brushes: list[str] = []
    seen: set[str] = set()
    for tok in raw:
        bname = tok.split(":", 1)[0]                  # accept a BRUSH:idx line — the :idx is irrelevant here
        try:
            canonical = query.resolve_actor_name(level, bname)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)         # unknown name → hard error (a typo must not pass)
            return 2
        if canonical not in seen:                     # dedup on canonical, first-seen order
            seen.add(canonical)
            brushes.append(canonical)
    use_json = getattr(args, "json", False)
    rows: list[dict] = []
    lines: list[str] = []
    matched = 0
    for canonical in brushes:
        actor = level.actors[canonical]
        if actor.brush is None:                       # non-brush: WARN and skip, don't fail the run
            print(f"skipping non-brush actor: {canonical}", file=sys.stderr)
            continue
        try:
            idxs = polyalign.find_faces(actor, canonical, item=args.item,
                                        facing=spec, texture=args.texture)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        matched += len(idxs)
        for i in idxs:
            if use_json:
                p = actor.brush.polys[i]
                vn = query.visible_normal(actor, p)
                live = any(vn)
                rows.append({"brush": canonical, "poly": i, "item": p.item,
                             "normal": [round(c, 4) for c in vn] if live else None,
                             "orientation": facing_spec.orientation(vn) if live else None,
                             "role": facing_spec.role(vn) if live else None,
                             "texture": p.texture})
            else:
                lines.append(f"{canonical}:{i}")
    if use_json:
        import json
        print(json.dumps(rows, indent=2))
    else:
        for ln in lines:
            print(ln)
    print(f"{matched} face(s) matched", file=sys.stderr)
    return 0


def _align(args, src) -> int:
    from .... import polyalign
    mode = args.align_mode
    tokens = target_names.resolve_target_names(args.targets)     # `-` → stdin (bare names or BRUSH:idx lines)
    if not tokens:
        return 0                                      # empty stdin / no targets: clean no-op
    fit_perimeter = getattr(args, "fit_perimeter", False)        # run-only; absent on wall/floor
    turn = getattr(args, "turn", 0)                              # run-only
    # `one-tile` always needs a texture's pixel size; `run` only under --fit-perimeter — wall/floor
    # and a plain `run` stay project-independent. Built before loading the level: a missing project
    # exits 2 via `package_path_or_exit`'s own message, matching every author-time validation site.
    needs_dims = mode == "one-tile" or (mode == "run" and fit_perimeter)
    resolve_dims = resources.texture_dims_resolver(args) if needs_dims else None
    level = src.load()
    try:
        touched = polyalign.align(level, tokens, mode, turn=turn, fit_perimeter=fit_perimeter,
                                  resolve_dims=resolve_dims)
        pairs = polyalign.resolve_align_targets(level, tokens)   # the exact aligned face set
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if not touched:
        return 0
    # Ruling 2: a per-face verb prints the BRUSH:idx selectors it acted on (stdout), not touched
    # brush names — so `align` chains into another per-face verb without silently widening the set.
    for brush_name, idx in pairs:
        print(f"{brush_name}:{idx}")
    print(f"aligned {len(pairs)} face(s) across {len(touched)} brush(es) ({mode})", file=sys.stderr)
    rec_args: dict = {"mode": mode}
    if turn:
        rec_args["turn"] = turn
    if fit_perimeter:
        rec_args["fit_perimeter"] = True
    src.save(verb="poly-align", args=rec_args, level=level, touched=touched)
    return 0
