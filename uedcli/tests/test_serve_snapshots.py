"""`uedcli serve`'s staging store for GUI actor edits (Plan Task 1): write/read/clear/discard
staged actor locations with baseline tracking. No app/HTTP involved — pure unit tests."""
from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

from uedcli.serve.snapshots import StagingStore


def test_stage_read_restage_keeps_baseline_discard_clear(tmp_path: Path) -> None:
    store = StagingStore(tmp_path)
    frac = (Decimal("-1729.945068"), Decimal("0"), Decimal("512.5"))
    store.stage(
        "TestLevel", "Brush1",
        actor_t3d_text="Begin Actor Class=Brush Name=Brush1\nEnd Actor\n",
        baseline_location=frac,
        staged_location=(Decimal("10"), Decimal("0"), Decimal("0")),
    )
    staged = store.read_staged("TestLevel")
    assert staged["Brush1"].baseline_location == frac  # exact Decimal round-trip, not `== float(...)`
    assert staged["Brush1"].staged_location == (Decimal("10"), Decimal("0"), Decimal("0"))
    blob_path = tmp_path / "blobs" / staged["Brush1"].blob_hash[:2] / staged["Brush1"].blob_hash
    assert blob_path.is_file()

    # re-stage the SAME actor with a further move: baseline must not move
    store.stage(
        "TestLevel", "Brush1",
        actor_t3d_text="Begin Actor Class=Brush Name=Brush1\nEnd Actor\n",
        baseline_location=(Decimal("999"), Decimal("999"), Decimal("999")),  # a caller bug, by mistake
        staged_location=(Decimal("20"), Decimal("0"), Decimal("0")),
    )
    staged = store.read_staged("TestLevel")
    assert staged["Brush1"].baseline_location == frac  # unchanged
    assert staged["Brush1"].staged_location == (Decimal("20"), Decimal("0"), Decimal("0"))  # updated

    store.stage(
        "TestLevel", "Brush2",
        actor_t3d_text="Begin Actor Class=Brush Name=Brush2\nEnd Actor\n",
        baseline_location=(Decimal("1"), Decimal("1"), Decimal("1")),
        staged_location=(Decimal("2"), Decimal("2"), Decimal("2")),
    )
    store.clear_actor("TestLevel", "Brush1")
    staged = store.read_staged("TestLevel")
    assert "Brush1" not in staged
    assert "Brush2" in staged

    store.discard("TestLevel")
    assert store.read_staged("TestLevel") == {}
