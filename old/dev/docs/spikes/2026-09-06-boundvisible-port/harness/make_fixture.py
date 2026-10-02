#!/usr/bin/env python3
"""Turn `parse_frame_probe.py --json` output into the Rust fixture table pinning `bound_visible`.

Each row is one live `URender::BoundVisible` call from a real UNATCO N=26 golden build: the view
`FCoords` (origin + the three axes, verbatim from the editor's own frame — NOT this port's face
basis, so the comparison is exact), the `FBox`, the return value, the `FScreenBounds` rect the
callee wrote, and which exit path it took. The exit path is what makes the row a two-way pin: an
`outcode`/`depth` row must be rejected by geometry alone, and every other row must be ACCEPTED by
geometry with that exact rectangle — including a `span` row, because the editor writes
`FScreenBounds` before consulting the span buffer. An `outcode`/`depth` row's rect is stale (the
callee returns before writing it) and is emitted as `-1`s.

Deduplicated on (box, coords); a geometry that returned both 0 and 1 across the run is dropped.

Usage: make_fixture.py <bv_calls.json>   # prints the Rust table to stdout
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def f32(v: float) -> str:
    s = repr(float(v))
    return s if ("." in s or "e" in s or "E" in s) else s + ".0"


def main() -> int:
    recs = json.load(open(sys.argv[1]))
    gather = [r for r in recs if r["sx"] == 1024]
    uniq: dict[tuple, list] = {}
    for r in gather:
        k = (tuple(r["box_min"]), tuple(r["box_max"]), tuple(r["origin"]),
             tuple(r["xaxis"]), tuple(r["yaxis"]), tuple(r["zaxis"]))
        uniq.setdefault(k, []).append(r)
    rows, dropped = [], 0
    for k, v in sorted(uniq.items()):
        rets = {x["ret"] for x in v}
        if len(rets) > 1:
            dropped += 1
            continue
        rows.append((k, v[0]))
    print(f"// {len(gather)} live calls -> {len(rows)} unique (box, coords) cases "
          f"({dropped} dropped: same geometry, both outcomes -> span-buffer-decided)",
          file=sys.stderr)
    print("# live URender::BoundVisible calls, UNATCO N=26 golden build "
          "(spikes/2026-09-06-boundvisible-port). One row per unique (FBox, view FCoords):")
    print("# origin.xyz, xaxis.xyz, yaxis.xyz, zaxis.xyz, box.min.xyz, box.max.xyz, ret, "
          "screen minx,miny,maxx,maxy, exit path (inside|depth|outcode|span|accept)")
    for k, r in rows:
        bmin, bmax, org, xa, ya, za = k
        vals = list(org) + list(xa) + list(ya) + list(za) + list(bmin) + list(bmax)
        path = r.get("exit") or "accept"
        rect = ["-1"] * 4 if path in ("outcode", "depth") else [str(int(x)) for x in r["sb"][:4]]
        print(",".join([f32(x) for x in vals] + [str(r["ret"])] + rect + [path]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
