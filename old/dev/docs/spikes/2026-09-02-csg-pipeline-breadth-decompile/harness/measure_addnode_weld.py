"""Offline A/B: native geometry counts with UEDCLI_BSPCSG_ADDNODE_WELD off vs on, vs the cached
golden, for the tracked levels. No editor — builds native in-process against a cached parity trunk,
reads golden node/surf/leaf/verts/points/vectors counts from the cached golden .dx.

Run each level in its OWN subprocess so the env flag takes effect (the flag is read at build time,
and the parity harness imports must see it). Prints a per-level table: golden counts, native(off),
native(on), and the delta each produces.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path("/workspace/uedcli/.claude/worktrees/agent-a77ba41fcc29431d9")
PARITY_HARNESS = ROOT / "dev/docs/spikes/2026-08-31-native-parity-report/harness"
CACHE = Path("/tmp/uedcli-parity-cache")
PY = str(ROOT / ".venv/bin/python")

LEVELS = [
    "15_area51_entrance", "04_nyc_nsfhq", "00_trainingfinal", "12_vandenberg_gas",
    "03_nyc_unatcohq", "08_nyc_bar", "dx", "03_nyc_747", "14_oceanlab_lab",
    "08_nyc_freeclinic", "06_hongkong_wanchai_market",
]


def cache_for(level: str) -> Path | None:
    for m in CACHE.glob("*/meta.json"):
        d = json.load(open(m))
        if d.get("level_name") == level and d.get("status") == "complete":
            return m.parent
    return None


WORKER = r'''
import sys, json
from pathlib import Path
ROOT = Path("%s")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "%s")
import parity_pipeline as pp
import parity_compare as pc
dx_path = Path(sys.argv[1])
layout, level_name, trunk_dir, cache_hit = pp.ensure_golden(dx_path, cache_root=Path("/tmp/uedcli-parity-cache"))
g = pc.compare_geometry(trunk_dir, layout.golden)
out = {}
for f in ("nodes","surfs","leaves","verts","points","vectors"):
    out[f] = [getattr(g.native, f), getattr(g.golden, f)]
print("RESULT " + json.dumps(out))
''' % (ROOT, PARITY_HARNESS)


def src_dx(level: str) -> Path | None:
    cd = cache_for(level)
    if cd is None:
        return None
    d = json.load(open(cd / "meta.json"))
    p = Path(d.get("source_dx", ""))
    return p if p.is_file() else None


def run(level: str, weld: bool):
    dx = src_dx(level)
    if dx is None:
        return f"NO SOURCE DX for {level}"
    env = dict(os.environ)
    if weld:
        env["UEDCLI_BSPCSG_ADDNODE_WELD"] = "1"
    else:
        env.pop("UEDCLI_BSPCSG_ADDNODE_WELD", None)
    p = subprocess.run([PY, "-c", WORKER, str(dx)],
                       env=env, capture_output=True, text=True, timeout=1800)
    for line in p.stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[7:])
    return f"FAIL rc={p.returncode}: {(p.stderr.strip()[-500:] or p.stdout.strip()[-300:])}"


def main():
    sel = sys.argv[1:] or LEVELS
    for level in sel:
        off = run(level, False)
        on = run(level, True)
        print(f"\n=== {level} ===")
        if isinstance(off, str) or off is None:
            print(f"  off: {off}")
            continue
        print(f"  {'count':8} {'golden':>8} {'off':>8} {'d_off':>7} {'on':>8} {'d_on':>7}")
        for f in ("nodes", "surfs", "leaves", "verts", "points", "vectors"):
            gn = off[f][1]
            no = off[f][0]
            if isinstance(on, dict):
                nn = on[f][0]
                print(f"  {f:8} {gn:8} {no:8} {no-gn:+7} {nn:8} {nn-gn:+7}")
            else:
                print(f"  {f:8} {gn:8} {no:8} {no-gn:+7}   on={on}")


if __name__ == "__main__":
    main()
