#!/usr/bin/env python3
"""Diff native's render-bound box tests against the live editor's, call for call.

Feed it the `UEDCLI_VISGATE_TRACE_BOX` stderr of a native build and the JSON from
`parse_frame_probe.py --json` for the SAME level/N. Calls are matched on (light origin, view
forward axis, node index) -- the editor's `Coords.ZAxis` is the face forward, so the pairing is
exact even though the two use different in-plane axes.

Usage: compare_box_tests.py <native-trace.log> <bv_calls.json>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LINE = re.compile(
    r"VISGATE_BOX light=\[([^\]]*)\] fwd=\[([^\]]*)\] node=(\d+) bound=(-?\d+) visible=(\w+)")


def key(origin, forward, node) -> tuple:
    return (tuple(round(v, 2) for v in origin), tuple(round(v, 3) for v in forward), node)


def main() -> int:
    native: dict[tuple, list[bool]] = {}
    for line in Path(sys.argv[1]).read_text(errors="replace").splitlines():
        if m := LINE.search(line):
            k = key([float(x) for x in m.group(1).split(",")],
                    [float(x) for x in m.group(2).split(",")], int(m.group(3)))
            native.setdefault(k, []).append(m.group(5) == "true")

    editor: dict[tuple, list[bool]] = {}
    for r in json.load(open(sys.argv[2])):
        if r["sx"] != 1024:
            continue
        editor.setdefault(key(r["origin"], r["zaxis"], r["node"]), []).append(bool(r["ret"]))

    only_n = sorted(set(native) - set(editor))
    only_e = sorted(set(editor) - set(native))
    both = sorted(set(native) & set(editor))
    agree = [k for k in both if native[k] == editor[k]]
    print(f"native {sum(len(v) for v in native.values())} tests / {len(native)} keys; "
          f"editor {sum(len(v) for v in editor.values())} / {len(editor)} keys")
    print(f"matched keys {len(both)}, agreeing {len(agree)}, "
          f"native-only {len(only_n)}, editor-only {len(only_e)}")
    for k in both:
        if native[k] != editor[k]:
            print(f"  DIFF node={k[2]} light={k[0]} fwd={k[1]} native={native[k]} editor={editor[k]}")
    for k in only_n:
        print(f"  NATIVE-ONLY node={k[2]} light={k[0]} fwd={k[1]} {native[k]}")
    for k in only_e:
        print(f"  EDITOR-ONLY node={k[2]} light={k[0]} fwd={k[1]} {editor[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
