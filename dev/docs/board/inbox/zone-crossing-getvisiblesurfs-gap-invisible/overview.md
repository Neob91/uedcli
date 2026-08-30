+++
priority = "p2"
kind = "debug"
summary = "Root-caused Wanchai's zone-crossing GetVisibleSurfs misses: PF_Invisible was wrongly gating portal zone-crossing (not just emission); fixed and shipped, partial improvement on both Wanchai and UNATCO."
depends-on = ["getvisiblesurfs-wanchai-run-gap-root-cause", "mergewith-fully-decoded-confirms-merge-into", "port-urender-getvisiblesurfs-so-each-light-gets"]
spikes = ["dev/docs/spikes/2026-08-29-unatco-repart-live-diff/"]
+++

# Zone-crossing `GetVisibleSurfs` gap: invisible portals were never crossed, now fixed

Resumes `getvisiblesurfs-wanchai-run-gap-root-cause`'s open tail: `MergeWith` was confirmed correct
(`mergewith-fully-decoded-confirms-merge-into`), leaving the ~20% zone-crossing share of Wanchai's
missed (surf,light) pairs unexplained. This item finds and fixes the real cause.

## Finding a concrete pair

`zone_crossing_pairs.py` (new, `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`, extends
`pair_geometry.py`) lists concrete editor-only (surf,light) pairs whose light BSP zone differs from
the surf's BSP zone (both read from the editor's own golden build, so the zone LABELS are
self-consistent). Picked `Light482`/`surf881` on Wanchai (light zone 4, surf zone 1 in the editor's
numbering) — one light, seven surfaces, all missed by native, all in the same far zone.

## Live trace: the only connecting portal is rejected before rasterization

Added `UEDCLI_VISGATE_TRACE_PORTALS` to `visible_surfs.rs` (kept as a reusable probe, matching the
existing `_TRACE_SURF`/`_LOC` pair): when set, prints every `PF_Portal` node the traversal visits for
the traced light, regardless of target surf. For Light482 (native's own zone numbering: view_zone=2),
the ONLY portal connecting to the target's zone (native zone 1) is surf 998 — and it is rejected
`REJECTED_BEFORE_RASTER ... invisible=true` on every one of the six cube faces. Never rasterized,
never tested, never crossed.

Checked whether this is a native flags bug: surf 998's `PolyFlags = 0x4000109` (`PF_Portal|
PF_NotSolid|PF_TwoSided|PF_Invisible`) is IDENTICAL, bit for bit, between native's build and the
editor's own golden — same node index too (Wanchai's tree is node/surf/leaf-exact between the two).
So this is the SAME physical portal in both builds, correctly flagged invisible on both sides — not a
flags-decode bug. The zone LABELS differ (native back-zone=2 vs editor back-zone=4) but that is
expected: zone IDs are arbitrary union-find output, not stable across independently-run builds; the
portal's zones agree with the light's own zone and the target's own zone on EACH side independently,
confirming it is the genuine physical connector.

## Root cause: `invisible` was gating zone-crossing, not just emission

The disassembly in `port-urender-getvisiblesurfs-so-each-light-gets` ("per-node/per-surface filters,
in traversal order") already had the answer, previously mis-read as one combined gate. Step 10 (zone
reachability) and the portal-crossing code named under step 1 (`ActiveZoneMask` OR + `MergeWith`,
address `0x1001a257`) both run BEFORE step 11's `PF_Invisible` emission-exclusion check (address
`0x1001a30d`) — a real address-ORDER fact, not adjacency. So the real editor rasterizes, span-tests
and zone-crosses a `PF_Portal` node regardless of `PF_Invisible`; the flag only suppresses the surf's
own appearance in the light's final run.

`visible_surfs.rs::traverse` had folded `!invisible` into the SAME gate as `reachable`/`front_ok`/
`!portal_needs_zones` — so an invisible surface (portal or not) never got rasterized, tested, or
crossed at all. Since a `PF_Portal` surface is near-universally ALSO `PF_Invisible` (a zone portal is
not meant to render — real Deus Ex portal brushes carry exactly this `0x4000109` combination), this
silently blocked most/all invisible-portal zone-crossings.

## Fix

Moved `!invisible` out of the shared raster/test/portal-cross gate into ONLY the `out.insert(n.i_surf)`
step (the final "add to the light's run" emission). Rasterization, `test_and_maybe_subtract` and the
portal `merge_into`/`active_mask` update now run unconditionally on `invisible`, still gated on
`reachable && front_ok && !portal_needs_zones` as before. Non-portal invisible surfaces are now also
rasterized/tested (matching the real editor's `CopyFromRaster` call for every non-occluding surface)
but this is functionally harmless — `PF_Invisible ⊂ PF_NONOCCLUDING` already keeps `opaque=false` for
them, so no span-buffer mutation happens either way; they still never reach `out.insert`.

## TDD

`an_invisible_portal_still_propagates_visibility_into_its_far_zone` (`visible_surfs.rs`): a hand-built
two-zone `Model` (no CSG — a single portal node dividing one open volume, mirroring how a real portal
brush is typically placed in open space with nothing to carve) with a `PF_Portal|PF_Invisible`
boundary. Asserts the far wall IS reached (RED before the fix) and the portal surf itself is still
never emitted (guards against a naive "just delete `!invisible` everywhere" overcorrection that would
also list portals themselves as lit surfaces). `cargo test`: 89/89 (was 88).

## Measured result — shipped

Pure lighting-bake change; geometry unaffected (`regression_gate.py`/`breadth_gate.py`: UNATCO
6314/6314, Wanchai 11648/11648, both exact, unchanged before/after).

| | Wanchai (`light_spotcheck_wanchai.py`) | UNATCO (`light_spotcheck_unatco.py`, geometry-matched) |
|---|---|---|
| before | records byte-identical 3297/4530 = 72.8%; run differs 266 | records byte-identical 2692/3345 = 80.5% |
| after  | records byte-identical 3319/4530 = 73.3%; run differs 240 | records byte-identical 2739/3345 = 81.9% |

Shadow-bit agreement flat-to-slightly-up on both (Wanchai 99.00%→99.01%, UNATCO 99.23%→99.25%). Real,
modest, same-direction improvement on both levels — consistent with fixing a SUBSET of the
zone-crossing share (only ~20% of Wanchai's missed pairs cross a zone at all, and not every crossing
goes through a purely-invisible portal). `bin/test -k "visible_surfs or light"` and full `cargo test`
green; full `bin/test` run to confirm no other regression.

## Still open

The remaining zone-crossing misses (this did not close 100% of the ~20% share — no further live trace
done this round to find a second cause). The much larger buckets are unrelated and untouched: the
`Pan`/`UScale`/`VScale` bucket (`Points`/geometry residual, `unatco-verts-points-residual-after-the-
zone`) and the `bits`-only bucket (`line_clear`, `line-clear-shadow-ray-algorithm-gap-found-real`).
