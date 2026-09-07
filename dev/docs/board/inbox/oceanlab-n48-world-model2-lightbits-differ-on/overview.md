+++
priority = "p2"
kind = "debug"
summary = "OceanLab N48 FAILS on the world Model2's LightBits alone -- 28 bytes across 3 lightmaps; every geometry array is byte-exact."
+++

# OceanLab N48 world Model2 LightBits differ on three surfs

OceanLab reaches N=47 (the Pass-D kill-the-original fix,
`oceanlab-n46-world-model2-bounds-leafhulls-and`) and bails at N=48.

`model_dump.py native_N48.dx ref_N48.dx model2`: `bbox`, `sphere`, `vectors`, `points`, `zones`,
`lightmap`, `bounds`, `leafhulls`, `leaves` and `numsharedsides` are all SAME, and
`spikes/2026-09-06-passd-kill-split-original/model_field_diff.py` reports 0 differing node fields, 0
live-ring verts and 0 surf fields once the gate's masks are applied. `lightrun_diff.py` reports 0
differing light RUNS. The whole residual is **`LightBits`**: 28 of 101186 bytes, in lightmaps 182
(20 bytes, surf 194), 183 (5, surf 204) and 201 (3, surf 209).

So this is a shadow-RASTER divergence, not a gather or a geometry one — same family as
`wanchai-n45-spotlight22-light-runs-differ-on-4` reaches into (`FSpanBuffer` / `ClipBspSurf` /
fixed-point scanline setup), but here the light SET per surf already agrees and only the lumel bits
differ.

Confirmed real 2026-09-07: re-run with `--force-ref`, so scored against a freshly built reference,
N=48 still FAILs on `BODY model model2`. It is not the bad-reference class of
`unatco-n-116-world-model2-light-runs-differ-on`.

## Repro

    ladder_run.py --dx <…>/Maps/14_OceanLab_Lab.dx --from 48 --to 48 --keep-native
    model_dump.py <…>/native_N48.dx <…>/ref_N48.dx model2
