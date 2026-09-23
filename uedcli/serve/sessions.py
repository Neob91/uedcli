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


def _index_path(sessions_root: Path, session_id: str) -> Path:
    return Path(sessions_root) / session_id / "index.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_session(sessions_root: Path, level: str) -> SessionRecord:
    now = _now()
    rec = SessionRecord(id=uuid7(), level=level, created_at=now, last_active_at=now)
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
    })


def set_last_seen_generation(sessions_root: Path, session_id: str, generation: int) -> None:
    rec = get_session(sessions_root, session_id)
    if rec is None:
        return
    atomic_write_json(_index_path(sessions_root, session_id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": rec.last_active_at, "last_seen_generation": generation,
    })
