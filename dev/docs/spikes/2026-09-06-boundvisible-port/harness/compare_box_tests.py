#!/usr/bin/env python3
"""Diff native's render-bound box tests against the live editor's, call for call.

Feed it the `UEDCLI_VISGATE_TRACE_BOX` stderr of a native build and the JSON from
`parse_frame_probe.py --json` for the SAME level/N. Calls are matched on (light origin, view
forward axis, node index) -- the editor's `Coords.ZAxis` is the face forward, so the pairing is
exact even though the two use different in-plane axes.

Two things this gets right that an earlier version did not, both of which invented differences that
were not there (`2026-09-07-gather-box-verdict/spike.md`):

- The key compares the f32 BITS, not `round(v, 2)`. Native prints a float shortest-roundtrip
  (`234.255`) and the gdb probe prints `%.9g` (`234.255005`); those are one f32 value but round to
  234.25 and 234.26, so one light split into 45 "native-only" plus 45 "editor-only" keys.
- It compares the editor's FINAL verdict (`visible`), not `BoundVisible`'s return. Under
  `bUseZones` the call gets a NULL `FSpanBuffer*` and `OccludeBsp` runs the span test itself
  afterwards, per active zone; comparing native's post-zone-loop answer against the pre-zone-loop
  return reported 54 phantom "native over-occludes" cases on OceanLab N=48. A JSON from a probe
  without the outcome sites (`box_verdict_probe.py`) cannot answer this and is called out.

It also reports whether the two ran the tests in the same ORDER, which is the only check here that
exercises the traversal rather than the box test.

Usage: compare_box_tests.py <native-trace.log> <bv_calls.json>
"""
from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path

LINE = re.compile(
    r"VISGATE_BOX light=\[([^\]]*)\] fwd=\[([^\]]*)\] node=(\d+) bound=(-?\d+) visible=(\w+)")


def key(origin, forward, node) -> tuple:
    f32 = lambda v: struct.pack("<f", v)  # noqa: E731
    return (tuple(map(f32, origin)), tuple(map(f32, forward)), node)


def main() -> int:
    native: dict[tuple, list[bool]] = {}
    nat_order: list[tuple] = []
    for line in Path(sys.argv[1]).read_text(errors="replace").splitlines():
        if m := LINE.search(line):
            k = key([float(x) for x in m.group(1).split(",")],
                    [float(x) for x in m.group(2).split(",")], int(m.group(3)))
            native.setdefault(k, []).append(m.group(5) == "true")
            nat_order.append(k)

    editor: dict[tuple, list[bool]] = {}
    ed_order: list[tuple] = []
    probed = False
    for r in json.load(open(sys.argv[2])):
        if r["sx"] != 1024:
            continue
        probed |= r.get("probed", False)
        k = key(r["origin"], r["zaxis"], r["node"])
        editor.setdefault(k, []).append(bool(r.get("visible", r["ret"])))
        ed_order.append(k)
    if not probed:
        print("WARNING: this capture has no VERDICT lines -- it holds BoundVisible's return, not "
              "the box-occlusion verdict, so every zoned span rejection will read as a difference")

    only_n = sorted(set(native) - set(editor))
    only_e = sorted(set(editor) - set(native))
    both = sorted(set(native) & set(editor))
    agree = [k for k in both if native[k] == editor[k]]
    print(f"native {sum(len(v) for v in native.values())} tests / {len(native)} keys; "
          f"editor {sum(len(v) for v in editor.values())} / {len(editor)} keys")
    print(f"matched keys {len(both)}, agreeing {len(agree)}, "
          f"native-only {len(only_n)}, editor-only {len(only_e)}")
    # The SEQUENCE, not just the set: it is the only check here that exercises the traversal
    # itself — near/far child choice, the coplanar-chain walk, the zone-mask prune, the
    # frustum-cone reject and the zone retire all decide which node is box-tested next.
    print(f"same ORDER: {nat_order == ed_order}")
    if nat_order != ed_order:
        i = next((k for k, (a, b) in enumerate(zip(nat_order, ed_order)) if a != b),
                 min(len(nat_order), len(ed_order)))
        print(f"  first order divergence at index {i}: "
              f"native next {[k[2] for k in nat_order[i:i + 12]]}, "
              f"editor next {[k[2] for k in ed_order[i:i + 12]]}")
    show = lambda k: f"node={k[2]} light={[struct.unpack('<f', b)[0] for b in k[0]]}"  # noqa: E731
    for k in both:
        if native[k] != editor[k]:
            print(f"  DIFF {show(k)} native={native[k]} editor={editor[k]}")
    for k in only_n:
        print(f"  NATIVE-ONLY {show(k)} {native[k]}")
    for k in only_e:
        print(f"  EDITOR-ONLY {show(k)} {editor[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
