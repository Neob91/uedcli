"""`level photo --native`'s and `uedcli serve`'s disk cache for `preview_native.build_scene` (owner
ruling 2026-09-13): a CSG solve is ~24s CPU on a mid-size level, so a level whose non-light actors
haven't changed reuses the prior CSG + texture-decode work and only reruns the (cheap) lighting
bake; a level unchanged on BOTH the geometry and light actors reuses the fully-lit scene outright.

On-disk layout: `.uedcli/build/cache/v{_CACHE_VERSION}/<level_name>/geometry/<geom_hash12>.marshal`
and `.../<level_name>/lighting/<geom_hash12>/<light_hash12>.marshal` — nested per-level and
per-kind, not the flat filename-prefix scheme this module used before persistent GUI editing
sessions (multiple sessions sharing one project's cache need eviction scoped by level and by real
reference, not a flat newest-N-by-mtime sweep). A version bump is just a new `v{N}/` directory; the
old one is abandoned rather than swept (see `evict_unreferenced` below, which replaces the old
`_sweep_old_versions`/`_prune_prefix` mechanism entirely).

Serialized with `marshal`, NOT `pickle` — same reasoning as `schema_cache.py` (its own module
docstring: "marshal has no pickle RCE"). The cache dir holds only entries this same user's own
uedcli process wrote, but a cache file's whole point is that something OTHER than the call that
wrote it reads it back later, so it is exactly the kind of file that should stay safe to load even
if tampered with (a shared machine, a stale NFS mount, a restored backup) — `pickle` would let a
crafted file execute arbitrary code on load; `marshal` only ever produces plain Python built-ins
(int/float/bytes/str/tuple/list/dict/None/bool/…), which is everything every payload here actually
needs.
"""
from __future__ import annotations

import marshal
from pathlib import Path

from . import config

_CACHE_VERSION = 4   # bumped: geometry/scene payloads gained a trailing texture_table `groups` list


def _dir(project, level_name: str) -> Path:
    root = config.state_subdir(project.root, "build/cache", create=True)
    return root / f"v{_CACHE_VERSION}" / level_name


def _geometry_path(project, level_name: str, geom_hash12: str) -> Path:
    return _dir(project, level_name) / "geometry" / f"{geom_hash12}.marshal"


def _lighting_path(project, level_name: str, geom_hash12: str, light_hash12: str) -> Path:
    return _dir(project, level_name) / "lighting" / geom_hash12 / f"{light_hash12}.marshal"


def _load(path: Path):
    if not path.is_file():
        return None
    try:
        return marshal.loads(path.read_bytes())
    except Exception:
        # Broad except deliberately, matching `schema_cache.py::_disc_loads`'s own precedent:
        # `marshal` can raise a variety of exception types on malformed/truncated input, and every
        # one of them means the same thing here — a corrupt/partial file reads as a miss, never a
        # crash.
        return None


def _store(path: Path, payload) -> None:
    # The nested geometry/lighting subdir may not exist yet (the old flat layout never needed this).
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(marshal.dumps(payload))
    tmp.replace(path)                        # atomic swap — a reader never sees a partial file


def load_geometry(project, level_name: str, geom_hash12: str):
    """`(model_body, portals, polys_no_light, i_surf_by_poly, actor_names_by_poly, texture_table,
    texture_groups)` for `geom_hash12`, or None. `portals` is `uedcli_native.leaf_portals(built)`'s
    output (the frozen portal graph, not part of `model_body`'s on-disk format — MUST be restored
    via `load_model(body, leaf_portals=portals)`, never dropped, or `bake_lighting` silently falls
    back to a stale recompute). `polys_no_light` entries omit the trailing lightmap field;
    `i_surf_by_poly[i]` is the world-BSP surf index feeding `polys_no_light[i]`'s eventual lightmap
    (None for a mover/mesh poly, which never gets one); `actor_names_by_poly[i]` is that same poly's
    owning actor name (None for an out-of-range CSG join). `texture_groups[i]` is
    `_TextureTable.group_for(i)` for `texture_table[i]` — the real `Package.Group.Name` identity
    `build_scene`'s `groups_out` out-param needs, carried through the cache so a geometry-cache HIT
    doesn't lose it (board/review finding: it used to)."""
    return _load(_geometry_path(project, level_name, geom_hash12))


def store_geometry(project, level_name: str, geom_hash12: str, payload) -> None:
    _store(_geometry_path(project, level_name, geom_hash12), payload)


def load_scene(project, level_name: str, geom_hash12: str, light_hash12: str):
    """The cached fully-lit `(polys, texture_table, actor_names_by_poly, texture_groups)` for this
    exact geometry+light combination (both hashes must match), or None. `texture_groups[i]` is
    `_TextureTable.group_for(i)` for `texture_table[i]` — see `load_geometry`'s docstring."""
    return _load(_lighting_path(project, level_name, geom_hash12, light_hash12))


def store_scene(project, level_name: str, geom_hash12: str, light_hash12: str, payload) -> None:
    _store(_lighting_path(project, level_name, geom_hash12, light_hash12), payload)


def evict_unreferenced(
    project, level_name: str, *, live_geom_hashes: set[str], live_pairs: set[tuple[str, str]],
    max_bytes: int | None = None,
) -> dict:
    """Delete geometry/lighting cache entries with no live reference, oldest-atime-first, until
    under `max_bytes` (or `project.build_cache_max_bytes` if not given). A live entry is NEVER
    evicted regardless of budget — `live_geom_hashes`/`live_pairs` name every (geom_hash) and
    (geom_hash, light_hash) currently pinned by any session's build.json or any level's
    build/pin/<level>/current.json; the caller gathers those sets, this function only deletes."""
    budget = max_bytes if max_bytes is not None else project.build_cache_max_bytes
    base = _dir(project, level_name)
    geo_dir, lit_dir = base / "geometry", base / "lighting"
    candidates: list[tuple[float, int, Path]] = []
    total = 0
    total_entries = 0
    if geo_dir.is_dir():
        for f in geo_dir.iterdir():
            if not f.is_file():
                continue
            st = f.stat()
            total += st.st_size
            total_entries += 1
            if f.stem not in live_geom_hashes:
                candidates.append((st.st_atime, st.st_size, f))
    if lit_dir.is_dir():
        for geom_sub in lit_dir.iterdir():
            if not geom_sub.is_dir():
                continue
            for f in geom_sub.iterdir():
                if not f.is_file():
                    continue
                st = f.stat()
                total += st.st_size
                total_entries += 1
                if (geom_sub.name, f.stem) not in live_pairs:
                    candidates.append((st.st_atime, st.st_size, f))
    evicted = freed = 0
    if budget is not None and total > budget:
        candidates.sort(key=lambda c: c[0])
        for _atime, size, path in candidates:
            if total <= budget:
                break
            try:
                path.unlink()
            except OSError:
                continue
            total -= size
            evicted += 1
            freed += size
    return {"evicted": evicted, "freed_bytes": freed, "kept_bytes": total,
            "kept_entries": total_entries - evicted}
