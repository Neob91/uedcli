+++
priority = "p2"
kind = "debug"
summary = "Lighting record failure modes now split into 3 named, measured buckets (grid/bits/run); grid-only traced to real (but tiny) Points-value drift even on count-exact NYC Bar, bits-only traced to specific per-light shadow traces (not diffuse precision noise) -- both need live capture to go further"
depends-on = []
+++

# Lighting record divergence: failure-mode breakdown, two new localized findings

Full record-level breakdown of NYC Bar (87.7%, 821/936) and UNATCO (83.6%, 2797/3345) lighting
divergence -- not previously done this session (`native-light-apply-bake-where-it-stands-and` only
had aggregate percentages). Read-only against cached goldens (`/tmp/uedcli-parity-cache/`,
`_scratch/uedcli-parity-cache/<hash>/trunk`), no docker/live editor. Reproduction:
`dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/lightparity.py native.dx golden.dx`
gives the per-field counts; the mutually-exclusive bucket/correlation numbers below used one-off
scripts built on `lightparity.py`'s own `level_model`/`runs`/`planes` helpers (not committed --
exploratory, not a standing fact to pin with a test; see spikes.md's "one-off decision" exception).

## 1. Mutually-exclusive failure-mode partition (new -- not measured before)

`lightparity.py`'s own field breakdown (`u_size`/`v_size`/`pan`/`u_scale`/`v_scale`/`run`/`bits`) double
counts records with more than one bad field. Partitioning into MUTUALLY EXCLUSIVE buckets:

| bucket | NYC Bar (115 bad) | UNATCO (548 bad) |
|---|---:|---:|
| `bits`-only (grid+run agree, shadow bits differ) | 50 (43%) | 250 (46%) |
| `grid`-only (pan/scale differ, run+bits agree) | 49 (43%) | 196 (36%) |
| `run` differs (implies bits differ too) | 15 (13%) | 72 (13%) |
| other combinations | 1 | 30 |

Both levels show the same shape: `bits`-only and `grid`-only are roughly equal-sized, together ~85%
of all bad records; `run` (the known `GetVisibleSurfs` gap) is a consistent ~13%.

## 2. `grid`-only bucket: traced to real Points-VALUE drift, even where Points COUNT is exact

NYC Bar's geometry is COUNT-exact on all six metrics (verts/points/vectors/nodes/surfs/leaves, `d=+0`
all). The standing "Points residual" thread (`wanchai-verts-points-residual-independently`,
`unatco-verts-points-residual-after-the-zone`) only ever tracked COUNT deltas, so NYC Bar was assumed
clean on this axis. It is not: a multiset compare of native's vs golden's `Model.Points` arrays (2762
each) finds 54 native points (2%) whose VALUE doesn't match any golden point (e.g. native
`(0.0, -311.9998779296875, -255.99993896484375)` vs golden's `(0.0, -312.0, -256.0)` -- tens of ULPs,
not one). `Model.Vectors` similarly has 47/138 (34%) value-mismatched. UNATCO shows the same thing at
larger scale: 393/10768 points (3.6%) value-mismatched, on top of its already-known +16 count residual.

Correlating each record's owning surf (via `i_light_map`, then that surf's node vert-pool + `p_base`)
against this divergent-point set:

| level | `grid`-only bucket touches a divergent point | `identical`-record baseline |
|---|---:|---:|
| NYC Bar | 32/49 = 65.3% | 39/821 = 4.8% |
| UNATCO | 148/196 = 75.5% | 150/2797 = 5.4% |

13-14x enrichment on both levels -- this is a real, direct causal link, not aggregate coincidence:
the `Pan`/`UScale`/`VScale` divergence on a `grid`-only record is because its surf's base point or
texture vector is one of these value-drifted points, not a bug in the bake's grid-sizing math
(`axis_grid` in `light.rs` is unaffected; it correctly reproduces whatever `vmin`/`vmax` it's handed).
**No lighting-side fix is possible here** -- this is a geometry-side (CSG float-accumulation) bug,
already flagged as exhausted across 4 rounds in `wanchai-verts-points-residual-independently`
(recommend not reopening without a fresh live-capture angle: WHY specific points drift by tens of ULPs
even when the total count matches, which needs tracing the intermediate CSG split arithmetic, not the
lighting bake).

## 3. `bits`-only bucket (the largest, ~45% both levels): NOT diffuse precision noise -- localizes to specific (surf, light) pairs, and to specific RECURRING lights

The divergent-point correlation is weak here (NYC Bar 16.0%, UNATCO 8.4%, barely above the 4.8%/5.4%
baseline) -- this bucket is not explained by the Points-value-drift mechanism above.

Two further measurements pin it down more precisely:

**Mismatched bits cluster within ONE light's own sub-plane, not smeared across the whole record.**
For every multi-light record in this bucket, split `LightBits` back into its per-light `USize x VSize`
sub-planes (they're stored consecutively per the run) and XOR each independently:

- NYC Bar: 36/50 (72%) of bad records have EXACTLY ONE light with any wrong bits; every other light on
  that same surface, same grid, is bit-perfect.
- UNATCO: 132/250 (53%) likewise.
- Where more than one light is bad, the split is still typically 1-2 lights out of 4-9, not "all
  slightly off" -- e.g. NYC Bar record #7 (8-light run): 6 lights 0/96 bits wrong, 2 lights 12/96 each.

This rules out a diffuse per-lumel rounding-noise explanation (that would scatter errors evenly across
every light sharing a record) and points at a real, still-open shadow-TRACE divergence for specific
(surf, light) pairs.

**The "bad" light is not random per-surface noise -- specific light ACTORS recur as the bad one across
many different surfaces.** Tallying which light name carries the nonzero bits across the whole bucket:
NYC Bar's `Light30` is the bad light on 7 different surfaces (of only 50 bad records total); UNATCO's
`Light227` on 12 (of 250). Meanwhile co-located, same-radius lights on the SAME surfaces (e.g. NYC
Bar's `Light4`, radius 24, sharing surfaces with bad `Light31`, also radius 24) are consistently
bit-perfect. Checked the trunk T3D for an obvious static distinguisher (class, `LightRadius`) between
recurring-bad and always-good lights on NYC Bar -- none found; all are plain `Engine.Light` with
ordinary radii, no `LightEffect`/cone fields set. Whatever makes `Light30`/`Light227` (and the other
recurring names) special is not visible in the actor's declared properties alone -- likely a specific
Location/geometry relationship that only a live trace would surface.

**Also explains the earlier light-count correlation** (bits-only bucket's avg lights-per-surface is
2-3x the identical-record baseline on both levels): a surface lit by more lights has more chances that
one of them is a "bad" light, not that per-lumel noise scales with exposure.

## Bottom line

- No fix shipped -- both root causes need live capture to go further:
  1. `grid`-only: WHY do 54-393 Points/Vectors values drift by tens of ULPs even when total counts
     match. Needs live capture of the intermediate CSG split arithmetic (geometry side, already flagged
     exhausted 4x -- a genuinely new angle, not a retry of the old one).
  2. `bits`-only: WHY do specific recurring lights (`Light30`, `Light227`, ...) produce a wrong shadow
     trace on multiple surfaces while every co-located light on the same surfaces is correct. Needs a
     live gdb trace of `line_clear`/the editor's shadow ray for one of these SPECIFIC (surf, light)
     pairs, comparing native's ray walk against the real editor's step by step -- the same mechanism
     `line_clear_algorithm_check.py`/`linecheck_*.py` already use, just pointed at a newly-identified
     concrete repro (`Light30` vs any of its 7 bad NYC Bar surfaces) instead of a generic sweep.
- `9827f07` (the round-8 `line_clear` port, re-verified through round 10) is NOT contradicted by this
  finding -- 99.27%/99.76% shadow-bit agreement stands; this narrows what's left of the remaining
  0.24-0.73% to a small number of specific, reproducible (surf, light) pairs instead of "diffuse
  precision, chased+refuted" (the prior framing in `native-light-apply-bake-where-it-stands-and`'s
  "Two smaller leads" section, which this supersedes for the bits-only bucket specifically -- the
  refuted leads there, `lumel_axes`'s determinant and `MergeWith`, are independently confirmed correct
  and this finding does not reopen either).
- Both leads named as "chased" in the standing docs (shadow-ray precision, `MergeWith`) were checked
  against this new evidence and are NOT what's causing either bucket: `lumel_axes` was live-proven
  bit-identical (unrelated computation -- the determinant, not the ray walk) and `MergeWith` is fully
  decoded and confirmed faithfully ported (span-buffer merge, not per-lumel shadow tracing). Neither
  contradicts a real remaining gap in the ray walk itself for specific geometries.
