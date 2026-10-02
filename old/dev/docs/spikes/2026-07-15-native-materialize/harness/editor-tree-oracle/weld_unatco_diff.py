#!/usr/bin/env python3
r"""Full-UNATCO weld-log comparator: editor INS (bspopt_insert_unatco.py) vs native NINS/NCAP.

Reports, keyed permutation-invariantly on (plane@1e-3, P@1e-2) since node ids don't align across the
two trees:
  * totals: editor attempts = splices + cap refusals (INS lines with nv>=15); native splices + NCAP;
  * splice multiset diff + the fraction of divergent welds sitting on a plane where the FINAL trees
    themselves disagree (causality check: weld divergence downstream of repartition divergence);
  * shared-weld ORDER alignment (positional match + difflib ratio);
  * orphan accounting: pass-1 orphan slots = sum(nv at splice) per side, and the editor's pre-pass1
    pool inferred as golden_pool - sum(nv+1) (identity-checked against the golden .dx).

Numbers land in board item `front-2-re-characterized-diffuse-repartition` (follow-up 2026-08-25).

Usage:
  UEDCLI_OPTGEOM_DEBUG=1 native build 2>/tmp/nins.log   # e.g. via unatco_subset + build_geometry_bspcsg
  weld_unatco_diff.py /tmp/nins.log <native.bin> [golden.dx]
    native.bin = serialize_model() bytes of the same build; golden default /tmp/UEDGolden_unatco_full.dx
"""
import difflib
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT))
from uedcli.native import umodel as UM  # noqa: E402
from uedcli.native.pkg_write import parse_package  # noqa: E402

HERE = Path(__file__).resolve().parent
EDITOR_INS = HERE / "logs" / "bspopt-insert-unatco.log"
RX = re.compile(r'^(NINS|INS|NCAP) node=(\d+) edge=(-?\d+) point=(-?\d+) plane=(\S+) P=(\S+?)(?: nv=(\d+))?\s*$')


def parse(path):
    out = []
    for line in open(path, errors="replace"):
        m = RX.match(line.strip())
        if not m:
            continue
        plane3 = tuple(round(float(x), 3) for x in m.group(5).split(','))
        plane2 = tuple(round(float(x), 2) for x in m.group(5).split(','))
        P = tuple(round(float(x), 2) for x in m.group(6).split(','))
        nv = int(m.group(7)) if m.group(7) else None
        out.append((m.group(1), plane3, plane2, P, nv))
    return out


def main():
    nins_log = Path(sys.argv[1])
    native_bin = Path(sys.argv[2])
    golden = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/tmp/UEDGolden_unatco_full.dx")

    ed_all = parse(EDITOR_INS)
    ed_ref = [e for e in ed_all if e[0] == "INS" and e[4] is not None and e[4] >= 15]
    ed = [e for e in ed_all if e[0] == "INS" and not (e[4] is not None and e[4] >= 15)]
    nat_all = parse(nins_log)
    nat = [e for e in nat_all if e[0] == "NINS"]
    nat_ref = [e for e in nat_all if e[0] == "NCAP"]
    print(f"editor: {len(ed) + len(ed_ref)} attempts = {len(ed)} splices + {len(ed_ref)} cap refusals")
    print(f"native: {len(nat)} splices + {len(nat_ref)} cap refusals")

    raw = native_bin.read_bytes()
    nm = UM.parse_model_body(raw, 0, len(raw))
    pkg = parse_package(golden.read_bytes())
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    gm = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])

    def pk2(p):
        return tuple(round(c, 2) for c in p)
    tn = Counter(pk2(n.plane) for n in nm.nodes)
    tg = Counter(pk2(n.plane) for n in gm.nodes)
    disagree = set(tn - tg) | set(tg - tn)

    kw_n = Counter((p2, P) for _, _, p2, P, _ in nat)
    kw_e = Counter((p2, P) for _, _, p2, P, _ in ed)
    shared, on, oe = kw_n & kw_e, kw_n - kw_e, kw_e - kw_n
    print(f"splice multiset: shared={sum(shared.values())} only-native={sum(on.values())} "
          f"only-editor={sum(oe.values())}")
    for name, c in (("shared", shared), ("only-native", on), ("only-editor", oe)):
        tot = sum(c.values())
        hit = sum(v for (p, P), v in c.items() if p in disagree)
        print(f"  {name}: {hit}/{tot} ({100*hit/tot:.1f}%) on a tree-disagreement plane")

    def filt(seq, budget):
        b = dict(budget)
        out = []
        for _, _, p2, P, _ in seq:
            k = (p2, P)
            if b.get(k, 0) > 0:
                b[k] -= 1
                out.append(k)
        return out
    es, ns = filt(ed, shared), filt(nat, shared)
    same = sum(1 for a, b in zip(es, ns) if a == b)
    r = difflib.SequenceMatcher(a=es, b=ns, autojunk=False).ratio()
    print(f"shared-weld order: {same}/{len(es)} positionally aligned; difflib ratio {r:.3f}")

    ed_orph = sum(nv for *_, nv in ed)
    g_pool = len(gm.verts)
    pre = g_pool - (ed_orph + len(ed))
    print(f"pass-1 orphan slots: editor sum(nv)={ed_orph}; editor pre-pass1 pool inferred "
          f"{pre} (identity: {pre} + {ed_orph + len(ed)} = {g_pool} golden pool)")
    n_live = sum(n.num_vertices for n in nm.nodes)
    n_pool = len(nm.verts)
    print(f"native: pool={n_pool} live={n_live} orphans={n_pool - n_live} "
          f"(pre-pass1 pool = pool - sum(nv+1) over NINS; see UEDCLI_BSPCSG_PREOPT_NODES for direct dump)")


if __name__ == "__main__":
    main()
