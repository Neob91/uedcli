#!/usr/bin/env python3
"""SP-E.1 completion — canonical-compare the GENUINELY-reused successful builds vs a fresh build.

Cold review of results.md noted that the original SP-E.1 leg only compared `cold.dx == warm1.dx`,
but warm1 is the FIRST drive after boot (empty object pool) — it cannot exhibit the surviving-pool
contamination SP-E.1 exists to detect. The genuinely-reused successful builds are warm4 and warm6
(they ran after prior builds populated the pool). Their raw bytes differ from cold (object-table
renumbering, §82/§83), so this canonically compares them via the SAME oracle H3 uses
(`export_dx_level` → `canonical_level_hash`), in one throwaway editor.

Run: cd Tools/uedctl && .venv/bin/python dev/docs/spikes/2026-07-18-warm-editor-materialize/harness/warm_editor_canoncmp.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(TOOL))

from uedctl import config, trunk                      # noqa: E402
from uedctl import editor as editor_mod              # noqa: E402
from uedctl.container_assets import resource_mounts  # noqa: E402
from uedctl.normalize import canonical_level_hash    # noqa: E402
from uedctl.store_export import export_dx_level      # noqa: E402
from uedctl.uuid7 import uuid7                         # noqa: E402

OUT = TOOL / "_scratch/warm-spike"
CASTLE = TOOL / "_scratch/castle/uedctl"
TARGETS = ["cold", "warm1", "warm4", "warm6"]


def main():
    project = config.load_project(str(CASTLE))
    uc = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, uc)
    state_dir = config.state_dir(project.root, create=True)
    ed_id = uuid7()
    container = editor_mod.ensure_editor(ed_id, mounts=resource_mounts(search_dirs), state_dir=state_dir)
    hashes = {}
    try:
        for name in TARGETS:
            host = OUT / f"{name}.dx"
            if not host.exists():
                hashes[name] = None
                continue
            cpath = f"/work/cmp_{name}.dx"
            subprocess.run(["docker", "cp", str(host), f"{container}:{cpath}"],
                           check=True, capture_output=True, text=True)
            hashes[name] = canonical_level_hash(export_dx_level(container, cpath))
            print(f"{name}: {hashes[name]}", flush=True)
    finally:
        editor_mod.stop_editor(ed_id, state_dir)
    ref = hashes.get("cold")
    result = {"hashes": hashes,
              "warm1_eq_cold": hashes.get("warm1") == ref and ref is not None,
              "warm4_eq_cold": hashes.get("warm4") == ref and ref is not None,
              "warm6_eq_cold": hashes.get("warm6") == ref and ref is not None}
    (OUT / "warm_canoncmp_results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
