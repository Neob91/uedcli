"""`level photo --native`'s disk cache for `preview_native.build_scene` (owner ruling 2026-09-13):
a CSG solve is ~24s CPU on a mid-size level, so a level whose non-light actors haven't changed
reuses the prior CSG + texture-decode work and only reruns the (cheap) lighting bake; a level
unchanged on BOTH the geometry and light actors reuses the fully-lit scene outright.

Same self-ignoring state dir and hash-named-file convention `preview_game.materialized_dx` already
uses (`.uedcli/preview/`, `_compose_stem`/`_prune_prefix`, `PREVIEW_KEEP`-bounded) — a hash mismatch
just costs a rebuild, never serves a stale scene (`preview_native._scene_hashes` errs strict the
same way `normalize.canonical_level_hash` does).

Serialized with `marshal`, NOT `pickle` — same reasoning as `schema_cache.py` (its own module
docstring: "marshal has no pickle RCE"). `.uedcli/preview/` holds only cache entries this same
user's own uedcli process wrote, but a cache file's whole point is that something OTHER than the
call that wrote it reads it back later, so it is exactly the kind of file that should stay safe to
load even if tampered with (a shared machine, a stale NFS mount, a restored backup) — `pickle` would
let a crafted file execute arbitrary code on load; `marshal` only ever produces plain Python
built-ins (int/float/bytes/str/tuple/list/dict/None/bool/…), which is everything every payload here
actually needs.

`_CACHE_VERSION` is baked into the filename PREFIX, not read from the cached payload — same reason
`schema_cache.py` puts its version in the cache key rather than inside the cached bytes: a payload
whose shape changed across a uedcli version must never be unmarshalled and unpacked into new code
that expects a different shape (a `ValueError`/`KeyError`, not a clean miss). A version bump makes an
old-version file invisible to `_prune_prefix`'s prefix glob (it would otherwise sit on disk forever,
unlike `schema_cache.py`'s own versioned dirs, which its `sweep()` reclaims) — `_sweep_old_versions`
below deletes any file from a prior version on the next write, so a bump needs no migration step.
"""
from __future__ import annotations

import marshal
import re
from pathlib import Path

from . import config
from .preview_game import _compose_stem, _prune_prefix

_CACHE_VERSION = 3   # bumped: the per-poly actor-owner list's elements widened to (name, i_brush_poly)
_GEO_PREFIX = f"scenegeo{_CACHE_VERSION}"
_LIT_PREFIX = f"scenelit{_CACHE_VERSION}"
_VERSIONED_PREFIX_RE = re.compile(r"^(scenegeo|scenelit)(\d+)__")


def _dir(project) -> Path:
    return config.state_subdir(project.root, "preview", create=True)


def _sweep_old_versions(d: Path) -> None:
    """Delete any `scenegeo`/`scenelit` file from a PRIOR `_CACHE_VERSION` — `_prune_prefix` only
    ever globs the CURRENT version's prefix, so without this a version bump would leave the old
    version's files on disk forever. Best-effort: a file another process is mid-writing loses the
    race harmlessly (it just isn't swept this time)."""
    for p in d.iterdir():
        if not p.is_file():
            continue
        m = _VERSIONED_PREFIX_RE.match(p.name)
        if m and int(m.group(2)) != _CACHE_VERSION:
            p.unlink(missing_ok=True)


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
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(marshal.dumps(payload))
    tmp.replace(path)                        # atomic swap — a reader never sees a partial file


def load_geometry(project, level_name: str, geom_hash12: str):
    """`(model_body, portals, polys_no_light, i_surf_by_poly, actor_names_by_poly, texture_table)`
    for `geom_hash12`, or None. `portals` is `uedcli_native.leaf_portals(built)`'s output (the
    frozen portal graph, not part of `model_body`'s on-disk format — MUST be restored via
    `load_model(body, leaf_portals=portals)`, never dropped, or `bake_lighting` silently falls back
    to a stale recompute). `polys_no_light` entries omit the trailing lightmap field;
    `i_surf_by_poly[i]` is the world-BSP surf index feeding `polys_no_light[i]`'s eventual lightmap
    (None for a mover/mesh poly, which never gets one); `actor_names_by_poly[i]` is that same poly's
    owning actor name (None for an out-of-range CSG join)."""
    return _load(_dir(project) / f"{_compose_stem(_GEO_PREFIX, level_name, geom_hash12)}.marshal")


def store_geometry(project, level_name: str, geom_hash12: str, payload) -> None:
    d = _dir(project)
    target = d / f"{_compose_stem(_GEO_PREFIX, level_name, geom_hash12)}.marshal"
    _store(target, payload)
    _prune_prefix(d, _GEO_PREFIX, protect=target)
    _sweep_old_versions(d)


def load_scene(project, level_name: str, geom_hash12: str, light_hash12: str):
    """The cached fully-lit `(polys, texture_table, actor_names_by_poly)` for this exact
    geometry+light combination (both hashes must match), or None."""
    stem = _compose_stem(_LIT_PREFIX, level_name, geom_hash12 + light_hash12)
    return _load(_dir(project) / f"{stem}.marshal")


def store_scene(project, level_name: str, geom_hash12: str, light_hash12: str, payload) -> None:
    d = _dir(project)
    target = d / f"{_compose_stem(_LIT_PREFIX, level_name, geom_hash12 + light_hash12)}.marshal"
    _store(target, payload)
    _prune_prefix(d, _LIT_PREFIX, protect=target)
    _sweep_old_versions(d)
