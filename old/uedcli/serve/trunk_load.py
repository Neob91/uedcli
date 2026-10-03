"""Incremental Load for `uedcli serve`: build a `_LoadedTrunk` while re-reading and re-resolving
only the actors that changed on disk since the previous Load (board
`incremental-gui-reload-only-re-resolve-actors`).

Measured on a 2745-actor level, warm process: a Load cost ~9.7s regardless of whether anything had
changed — 8.2s of it the trunk's own file I/O (`t3dtree.read_actor_tree`), 1.5s the three Load-owned
resolvers. Both halves are now skipped per unchanged actor: `t3dtree.read_actor_tree_delta` reuses
an already-parsed actor whose `ActorStamp` hasn't moved, and `_ActorRender` holds that actor's
already-resolved sprite/mesh/mover render data.

The resolvers are NOT restructured to run per actor. They still run once per Load over a `Level`
holding just the changed actors, and `_localize` splits their flat returns back out per owning actor
afterwards — so a cold Load (every actor changed) makes exactly the three calls it makes today, over
exactly today's level, sharing one `TextureResolver`. This is sound only because the three are
per-actor-independent: a sprite, a mesh actor's triangles and a Mover's brush polys each resolve
from that actor plus the class/package inputs alone, with no cross-actor geometry — unlike world BSP
surfaces, which is why those live in `_BuiltGeometry` and not here.

Texture tables are rebuilt dense on every Load. Each actor's cached polys carry texture slots local
to that actor's own little table, and `_merge` folds them into one shared table in the same
first-encounter order a full Load produces, deduping by `(entry, group)`. Keeping a persistent
table instead would be cheaper still, but its indices can only ever be append-only, so every
removed actor would strand an entry in the atlas the GUI then has to ship.

A reused actor's `Actor` object is the one the previous Load parsed, so it now lives as long as the
cache rather than only until the next Load. Nothing in `serve` may mutate it — the invariant
`LevelContext.trunk_ref` already relies on, since one `_LoadedTrunk` is shared across every
`/scene`/`/atlas` request (`session_rebuild` copies via `edits.apply_staged_overlay` for exactly
this reason; `edits.save_staged` mutates only its own separately-loaded `Level`)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import t3dtree, trunk
from ..model import Level
from ..preview_native import (resolve_actor_sprites, resolve_mesh_scene_polys,
                              resolve_mover_scene_polys)
from .scene import _LoadedTrunk

# One texture-table row, `(width, height, rgb, mask)` — `_TextureTable.table`'s own row shape.
_TexEntry = tuple[int, int, bytes, bytes]


@dataclass(frozen=True, kw_only=True)
class _ActorRender:
    """One actor's Load-owned, CSG-independent render data, held per actor name so an unchanged
    actor survives the next Load without being re-resolved.

    Every `tex_index` in `mesh_polys`/`mover_polys` is LOCAL: it indexes this actor's own
    `mesh_texes`/`mover_texes`, not the shared table `_LoadedTrunk` publishes — that one is rebuilt
    per Load by `_merge`. `-1` (no texture) passes through unchanged.

    `sprite` is `resolve_actor_sprites`'s per-actor answer with its table row inlined, so the row
    travels with the actor that needs it. `mover_owners` is kept per poly because a Mover's owner
    tuple carries the poly's own `i_brush_poly`; a mesh poly's owner is always `(name, None)` and is
    regenerated instead of stored. `mesh_texes` carries no group: a mesh skin resolves via
    `_TextureTable.index_for_decoded`, whose group is always `None` (`_LoadedTrunk`'s docstring)."""
    sprite: tuple[_TexEntry, float, float] | None
    mesh_polys: list[tuple]
    mesh_texes: list[_TexEntry]
    mover_polys: list[tuple]
    mover_owners: list[tuple[str, int]]
    mover_texes: list[tuple[_TexEntry, str | None]]


@dataclass(frozen=True, kw_only=True)
class TrunkCache:
    """What one Load leaves for the next: the parsed tree plus its filesystem stamps
    (`t3dtree.TrunkRead`), and each actor's resolved render data.

    `inputs` is the `(search_files, index, defaults)` tuple the renders were resolved against.
    `load_trunk` compares it with `==` rather than `is`, since each caller builds its own tuple from
    the trio `_scene_inputs` memoizes; tuple comparison short-circuits on identity per element, so
    a rebuilt `index`/`defaults` is what actually invalidates the cached resolutions. In practice
    `_scene_inputs` memoizes that trio for the life of the process, so this guard never fires
    today — it is here so a future invalidation path cannot silently reuse renders resolved against
    a replaced class resolver."""
    read: t3dtree.TrunkRead
    renders: dict[str, _ActorRender]
    inputs: tuple


def _localize(polys: list[tuple], owners: list[tuple], table: list[_TexEntry],
              groups: list[str | None] | None) -> dict[str, tuple[list, list, list]]:
    """Split one resolver's flat `(polys, owners)` return per owning actor, renumbering each poly's
    texture slot into that actor's own `(entry, group)` list → `{name: (polys, owners, texes)}`.
    `groups=None` (the mesh table) stores a bare entry rather than an `(entry, None)` pair."""
    per: dict[str, tuple[list, list, list]] = {}
    seen: dict[str, dict[int, int]] = {}
    for poly, owner in zip(polys, owners):
        name = owner[0]
        local_polys, local_owners, local_texes = per.setdefault(name, ([], [], []))
        by_global = seen.setdefault(name, {})
        index = poly[5]
        if index >= 0:
            local = by_global.get(index)
            if local is None:
                local = by_global[index] = len(local_texes)
                local_texes.append(table[index] if groups is None
                                   else (table[index], groups[index]))
            index = local
        local_polys.append(poly[:5] + (index,) + poly[6:])
        local_owners.append(owner)
    return per


def _resolve_actors(level: Level, inputs: tuple) -> dict[str, _ActorRender]:
    """Resolve every actor in `level` — the changed subset on an incremental Load, the whole level
    on a cold one — into per-actor render data. Three resolver calls over the whole `level`, as a
    full Load makes today, split per actor by `_localize` afterwards."""
    search_files, index, defaults = inputs
    sprite_table, actor_sprites = resolve_actor_sprites(level, search_files, defaults)
    mesh_polys, mesh_owners, mesh_table, _mesh_groups = resolve_mesh_scene_polys(
        level, index, search_files, defaults)
    mover_polys, mover_owners, mover_table, mover_groups = resolve_mover_scene_polys(
        level, index, search_files, defaults)
    mesh_by = _localize(mesh_polys, mesh_owners, mesh_table, None)
    mover_by = _localize(mover_polys, mover_owners, mover_table, mover_groups)
    renders = {}
    for name in level.actors:
        sprite = actor_sprites.get(name)
        mesh = mesh_by.get(name)
        mover = mover_by.get(name)
        renders[name] = _ActorRender(
            sprite=None if sprite is None else (sprite_table[sprite[0]], sprite[1], sprite[2]),
            mesh_polys=mesh[0] if mesh else [],
            mesh_texes=mesh[2] if mesh else [],
            mover_polys=mover[0] if mover else [],
            mover_owners=mover[1] if mover else [],
            mover_texes=mover[2] if mover else [])
    return renders


def _merge(level: Level, renders: dict[str, _ActorRender]):
    """Fold every actor's render data into the flat, shared-table form `_LoadedTrunk` publishes,
    in the order each resolver's own whole-level pass would have produced (see the two walks below).

    Each table is deduped by `(entry, group)`: the entry alone would let two refs whose pixels are
    identical collapse onto one row and so onto one `AtlasRect.name`, which the GUI shows as that
    surface's texture name."""
    sprite_table: list[_TexEntry] = []
    actor_sprites: dict[str, tuple[int, float, float]] = {}
    sprite_seen: dict[tuple, int] = {}
    mesh_polys: list[tuple] = []
    mesh_owners: list[tuple[str, None]] = []
    mesh_table: list[_TexEntry] = []
    mesh_seen: dict[tuple, int] = {}
    mover_polys: list[tuple] = []
    mover_owners: list[tuple[str, int]] = []
    mover_table: list[_TexEntry] = []
    mover_groups: list[str | None] = []
    mover_seen: dict[tuple, int] = {}

    def fold(entry: _TexEntry, group: str | None, table: list[_TexEntry],
             seen: dict[tuple, int], groups: list[str | None] | None) -> int:
        """`entry`'s row index in `table`, appending it (and its group) on first sight."""
        key = entry + (group,)
        index = seen.get(key)
        if index is None:
            index = seen[key] = len(table)
            table.append(entry)
            if groups is not None:
                groups.append(group)
        return index

    # Two walks, because the resolvers themselves disagree on order and each output has to keep
    # the order its own resolver produced: `resolve_actor_sprites` and `resolve_mesh_actor_polys`
    # iterate `level.actors.values()` (the actors/ scan's NAME order), while
    # `_mover_world_polys` iterates `level.order` (the `(order_value, name)` CSG sort). The two
    # differ for any level whose ranks don't follow its names, i.e. essentially every real one.
    for name in level.actors:
        render = renders[name]
        if render.sprite is not None:
            entry, width, height = render.sprite
            actor_sprites[name] = (fold(entry, None, sprite_table, sprite_seen, None),
                                   width, height)
        mesh_remap = [fold(entry, None, mesh_table, mesh_seen, None)
                      for entry in render.mesh_texes]
        for poly in render.mesh_polys:
            mesh_polys.append(poly[:5] + (mesh_remap[poly[5]] if poly[5] >= 0 else -1,) + poly[6:])
            mesh_owners.append((name, None))
    for name in level.order:
        render = renders[name]
        mover_remap = [fold(entry, group, mover_table, mover_seen, mover_groups)
                       for entry, group in render.mover_texes]
        for poly, owner in zip(render.mover_polys, render.mover_owners):
            mover_polys.append(poly[:5] + (mover_remap[poly[5]] if poly[5] >= 0 else -1,)
                               + poly[6:])
            mover_owners.append(owner)
    return (sprite_table, actor_sprites, mesh_polys, mesh_owners, mesh_table,
            mover_polys, mover_owners, mover_table, mover_groups)


def load_trunk(trunk_dir: Path, *, inputs: tuple,
               previous: TrunkCache | None) -> tuple[_LoadedTrunk, TrunkCache]:
    """Read `trunk_dir` and build its `_LoadedTrunk`, reusing whatever `previous` still holds for
    an actor whose files have not changed → `(loaded, cache)`, the cache to hand the next Load.
    `previous=None` (or one resolved against different `inputs`) reads and resolves everything."""
    if previous is not None and previous.inputs != inputs:
        previous = None
    delta = trunk.read_level_delta(trunk_dir, None if previous is None else previous.read)
    level = delta.read.level
    renders = {} if previous is None else {n: r for n, r in previous.renders.items()
                                           if n in level.actors and n not in delta.reread}
    if delta.reread:
        stale = Level(actors={n: a for n, a in level.actors.items() if n in delta.reread})
        stale.order = [n for n in level.order if n in delta.reread]
        renders.update(_resolve_actors(stale, inputs))
    (sprite_table, actor_sprites, mesh_polys, mesh_owners, mesh_table,
     mover_polys, mover_owners, mover_table, mover_groups) = _merge(level, renders)
    loaded = _LoadedTrunk(level=level, ranks=delta.read.ranks, folders=delta.read.folders,
                          sprite_table=sprite_table, actor_sprites=actor_sprites,
                          mesh_polys=mesh_polys, mesh_owners=mesh_owners,
                          mesh_texture_table=mesh_table,
                          mover_polys=mover_polys, mover_owners=mover_owners,
                          mover_texture_table=mover_table, mover_groups=mover_groups)
    return loaded, TrunkCache(read=delta.read, renders=renders, inputs=inputs)
