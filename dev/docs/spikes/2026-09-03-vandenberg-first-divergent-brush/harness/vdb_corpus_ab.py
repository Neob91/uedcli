#!/usr/bin/env python3
"""Offline corpus sweep: for every complete `/tmp/uedcli-parity-cache/<hash>` entry, build the
cached trunk with THIS worktree's `build_geometry_bspcsg` and print count deltas vs the cached
golden (native - golden, nodes/surfs/leaves/verts/points/vectors) plus the native build's sha256
(for byte-level A/B between two code states).

Usage: .venv/bin/python vdb_corpus_ab.py [level-substring ...] > table.txt
"""
import hashlib
import json
import os
import sys
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

CACHE = Path("/tmp/uedcli-parity-cache")
TRUNKS = Path("/workspace/uedcli/.claude/worktrees/uedcli-parity-trunk-cache")

from uedcli import trunk as trunk_mod              # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                                # noqa: E402
import utexture_decode as UT                        # noqa: E402
from spike_classindex import class_index            # noqa: E402


def golden_model(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    return UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])


def main() -> int:
    want = sys.argv[1:]
    entries = []
    for d in sorted(CACHE.iterdir()):
        meta = d / "meta.json"
        if not meta.is_file():
            continue
        m = json.loads(meta.read_text())
        if m.get("status") != "complete":
            continue
        if want and not any(w.lower() in m["level_name"].lower() for w in want):
            continue
        entries.append((m["level_name"], d))
    ci = None
    for name, d in entries:
        trunk_dir = TRUNKS / d.name / "trunk"
        os.environ["UEDCLI_PROJECT"] = str(trunk_dir)
        if ci is None:
            ci = class_index()
        level, _ = trunk_mod.read_level(trunk_dir / "maps" / name)
        names = [n for n in level.order
                 if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
        try:
            ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
            built = uedcli_native.build_geometry_bspcsg(ins)
        except Exception as e:
            print(f"{name:28s} BUILD ERROR: {e}")
            continue
        nbody = uedcli_native.serialize_model(built)
        nm = UM.parse_model_body(nbody, 0, len(nbody))
        gm = golden_model(d / "golden.dx")
        deltas = {f: len(getattr(nm, f)) - len(getattr(gm, f))
                  for f in ("nodes", "surfs", "leaves", "verts", "points", "vectors")}
        sha = hashlib.sha256(nbody).hexdigest()[:12]
        exact = sum(1 for v in deltas.values() if v == 0)
        print(f"{name:28s} {exact}/6 " + " ".join(f"{k}={v:+d}" for k, v in deltas.items())
              + f" sha={sha}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
