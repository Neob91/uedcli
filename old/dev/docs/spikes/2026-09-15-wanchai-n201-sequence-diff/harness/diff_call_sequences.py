#!/usr/bin/env python3
"""Settle the WanChai N=201 245-vs-165 `OccludeBsp` rasterize-call-count question with a real
sequence diff (not inference): parse the real editor's `raster-callsite.log` (245 PRECALL hits,
already isurf-tagged per hit -- `raster_callsite_probe.py` prints `isurf` for every hit, it never
needed extending) and native's own `UEDCLI_VISGATE_TRACE_SURF=-1` whole-traversal trace for the same
face, extract each side's ordered isurf sequence, and diff them with `difflib.SequenceMatcher`.

Usage:
    diff_call_sequences.py <real raster-callsite.log> <native whole-trace log> [--face N]

`<native whole-trace log>` is produced by `full_trace_light431.py` (same dir as the parent spike,
`2026-09-15-wanchai-n201-raster-footprint/harness/`) with `UEDCLI_VISGATE_TRACE_SURF=-1`. `--face`
selects which of the 6 `VISGATE_VISIT face=N` blocks to diff against (default 5, Light431's
straight-down face, the one `raster-callsite.log` itself is origin+zaxis-gated to).
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path


def real_sequence(path: Path) -> list[tuple[int, str]]:
    """[(hit, isurf)] in PRECALL order."""
    pat = re.compile(r"PRECALL hit=(\d+) isurf=(-?\d+)")
    out = []
    for line in path.read_text().splitlines():
        m = pat.match(line)
        if m:
            out.append((int(m.group(1)), m.group(2)))
    return out


def native_face_sequence(path: Path, face: int) -> list[tuple[int, str]]:
    """[(node, surf)] of every successful `rasterize_node` call within one `VISGATE_VISIT face=N`
    block, in call order. A node's own `surf=` is read off the immediately-preceding
    `VISGATE_TRACE node=X surf=Y near_zone=...` diagnostic line for that same node."""
    lines = path.read_text().splitlines()
    face_re = re.compile(r"^VISGATE_VISIT face=(\d+)")
    nodesurf_re = re.compile(r"^VISGATE_TRACE node=(\d+) surf=(-?\d+) near_zone=")
    raster_re = re.compile(r"^VISGATE_TRACE node=(\d+) rasterized rows=")

    cur_face = None
    node_surf: dict[int, str] = {}
    out = []
    for line in lines:
        m = face_re.match(line)
        if m:
            cur_face = int(m.group(1))
            continue
        m = nodesurf_re.match(line)
        if m:
            node_surf[int(m.group(1))] = m.group(2)
            continue
        m = raster_re.match(line)
        if m and cur_face == face:
            n = int(m.group(1))
            out.append((n, node_surf.get(n, "?")))
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    real_log = Path(sys.argv[1])
    native_log = Path(sys.argv[2])
    face = 5
    if "--face" in sys.argv:
        face = int(sys.argv[sys.argv.index("--face") + 1])

    real = real_sequence(real_log)
    native = native_face_sequence(native_log, face)
    real_surfs = [s for _, s in real]
    native_surfs = [s for _, s in native]

    print(f"real: {len(real)} PRECALL hits (origin+zaxis-gated capture)")
    print(f"native: {len(native)} rasterize_node calls (face={face})")
    print()

    sm = difflib.SequenceMatcher(None, real_surfs, native_surfs, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            print(f"EQUAL   real[{i1}:{i2}] native[{j1}:{j2}]  len={i2 - i1}")
        else:
            print(f"{tag.upper():7} real[{i1}:{i2}]={real_surfs[i1:i2]}  "
                  f"native[{j1}:{j2}]={native_surfs[j1:j2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
