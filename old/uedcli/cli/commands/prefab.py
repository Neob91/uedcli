"""`prefab` command family — the durable tier-2 library.

`cli.dispatch` enters through `run(args)`. Reads (list/show/diagram/drop) touch only the tracked
prefab dir; `apply` resolves the selected trunk level and reuses `cli.placement.apply_set`. Every
subverb that takes a member name validates that name (`stashlib.validate_member_name`) before ANY
filesystem touch, so a `../../x` name cannot escape the library root. This module uses the shared
`cli.placement` and `cli.rendering` orchestrators and `stashlib`; it never imports another command
family or the router.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .. import level_sources, placement, rendering, resources
from ..errors import CommandError
from ... import stashlib
from ...model import parse_t3d


def read_or_exit(root, name: str):
    """Read a prefab, converting a missing name, an OLD-format prefab, or a corrupt sidecar into a
    clean exit 2 instead of a traceback. Returns (full, order, packages, meta, folders). Callers must
    already have validated the name grammar (`validate_member_name`)."""
    if name not in stashlib.list_prefabs(root):
        raise CommandError(f"prefab not found: {name!r}")
    try:
        return stashlib.read_prefab(root, name)
    except stashlib.OldFormatPrefab as e:               # HARD CUTOVER: actionable, never a traceback
        raise CommandError(str(e))
    except (OSError, ValueError) as e:                  # corrupt/unreadable per-actor tree or sidecar
        raise CommandError(f"cannot read prefab {name!r}: {e}")


def run(args) -> int:
    """The durable tier-2 library. Reads (list/show/diagram/drop) touch only the tracked dir;
    apply resolves the selected trunk level and reuses `placement.apply_set`."""
    root = resources.prefab_root(args)
    # M1: validate the name before ANY filesystem touch (read OR the drop unlink) so a
    # `../../x` name can't escape the library root. validate_member_name raises ValueError;
    # surface it as a clean exit-2, not a traceback.
    if getattr(args, "name", None) is not None:
        try:
            stashlib.validate_member_name(args.name)
        except ValueError as e:
            raise CommandError(str(e))
    if args.sub == "list":
        for name in stashlib.list_prefabs(root):
            print(name)
        return 0
    if args.sub == "show":
        actors_t3d, order, _pkgs, _meta, _folders = read_or_exit(root, args.name)
        chosen = args.names or order
        if args.summary:
            level = parse_t3d("Begin Map\n" + "\n".join(actors_t3d[n] for n in chosen
                                                        if n in actors_t3d) + "\nEnd Map\n")
            print(stashlib.format_summary(args.name, [level.actors[n] for n in chosen
                                                     if n in level.actors]))
        else:
            print("\n".join(actors_t3d[n] for n in chosen if n in actors_t3d))
        return 0
    if args.sub == "diagram":
        return preview(args, root)
    if args.sub == "drop":
        # A NEW prefab is a DIR `<name>/`; also unlink any OLD-format `<name>.t3d`/`.json` so a stale
        # pre-cutover prefab can still be dropped.
        dest = root / args.name
        if dest.is_dir():
            shutil.rmtree(dest)
        (root / f"{args.name}.t3d").unlink(missing_ok=True)
        (root / f"{args.name}.json").unlink(missing_ok=True)
        return 0
    if args.sub == "apply":
        level_src = level_sources.resolve_level_source(args)         # the trunk level (no project ⇒ clean exit 2)
        actors_t3d, order, packages, _meta, folders = read_or_exit(root, args.name)
        # Prefab apply defaults to the ORIGIN (anchor=0), not the prefab's captured world bbox-min:
        # a shared prefab's original coords are meaningful only in its capture level, so without
        # --at it lands at the world origin. (stash apply keeps the captured anchor — paste-it-back
        # within the same level is the common case there.)
        return placement.apply_set(args, level_src, actors_t3d, order, packages,
                          default_group=Path(args.name).name,           # basename, never slashed path
                          anchor=["0", "0", "0"], folders=folders)
    raise CommandError(f"unimplemented prefab sub-verb: {args.sub}")


def preview(args, root) -> int:
    """`prefab diagram <name> [names…]` — render a stored prefab's actors. `run` has already
    validated the member name; this reads the prefab and hands its actors to the shared renderer."""
    actors_t3d, order, _pkgs, _meta, _folders = read_or_exit(root, args.name)
    return rendering.render_actors_to_out(
        rendering.brush_actors_from(actors_t3d, order, args.names, brushes_only=False), args)
