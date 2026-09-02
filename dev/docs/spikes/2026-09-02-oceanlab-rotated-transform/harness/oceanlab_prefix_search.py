#!/usr/bin/env python3
"""OceanLab Lab world-CSG-brush prefix binary search -- generalizes
`dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness/prefix_search_lib.py`'s `PrefixSearch`
to this level and this round's worktree. OceanLab's node/leaf residual (+465/+86, the largest in
the corpus) is the target: does it localize to one brush (like Brush586/1852/8321/842 on the
smaller-residual levels), or does the divergence appear early and grow roughly proportionally with
brush-set size (a diffuse, systemic pattern, per this round's task framing)?

Usage: .venv/bin/python oceanlab_prefix_search.py
Run as a bounded background job -- each prefix build is a real editor round-trip
(dev/docs/rules/background-work.md).
"""
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/agent-ad11af2d5c5e7d2ab")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness"))

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402
import os
import shutil
import subprocess

BUILD_SCRIPT = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py"
PYEXE = str(ROOT / ".venv/bin/python3")
CACHE = (ROOT / "_scratch/uedcli-parity-cache/"
         "4e3757c3f3b2144f3750084db83cdbbc8bd4412047aadffa17c0494f4fa51a39")
SRC_TRUNK = CACHE / "trunk/maps/14_oceanlab_lab"
PREFIX_ROOT = ROOT / "_scratch/oceanlab-prefix"


class PrefixSearch:
    def __init__(self, level_name, src_trunk, prefix_root):
        self.level_name = level_name
        self.src_trunk = Path(src_trunk)
        self.prefix_root = Path(prefix_root)
        # project root is the TRUNK's PARENT (holds uedcli.toml), not the level dir itself.
        os.environ["UEDCLI_PROJECT"] = str(CACHE / "trunk")
        self.level, self.ranks = trunk.read_level(self.src_trunk)
        ci = class_index()
        self.brush_names = [n for n in self.level.order
                             if self.level.actors[n].brush is not None
                             and BM._in_world_csg(self.level.actors[n], ci)]
        self.other_names = [n for n in self.level.order if n not in set(self.brush_names)]
        print(f"[{level_name}] {len(self.level.actors)} actors; {len(self.brush_names)} "
              f"world-csg brushes; {len(self.other_names)} other actors", flush=True)

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
            print(f"  [n={n}] reusing existing golden {golden}", flush=True)
        else:
            cmd = [PYEXE, str(BUILD_SCRIPT), "--trunk", str(dst), "--out", str(golden),
                   "--world-only", "--no-light", "--no-obj-load", "--overwrite"]
            print(f"  [n={n}] building editor golden: {' '.join(cmd)}", flush=True)
            r = subprocess.run(cmd, cwd=str(ROOT))
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
              f"d_nodes={d_nodes:+d} d_surfs={d_surfs:+d} d_leaves={d_leaves:+d}", flush=True)
        return d_nodes, d_surfs, d_leaves

    def sweep(self, ns):
        """Sample the residual at a fixed set of prefix lengths (not a binary search) -- what this
        round actually wants: does the delta jump once (localizes) or grow steadily (diffuse)?"""
        results = []
        for n in ns:
            d = self.compare(n)
            results.append((n, d))
        return results


def main():
    ps = PrefixSearch("14_oceanlab_lab", SRC_TRUNK, PREFIX_ROOT)
    total = len(ps.brush_names)
    # Geometric-ish sample of prefix lengths across the full 1886-brush range, so a single jump
    # vs steady growth is visible without paying for a full binary search's ~11 builds at large n
    # (each large-n build is a real editor round-trip over hundreds/thousands of brushes).
    sample_ns = sorted(set([
        100, 400, 800, 1200, 1600, total,
    ]))
    sample_ns = [n for n in sample_ns if n <= total]
    print(f"total world-csg brushes: {total}; sampling at {sample_ns}", flush=True)
    results = ps.sweep(sample_ns)
    print("\n=== SUMMARY ===", flush=True)
    for n, (dn, ds, dl) in results:
        print(f"n={n:5d}  d_nodes={dn:+6d}  d_surfs={ds:+5d}  d_leaves={dl:+5d}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
