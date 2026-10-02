#!/usr/bin/env python3
r"""Side-by-side of the native and editor committed-tree dumps over an index range.

`committed_tree_diff.py` answers "is there a structural divergence, and at which index" — counts
plus the first offending node. It cannot show WHAT KIND of divergence, and in particular cannot show
an INSERTION: when one tree gains a node, every later index is shifted and the diff reports hundreds
of unrelated mismatches. Reading the two dumps against each other around the first structural index
is what distinguishes "one tree emitted an extra node here" (everything after lines up at an offset)
from "the two trees genuinely partition differently from here on".

That is how board item `wanchai-bsp-gap-localized-to-one-dropped` §4 was pinned: native node `i+1`
== editor node `i` for every `i` past the insertion point, and native surf `j+1` == editor surf `j`
— a single extra node, not a diffuse divergence.

Inputs are the same two dumps `committed_tree_diff.py` takes:
  * native — `UEDCLI_BSPCSG_TREE_STRUCT=1` ("STRUCT node=..." lines)
  * editor — `ed_committed_tree.py` ("ND ..." lines)

A `*` in the left margin marks an index where the two rows differ.

Usage:  committed_tree_side.py <native.log> <editor.log> <lo> <hi>
"""
import re
import sys

_NA = re.compile(r"^STRUCT node=(\d+) plane=\(([-0-9.eE,]+)\) iF=(-?\d+) iB=(-?\d+) iP=(-?\d+) "
                 r"isurf=(-?\d+) nf=(\S+) nv=(-?\d+)")
_ED = re.compile(r"^ND (\d+) plane=([-0-9.eE,]+) iF=(-?\d+) iB=(-?\d+) iP=(-?\d+) isurf=(-?\d+) "
                 r"nv=(-?\d+) nf=(\S+)")

# (plane, iF, iB, iP, isurf, nv) — the two dumps order `nv` and `nf` differently, hence two groupings.
_NA_G = (2, 3, 4, 5, 6, 8)
_ED_G = (2, 3, 4, 5, 6, 7)


def _parse(path, rx, groups):
    out = {}
    for ln in open(path):
        if m := rx.match(ln):
            out[int(m[1])] = tuple(m[i] for i in groups)
    return out


def _fmt(row):
    if row is None:
        return "-" * 62
    plane = ",".join(f"{float(x):g}" for x in row[0].split(","))
    return (f"{plane:<34} iF={row[1]:>6} iB={row[2]:>6} iP={row[3]:>6} "
            f"s={row[4]:>5} nv={row[5]}")


def main():
    if len(sys.argv) != 5:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    native = _parse(sys.argv[1], _NA, _NA_G)
    editor = _parse(sys.argv[2], _ED, _ED_G)
    if not native or not editor:
        print(f"no rows parsed (native={len(native)} editor={len(editor)}) — wrong dump format?",
              file=sys.stderr)
        return 2
    lo, hi = int(sys.argv[3]), int(sys.argv[4])
    print(f"native={len(native)} editor={len(editor)} showing [{lo},{hi})")
    for i in range(lo, hi):
        na, ed = native.get(i), editor.get(i)
        print(f"{' ' if na == ed else '*'}{i:>7}  NA {_fmt(na)}")
        print(f"         ED {_fmt(ed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
