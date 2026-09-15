"""On-disk build-pin pointer for `uedcli serve` (spec §1): `.uedcli/build/<level>/current.json`
names the `(geom_hash, light_hash)` pair a Save last committed, resolved against the existing
`preview_cache` scene store. Read-only — nothing in this plan's scope ever writes this file; Save
(P2, doesn't exist yet) owns the write, atomically with its own trunk write."""
from __future__ import annotations

import json
from pathlib import Path

from .. import config, preview_cache


def pointer_path(project, level_name: str) -> Path:
    """`.uedcli/build/<level_name>/current.json`. Never creates the `build` subdir — read-only
    helper, nothing in this plan's scope ever writes it (see module docstring)."""
    return config.state_subdir(project.root, "build", create=False) / level_name / "current.json"


def load_pointer(project, level_name: str) -> tuple[str, str] | None:
    """`(geom_hash, light_hash)` from the on-disk pointer, or `None` if it's absent, unreadable, or
    malformed — a corrupt/partial pointer degrades to "never built" like any other cache miss,
    never an exception (matches `preview_cache._load`'s own corrupt-entry posture)."""
    try:
        raw = pointer_path(project, level_name).read_text()
    except OSError:
        return None
    try:
        data = json.loads(raw)
        return data["geom_hash"], data["light_hash"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def resolve_pin(project, level_name: str, pin: tuple[str, str]):
    """The cached `(polys, texture_table, actor_names_by_poly)` scene for `pin`, or `None` on a
    miss — the pointer names a hash pair `preview_cache` no longer holds (evicted by its
    project-wide LRU, spec §1's "Eviction caveat"). Does not itself decide what "degraded" means to
    a caller; a pure lookup wrapper."""
    geom_hash, light_hash = pin
    return preview_cache.load_scene(project, level_name, geom_hash, light_hash)
