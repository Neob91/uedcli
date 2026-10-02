"""Stash/prefab apply merge — the cross-family placement orchestrator.

`apply_set` merges a captured actor set (from a stash or a prefab) into a target trunk level: it
translates to the anchor/`--at` corner, allocates names, stamps group/folder, validates geometry and
class/texture up front (all-or-nothing), and saves. Shared by `stash apply` and `prefab apply`.
Callers use module-qualified lookup (`placement.apply_set(...)`). It may use the earlier `ingest`
owner for the author-time gate; it never imports a command family (spec "Dependency rules" 4-5).
"""
from __future__ import annotations

import sys
from decimal import Decimal

from .. import folderlib, trunk, writes
from ..geometry import validate_brush
from ..model import parse_t3d
from ..order_ops import order_after_add
from . import ingest
from .errors import CommandError


def apply_set(args, level_src, actors_t3d: dict, order: list[str], packages: list[str], *,
              default_group: str, anchor: list[str],
              folders: dict[str, str | None] | None = None) -> int:
    """Model-side merge of a captured actor set into the target trunk level via the `LevelSource`
    seam. Translate (--at → bbox-min corner, else the captured world `anchor`), allocate names, set
    Group, append to order. Validate all geometry up front (all-or-nothing at the write level). NO
    editor. Source-agnostic: the caller supplies `anchor` (stash from read_stash meta, prefab from
    read_prefab meta). Names are coordination-free random-suffix (decisions 2026-07-05 15:11,
    mirroring `actor add`); the trunk has no package manifest (the load set derives on demand at
    build, decisions 2026-06-30 18:47), so `packages` is not recorded.

    `folders` (name→folder|None) is each source member's STORED folder (persisted since the
    unify-T3D-trees change). It is the placement DEFAULT — a member lands in its stored folder;
    `--folder` OVERRIDES all placed actors (decisions 2026-07-18 addendum, sub-choice 2)."""
    from .. import stashlib
    if not order:
        raise CommandError("nothing to apply: source is empty")
    stored_folders = folders or {}
    main_level = level_src.load()
    src_level = parse_t3d("Begin Map\n" + "\n".join(actors_t3d[n] for n in order
                                                    if n in actors_t3d) + "\nEnd Map\n")
    src = [src_level.actors[n] for n in order if n in src_level.actors]
    for a in src:                                       # re-attach each member's stored folder (a T3D
        a.folder = stored_folders.get(a.name)           # blob dropped it) as the placement default

    # `--at`/`anchor` anchor the bbox-min CORNER, not the actor Location (the documented contract).
    # Derive the delta from the source's ACTUAL world bbox-min so the placed corner lands exactly on
    # the target, regardless of whether the captured set is perfectly origin-normalized (actor_bounds
    # now honours MainScale/PostScale, so a scaled brush's bbox-min is its true scaled world corner).
    target = args.at if args.at is not None else tuple(Decimal(c) for c in anchor)
    src_lo, _src_hi = writes.union_bounds(src)
    delta = tuple(target[i] - src_lo[i] for i in range(3))
    group = None if getattr(args, "no_group", False) else (args.group or default_group)
    # `--folder` is an INDEPENDENT placement dimension from `--group` (spec §6): it stamps the
    # uedcli-side sidecar. Since the unify-T3D-trees change a member carries its STORED folder as the
    # default; an explicit `--folder` OVERRIDES it for every placed actor. The trunk always persists
    # it (apply's placement target is a trunk; the trunk-only restriction is on the folder VERBS, not
    # apply). Validate the override path AND every stored folder before any write (all-or-nothing).
    folder_override = getattr(args, "folder", None)
    if folder_override is not None:
        try:
            folderlib.validate_folder_path(folder_override)
        except ValueError as e:
            raise CommandError(str(e))
    else:
        for f in {a.folder for a in src if a.folder is not None}:   # defensive: a hand-edited sidecar
            try:
                folderlib.validate_folder_path(f)
            except ValueError as e:
                raise CommandError(f"stored folder in source: {e}")
    placed = []
    for a in stashlib.translate(src, delta):
        a = stashlib.with_group(a, group)
        if folder_override is not None:
            a = stashlib.with_folder(a, folder_override)
        # else: `with_group`/`translate` preserve the member's stored `folder` (the default)
        placed.append(a)
    for a in placed:                                    # all-or-nothing: validate before any write
        if a.brush is not None:
            validate_brush(a.brush)
    # Author-time gate on the captured set entering the trunk: existence-validate classes & textures
    # (usually already FQCN, so a cheap re-check — but covers a hand-edited stash/prefab box). Runs
    # after geometry validation, before any write (all-or-nothing).
    ingest.validate_ingest_actors(placed, args)

    # alloc_name must see each prior placement, so add into main_level as we go and record once
    # with all touched names (M3: one apply = one commit, not N).
    existing_names = set(main_level.actors)
    placed_names: list[str] = []
    for a in placed:
        stem = a.name          # keep the name as-authored: `--base-name Pillar1` must stay `Pillar1_<rand>`
        a.name = trunk.alloc_name(stem, existing_names)         # random suffix; sees prior placements
        existing_names.add(a.name)
        main_level.actors[a.name] = a
        main_level.order = order_after_add(main_level.order, a.name)
        placed_names.append(a.name)
    rec_args = {"source": getattr(args, "id", None) or getattr(args, "name", None),
                "names": placed_names}
    level_src.save(verb="add", args=rec_args, level=main_level, touched=placed_names)
    for name in placed_names:                            # PRODUCER: placed names to stdout (feed `| verb -`)
        print(name)
    print(f"applied {len(placed)} actors", file=sys.stderr)
    return 0
