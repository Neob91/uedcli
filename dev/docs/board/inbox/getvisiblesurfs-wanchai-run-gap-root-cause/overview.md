+++
priority = "p2"
kind = "debug"
summary = "Root-caused Wanchai's larger GetVisibleSurfs missed-pair count to same-zone rasterization over-occlusion, not MergeWith/portal fidelity as previously suspected; shipped a pixel-center rounding fix."
depends-on = ["port-urender-getvisiblesurfs-so-each-light-gets"]
+++

# GetVisibleSurfs Wanchai run-gap root cause: pixel-center rasterization fix

Resumes `native-light-apply-bake-where-it-stands-and`'s lead 1 (light runs). Wanchai's lighting was
71.3% byte-identical (3228/4530 `LightMap` records) with the "missed" (surf,light) pair count (350)
far exceeding "extra" (134) — 2026-08-29 measurement, current tree.

## Zone-crossing is NOT the dominant cause

The code comment on `visible_surfs.rs::SUBTRACT_OCCLUSION` speculated `MergeWith`
(`render.dll 0x1001e3b0`, undecoded) — the portal-merge-into-far-zone op — was "the likeliest
source of Wanchai's larger missed count (more zone/portal crossings than UNATCO)". Measured with
`pair_geometry.py` (fixed a stale `gather_lights` 3-tuple unpack to the current 4-tuple signature):
light/surf BSP-zone agreement is 94.6% on correctly-matched pairs, 96.3% on native's own false
positives, but only 80.0% on missed pairs — a real skew, but it means at most ~20% of the 350
missed pairs are zone-crossing. The other ~80% are same-zone: the light and the surface it fails to
reach share a BSP zone, so no portal merge is even involved.

## Live trace of a concrete same-zone miss

Added an env-gated diagnostic to `visible_surfs.rs` (`UEDCLI_VISGATE_TRACE_SURF`/
`UEDCLI_VISGATE_TRACE_LOC`, kept in the tree as a reusable probe) and traced Light45 → surf 2920 (a
same-zone miss, 21 surfaces affected by this light alone). Per-face breakdown: 2 faces reachable=
false (the whole zone-1 span buffer already exhausted before reaching the target), 2 faces clipped
away (target polygon outside that face's frustum — expected, it's a near-horizontal ceiling patch),
1 face reachable=false again, and 1 face where the target DID rasterize to real screen pixels but
`accepted_px=0` for every fragment. Tracing that last face's row 496 showed ~40 small, legitimately
opaque market-clutter surfaces (walls, stall dividers, furniture) had already consumed all of
row 496 except a small unclaimed strip the target's fragments didn't reach.

## The fix: pixel-center rasterization coverage

`rasterize_node` rounded each row's screen-space span outward to pixel boundaries (`lo.floor()`,
`hi.ceil()`) — "any pixel any part of the polygon touches", which pads every polygon's footprint by
up to ~1px per edge. In a scene with dozens of small adjacent opaque surfaces (Wanchai's market
clutter, denser than UNATCO), those pads compound across neighbours in one row and can swallow a
genuine gap a proper pixel-center rasterizer would leave open. Switched to the standard
pixel-center-inclusion formula (`x0=ceil(lo-0.5)`, `x1=ceil(hi-0.5)`: include column *i* iff its
center *i+0.5* lies in `[lo,hi)`).

## Measured result — shipped

| | Wanchai (positional, tree node-exact) | UNATCO (geometry-matched, tree not node-exact) |
|---|---|---|
| before | records byte-identical 3228/4530 = 71.3%; run differs 348; extra 134; missed 350 | run_ok 3077/3343 = 92.0%; dark/lit mismatch 29+36 |
| after  | records byte-identical 3297/4530 = 72.8%; run differs 266; extra 79; missed 314  | run_ok 3150/3343 = 94.2%; dark/lit mismatch 27+20 |

No regression on either level's shadow-bit-equal rate (99.00%→99.0X%, flat), grid/pan/scale rates,
or Wanchai's geometry exactness (surf/node/leaf counts unchanged — purely a lighting-side change).
`bin/test -k light` and full `cargo test` (uedcli-native) green.

## Still open

**`MergeWith` decoded and RULED OUT, same day** (`mergewith-fully-decoded-confirms-merge-into`,
`dev/docs/board/done/`): full disassembly + a 10-sample live capture during a real Wanchai
`LIGHT APPLY` shows `merge_into` already reproduces the real editor's row-merge algorithm exactly,
10/10 (7 pure appends, 3 genuine merges including touching-boundary cases). So the ~20%
zone-crossing share of the missed count is NOT a `MergeWith`-fidelity gap — its real cause is still
unidentified. The bulk of the remaining gap (Wanchai still only 72.8% byte-identical) is the largest
single bucket — pure `Pan`/`UScale`/`VScale` divergence with matching run+bits (711 of 1233 bad
records, re-measured 2026-08-30 on the current, post-`repartition_frontier` tree) — which follows from
the `Points`/geometry residual tracked in `wanchai-verts-points-residual-independently`, out of scope
here. After that, `bits`-only divergence with matching run/grid/pan/scale (255 records): the
`lumel_axes` vs `FCoords::Inverse` determinant-grouping-ulp hypothesis was CHASED 2026-08-30 and
REFUTED (disassembly proof + live gdb capture, 80/80 match — see the findings ledger and
`native-light-apply-bake-where-it-stands-and`) — `lumel_axes` needs no fix.

**2026-08-30, same day: `linecheck::line_clear` investigated and CONFIRMED as the real cause** (not
a geometry residual) — it disagrees with the editor's real bit even when fed the editor's own real
tree/inputs (20/40 sampled mismatches). Live-disassembled the real editor function on the current
build: refutes an old epsilon-tolerance hypothesis, rules out a plane-dot summation-order hypothesis
for the traced exemplar, but the exact per-node state formula was not fully decoded — no fix shipped.
Full writeup: `dev/docs/board/inbox/line-clear-shadow-ray-algorithm-gap-found-real/overview.md`.
