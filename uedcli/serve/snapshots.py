"""Staging store for GUI actor edits: persists staged actor locations with baseline tracking.
Stores actor T3D text in content-addressed blobs (shared across every session, in `blobs_root`),
and staged/baseline coordinates in a per-session manifest (`sessions_root/<session_id>/staged.json`).
Re-staging an actor preserves its original baseline, enabling conflict detection on Save."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .atomic_io import atomic_write_json


@dataclass(frozen=True, kw_only=True)
class StagedActor:
    """A staged actor's baseline and current (staged) location."""
    baseline_location: tuple[Decimal, Decimal, Decimal]
    staged_location: tuple[Decimal, Decimal, Decimal]
    blob_hash: str


class StagingStore:
    """Staging store for staged actor edits: shared blobs + per-session manifest."""

    def __init__(self, sessions_root: Path, blobs_root: Path) -> None:
        """Initialize the store with a per-session manifest root and a shared content-addressed
        blob root (typically `.uedcli/sessions` and `.uedcli/staging/blobs`)."""
        self.sessions_root = Path(sessions_root)
        self.blobs_root = Path(blobs_root)

    def _manifest_path(self, session_id: str) -> Path:
        return self.sessions_root / session_id / "staged.json"

    def _blob_path(self, blob_hash: str) -> Path:
        return self.blobs_root / blob_hash[:2] / blob_hash

    def stage(
        self,
        session_id: str,
        actor_name: str,
        *,
        actor_t3d_text: str,
        baseline_location: tuple[Decimal, Decimal, Decimal],
        staged_location: tuple[Decimal, Decimal, Decimal],
    ) -> None:
        """Stage an actor edit: compute blob hash, write blob if missing, update manifest entry.
        Re-staging the same actor keeps its original baseline_location; only staged_location and
        blob_hash are updated."""
        blob_hash = hashlib.sha256(actor_t3d_text.encode("utf-8")).hexdigest()
        blob_path = self._blob_path(blob_hash)
        if not blob_path.exists():
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_text(actor_t3d_text, encoding="utf-8")

        manifest = self._read_manifest(session_id)
        existing = manifest.get(actor_name)
        # Re-staging an already-staged actor keeps its ORIGINAL baseline -- the caller's
        # baseline_location argument is only used the first time this actor is staged in this
        # session. Overwriting it on every re-stage would corrupt Save's conflict check, which
        # compares this baseline against the trunk's CURRENT state, not against whatever the most
        # recent drag happened to load.
        effective_baseline = (
            [Decimal(c) for c in existing["baseline_location"]] if existing is not None
            else list(baseline_location)
        )
        manifest[actor_name] = {
            "baseline_location": [str(c) for c in effective_baseline],
            "staged_location": [str(c) for c in staged_location],
            "blob_hash": blob_hash,
        }
        atomic_write_json(self._manifest_path(session_id), manifest)

    def read_staged(self, session_id: str) -> dict[str, StagedActor]:
        """Read all staged actors for a session, or {} if the manifest doesn't exist."""
        manifest = self._read_manifest(session_id)
        return {
            name: StagedActor(
                baseline_location=tuple(Decimal(c) for c in v["baseline_location"]),  # type: ignore
                staged_location=tuple(Decimal(c) for c in v["staged_location"]),  # type: ignore
                blob_hash=v["blob_hash"],
            )
            for name, v in manifest.items()
        }

    def clear_actor(self, session_id: str, actor_name: str) -> None:
        """Remove a single staged actor from the manifest, if it exists."""
        manifest = self._read_manifest(session_id)
        if actor_name not in manifest:
            return
        manifest.pop(actor_name, None)
        atomic_write_json(self._manifest_path(session_id), manifest)

    def discard(self, session_id: str) -> None:
        """Discard all staged edits for a session (delete the manifest file)."""
        self._manifest_path(session_id).unlink(missing_ok=True)

    def _read_manifest(self, session_id: str) -> dict:
        p = self._manifest_path(session_id)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def evict_unreferenced_blobs(self, *, live_hashes: set[str], max_bytes: int | None = None) -> dict:
        """Delete blobs no session's staged.json names, oldest-atime-first. A blob named in
        `live_hashes` is NEVER deleted, regardless of budget. With `max_bytes=None`, every
        unreferenced blob is deleted (no budget to stay under); with `max_bytes` given, only enough
        unreferenced blobs are deleted (oldest first) to bring total usage back under it. Caller
        computes `live_hashes` by scanning every sessions/*/staged.json -- see app.py's eviction
        orchestration (Task 9) for the lock scope this must run under."""
        candidates: list[tuple[float, int, Path]] = []
        total = 0
        if self.blobs_root.is_dir():
            for shard in self.blobs_root.iterdir():
                if not shard.is_dir():
                    continue
                for f in shard.iterdir():
                    if not f.is_file():
                        continue
                    st = f.stat()
                    total += st.st_size
                    if f.name not in live_hashes:
                        candidates.append((st.st_atime, st.st_size, f))
        evicted = freed = 0
        candidates.sort(key=lambda c: c[0])
        for _atime, size, path in candidates:
            if max_bytes is not None and total <= max_bytes:
                break
            try:
                path.unlink()
            except OSError:
                continue
            total -= size
            evicted += 1
            freed += size
        return {"evicted": evicted, "freed_bytes": freed, "kept_bytes": total}
