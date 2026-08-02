"""`stash` command family — the tier-1 capture register (`<root>/.uedcli/stash/`).

`cli.dispatch` enters through `run(args)`, which resolves the project-scoped register and routes the
subverb (capture/list/show/drop/apply/promote/preview). Every read validates the stash's existence
before touching its contents, and `preview` reads only after the existence gate — the prologue order
is unchanged from the transitional monolith. This module uses the shared `cli.ingest`,
`cli.placement`, `cli.rendering` and `cli.level_sources` orchestrators; it never imports another
command family or the router.
"""
from __future__ import annotations

import time

from .. import ingest, level_sources, placement, rendering, resources
from ..errors import CommandError
from ... import stash_register, trunk
from ...model import parse_t3d, parse_t3d_actors
from ...normalize import normalize_actor, canonical_actor_t3d, is_builder_brush


def run(args) -> int:
    """Route one `stash` invocation: resolve the project's register, then dispatch the subverb."""
    return _dispatch_stash(args, _resolve_stash_register(args))


def _resolve_stash_register(args) -> "stash_register.FileStashRegister":
    """The stash register for the resolved project (`<root>/.uedcli/stash/`). Exposes
    `write_stash`/`read_stash`/`list_stashes`/`drop_stash` for `_dispatch_stash`."""
    return stash_register.for_project(resources.resolve_project(args))   # raises ProjectError → exit 2


def _capture_from_t3d(text: str, names: list[str], *, index, validate=None,
                      folders: dict[str, str | None] | None = None
                      ) -> tuple[dict, list[str], list, set[str], dict[str, str | None]]:
    """Parse T3D, drop the builder brush, optionally subset by name (a FILTER over source order,
    never a reorder), normalize to bbox-min. Returns (full{name:canonical_t3d}, order, anchor,
    texture_packages, folders{name:folder|None}). `validate(actors)` (if given) runs on the chosen
    set BEFORE serialization — the author-time ingest gate for an EXTERNAL T3D source (it may qualify
    bare classes in place, so it must run before `canonical_actor_t3d` freezes the stored form).

    `folders` is the SOURCE per-name folder map (trunk capture supplies each actor's stored folder;
    an external T3D source has none → all None). Because a T3D blob carries no folder (folder is a
    uedcli-side sidecar), it must be threaded separately (dev/docs/direction/trunk-and-editor.md 2026-07-18 addendum, sub-choice
    2 — persist folder per member). Trunk actor names are unique so the map keys survive uniquify; an
    external source's None-folders are unaffected by the (dup-only) rename below.

    `index` is the `classindex.ClassIndex` the mover canonicalization gate resolves against
    (`movers.is_mover` is schema-aware since 2026-07-25), so capture needs the game's `.u`
    packages like every other mover-aware verb."""
    from ... import stashlib
    from ...movers import canonicalize_mover
    # parse_t3d_actors (NOT parse_t3d): user-concatenated T3D may share a Name; the Name-keyed dict
    # would drop all-but-last. Keep an ordered list, drop builder brushes, strip computed props.
    candidates = [a for a in parse_t3d_actors(text) if not is_builder_brush(a)]
    for a in candidates:
        normalize_actor(a)
        # Canonicalize an ingested Mover to KeyNum=0 (spec §3): the unified T3D-tree read path no
        # longer canonicalizes movers on read (the retired `tree_io` did), so a captured EXTERNAL
        # mover at KeyNum!=0 must be folded to base pose HERE or it would round-trip non-canonical.
        canonicalize_mover(a, index)
    # Filter by the `names` subset FIRST, against the RAW source Names, THEN uniquify only the chosen
    # set. (Uniquifying first would suffix a duplicate the user explicitly asked for, so a bare-Name
    # filter would then match only the first — silently re-dropping the rest.)
    requested = set(names)
    missing = requested - {a.name for a in candidates}
    if missing:
        raise CommandError(f"actors not found in source: {', '.join(sorted(missing))}")
    chosen = [a for a in candidates if not requested or a.name in requested]
    if not chosen:
        raise CommandError("capture source has no actors")
    # Uniquify duplicate Names in source order: first occurrence keeps its bare Name, each later
    # collision gets a `<stem>_<rand>` suffix — so none is silently dropped when keyed below.
    seen: set[str] = set()
    for a in chosen:
        if a.name in seen:
            a.name = trunk.alloc_name(a.name.rstrip("0123456789") or a.name, seen)
        seen.add(a.name)
    shifted, anchor = stashlib.normalize_for_capture(chosen)
    if validate is not None:
        validate(shifted)                                # qualify/validate before freezing the T3D
    full = {a.name: canonical_actor_t3d(a) for a in shifted}
    src_folders = folders or {}
    out_folders = {a.name: src_folders.get(a.name) for a in shifted}
    return (full, [a.name for a in shifted], list(anchor),
            stashlib.referenced_packages(shifted), out_folders)


def _auto_slug(reg, order: list[str]) -> str:
    """Collision-resistant: first actor name lowercased, with a -N suffix if taken."""
    base = order[0].lower() if order else "stash"
    existing = set(reg.list_stashes())
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


def _dispatch_stash(args, reg) -> int:
    if args.sub == "capture":
        # `--tree` names the SOURCE box (explicit alternative to the ambient $UEDCLI_LEVEL); it is
        # only consulted in the trunk branch below, so combining it with an explicit --from-* source
        # would silently ignore one — reject that up front instead of guessing.
        if getattr(args, "tree", None) and args.from_t3d:
            raise CommandError("--tree names the capture SOURCE box; it cannot be combined with "
                                 "--from-t3d")
        # Validate only an EXTERNAL T3D source; capturing from the trunk is already qualified/valid.
        validate = None
        src_folders: dict[str, str | None] = {}          # per-member folders (trunk parity); external → none
        if args.from_t3d:
            text = ingest.read_t3d_files(args.from_t3d)         # <FILE…|-> (multiple concatenate; `-` = stdin)
            validate = lambda actors: ingest.validate_ingest_actors(actors, args)
        else:
            # trunk default = the ambient $UEDCLI_LEVEL (no package manifest; the load set derives at
            # build). Announce which level we captured FROM when it came from the env (visibility guard
            # against a stale export — decisions 2026-07-20); silent with an explicit --tree.
            from ...emit import emit_map
            cap_src = level_sources.resolve_level_source(args)
            if getattr(cap_src, "from_env", False):
                level_sources.announce_env_level(cap_src.display_name, action="capturing from")
            level = cap_src.load()
            # Capture each source actor's stored folder so the stash persists it (a T3D blob can't
            # carry it, so it rides the separate folder channel, decisions 2026-07-18 sub-choice 2).
            src_folders = {n: level.actors[n].folder for n in level.order if n in level.actors}
            text = emit_map([level.actors[n] for n in level.order if n in level.actors])
        full, order, anchor, tex_pkgs, folders = _capture_from_t3d(
            text, args.names, index=resources.mover_index(args, "stash capture"),
            validate=validate, folders=src_folders)
        packages = sorted(tex_pkgs)
        sid = args.id or _auto_slug(reg, order)
        try:
            reg.write_stash(sid, full_level=full, order=order, packages=packages, folders=folders,
                            force=getattr(args, "force", False),
                            meta={"anchor": [str(c) for c in anchor], "ts": int(time.time() * 1000)})
        except (FileExistsError, ValueError) as e:
            raise CommandError(str(e))
        print(sid)
        return 0
    return _dispatch_stash_reads(args, reg)


def _dispatch_stash_reads(args, reg) -> int:
    from ... import stashlib
    if args.sub == "list":
        for sid in reg.list_stashes():
            print(sid)
        return 0
    # Every remaining verb takes an id. An unknown id reads back as empties (register design), which
    # would silently no-op (show/preview) or promote nothing — so validate up front. `reg.exists`
    # keys on `meta.json` (resolves NESTED ids, and stays true for an emptied stash — `--target`
    # editing can delete a stash to zero actors, which content-emptiness can't distinguish from
    # missing). `drop` stays idempotent (a no-op on a missing id, like `rm -f`).
    if args.sub != "drop" and not reg.exists(args.id):
        raise CommandError(f"stash not found: {args.id!r}")
    if args.sub != "drop":
        try:                                             # corrupt meta.json/state → clean, not a traceback
            reg.read_stash(args.id)
        except (OSError, ValueError) as e:
            raise CommandError(f"cannot read stash {args.id!r}: {e}")
    if args.sub == "drop":
        reg.drop_stash(args.id)
        return 0
    if args.sub == "show":
        actors_t3d, order, _pkgs, _meta, _folders = reg.read_stash(args.id)
        chosen = args.names or order
        if args.summary:
            level = parse_t3d("Begin Map\n" + "\n".join(actors_t3d[n] for n in chosen
                                                         if n in actors_t3d) + "\nEnd Map\n")
            print(stashlib.format_summary(args.id, [level.actors[n] for n in chosen
                                                    if n in level.actors]))
        else:
            print("\n".join(actors_t3d[n] for n in chosen if n in actors_t3d))
        return 0
    if args.sub == "preview":
        return preview(args, reg)
    if args.sub == "apply":
        actors_t3d, order, pkgs, meta, folders = reg.read_stash(args.id)
        return placement.apply_set(args, level_sources.resolve_level_source(args), actors_t3d, order, pkgs,
                          default_group=args.id, anchor=meta.get("anchor", ["0", "0", "0"]),
                          folders=folders)
    if args.sub == "promote":
        return _promote_stash(args, reg)              # Task 15
    raise CommandError(f"unimplemented stash sub-verb: {args.sub}")


def _promote_stash(args, reg) -> int:
    # No class/texture re-validation here: promote copies an already-validated stash blob-for-blob to
    # the prefab library, and the prefab is itself gated by `ingest.validate_ingest_actors` when it is
    # `prefab apply`'d into a trunk — so nothing unvalidated can reach a trunk. Re-parsing the set
    # here just to re-check a validated set would be pure waste (spec: "may be dropped as redundant").
    from ... import stashlib
    root = resources.prefab_root(args)
    actors_t3d, order, packages, meta, folders = reg.read_stash(args.id)
    try:
        stashlib.write_prefab(root, args.as_name, full_level=actors_t3d, order=order,
                              packages=packages, meta=meta, folders=folders, force=args.force)
    except (FileExistsError, ValueError) as e:
        raise CommandError(str(e))
    return 0


def preview(args, reg) -> int:
    """`stash preview <id> [names…]` — render a captured set's actors. `run` has already resolved
    `reg` and (via the read prologue) validated that the id exists; this reads the stash and hands
    its actors to the shared renderer."""
    actors_t3d, order, _pkgs, _meta, _folders = reg.read_stash(args.id)
    return rendering.render_actors_to_out(
        rendering.brush_actors_from(actors_t3d, order, args.names, brushes_only=False), args)
