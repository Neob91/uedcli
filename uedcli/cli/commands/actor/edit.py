"""Actor mutating verbs: `add`, `duplicate`, `order`, `delete`, `move`, `rotate`. Pure, model-side
(no editor; design D-F).

Each verb resolves the trunk level source (honouring `--tree` / `$UEDCLI_LEVEL`), transforms the
in-memory model, and writes the trunk back. The source-free trunk-only surface guards (folder/label/
order rejection of `--tree stash|prefab`) run in `routes.py` before this module resolves anything;
the CARRIER-based rejection inside `_ingest_actor_t3d` (a `// uedcli-folder:`/`// uedcli-labels:`
comment in ingested T3D) is a distinct post-parse check with its own local copies of those two
guards. This module uses `cli.level_sources`/`cli.resources`/`cli.ingest`/`cli.targets` and the
model-side services; it never imports another command family or the router.
"""
from __future__ import annotations

import sys
from decimal import Decimal

from ... import ingest, level_sources, resources
from ... import targets as target_names
from ...errors import CommandError
from .... import (emit, folderlib, labellib, order_ops, query, rotation, stashlib,
                  t3dtree, trunk, writes)
from ....geometry import validate_brush
from ....model import parse_t3d_actors
from ....normalize import is_builder_brush
from ....order_ops import order_after_add, order_after_delete


def run(args) -> int:
    """Route one actor mutating verb. Resolves the trunk level source first (no project ⇒ clean
    exit 2), then runs the requested subverb."""
    src = level_sources.resolve_level_source(args)
    if args.sub == "move":
        return _move(args, src)
    if args.sub == "order":
        return _order(args, src)
    if args.sub == "delete":
        return _delete(args, src)
    if args.sub == "add":
        return _add(args, src)
    if args.sub == "duplicate":
        return _duplicate(args, src)
    if args.sub == "rotate":
        return _rotate(args, src)
    raise CommandError(f"unimplemented actor edit sub-verb: {args.sub}")


def _move(args, src) -> int:
    """`actor move <name> (--to|--by)` — set or shift one actor's Location. PRODUCER: the moved name
    to stdout."""
    level = src.load()
    try:
        canonical = query.resolve_actor_name(level, args.name)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    a = level.actors[canonical]
    loc = a.location or (Decimal(0), Decimal(0), Decimal(0))
    record_args = {"name": canonical}
    if args.to is not None:
        a.location = tuple(args.to)
        record_args["to"] = [str(c) for c in args.to]
    elif args.by is not None:
        a.location = tuple(loc[i] + args.by[i] for i in range(3))
        record_args["by"] = [str(c) for c in args.by]
    src.save(verb="move", args=record_args, level=level, touched=[canonical])
    print(canonical)                                 # PRODUCER: moved name → stdout (feed `| verb -`)
    print(f"moved {canonical}", file=sys.stderr)
    return 0


def _order(args, src) -> int:
    """`actor order <names…|-> (--first|--last|--before N|--after N)` — reorder existing actors' CSG
    precedence by minting new order_values (spec 2026-07-18). Trunk-only (guarded pre-resolve)."""
    raw = target_names.resolve_target_names(args.names)          # `-` → names from stdin (spec §7)
    if not raw:
        return 0                                      # empty stdin: no-op, exit 0
    level = src.load()
    try:
        resolved = query.resolve_actor_names(level, raw)
    except KeyError as e:                            # unknown moved actor → exit 2 (all-or-nothing)
        print(e.args[0], file=sys.stderr)
        return 2
    moved = list(dict.fromkeys(resolved))            # dedupe on CANONICAL names, order-preserving
    if args.first:
        selector, ref = "first", None
    elif args.last:
        selector, ref = "last", None
    elif args.before is not None:
        selector, ref = "before", args.before
    else:
        selector, ref = "after", args.after
    if ref is not None:
        try:
            ref = query.resolve_actor_name(level, ref)   # --before/--after NAME must exist
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        if ref in set(moved):                        # ordering relative to self is undefined
            raise CommandError(
                f"actor order: cannot order relative to {ref} — it is in the moved set")
    try:                                             # src._ranks: the load-snapshot order_values
        override = order_ops.compute_reorder_ranks(src._ranks, moved, selector, ref)
    except ValueError as e:                          # adjacent/duplicate imported ranks — no gap
        raise CommandError(f"cannot reorder: {e}")
    src.save(verb="order", args={"names": moved, "selector": selector, "ref": ref},
             level=level, touched=moved, ranks=override)
    for name in moved:                               # PRODUCER: reordered names to stdout (feed `| verb -`)
        print(name)
    print(f"reordered {len(moved)} actor(s)", file=sys.stderr)
    return 0


def _delete(args, src) -> int:
    """`actor delete <names…|->` — remove actors and repair `order`. PRODUCER: deleted names to
    stdout."""
    raw = target_names.resolve_target_names(args.names)          # `-` → names from stdin (spec §8)
    if not raw:
        return 0                                      # empty stdin: no-op, exit 0
    level = src.load()
    try:
        resolved = query.resolve_actor_names(level, raw)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    # Dedupe on CANONICAL names (order-preserving): two differently-cased piped tokens are the
    # SAME actor, and a second `pop` would raise KeyError (spec §8).
    names = list(dict.fromkeys(resolved))
    for name in names:
        level.actors.pop(name)
    level.order = order_after_delete(level.order, names)
    src.save(verb="delete", args={"names": names},
                    level=level, touched=names)
    for name in names:                               # PRODUCER: deleted names → stdout (a log/count)
        print(name)
    print(f"deleted {len(names)} actor(s)", file=sys.stderr)
    return 0


def _add(args, src) -> int:
    """`actor add (<file>|-)` — ingest a T3D snippet as fresh-named actors. A PURE carrier-consumer:
    the `// uedcli-folder:`/`// uedcli-labels:` carriers in the T3D win as-is; there is no override
    channel (post-hoc changes use `actor folder set` / `actor label`)."""
    level = src.load()
    text = ingest.read_t3d_input(args.file)
    return _ingest_actor_t3d(args, src, level, text, verb="add", labels_override=None)


def _duplicate(args, src) -> int:
    """`actor duplicate <names…|-> (--by|--at)` — sugar for `actor show <names…> | actor add -`:
    re-ingest the named actors' show-blocks (folder + label carriers included so both round-trip) →
    fresh-named copies. A REQUIRED --by/--at placement shifts the copies off their originals; every
    copy inherits the source labels and gets ONE fresh dup-<rand> batch label so the batch is
    re-addressable afterwards."""
    raw = target_names.resolve_target_names(args.names)
    if not raw:
        return 0                                       # empty stdin: no-op, exit 0
    level = src.load()
    try:
        names = list(dict.fromkeys(query.resolve_actor_names(level, raw)))
    except KeyError as e:
        print(e.args[0], file=sys.stderr)              # "Actors not found: …" — never a traceback
        return 2
    # Apply the placement by translating the SOURCE actors before emitting their show-blocks, so
    # the copies' Locations are already correct when re-ingested (--by = per-actor delta; --at =
    # anchor the set's union bbox-min corner, shifting the whole set together).
    sources = [level.actors[n] for n in names]
    by = getattr(args, "by", None)
    at = getattr(args, "at", None)
    if by is not None:
        placed = stashlib.translate(sources, tuple(by))
    else:
        lo, _hi = writes.union_bounds(sources)
        placed = stashlib.translate(sources, tuple(a - b for a, b in zip(at, lo)))
    text = "\n".join(query.actor_show_block(a, with_sidecars=True) for a in placed)
    # Fresh batch token, re-rolled until it is not already a label anywhere in the level — so the
    # batch handle can't collide with a prior duplicate's still-live token.
    existing_labels = {lbl for a in level.actors.values() for lbl in a.labels}
    while (dup_token := f"dup-{t3dtree._rand_suffix()}") in existing_labels:
        pass
    labels_add = frozenset({dup_token}) | frozenset(getattr(args, "label", None) or [])
    rc = _ingest_actor_t3d(args, src, level, text, verb="duplicate", labels_add=labels_add)
    if rc == 0:                                        # only echo the batch label if the copy landed
        print(f"batch label: {dup_token}", file=sys.stderr)
    return rc


def _warn_rotate_postscale_distortion(actor):
    # Rotating a NON-UNIFORM PostScale brush warps it — PostScale is world/post-rotation, so
    # old→new is a shear-conjugated rotation `PostScale·R·PostScale⁻¹` (spec §7). Inherent UE1
    # behavior (UnrealEd's own gizmo distorts it identically, silently). Warn, don't block.
    ps = rotation.actor_post_scale(actor)
    axes = [Decimal(str(c)) for c in ps.scale]
    if not (axes[0] == axes[1] == axes[2]):
        print(f"warning: {actor.name} has a non-uniform PostScale — rotating it WARPS the brush "
              f"(PostScale is post-rotation; UnrealEd distorts it identically). Consider "
              f"apply-transform first", file=sys.stderr)


def _rotate(args, src) -> int:
    """`actor rotate <names…|-> (--to|--by)` — absolute (`--to`, in-place) or orbit (`--by`, about a
    pivot) rotation. PRODUCER: rotated names to stdout; the summary (with the pivot/target) to
    stderr."""
    raw = target_names.resolve_target_names(args.names)          # `-` → names from stdin (spec §8)
    if not raw:
        return 0                                      # empty stdin: no-op, exit 0
    level = src.load()
    try:
        resolved = query.resolve_actor_names(level, raw)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    # Dedupe on CANONICAL names (order-preserving): a repeated name is the SAME actor
    # object, and applying the orbit + field-add twice would double-rotate it.
    names = list(dict.fromkeys(resolved))
    targets = [level.actors[n] for n in names]
    if getattr(args, "to", None) is not None:
        # ABSOLUTE rotation (--to): set the Rotation field IN PLACE (Location never moves;
        # excludes --pivot — spec §4). Each actor's field is replaced with the target value.
        if args.pivot is not None or args.pivot_actor is not None:
            print("actor rotate --to is in-place and cannot take a --pivot/--pivot-actor",
                  file=sys.stderr)
            return 2
        to_uu = tuple(rotation.uu_field(c) for c in args.to)
        for actor in targets:
            _warn_rotate_postscale_distortion(actor)
            props = [(k, v) for k, v in actor.props if k != "Rotation"]
            # ALWAYS written, `--to 0,0,0` included: an omitted `Rotation` does not mean
            # "unrotated", it means "whatever the CLASS defaults to" — and `TNM.LavaSpitter`
            # defaults `(Pitch=16384,Yaw=0,Roll=0)`, so dropping the prop here used to build it
            # pitched 90° with the post-verify passing (both compare sides shared the mistake).
            props.append(("Rotation", f"(Pitch={to_uu[0]},Yaw={to_uu[1]},Roll={to_uu[2]})"))
            actor.props = props
            if actor.brush is not None:
                validate_brush(actor.brush)
        for name in names:                           # PRODUCER: rotated names to stdout (feed `| verb -`)
            print(name)
        print(f"rotated {len(targets)} actor(s) to "
              f"{','.join(emit.fmt_coord(c) for c in args.to)}", file=sys.stderr)
        src.save(verb="rotate", args={"names": names, "to": [str(c) for c in args.to]},
                 level=level, touched=names)
        return 0
    # ONE closure per invocation: it carries the per-class memo, so building a second one for the
    # orbit doubled every class resolution (~50 ms each, 250 ms for a DeusExMover).
    default_loc = resources.default_location_for(args)
    if args.pivot is not None:
        pivot = args.pivot
    elif args.pivot_actor is not None:
        try:
            pivot_canonical = query.resolve_actor_name(level, args.pivot_actor)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        # The named actor's EFFECTIVE Location — the same answer the default pivot would give for
        # it. `location or (0,0,0)` made one verb report two different positions for one actor
        # depending only on whether it was named or chosen (build review, round 3).
        pa = level.actors[pivot_canonical]
        pivot = rotation.actor_own_pivot(
            pa, None if pa.location is not None else default_loc(pa))
    else:
        pivot = rotation.best_grid_pivot(targets, default_loc)
    delta_uu = tuple(rotation.uu_field(c) for c in args.by)
    # Orbit with the SAME quantized delta the actors store, via the GMath table — so Location and
    # the stored Rotation are consistent AND match what the editor renders (not float degrees).
    R = rotation.euler_to_matrix_uu(*delta_uu)
    for actor in targets:
        _warn_rotate_postscale_distortion(actor)
        # The ORBIT reads the same EFFECTIVE Location the pivot does. Using `or (0,0,0)` here
        # while `best_grid_pivot` resolves the class default is the assume-zero bug half-fixed:
        # an `Engine.Camera` stating no Location (class default (-500,-300,300)) pivots about
        # its own position — so it must not move — but with a zero orbit it landed at
        # (-800,200,0). Location is then always WRITTEN, exactly as `Rotation` is below: once a
        # verb has computed a new value, omitting it would re-import as the class default.
        loc = rotation.actor_own_pivot(
            actor, None if actor.location is not None else default_loc(actor))
        actor.location = rotation.rotate_point(loc, R, pivot)
        new_uu = rotation.compose_uu(delta_uu, rotation.actor_rotation_uu(actor))
        props = [(k, v) for k, v in actor.props if k != "Rotation"]
        # Written even when the composed result is (0,0,0) — see the `--to` note above: an
        # omitted `Rotation` re-imports as the CLASS DEFAULT, which is non-zero for
        # `TNM.LavaSpitter`, so "don't write a spurious Rotation=(0,0,0)" silently rotated it.
        props.append(("Rotation", f"(Pitch={new_uu[0]},Yaw={new_uu[1]},Roll={new_uu[2]})"))
        actor.props = props
        if actor.brush is not None:
            validate_brush(actor.brush)     # rigid → local geometry still valid
    for name in names:                               # PRODUCER: rotated names to stdout (feed `| verb -`)
        print(name)
    print(f"rotated {len(targets)} actor(s) about "
          f"{','.join(emit.fmt_coord(c) for c in pivot)}", file=sys.stderr)
    src.save(verb="rotate",
                    args={"names": names, "by": [str(c) for c in args.by],
                          "pivot": [str(c) for c in pivot]},
                    level=level, touched=names)
    return 0


# ── ingest shared by `add` and `duplicate` ──────────────────────────────────────────────────────


def _warn_duplicate_point_locations(level, added_names: list[str]) -> None:
    """Point actors (no brush) silently accept a shared Location — each still gets a unique Name, so
    two decorations dropped on the same spot is invisible. Warn (stderr) when 2+ point actors, at
    least one of them just added, share a Location. Cheap, advisory; never blocks the add."""
    added = set(added_names)
    by_loc: dict[tuple, list[str]] = {}
    for name, a in level.actors.items():
        if a.brush is not None or a.location is None:   # brushes / location-less actors don't count
            continue
        by_loc.setdefault(tuple(a.location), []).append(name)
    for loc, names in by_loc.items():
        if len(names) >= 2 and any(n in added for n in names):
            coord = ",".join(str(c) for c in loc)
            print(f"warning: {len(names)} actors share Location ({coord}): {', '.join(sorted(names))}",
                  file=sys.stderr)


def _parse_add_order(spec: str) -> tuple[str, str | None]:
    """Parse `actor add --order POS` → (selector, ref). POS is `first` | `last` | `before=NAME` |
    `after=NAME`. A malformed value or an empty NAME raises `CommandError` (clean exit 2)."""
    s = spec.strip()
    low = s.casefold()                                    # selector keyword is case-insensitive
    if low in ("first", "last"):
        return low, None
    for kw in ("before", "after"):
        prefix = kw + "="
        if low.startswith(prefix):
            ref = s[len(prefix):].strip()                 # NAME keeps its case (resolve is case-insensitive)
            if not ref:
                raise CommandError(f"actor add --order {kw}=NAME needs a NAME")
            return kw, ref
    raise CommandError(
        f"actor add --order: expected first|last|before=NAME|after=NAME, got {spec!r}")


def _reject_nonlevel_target_for_folders(args) -> None:
    """Carrier-check copy of the source-free folder guard `routes.py` owns: a `// uedcli-folder:`
    carrier in ingested T3D is a folder surface too, and folders are TRUNK-ONLY (spec §4), so it
    rejects `--tree stash|prefab` (else the box save would drop the folder silently). Kept local
    rather than imported from `routes` because a feature module never imports the family route."""
    tgt = getattr(args, "tree", None)
    if tgt and tgt.partition("/")[0] in ("stash", "prefab"):
        raise CommandError("folders apply only to a level (not --tree stash|prefab)")


def _reject_nonlevel_target_for_labels(args) -> None:
    """Carrier-check copy of the source-free label guard `routes.py` owns: a `// uedcli-labels:`
    carrier in ingested T3D is a label surface too, and labels are TRUNK-ONLY this slice, so it
    rejects `--tree stash|prefab` (else the box save would drop the label silently). Kept local
    rather than imported from `routes` because a feature module never imports the family route."""
    tgt = getattr(args, "tree", None)
    if tgt and tgt.partition("/")[0] in ("stash", "prefab"):
        raise CommandError("labels apply only to a level (not --tree stash|prefab)")


def _ingest_actor_t3d(args, src, level, text, *, verb: str,
                      labels_override: frozenset[str] | None = None,
                      labels_add: frozenset[str] | None = None) -> int:
    """Shared ingest for `actor add` and `actor duplicate`: parse a T3D snippet, drop transient
    builder brushes, apply folder precedence, validate classes/textures, allocate fresh
    `<stem>_<rand>` Names, add each actor to `level` with CSG-order placement, save, and print the
    new Names to stdout (allocation order) with a count to stderr. `text` is the T3D to ingest —
    for `actor add` the --file/stdin input, for `actor duplicate` the source actors' show-blocks.
    `verb` only labels the save + summary. `labels_override` (set by the ADD handler ONLY, from
    `--label`) REPLACES each ingested actor's carrier-parsed labels, mirroring `folder_override`;
    absent (None), the `// uedcli-labels:` carrier wins. It is a PARAM — not read from `args.label`
    inside — because `duplicate` also has `--label` but needs a UNION channel, not this override.
    `labels_add` (set by the DUPLICATE handler ONLY) is that UNION channel: each ingested actor's
    labels become `resolved_labels ∪ labels_add` (used for the fresh `dup-<rand>` batch token plus
    duplicate's additive `--label`). `add` never sets `labels_add`; `duplicate` never sets
    `labels_override` — they are distinct, non-conflated channels.
    Returns the process exit code."""
    # parse_t3d_actors (NOT parse_t3d): a Name-keyed dict silently drops all-but-last of any
    # duplicate-Named group in user-concatenated T3D (14 same-Named merlons → 1). The uniquify
    # loop below then mints a distinct `<stem>_<rand>` identity per actor.
    incoming_actors = [a for a in parse_t3d_actors(text) if not is_builder_brush(a)]
    if not incoming_actors:
        raise CommandError("no actors found in the T3D input (nothing to add)")
    # Folders are trunk-only, and a `// uedcli-folder:` carrier is a folder surface too: reject
    # `--target stash|prefab` when the input carries a folder (else level_sources.StashLevelSource.save would
    # DROP it silently — the exact outcome the guard exists to prevent; the explicit-`--folder`
    # case is already caught pre-resolve). Fires only when a folder is actually present.
    if any(a.folder is not None for a in incoming_actors):
        _reject_nonlevel_target_for_folders(args)
    # Same for a `// uedcli-labels:` carrier — labels are trunk-only this slice (no stash/prefab
    # channel), so a carrier into a box would drop silently on save; reject it (the explicit
    # `--label` case is already caught pre-resolve). Fires only when a label is actually present.
    if any(a.labels for a in incoming_actors):
        _reject_nonlevel_target_for_labels(args)
    # Folder precedence (spec §4): an explicit `--folder` OVERRIDES any `// uedcli-folder:`
    # carrier the parser read into `actor.folder`; absent it, the carrier (from `actor show`)
    # stands; absent both, the actor is unfoldered. Validate every resulting folder BEFORE the
    # write loop (all-or-nothing — save is after the loop, so a raise here writes nothing).
    folder_override = getattr(args, "folder", None)
    if folder_override is not None:
        try:
            folderlib.validate_folder_path(folder_override)
        except ValueError as e:
            raise CommandError(str(e))
    else:
        for a in incoming_actors:
            if a.folder is not None:                  # a carrier (possibly hand-edited) → validate
                try:
                    folderlib.validate_folder_path(a.folder)
                except ValueError as e:
                    raise CommandError(f"in `// uedcli-folder:` carrier: {e}")
    # Label precedence mirrors folders: `labels_override` (explicit `--label`) REPLACES the carrier;
    # absent, the carrier stands. Validate every resulting label BEFORE the write loop.
    if labels_override is not None:
        for lbl in labels_override:
            try:
                labellib.validate_label(lbl)
            except ValueError as e:
                raise CommandError(str(e))
    else:
        for a in incoming_actors:
            for lbl in a.labels:                      # a carrier (possibly hand-edited) → validate
                try:
                    labellib.validate_label(lbl)
                except ValueError as e:
                    raise CommandError(f"in `// uedcli-labels:` carrier: {e}")
    if labels_add is not None:                        # duplicate's UNION channel: validate before write
        for lbl in labels_add:
            try:
                labellib.validate_label(lbl)
            except ValueError as e:
                raise CommandError(str(e))
    # Author-time gate: qualify bare classes → FQCN + existence-validate classes & texture refs
    # (AFTER the builder-brush filter above — qualifying `Brush`→`Engine.Brush` first would let
    # the transient builder brush escape it). All-or-nothing: raises before the write loop below.
    ingest.validate_ingest_actors(incoming_actors, args)
    # git-native: coordination-free random-suffix identity (decisions 2026-07-05 15:11) so two
    # concurrent branch-adds never collide add/add on the actor dir.
    existing = {a.name for a in level.actors.values()}
    new_names = []
    for a in incoming_actors:
        stem = a.name          # keep the name as-authored (e.g. `--base-name Pillar1` → `Pillar1_<rand>`)
        n = trunk.alloc_name(stem, existing)
        existing.add(n)
        new_names.append(n)
    touched = []
    for actor, new_name in zip(incoming_actors, new_names):
        actor.name = new_name
        if folder_override is not None:               # explicit --folder wins over any carrier
            actor.folder = folder_override
        if labels_override is not None:               # explicit --label wins over any carrier
            actor.labels = labels_override
        if labels_add is not None:                    # duplicate: union onto the resolved labels
            actor.labels = actor.labels | labels_add
        if actor.brush is not None:
            actor.brush.model_name = f"Model_{new_name}"
            actor.props = [
                ("Brush", f"Model'MyLevel.Model_{new_name}'") if k == "Brush" else (k, v)
                for k, v in actor.props
            ]
            validate_brush(actor.brush)            # reject degenerate geometry pre-store
        level.actors[new_name] = actor
        level.order = order_after_add(level.order, new_name)
        touched.append(new_name)
    _warn_duplicate_point_locations(level, touched)   # advisory: stacked point actors are silent
    # CSG-order placement (spec §2): default `last` == today's append (no override). A non-last
    # placement mints ranks in the target gap for the new block, keeping emit order. Trunk-only
    # (a stash/prefab target with a non-last `--order` was rejected pre-resolve).
    order_override: dict[str, str] | None = None
    order_spec = getattr(args, "order", "last") or "last"
    if order_spec.strip().casefold() != "last":
        selector, ref = _parse_add_order(order_spec)
        if ref is not None:
            try:
                ref = query.resolve_actor_name(level, ref)   # before=/after=NAME must exist
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            # …and be a PRE-EXISTING actor: `level` already holds the just-added block, so a ref
            # resolving to one of those (not in the load snapshot `src._ranks`) is not a valid
            # placement anchor — reject cleanly instead of a bare KeyError in `_placement_gap`.
            if ref not in src._ranks:
                raise CommandError(
                    f"actor {verb} --order {selector}=NAME: {ref} is not an existing actor")
        try:                                         # src._ranks excludes the not-yet-saved new names
            order_override = order_ops.compute_add_ranks(src._ranks, new_names, selector, ref)
        except ValueError as e:                      # adjacent/duplicate imported ranks — no gap
            raise CommandError(f"cannot place: {e}")
    src.save(verb=verb, args={"names": touched}, level=level, touched=touched,
             ranks=order_override)
    # Allocated Names → stdout (one/line, allocation order), ONLY AFTER the save returns so a
    # live `add - | prop -` pipe's downstream load() can never race ahead of the trunk write
    # (spec 2026-07-18 §8). The human-facing count goes to stderr — never polluting the pipe.
    for n in touched:
        print(n)
    summary = "added" if verb == "add" else "duplicated"
    print(f"{summary} {len(touched)} actor(s)", file=sys.stderr)
    return 0
