#!/usr/bin/env python3
"""Round-2 (post-`528e602` CsgOper::Active fix) copy of `prefix_search_lib.py`, repointed at this
investigation's OWN worktree (`agent-ae0566a6958bb95c7`) instead of the now-gone
`nsfhq04-residual-investigation` worktree the original hardcoded. Same shared prefix-binary-search
library: native in-process build + live-editor `build_ued_golden.py` build, per-*N* compare.

CRITICAL (per the original's own header + the findings-ledger methodology note): import the
`uedcli` PYTHON PACKAGE from THIS ISOLATED WORKTREE only, never from `/workspace/uedcli` (the
shared main checkout, which other concurrent agents may be actively editing) or from any other
session's worktree. `WORKTREE` below is computed from `__file__`, so it always resolves to
wherever this script itself lives.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[5]  # harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> ROOT
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

BUILD_SCRIPT = WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py"
PYEXE = str(WORKTREE / ".venv/bin/python")

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402


class PrefixSearch:
    def __init__(self, level_name, src_trunk, prefix_root, project_env):
        self.level_name = level_name
        self.src_trunk = Path(src_trunk)
        self.prefix_root = Path(prefix_root)
        os.environ["UEDCLI_PROJECT"] = str(project_env)
        self.level, self.ranks = trunk.read_level(self.src_trunk)
        ci = class_index()
        self.brush_names = [n for n in self.level.order
                             if self.level.actors[n].brush is not None
                             and BM._in_world_csg(self.level.actors[n], ci)]
        self.other_names = [n for n in self.level.order if n not in set(self.brush_names)]
        print(f"[{level_name}] {len(self.level.actors)} actors; {len(self.brush_names)} "
              f"world-csg brushes; {len(self.other_names)} other actors")

    def native_counts(self, n):
        ins = [BM._build_brush_input(nm, self.level.actors[nm]) for nm in self.brush_names[:n]]
        built = uedcli_native.build_geometry_bspcsg(ins)
        nbody = uedcli_native.serialize_model(built)
        return UM.parse_model_body(nbody, 0, len(nbody))

    def _write_prefix_trunk(self, n):
        keep = set(self.other_names) | set(self.brush_names[:n])
        new_order = [nm for nm in self.level.order if nm in keep]
        dst = self.prefix_root / f"n{n:04d}" / f"maps/{self.level_name}"
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        new_level = type(self.level)(
            actors={k: v for k, v in self.level.actors.items() if k in keep}, order=new_order)
        new_ranks = {k: v for k, v in self.ranks.items() if k in keep}
        trunk.write_level(dst, new_level, new_ranks)
        proj = dst.parent.parent
        (proj / "uedcli.toml").write_text('game = "deusex"\nmaps = "maps"\n')
        return dst, proj

    @staticmethod
    def _parse_golden(path):
        pkg = UT.load_package(str(path))
        models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
        mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
        return UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])

    def editor_counts(self, n, *, force=False):
        dst, proj = self._write_prefix_trunk(n)
        golden = proj / f"golden_n{n:04d}.dx"
        if golden.exists() and not force:
            print(f"  [n={n}] reusing existing golden {golden}")
        else:
            cmd = [PYEXE, str(BUILD_SCRIPT), "--trunk", str(dst), "--out", str(golden),
                   "--world-only", "--no-light", "--no-obj-load", "--overwrite"]
            print(f"  [n={n}] building editor golden: {' '.join(cmd)}", flush=True)
            r = subprocess.run(cmd, cwd=str(WORKTREE))
            if r.returncode != 0:
                raise RuntimeError(f"build_ued_golden.py failed for n={n} (rc={r.returncode})")
        return self._parse_golden(golden)

    def compare(self, n, *, force=False):
        nm = self.native_counts(n)
        gm = self.editor_counts(n, force=force)
        d_nodes = len(nm.nodes) - len(gm.nodes)
        d_leaves = len(nm.leaves) - len(gm.leaves)
        d_surfs = len(nm.surfs) - len(gm.surfs)
        label = self.brush_names[n - 1] if n >= 1 else "-"
        print(f"n={n:4d} brush={label:20s} "
              f"native(nodes={len(nm.nodes)},surfs={len(nm.surfs)},leaves={len(nm.leaves)}) "
              f"editor(nodes={len(gm.nodes)},surfs={len(gm.surfs)},leaves={len(gm.leaves)}) "
              f"d_nodes={d_nodes:+d} d_surfs={d_surfs:+d} d_leaves={d_leaves:+d}")
        return d_nodes, d_surfs, d_leaves

    def binary_search(self):
        lo, hi = 1, len(self.brush_names)
        d = self.compare(hi)
        if d == (0, 0, 0):
            print("full prefix is EXACT -- nothing to localize.")
            return None
        d0 = self.compare(lo)
        if d0 != (0, 0, 0):
            print(f"n={lo} ALREADY diverges -- cannot binary search from lo=1.")
            return lo
        while hi - lo > 1:
            mid = (lo + hi) // 2
            d = self.compare(mid)
            if d == (0, 0, 0):
                lo = mid
            else:
                hi = mid
        print(f"\nFIRST DIVERGING BRUSH [{self.level_name}]: n={hi} -> {self.brush_names[hi-1]} "
              f"(prefix n={lo}={self.brush_names[lo-1]} exact, n={hi} not)")
        return hi
