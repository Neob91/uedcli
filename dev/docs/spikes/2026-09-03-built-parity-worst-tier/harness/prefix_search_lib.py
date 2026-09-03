#!/usr/bin/env python3
"""Shared library: binary-search a structural-only world-CSG brush ORDER to localize the first
brush whose incremental CSG add makes native's Pass-1 tree diverge from the real editor's.
Generalizes `fc08_prefix_search.py` (level-specific) to any level trunk. See that script's
docstring for the full rationale (freeclinic08-nsfhq04-1-surf-under-build-root, 4th continuation).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

# CRITICAL: import the `uedcli` PYTHON PACKAGE from the ISOLATED WORKTREE, never from the shared
# main checkout `/workspace/uedcli` -- a concurrent agent has uncommitted, actively-changing edits
# to `uedcli/native/brush_marshal.py` there (the Vandenberg CsgOper investigation), and importing
# from that path silently reads THEIR in-flight code instead of this investigation's clean,
# master-based worktree copy. Discovered live this round after `_build_brush_input` calls started
# nondeterministically raising `BuildError: unknown CsgOper 0` -- traced to `sys.path` resolving
# `uedcli.native.brush_marshal` from `/workspace/uedcli` (main checkout) instead of the worktree.
# Self-resolve to THIS worktree (dev/docs/spikes/<slug>/harness -> root) so the import-contamination
# trap the comment above describes cannot recur when the harness is copied between worktrees.
WORKTREE = Path(__file__).resolve().parents[5]  # harness/<slug>/spikes/docs/dev -> repo root
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

    @staticmethod
    def _yield_editor_slot(timeout=3600, poll=60):
        """One uned container at a time (session rule): if another `uned-*` is running (e.g. the
        corpus sweep), wait for it before starting our ephemeral editor."""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            r = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                               capture_output=True, text=True)
            others = [nm for nm in r.stdout.split() if nm.startswith("uned-")]
            if not others:
                return
            print(f"  editor slot busy ({others}); yielding {poll}s", flush=True)
            time.sleep(poll)
        raise RuntimeError(f"editor slot still busy after {timeout}s")

    def editor_counts(self, n, *, force=False):
        dst, proj = self._write_prefix_trunk(n)
        golden = proj / f"golden_n{n:04d}.dx"
        if golden.exists() and not force:
            print(f"  [n={n}] reusing existing golden {golden}")
        else:
            self._yield_editor_slot()
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
