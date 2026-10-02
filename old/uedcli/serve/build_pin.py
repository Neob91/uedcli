"""Two build pins, not one. `sessions/<sid>/build.json` is this session's own current pin while it
edits — corrupt-and-instruct, since a session's own state is closer to "work" than to a cache
(direction/safety.md). `build/pin/<level>/current.json` is the level's pin, written only by Save,
naming the build matching the last-saved trunk — unchanged from before this feature: silent-degrade
to "never built" on any read failure, since it's purely regenerable (a fresh Rebuild replaces it)."""
from __future__ import annotations

import json
from pathlib import Path

from .. import build_cache, config
from .atomic_io import atomic_write_json


class SessionPointerCorruptError(Exception):
    pass


def session_pointer_path(sessions_root: Path, session_id: str) -> Path:
    return Path(sessions_root) / session_id / "build.json"


def load_session_pointer(sessions_root: Path, session_id: str) -> tuple[str, str]:
    p = session_pointer_path(sessions_root, session_id)
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data["geom_hash"], data["light_hash"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SessionPointerCorruptError(
            f"session {session_id}: build pin at {p} is missing or unreadable: {exc}"
        ) from exc


def write_session_pointer(sessions_root: Path, session_id: str, geom_hash: str, light_hash: str) -> None:
    atomic_write_json(session_pointer_path(sessions_root, session_id),
                       {"geom_hash": geom_hash, "light_hash": light_hash})


def resolve_session_pin(project, level_name: str, sessions_root: Path, session_id: str):
    geom_hash, light_hash = load_session_pointer(sessions_root, session_id)
    return build_cache.load_scene(project, level_name, geom_hash, light_hash)


def level_pointer_path(project, level_name: str) -> Path:
    return config.state_subdir(project.root, "build/pin", create=False) / level_name / "current.json"


def load_level_pointer(project, level_name: str) -> tuple[str, str] | None:
    try:
        raw = level_pointer_path(project, level_name).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
        return data["geom_hash"], data["light_hash"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def write_level_pointer(project, level_name: str, geom_hash: str, light_hash: str) -> None:
    atomic_write_json(level_pointer_path(project, level_name),
                       {"geom_hash": geom_hash, "light_hash": light_hash})


def resolve_level_pin(project, level_name: str):
    """The cached `(polys, texture_table, actor_names_by_poly, texture_groups)` scene for the
    level's own saved pin, or `None` on a miss -- either nothing is pinned yet, or the pointer
    names a hash pair `build_cache` no longer holds (evicted by its project-wide LRU). `texture_
    groups[i]` is the real `Package.Group.Name` identity for `texture_table[i]` (`AtlasRect.name`)
    -- carried by `build_cache.load_scene` itself, so a pin-restored geometry gets real names too,
    not just a fresh `build_scene` call."""
    pin = load_level_pointer(project, level_name)
    if pin is None:
        return None
    geom_hash, light_hash = pin
    return build_cache.load_scene(project, level_name, geom_hash, light_hash)
