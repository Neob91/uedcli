#!/usr/bin/env python3
"""Thin passthrough to `parity_gate.py` — kept for callers that reference this path.

Historically this disabled the x=448 point-dedup near-tie mask (`NODE_W_DEDUP_TOL=0`) to show what the
gate reported without the stopgap. That mask is now GONE: the divergence is fixed faithfully (native
dedups points with the editor's radius-pruned FindNearestVertex descent), so `parity_gate.py` is
already strict — this just forwards to it.

Run: `gate_nomask.py <native.dx> <ued.dx>`
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"))

import parity_gate as g  # noqa: E402

sys.argv = ["parity_gate.py"] + sys.argv[1:]
sys.exit(g.main())
