"""Staging store for GUI actor edits: persists staged actor locations with baseline tracking.
Stores actor T3D text in content-addressed blobs, and staged/baseline coordinates in a per-level
manifest. Re-staging an actor preserves its original baseline, enabling conflict detection on Save."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, kw_only=True)
class StagedActor:
    """A staged actor's baseline and current (staged) location."""
    baseline_location: tuple[Decimal, Decimal, Decimal]
    staged_location: tuple[Decimal, Decimal, Decimal]
    blob_hash: str


class StagingStore:
    """Staging store for staged actor edits: blobs + per-level manifest."""

    def __init__(self, root: Path) -> None:
        """Initialize the store at `root` (typically `.uedcli/snapshots`)."""
        self.root = Path(root)

    def stage(
        self,
        level: str,
        actor_name: str,
        *,
        actor_t3d_text: str,
        baseline_location: tuple[Decimal, Decimal, Decimal],
        staged_location: tuple[Decimal, Decimal, Decimal],
    ) -> None:
        """Stage an actor edit: compute blob hash, write blob if missing, update manifest entry.
        Re-staging the same actor keeps its original baseline_location; only staged_location and
        blob_hash are updated."""
        # Compute blob hash
        blob_hash = hashlib.sha256(actor_t3d_text.encode("utf-8")).hexdigest()

        # Write blob if it doesn't exist
        blob_dir = self.root / "blobs" / blob_hash[:2]
        blob_path = blob_dir / blob_hash
        if not blob_path.exists():
            blob_dir.mkdir(parents=True, exist_ok=True)
            blob_path.write_text(actor_t3d_text, encoding="utf-8")

        # Read existing manifest for this level
        manifest_path = self.root / "staged" / f"{level}.json"
        manifest: dict[str, dict] = {}
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        # If actor already staged, keep its baseline; otherwise use the provided one
        if actor_name in manifest:
            existing_baseline = manifest[actor_name]["baseline_location"]
        else:
            existing_baseline = [str(x) for x in baseline_location]

        # Update manifest entry with new staged_location and blob_hash
        manifest[actor_name] = {
            "baseline_location": existing_baseline,
            "staged_location": [str(x) for x in staged_location],
            "blob_hash": blob_hash,
        }

        # Write manifest
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def read_staged(self, level: str) -> dict[str, StagedActor]:
        """Read all staged actors for a level, or {} if the manifest doesn't exist."""
        manifest_path = self.root / "staged" / f"{level}.json"
        if not manifest_path.exists():
            return {}

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        result: dict[str, StagedActor] = {}
        for actor_name, entry in data.items():
            result[actor_name] = StagedActor(
                baseline_location=tuple(Decimal(x) for x in entry["baseline_location"]),  # type: ignore
                staged_location=tuple(Decimal(x) for x in entry["staged_location"]),  # type: ignore
                blob_hash=entry["blob_hash"],
            )
        return result

    def clear_actor(self, level: str, actor_name: str) -> None:
        """Remove a single staged actor from the manifest, if it exists."""
        manifest_path = self.root / "staged" / f"{level}.json"
        if not manifest_path.exists():
            return

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if actor_name in manifest:
            del manifest[actor_name]
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def discard(self, level: str) -> None:
        """Discard all staged edits for a level (delete the manifest file)."""
        manifest_path = self.root / "staged" / f"{level}.json"
        if manifest_path.exists():
            manifest_path.unlink()
