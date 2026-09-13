#!/usr/bin/env python3
"""Ad-hoc: run native's build against a cached actor-parity subset trunk, for UEDCLI_PORTAL_TRACE_NEAR."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_HARNESS = ROOT / "dev/docs/spikes/2026-08-31-native-parity-report/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPORT_HARNESS))

import parity_compare as pc  # noqa: E402

subset = Path(sys.argv[1]).resolve()
project_root = subset.parent.parent
dx, warn = pc.build_native_lit_dx(subset, project_root)
print(f"built {len(dx)} bytes, warnings={warn[:3]}", file=sys.stderr)
