#!/usr/bin/env python3
"""Decode the per-surface light RUNS (Model.Lights @0xe4 walked via FLightMapIndex.iLightActors)
for a native and an editor .dx, and reconcile them against LightMap/LightBits.

This is the diagnostic for the raw-byte gap in the three light sections
(Lights e4, LightMap a8, LightBits b4) reported by ground_truth_bytediff.py.

For each map it reports:
  * #lit surfs (surf.i_light_map != -1), #records, LightBits len, Lights len
  * per-record run length distribution (walking Lights from iLightActors to the first 0/NULL)
  * reconciliation: sum over records of run_len * ceil(USize/8) * VSize == LightBits len
  * total run entries + #terminators == len(Lights)

Usage: .venv/bin/python lights_run_diff.py [NATIVE.dx] [EDITOR.dx]
"""
from __future__ import annotations
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

from uedcli.native import umodel as UM  # noqa: E402
import utexture_decode as UT  # noqa: E402

NATIVE = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/gtruth/NativeCastle.dx"
EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"


def load_model(path):
    pkg = UT.load_package(path)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    m = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])
    return m, pkg


def walk_run(lights, start):
    """Walk Lights from index `start` to the first 0 (NULL terminator). Return list of refs."""
    run = []
    i = start
    while i < len(lights) and lights[i] != 0:
        run.append(lights[i])
        i += 1
    return run


def analyze(path, label):
    m, pkg = load_model(path)
    nsurf = len(m.surfs)
    lit_surfs = [s for s in m.surfs if s.i_light_map != -1]
    recs = m.light_map
    lights = m.lights
    lb = len(m.light_bits)

    # records with a real light run (iLightActors >= 0) vs dark (=-1)
    with_run = [r for r in recs if r.i_light_actors >= 0]
    dark = [r for r in recs if r.i_light_actors < 0]

    # walk each run
    run_lens = []
    recon_bits = 0
    total_entries = 0
    for r in with_run:
        run = walk_run(lights, r.i_light_actors)
        run_lens.append(len(run))
        row_bytes = (r.u_size + 7) // 8
        recon_bits += len(run) * row_bytes * r.v_size
        total_entries += len(run)

    print(f"===== {label}: {Path(path).name} =====")
    print(f"  surfs={nsurf}  lit(surf.iLightMap!=-1)={len(lit_surfs)}  records={len(recs)}")
    print(f"  records with run (iLA>=0)={len(with_run)}  dark (iLA<0)={len(dark)}")
    print(f"  LightBits len={lb}   reconstructed sum(run*ceil(U/8)*V)={recon_bits}  match={recon_bits==lb}")
    print(f"  Lights(e4) len={len(lights)}   run-entries={total_entries}  +terminators({len(with_run)})={total_entries+len(with_run)}")
    if run_lens:
        rc = Counter(run_lens)
        print(f"  run-length: min={min(run_lens)} max={max(run_lens)} mean={sum(run_lens)/len(run_lens):.2f} "
              f"median={sorted(run_lens)[len(run_lens)//2]}")
        print(f"  run-length hist (len:count): {dict(sorted(rc.items()))}")
    # count zeros in lights (terminators) and distinct positive refs
    zeros = sum(1 for x in lights if x == 0)
    pos = [x for x in lights if x > 0]
    print(f"  zeros(NULL) in Lights={zeros}  positive refs={len(pos)}  distinct pos refs={len(set(pos))}")
    # grid size distribution
    us = Counter((r.u_size, r.v_size) for r in recs)
    print(f"  #distinct (USize,VSize)={len(us)}  sample={dict(list(sorted(us.items()))[:6])}")
    return m, pkg


def main():
    nat = sys.argv[1] if len(sys.argv) > 1 else NATIVE
    ed = sys.argv[2] if len(sys.argv) > 2 else EDITOR
    analyze(nat, "NATIVE")
    print()
    analyze(ed, "EDITOR")


if __name__ == "__main__":
    main()
