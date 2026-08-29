+++
priority = "p2"
kind = "debug"
summary = "Geometry re-check on 4 more OG levels: 0/4 exact, all slightly over-built"
+++

# Geometry re-check on 4 more OG levels: 0/4 exact, all slightly over-built

Current-tree (post-`5b0a022`) geometry-only recheck via `uedcli_native.build_geometry_bspcsg`
direct (bypassing `level materialize`'s CLI — these `geo-confirm-*` trunks from the earlier
10-level spike aren't class-qualified) against their existing world-only goldens:

| level | nodes Δ | surfs Δ | leaves Δ | points Δ | vectors Δ | verts Δ |
|---|---:|---:|---:|---:|---:|---:|
| smuggler | +104 (+1.5%) | +138 | +1 | +256 | +25 | −9624 |
| paris-chateau | +401 (+3.6%) | +185 | +132 | +620 | +35 | −11246 |
| training-final | +17 (+0.2%) | +49 | +39 | +117 | +28 | −20798 |
| hk-helibase | +226 (+1.6%) | +330 | +233 | +398 | +3 | −9711 |

None exact. Native slightly OVER-builds nodes/surfs/leaves/points/vectors on all 4 (a few
percent), and under-builds Verts substantially on all 4 — the same SHAPE as UNATCO's
already-known Verts/Points residual (`unatco-verts-points-residual-after-the-zone`), not a new
distinct bug per level. Consistent with the small deltas the "10-level geometry-confirmation"
spike found ("9/10 at or above golden") — this just re-measures 4 of those on the current tree.

Combined with UNATCO+Wanchai (exact) and Area51 (severely under-built, separate cause): of 7
OG levels checked on the current tree, 2 are geometry-exact. Closing the shared Verts/Points
residual is likely the single highest-leverage next step for geometry across the whole corpus,
not a per-level chase.

## Update 2026-08-29: NOT the same bug as UNATCO's — the repartition-frontier fix makes these 4 WORSE

`unatco-verts-points-residual-after-the-zone` shipped the repartition-frontier fix, which was
assumed (per this item's "not a new distinct bug per level" line above) to help these 4 too. It
does not — re-measured with the fix in: all 4 flip from Verts UNDER-built to OVER-built (smuggler
−9624→+10615, paris-chateau −11246→+9771, training-final −20798→+11550, hk-helibase −9711→+15988),
and node over-build roughly doubles on 3 of the 4 (smuggler +104→+253, hk-helibase +226→+460). So
this item's premise was wrong: these 4 levels have a DIFFERENT, still-unexplained over-build cause
on top of (or instead of) the sub-BSP-repartition gap — fixing the shared mechanism exposed rather
than closed their residual. Still 0/4 exact; needs its own investigation, not covered by the
repartition-frontier fix.
