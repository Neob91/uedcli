"""In-memory-only claim-token ownership, one per running process. Never written to disk -- a
restart wiping this is fine (spec's "restart safety" note): the three-state check treats an
unrecorded session the same as a legitimate first claim, not as a conflict."""
from __future__ import annotations

import threading
import uuid


class ClaimRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, str] = {}
        self._session_locks: dict[str, threading.Lock] = {}

    def mint(self, session_id: str) -> str:
        token = uuid.uuid4().hex
        with self._lock:
            self._tokens[session_id] = token
        return token

    def check(self, session_id: str, token: str) -> bool:
        with self._lock:
            current = self._tokens.get(session_id)
            if current is None:
                self._tokens[session_id] = token
                return True
            return current == token

    def lock_for(self, session_id: str) -> threading.Lock:
        with self._lock:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._session_locks[session_id] = lock
            return lock

    def forget(self, session_id: str) -> None:
        """Called on session close -- drops bookkeeping for an id that will never be reused."""
        with self._lock:
            self._tokens.pop(session_id, None)
            self._session_locks.pop(session_id, None)
