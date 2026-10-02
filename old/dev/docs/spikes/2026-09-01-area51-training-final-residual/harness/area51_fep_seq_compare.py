#!/usr/bin/env python3
"""Compare native's and the editor's FilterEdPoly node-visit SEQUENCE for Brush1852's
`i_brush_poly=4` (Area51 Entrance, n=507 prefix) -- the live trace this round's task exists to run.

Raw node indices are NOT comparable across sides (`area51_frag_diff.py` already established this --
node/parent numbering schemes are unrelated). Both traces instead carry the CLASSIFY PLANE each step
tests against: native's `N=(a,b,c,d)` (`bspcsg.rs` DESC trace, `d` = Base.Normal, the same convention
as UE1's `FPlane.W`) and the editor's `nodeN=(a,b,c,d)` (raw `FPlane` struct read, same 4 fields).
Pairs step i of one sequence against step i of the other by that plane (rounded), reports the first
index where they disagree (a genuinely different classify plane visited) vs. where they still don't
match but agree on the PREFIX up to that point (a length/tail difference only).

Usage: area51_fep_seq_compare.py [editor_log]  (default: latest area51-fep-descent-*.log)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
NATIVE_LOG = ROOT / "_scratch/area51_p4_desc_trace.log"
ORACLE_DIR = ROOT / "_scratch/area51-oracle-logs"

ROUND = 3  # decimal places -- native computes in f32, editor's raw floats printed at 5-6dp


def _round_plane(a, b, c, d):
    return (round(a, ROUND), round(b, ROUND), round(c, ROUND), round(d, ROUND))


def parse_native(path):
    rows = []
    pat = re.compile(
        r"node=(\d+).*?N=\(([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\).*?-> (.*)$")
    for line in path.read_text().splitlines():
        if not line.startswith("DESC"):
            continue
        m = pat.search(line)
        if not m:
            continue
        inode = int(m.group(1))
        plane = _round_plane(*(float(m.group(i)) for i in (2, 3, 4, 5)))
        verdict = m.group(6)
        rows.append((inode, plane, verdict, line))
    return rows


def parse_editor(path):
    rows = []
    pat = re.compile(
        r"FEP inode=(\d+).*?nodeN=([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+).*?out=(\d+)")
    for line in path.read_text().splitlines():
        if not line.startswith("FEP"):
            continue
        m = pat.search(line)
        if not m:
            continue
        inode = int(m.group(1))
        plane = _round_plane(*(float(m.group(i)) for i in (2, 3, 4, 5)))
        rows.append((inode, plane, m.group(6), line))
    return rows


def main():
    if len(sys.argv) > 1:
        editor_log = Path(sys.argv[1])
    else:
        cands = sorted(ORACLE_DIR.glob("area51-fep-descent-*.log"))
        if not cands:
            raise SystemExit(f"no area51-fep-descent-*.log under {ORACLE_DIR}")
        editor_log = cands[-1]

    native = parse_native(NATIVE_LOG)
    editor = parse_editor(editor_log)
    print(f"native:  {len(native)} DESC lines from {NATIVE_LOG}")
    print(f"editor:  {len(editor)} FEP lines from {editor_log} (edN-filtered)")

    if not editor:
        print("EDITOR LOG EMPTY -- the edN tolerance window matched nothing. Check the gdb log for "
              "attach/timeout errors, or widen TOL in area51_filteredpoly_descent.py.")
        return

    n_planes = [r[1] for r in native]
    e_planes = [r[1] for r in editor]

    first_diff = None
    for i, (np_, ep_) in enumerate(zip(n_planes, e_planes)):
        if np_ != ep_:
            first_diff = i
            break
    else:
        if len(n_planes) != len(e_planes):
            first_diff = min(len(n_planes), len(e_planes))

    print()
    if first_diff is None:
        print("SEQUENCES IDENTICAL (same planes, same order, same length) -- no divergence found in "
              "this window. Re-check tolerance / whether the editor log over- or under-matched.")
    elif first_diff == 0:
        print("DIVERGE AT STEP 0 -- the very first classify plane differs. This is NOT a traversal-"
              "order/tie-break issue: native and the editor start descending through DIFFERENT parts "
              "of the tree from the first step. Re-open the classify-decision hypothesis for this "
              "specific node (degenerate input, first-node special case) rather than iLink ordering.")
    else:
        print(f"AGREE on first {first_diff} step(s), THEN DIVERGE at step {first_diff}.")
        print("Native step  :", native[first_diff] if first_diff < len(native) else "(exhausted)")
        print("Editor step  :", editor[first_diff] if first_diff < len(editor) else "(exhausted)")
        print()
        print("Check whether the DISAGREEING step's parent (step first_diff-1, printed below) has "
              "MULTIPLE coplanar/tied children (iLink chain) on one side but not the other -- the "
              "leading traversal-order/tie-break hypothesis.")
        print("Parent (native):", native[first_diff - 1])
        print("Parent (editor):", editor[first_diff - 1])

    print("\n--- native sequence (index, node, plane, verdict) ---")
    for i, (inode, plane, verdict, _) in enumerate(native):
        marker = " <-- DIVERGE" if first_diff == i else ""
        print(f"  [{i:2}] node={inode:5} plane={plane} {verdict}{marker}")

    print("\n--- editor sequence (index, inode, plane, out) ---")
    for i, (inode, plane, out, _) in enumerate(editor):
        marker = " <-- DIVERGE" if first_diff == i else ""
        print(f"  [{i:2}] inode={inode:5} plane={plane} out={out}{marker}")


if __name__ == "__main__":
    main()
