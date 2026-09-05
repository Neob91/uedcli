#!/usr/bin/env python3
"""Run `parity_gate.py` with the x=448 point-dedup near-tie mask DISABLED (NODE_W_DEDUP_TOL=0).

Shows what the gate would report if the stopgap mask were removed -- used to confirm UNATCO N8 still
FAILS without it (2 residuals: model node-plane W, polys soup base) and to check a candidate faithful
fix actually closes them rather than the mask hiding them.

Run: `gate_nomask.py <native.dx> <ued.dx>`
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
GATE = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
sys.path.insert(0, str(GATE))

import parity_gate as g  # noqa: E402

g.NODE_W_DEDUP_TOL = 0.0                       # disable the dedup-tie mask
sys.argv = ["parity_gate.py"] + sys.argv[1:]
sys.exit(g.main())
