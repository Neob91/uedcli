#!/usr/bin/env python3
"""Score `_model_point_region` against a UED22 reference package: for every actor that carries both
a `Location` and a `Region`, re-run the descent on that package's own world Model and compare to the
`Region` the editor stamped.

Also scores a FAITHFUL transcription of `UModel::PointRegion` (`Engine.dll 0x101aee60`), which
differs from ours in two respects we have no corpus case for: it takes `ZoneNumber` from the
terminating NODE's `iZone[IsFront]` rather than the leaf's, and it keeps `iLeaf` even when it is -1
(so a point in solid can still carry a non-zero zone). `cur_vs_faithful` counts where the two
disagree -- 0 across the whole exercised corpus as of 2026-09-06.

Usage:  region_corpus_check.py <ref_N<k>.dx> [...]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"))

import parity_gate as pg                              # noqa: E402
from uedcli.native import umodel as UM                # noqa: E402
from uedcli.native.csg_golden import _find_model_export  # noqa: E402
from uedcli.native.materialize import _model_point_region, _plane_dot  # noqa: E402
from uedcli.upackage import load_package              # noqa: E402


def faithful(model, p) -> tuple[int, int]:
    if not model.nodes:
        return (-1, 0)
    i_node, i_parent, is_front = 0, 0, 0
    while i_node != -1:
        n = model.nodes[i_node]
        is_front = 1 if _plane_dot(n.plane, p) >= 0 else 0
        i_parent, i_node = i_node, (n.i_back if is_front == 1 else n.i_front)
    par = model.nodes[i_parent]
    return (par.i_leaf[is_front], par.i_zone[is_front] if model.zones else 0)


def check(path: str) -> None:
    buf = Path(path).read_bytes()
    off, size = _find_model_export(buf)
    model = UM.parse_model_body(buf, off, size)
    pkg = load_package(path)
    idt = pg.Ident(pkg)
    n_actors = n_cur = n_faith = n_diff = 0
    for i0 in range(len(pkg.exports)):
        try:
            body = pg.canon_body(idt, i0)
        except Exception:
            continue
        if not body or body[0] != "actor":
            continue
        toks = {t[0]: t for t in body[2]}
        if "region" not in toks or "location" not in toks:
            continue
        loc, reg = toks["location"][3], toks["region"][3]
        if not (isinstance(loc, tuple) and loc[0] == "raw") or len(reg) != 4:
            continue
        p = struct.unpack_from("<3f", bytes.fromhex(loc[1]), 0)
        ued = (reg[2], reg[3])
        n_actors += 1
        cur, fai = _model_point_region(model, p), faithful(model, p)
        for label, got, bad in (("CUR", cur, cur != ued), ("FAI", fai, fai != ued)):
            if bad:
                print(f"{label}-DIFF {idt.export_identity(i0)} loc={p} got={got} ued={ued}")
        n_cur += cur != ued
        n_faith += fai != ued
        n_diff += cur != fai
    print(f"{Path(path).name}: actors={n_actors} current_mismatches={n_cur} "
          f"faithful_mismatches={n_faith} cur_vs_faithful={n_diff}")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        check(a)
