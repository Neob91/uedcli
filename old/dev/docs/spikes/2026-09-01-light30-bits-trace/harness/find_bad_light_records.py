#!/usr/bin/env python3
r"""Locate the concrete (record, light-name, sub-plane) repro for a NAMED recurring "bad" light in
the `bits`-only lighting bucket (`lighting-bits-only-divergence-localizes-to`).

Reuses `parity_compare.build_native_lit_dx` (native's own lit build of the trunk) and
`lightparity`'s pure helpers (`level_model`/`light_names`/`runs`/`planes`) -- no new parsing.

For every LightMap record where native and golden's shadow bits disagree (grid+run matched, so a
real bit-level mismatch, not a geometry-shape difference), splits `LightBits` back into each light's
own `USize x VSize` sub-plane (stored consecutively per the run, matching the `bits`-only-bucket
finding's own methodology) and reports, per light NAME, how many distinct records it is the (or a)
mismatching light in.

Usage: find_bad_light_records.py GOLDEN.dx TRUNK_DIR PROJECT_ROOT [--light NAME]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PARITY_HARNESS = ROOT / "dev/docs/spikes/2026-08-31-native-parity-report/harness"
LIGHT_HARNESS = ROOT / "dev/docs/spikes/2026-08-27-native-light-apply-parity/harness"
sys.path.insert(0, str(PARITY_HARNESS))
sys.path.insert(0, str(LIGHT_HARNESS))
sys.path.insert(0, str(ROOT))

import parity_compare as pc  # noqa: E402
import lightparity as LP  # noqa: E402
from uedcli import upackage  # noqa: E402
from uedcli.native import umodel  # noqa: E402


def sub_planes(model, rec, run_names: list[str | None]) -> list[tuple[str | None, bytes]]:
    """Split one record's shadow-bit block back into each light's own `ceil(USize/8) * VSize`
    sub-plane, in run order (`lightparity.planes`, but per-light instead of the whole run)."""
    if not run_names:
        return []
    stride = ((rec.u_size + 7) // 8) * rec.v_size
    out = []
    off = rec.data_offset
    for name in run_names:
        out.append((name, bytes(model.light_bits[off:off + stride])))
        off += stride
    return out


def main() -> int:
    golden_path = Path(sys.argv[1])
    trunk_dir = Path(sys.argv[2])
    project_root = Path(sys.argv[3])
    want_light = None
    for i, a in enumerate(sys.argv):
        if a == "--light":
            want_light = sys.argv[i + 1]

    native_bytes, warnings = pc.build_native_lit_dx(trunk_dir, project_root)
    if warnings:
        print(f"[find-bad-light] build warnings: {warnings}", file=sys.stderr)
    Path("/tmp/nyc_bar_native_lit.dx").write_bytes(native_bytes)
    native_path = pc._temp_dx(native_bytes)

    npkg, nm = LP.level_model(upackage, umodel, str(native_path))
    epkg, em = LP.level_model(upackage, umodel, str(golden_path))
    nnames, enames = LP.light_names(npkg, nm), LP.light_names(epkg, em)
    nruns, eruns = LP.runs(nm, nnames), LP.runs(em, enames)

    per_light_bad_records: dict[str, list[int]] = defaultdict(list)
    total_bits_only = 0
    for k, erec in enumerate(em.light_map):
        if k >= len(nm.light_map):
            continue
        nrec = nm.light_map[k]
        nrun, erun = nruns[k], eruns[k]
        if nrun != erun:
            continue  # run differs -- not the bits-only bucket
        if (nrec.u_size, nrec.v_size) != (erec.u_size, erec.v_size):
            continue  # grid differs -- not the bits-only bucket
        if not erun:
            continue
        nfull = LP.planes(nm, nrec, len(nrun))
        efull = LP.planes(em, erec, len(erun))
        if nfull == efull:
            continue  # bit-identical record
        total_bits_only += 1
        n_sub = sub_planes(nm, nrec, nrun)
        e_sub = sub_planes(em, erec, erun)
        for (nname, npl), (ename, epl) in zip(n_sub, e_sub):
            assert nname == ename
            if npl != epl and nname:
                per_light_bad_records[nname].append(k)

    print(f"total bits-only-bucket records: {total_bits_only}")
    ranked = sorted(per_light_bad_records.items(), key=lambda kv: -len(kv[1]))
    for name, recs in ranked[:20]:
        print(f"  {name}: {len(recs)} records -> {recs}")

    if want_light:
        recs = per_light_bad_records.get(want_light, [])
        print(f"\n--light {want_light}: {len(recs)} bad records: {recs}")
        for k in recs:
            erec = em.light_map[k]
            erun = eruns[k]
            nrec = nm.light_map[k]
            print(f"  record {k}: isurf lookup needed separately; USize={erec.u_size} "
                  f"VSize={erec.v_size} run={erun} "
                  f"n_data_offset={nrec.data_offset} e_data_offset={erec.data_offset}")

    native_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
