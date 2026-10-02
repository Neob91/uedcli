#!/usr/bin/env python3
"""Given `diff_call_sequences.py` proves native's own 165-call face-5 sequence maps, isurf for
isurf, IN ORDER, onto a 165-length matching region of the real editor's 245-hit capture (modulo 2
harmless degenerate-clip hits, see spike.md) -- this replays the OWN span-buffer subtraction
algorithm (`test_and_maybe_subtract` in `uedcli-native/src/visible_surfs.rs`, ported here 1:1) over
that matching chain using the REAL editor's OWN raw per-row rasterized windows (Start/End), instead
of native's, to check whether feeding real's own footprints through the SAME algorithm reproduces
native's own accept/reject verdict for every one of the 165 calls -- settling whether the divergence
is a footprint/subtraction bug in the matching chain itself, or lies elsewhere (see spike.md).

Needs, for each of native's 165 face-5 calls, in order: (node, surf, opaque flag) -- from native's
`UEDCLI_VISGATE_TRACE_SURF=-1` trace log (`full_trace_light431.py`, same as `diff_call_sequences.py`
consumes) -- and, for the corresponding real hit, its raw rows -- from `raster-callsite.log`'s own
ROW lines (already present for every hit, no probe change needed for this half).

Usage:
    replay_matching_chain.py <real raster-callsite.log> <native whole-trace log> \
        --leading N --gap-at I --gap-len G [--face N]

`--leading`/`--gap-at`/`--gap-len` come straight off `diff_call_sequences.py`'s own DELETE/EQUAL
report (the real[0:N] leading DELETE block's length, and the 0-based native index / length of the
DELETE block splitting the two EQUAL regions) -- re-derive them per run rather than hardcoding, since
a future N or level will have different numbers.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RES = 1024


def parse_real_hits(path: Path) -> dict[int, dict]:
    precall_re = re.compile(r"PRECALL hit=(\d+) isurf=(-?\d+) numpts=(\d+) span=(\S+) framey=(\d+)")
    row_re = re.compile(r"ROW hit=(\d+) y=(-?\d+) s=(-?\d+) e=(-?\d+)")
    hits: dict[int, dict] = {}
    for line in path.read_text().splitlines():
        m = precall_re.match(line)
        if m:
            h = int(m.group(1))
            hits[h] = {"isurf": m.group(2), "rows": []}
            continue
        m = row_re.match(line)
        if m:
            h = int(m.group(1))
            hits[h]["rows"].append((int(m.group(2)), int(m.group(3)), int(m.group(4))))
    return hits


def parse_native_calls(path: Path, face: int) -> list[dict]:
    face_re = re.compile(r"^VISGATE_VISIT face=(\d+)")
    nodesurf_re = re.compile(
        r"^VISGATE_TRACE node=(\d+) surf=(-?\d+) near_zone=(-?\d+) reachable=\w+ front_ok=\w+ "
        r"portal_needs_zones=\w+ invisible=\w+ poly_flags=(0x[0-9a-f]+)")
    raster_re = re.compile(
        r"^VISGATE_TRACE node=(\d+) rasterized rows=\d+ raster_px=\d+ accepted_px=(\d+) opaque=(\w+)")

    cur_face = None
    node_info: dict[int, dict] = {}
    calls = []
    for line in path.read_text().splitlines():
        m = face_re.match(line)
        if m:
            cur_face = int(m.group(1))
            continue
        m = nodesurf_re.match(line)
        if m:
            node_info[int(m.group(1))] = {
                "surf": m.group(2), "near_zone": int(m.group(3)), "poly_flags": int(m.group(4), 16)}
            continue
        m = raster_re.match(line)
        if m and cur_face == face:
            n = int(m.group(1))
            info = node_info.get(n, {})
            calls.append({
                "node": n, "surf": info.get("surf"), "near_zone": info.get("near_zone"),
                "opaque": m.group(3) == "true", "native_accepted_px": int(m.group(2)),
            })
    return calls


def test_and_maybe_subtract(buf_rows: list[list[tuple[int, int]]], rows: list[tuple[int, int, int]],
                             subtract: bool) -> list[tuple[int, int, int]]:
    """1:1 port of `visible_surfs.rs::test_and_maybe_subtract` -- see that function's own comments
    for the real `FSpanBuffer::CopyFromRaster`/`CopyFromRasterUpdate` provenance."""
    accepted = []
    for (y, wx0, wx1) in rows:
        if wx1 <= wx0:
            continue
        row = buf_rows[y]
        out_row: list[tuple[int, int]] = []
        touched = False
        i = 0
        n = len(row)
        while i < n:
            x0, x1 = row[i]
            if x1 <= wx0:
                if subtract:
                    out_row.append((x0, x1))
                i += 1
                continue
            if x0 >= wx1:
                if subtract:
                    out_row.extend(row[i:])
                break
            ax0, ax1 = max(x0, wx0), min(x1, wx1)
            accepted.append((y, ax0, ax1))
            touched = True
            if subtract:
                if x0 < ax0:
                    out_row.append((x0, ax0))
                if x1 > ax1:
                    out_row.append((ax1, x1))
            if x1 <= wx1:
                i += 1
            else:
                i += 1
                if subtract:
                    out_row.extend(row[i:])
                break
        if subtract and touched:
            buf_rows[y] = out_row
    return accepted


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    real_log = Path(sys.argv[1])
    native_log = Path(sys.argv[2])
    face = 5
    leading = 78
    gap_at = 91   # native 1-based call index right after the first EQUAL block
    gap_len = 2
    if "--face" in sys.argv:
        face = int(sys.argv[sys.argv.index("--face") + 1])
    if "--leading" in sys.argv:
        leading = int(sys.argv[sys.argv.index("--leading") + 1])
    if "--gap-at" in sys.argv:
        gap_at = int(sys.argv[sys.argv.index("--gap-at") + 1])
    if "--gap-len" in sys.argv:
        gap_len = int(sys.argv[sys.argv.index("--gap-len") + 1])

    real_hits = parse_real_hits(real_log)
    calls = parse_native_calls(native_log, face)

    def real_hit_for(i_1indexed: int) -> int:
        return i_1indexed + leading if i_1indexed <= gap_at else i_1indexed + leading + gap_len

    buf_rows: list[list[tuple[int, int]]] = [[(0, RES)] for _ in range(RES)]
    mismatches = []
    surf_mismatches = []
    for idx, c in enumerate(calls, start=1):
        h = real_hit_for(idx)
        real = real_hits.get(h)
        if real is None:
            print(f"WARNING: no real hit data for i={idx} -> hit={h}")
            continue
        if real["isurf"] != c["surf"]:
            # A misaligned --leading/--gap-at/--gap-len would surface here: the call-index mapping
            # is wrong, and any "0 mismatches" verdict below would be comparing the wrong pair of
            # calls, not proof of anything. Counts as a hard failure, not just a printed warning.
            print(f"SURF MISMATCH at i={idx}: native surf={c['surf']} real(hit={h}) isurf={real['isurf']}")
            surf_mismatches.append(idx)
        accepted = test_and_maybe_subtract(buf_rows, real["rows"], c["opaque"])
        acc_px = sum(a[2] - a[1] for a in accepted)
        if (acc_px > 0) != (c["native_accepted_px"] > 0):
            mismatches.append((idx, c["node"], c["surf"], acc_px, c["native_accepted_px"]))

    print(f"replayed {len(calls)} calls using REAL's own raw rows through native's own algorithm")
    print(f"accept/reject mismatches vs native's own trace: {len(mismatches)}")
    for m in mismatches:
        print("  i=%d node=%d surf=%s replay_acc_px=%d native_acc_px=%d" % m)
    if surf_mismatches:
        print(f"ABORT: {len(surf_mismatches)} surf-identity mismatch(es) -- the call-index mapping "
              f"(--leading/--gap-at/--gap-len) is wrong, so the accept/reject result above compares "
              f"the wrong pairs and proves nothing.")
    return 1 if (mismatches or surf_mismatches) else 0


if __name__ == "__main__":
    raise SystemExit(main())
