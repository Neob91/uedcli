+++
priority = "p1"
kind = "debug"
summary = "The editor carves a different world BSP from the SAME 734 UNATCO brushes depending on how they entered the level: MAP LOAD 3705 surfs / 6254 nodes / 776 leaves vs MAP NEW+EDIT PASTE 3616 / 6314 / 762. Native reproduces the paste tree exactly, so the tree the production `level materialize` editor path builds is one native does NOT match."
+++

# `MAP LOAD` and `EDIT PASTE` build different world BSPs from the same brushes

Measured on `01_NYC_UNATCOHQ` (the `_scratch/bsp-parity-proj` trunk), both builds bare `MAP REBUILD`,
both world-only, both from the identical 734 `Engine.Brush` actors:

| brushes entered the level via | surfs | nodes | leaves | zones | distinct owning brushes |
|---|---:|---:|---:|---:|---:|
| `MAP NEW` + `EDIT PASTE` (`build_ued_golden.py --world-only`) | 3616 | 6314 | 762 | 7 | 719 |
| assembled unbuilt package + `MAP LOAD` (production `level materialize`) | 3705 | 6254 | 776 | 7 | 719 |
| native `build_geometry_bspcsg` | 3616 | 6314 | 762 | 7 | 719 |

Not actor-set contamination: a `MAP LOAD` build of a trunk cut down to LevelInfo + PlayerStart + the
734 brushes gives the same 3705 / 6254 / 776 as the full 1437-actor trunk, and on BOTH sides every
world surf's `iActor` resolves to an `Engine.Brush` export (no mover leaked into world CSG) across the
same 719 owners.

Why it matters: native's BSP parity is established against the PASTE tree. The tree the shipping
`level materialize` editor path actually produces is the `MAP LOAD` one, and native is 89 surfaces /
60 nodes / 14 leaves away from it. Any byte-level comparison of a downstream product — the lighting
bake above all, whose `LightMap` array is one record per lit surf — is meaningless across that gap,
because record *k* describes a different surface on each side.

Cause not investigated (owner ruling, 2026-08-27: build the lit lighting oracle the paste way and
move on rather than reconcile the two). Candidates, none tested: brush arrival order into
`csgRebuild`; the paste path's -32uu pre-shift/cancel vs the exact coordinates the package writes; a
per-poly field the clipboard T3D carries that the written package does not (or vice versa); the
builder brush's own shape differing between `MAP NEW` and the assembled package.

Reproduce (each is one editor run, ~4 min):

    dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py \
        --trunk <trunk> --out paste.dx --world-only --no-light --overwrite
    UEDCLI_SKIP_NATIVE=1 bin/uedcli --project <proj> level materialize \
        --tree level/<lvl> --out mapload.dx --overwrite --no-verify

then compare with `dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/lightparity.py`
(its first table prints surfs/nodes/points/leaves for both sides).
