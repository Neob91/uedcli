"""Session lifecycle: sessions/<sid>/index.json (id, level, created_at, last_active_at,
last_seen_generation). Corrupt-and-instruct on a bad read of an EXISTING session's own index.json --
this is a session's own record, closer to "work" than to a cache. A session id that was simply never
created is a normal miss (returns None), not corruption."""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .atomic_io import atomic_write_json
from ..uuid7 import uuid7  # reuse the existing ephemeral-editor id generator (architecture.md D5/D7)

logger = logging.getLogger(__name__)

_TOUCH_THROTTLE = timedelta(seconds=30)


class SessionIndexCorruptError(Exception):
    pass


@dataclass(frozen=True, kw_only=True)
class SessionRecord:
    id: str
    level: str
    created_at: str
    last_active_at: str
    last_seen_generation: int = 0
    name: str | None = None


def _index_path(sessions_root: Path, session_id: str) -> Path:
    return Path(sessions_root) / session_id / "index.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_session(sessions_root: Path, level: str, *, last_seen_generation: int = 0) -> SessionRecord:
    """`last_seen_generation` should be the level's `LevelContext.generation[0]` at the moment of
    creation (the caller, `app.py`'s `create_session_route`, reads it fresh and passes it through) --
    NOT the dataclass default of 0. Otherwise a session created on a level whose generation counter
    is already > 0 (any level whose trunk has changed on disk even once since the server started --
    common, not exotic) would immediately report `changes_available: True` for a change that
    happened before this session ever existed, which it never had a chance to "miss".

    Race between the caller's read of the live generation and this write: safe by construction, not
    by locking. `generation[0]` only ever increases (a monotonic counter, bumped once per settled
    trunk change), so a plain read can only ever return the CURRENT value or a slightly-earlier one
    -- never one from later. If a settle event lands in the gap between the caller's read and this
    write, the session is seeded with a value that's a real, valid, merely-slightly-stale snapshot;
    the ONLY possible effect is `changes_available` reporting `True` sooner than it strictly needed
    to (a harmless, momentary "reload available" banner for a change this session's first Load would
    pick up anyway) -- never `False` when a real change is being missed. That asymmetry is why no
    lock is needed here: the race can only bias toward the safe (over-notify) side, never the unsafe
    (silently-stale) one."""
    now = _now()
    rec = SessionRecord(id=uuid7(), level=level, created_at=now, last_active_at=now,
                        last_seen_generation=last_seen_generation)
    atomic_write_json(_index_path(sessions_root, rec.id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": rec.last_active_at, "last_seen_generation": rec.last_seen_generation,
    })
    return rec


def get_session(sessions_root: Path, session_id: str) -> SessionRecord | None:
    p = _index_path(sessions_root, session_id)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return SessionRecord(
            id=data["id"], level=data["level"], created_at=data["created_at"],
            last_active_at=data["last_active_at"],
            last_seen_generation=data.get("last_seen_generation", 0),
            name=data.get("name"),
        )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SessionIndexCorruptError(
            f"session {session_id}: index.json at {p} is unreadable: {exc}"
        ) from exc


def list_sessions(sessions_root: Path) -> list[SessionRecord]:
    root = Path(sessions_root)
    if not root.is_dir():
        return []
    out = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            rec = get_session(sessions_root, child.name)
        except SessionIndexCorruptError:
            # One corrupt session must not take down the whole listing (review finding) --
            # skip it, but don't drop the fact on the floor either.
            logger.warning("session_index_corrupt_skipped", extra={"session_id": child.name})
            continue
        if rec is not None:
            out.append(rec)
    return out


def delete_session(sessions_root: Path, session_id: str) -> None:
    d = Path(sessions_root) / session_id
    shutil.rmtree(d, ignore_errors=True)


def touch_session(sessions_root: Path, session_id: str) -> None:
    rec = get_session(sessions_root, session_id)
    if rec is None:
        return
    last = datetime.strptime(rec.last_active_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - last < _TOUCH_THROTTLE:
        return
    atomic_write_json(_index_path(sessions_root, session_id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": _now(), "last_seen_generation": rec.last_seen_generation,
        "name": rec.name,
    })


def set_last_seen_generation(sessions_root: Path, session_id: str, generation: int) -> None:
    rec = get_session(sessions_root, session_id)
    if rec is None:
        return
    atomic_write_json(_index_path(sessions_root, session_id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": rec.last_active_at, "last_seen_generation": generation,
        "name": rec.name,
    })


def set_name(sessions_root: Path, session_id: str, name: str | None) -> None:
    """Empty/whitespace-only persists as `None` -- the caller (`app.py`'s rename route) is
    responsible for that normalization; this just writes whatever it's given."""
    rec = get_session(sessions_root, session_id)
    if rec is None:
        return
    atomic_write_json(_index_path(sessions_root, session_id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": rec.last_active_at, "last_seen_generation": rec.last_seen_generation,
        "name": name,
    })
