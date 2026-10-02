#!/usr/bin/env python3
"""Re-run native's WanChai N=201 lit build with `UEDCLI_VISGATE_TRACE_SURF=-1` (whole-traversal
trace) for Light431's straight-down cube face, to see EVERY node visited before node 774 (surf 616)
-- in particular node 776 (surf 2, `PF_FakeBackdrop` sky), the last large occluder the targeted trace
(`native-trace-surf616-light431.log`) already showed runs right before it.

Usage: full_trace_light431.py <N201 trunk maps dir> <project root> > full-trace.log
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-08-31-native-parity-report/harness"))

LIGHT431_LOC = "-1160.745361,-807.899902,220.417908"


def main() -> int:
    trunk_dir = Path(sys.argv[1]).resolve()
    project_root = Path(sys.argv[2]).resolve()
    os.environ.setdefault("UEDCLI_VISGATE_TRACE_SURF", "-1")
    os.environ.setdefault("UEDCLI_VISGATE_TRACE_LOC", LIGHT431_LOC)

    import parity_compare as pc
    dx, warn = pc.build_native_lit_dx(trunk_dir, project_root)
    if warn:
        print(f"warnings: {warn[:5]}", file=sys.stderr)
    print(f"built {len(dx)} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
