#!/usr/bin/env python3
"""Build a level's first-N-actor native package with a CHOSEN `uedcli_native` build on `sys.path`.

Lets one session compare two compiled extensions on the same input without touching the venv's
installed wheel: unpack each wheel somewhere, then

    .venv/bin/python run_native.py <unpacked-wheel-dir> <shipped.dx> <N>

The result lands where `actor_parity.py` puts it (`_scratch/actor-parity/<level>/native_N<n>.dx`),
so `parity_gate.py` scores it unchanged. `UEDCLI_PERM_MARGIN=<leaf>` (with the margin probe of
`permeating_margin_probe.patch` compiled in) dumps that leaf's flood decisions to stderr.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HARNESS = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"

so_dir, dx, n = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), int(sys.argv[3])
sys.path.insert(0, str(so_dir))
sys.path.insert(1, str(HARNESS))

import uedcli_native  # noqa: E402

print("uedcli_native from:", uedcli_native.__file__, file=sys.stderr)

import actor_parity as ap  # noqa: E402

trunk_dir, name = ap._resolve_trunk(dx, "deusex")
print("native ->", ap.build_native(ap.make_subset(trunk_dir, name, n), name, n))
