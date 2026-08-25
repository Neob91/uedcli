+++
priority = "p2"
kind = "debug"
summary = "bspMergeCoplanars 8-case merge gap: live-traced to RemoveColinears rejecting a valid shared edge; one real grouping bug fixed, root mechanism still open"
+++

# bspMergeCoplanars 8-case merge gap: live-traced to RemoveColinears rejecting a valid shared edge; one real grouping bug fixed, root mechanism still open

Follow-up to `findbestsplit-divergence-forensic-dive-17-real`, which narrowed the 448-node UNATCO
gap to 8 named surfaces (`iLink`) where `bspMergeCoplanars` groups a source face's CSG fragments
differently than the real editor. This item re-verifies the 8, live-traces one (`iLink=1144`) down
to the exact rejecting call, fixes one confirmed grouping bug (inert on this map, real on others),
and leaves the actual rejection mechanism open — not a clean close.

## The 8, re-verified fresh

Grouped native's own post-merge soup (`UEDCLI_BSPCSG_SOUP_ORDER`, current `bspcsg.rs`) against the
committed `logs/repart-soup-full-unatco.log` by `iLink`. Same 8, same shapes, as the prior session
(reproduced independently, not read off their numbers):

| iLink | native frags (nv) | editor frags (nv) | pattern |
|---|---|---|---|
| 300  | 1 (5)                    | 1 (4)                    | same count, native keeps an extra vertex |
| 896  | 1 (5)                    | 1 (4)                    | same count, native keeps an extra vertex |
| 878  | 6 (4,6,4,4,4,4)          | 6 (4,4,4,4,4,4)          | same count, one native frag absorbed 2 verts |
| 889  | 4 (6,4,4,4)              | 4 (4,4,4,4)              | same count, one native frag absorbed 2 verts |
| 977  | 16 (…, one 5)            | 17 (all 4)               | native fused one adjacent pair, editor didn't |
| 888  | 4 (4,4,8,4)              | 6 (4,4,4,4,4,4)          | native over-merges (6→4) |
| 1144 | 1 (10)                   | 4 (4,4,4,4)              | native over-merges (4→1) |
| 1163 | 1 (10)                   | 5 (5,4,4,5,4)            | native over-merges (5→1) |

Total soup +10 (2504 native vs 2514 editor) traces entirely to these 8, as before.

## `iLink=1144`, live-traced end to end

New oracle scripts (same gdb/container pattern as the existing `editor-tree-oracle` harness):

- `repart_soup_verts_unatco.py` — full vertex + TextureU/V dump of the editor's post-merge soup,
  filtered to the 8 `iLink`s (`logs/repart-soup-verts-unatco.log`).
- `trytomerge_live_unatco.py` — breaks at `FPoly::TryToMerge`'s two exit points
  (`Editor.dll 0x34b73` fail, `0x34e1d` success) and its post-first-match label (`0x34bf1`) and its
  post-`RemoveColinears` test (`0x34dea`), filtered to the 8 `iLink`s
  (`logs/trytomerge-live-unatco.log`).

**The 4 raw fragments are byte-identical on both sides** (same `Base`/`Normal`/`TextureU`/`TextureV`
and, vertex-for-vertex, the same float32 coordinates to 6 decimals) — this is not an upstream CSG
divergence, the merge STAGE itself is where the two sides diverge.

**The group forms identically on both sides.** `bspMergeCoplanars`'s grouping predicate
(`Editor.dll 0x36200`, disassembled fresh) tests only `iLink`, coplanar offset, normal dot, and
texture-UV proximity — no other gate. All 4 fragments pass it pairwise against the anchor; the
survivors' `PolyFlags` carry the transient `0x40000000` "grouped" bit on the real editor too,
confirming a size-4 group forms and `MergeCoplanarPolys` runs, exactly like native.

**`TryToMerge` runs all 6 pairs and finds the shared edge on the 3 truly-adjacent ones** — live trace
confirms, for each adjacent pair, the exact same first-shared-point indices
(`Start1=2, Start2=1`) my own hand-decode of `0x34b10` predicts, and a 6-vertex ring gets built
(`TTM RING ringcount=6`). **Then `RemoveColinears` rejects it** (`TTM AFTERRC rc_eax=0`) — this is
where the real editor and native diverge: native's own `remove_colinears` (`fpoly.rs`) accepts the
same ring and completes the merge.

The 6-vertex ring for each adjacent pair has exactly one **reflex** (non-convex) vertex — verified by
hand from the live-captured coordinates (cross-product sign flips once around the ring; e.g. for the
first pair, `-372.9` against neighbours of `3355`–`14695`). This is circumstantial, not
instruction-pinned (see below), but consistent across all 3 adjacent pairs tested: **the real editor
may be refusing a coplanar merge that would produce a non-convex face**, which native's
`remove_colinears` (a ratio/cross-product colinearity test only, no convexity check) does not.

### Why the exact mechanism is NOT pinned, and a real methodological trap found along the way

`Editor.dll`, `Engine.dll`, and `core.dll` all declare the same preferred image base (`0x10000000`,
confirmed via `pefile`) but are loaded together in one process — the loader must rebase at least two
of them. Live-read the actual runtime pointer at `Editor.dll`'s own IAT slot for `RemoveColinears`
(`*(int*)0x100cee2c`): **`0x01771090`, not the naively-computed `0x10151090`** (Engine.dll is rebased
by roughly `-0xF00000`; Editor.dll is not — every prior capture against `Editor.dll` addresses this
session and prior sessions stayed self-consistent because of this). A follow-up live probe at the
corrected address (entry + exit of the real `RemoveColinears`, filtered by `iLink==1144`) produced
data inconsistent with being the TryToMerge-nested call (`nv=4` unchanged, always "success") — almost
certainly a different, far more frequent call site (`RemoveColinears` runs from many places, e.g.
`FPoly::Finalize`) rather than the intended one. **Not resolved in this item.** A static
re-disassembly of `RemoveColinears`/its internal `VectorsNear` helper (by RVA, which — unlike a live
breakpoint address — does not need the runtime rebase, since relative calls resolve correctly from
file offsets) found only a duplicate-point pass and a near-parallel-consecutive-edge pass (`1e-4` box
test); recomputing both by hand on the real ring predicts ACCEPT, contradicting the live `rc_eax=0`
result. So either that static reading itself missed something (a third pass, a convexity check, or a
different function than intended — the same rebase risk applies to confirming an RVA maps to the
right code without a live cross-check I didn't complete), or the real function does something neither
decode pass captured. **Anyone continuing this: any new live breakpoint into `Engine.dll` (or
`core.dll`) code must resolve the true runtime address via a live IAT-slot read first — do not trust
the static file RVA.**

## One real, confirmed, fixed bug (inert on this map)

Fresh disassembly of `bspMergeCoplanars`'s own grouping loop (`0x100362f0`-`0x1003641d`) shows the
candidate (`j`) scan tests every candidate against the anchor unconditionally and does NOT skip a
`j` already claimed by an earlier anchor's group — only the anchor role itself is skip-gated on the
`0x40000000` flag. Native's `bsp_merge_coplanars` (`uedcli-native/src/bspcsg.rs`) had an extra
`if grouped[j] { continue; }` in the candidate loop with no basis in the disassembly. Fixed (removed);
`grouped[j]=true` is still set on a match, matching the engine's unconditional re-flag. Added a
regression test, `merge_coplanars_rescans_a_poly_already_claimed_by_an_earlier_group`
(`bspcsg.rs`), that fails on the old code and passes on the fix.

**Confirmed inert on UNATCO**: re-ran the full 734-brush build with the fix — soup is byte-identical
(same 8 diverging `iLink`s, same shapes, same 2504 count) and the final tree is unchanged
(`nodes=6366`, matching before). None of the 8 cases' groups happen to hit the scenario this fixes
(a poly compatible with two mutually-incompatible anchors via the non-transitive texture-UV-proximity
test) on this particular map. Kept anyway — it is what the binary does, and could matter on other
content.

## The other 7 cases — not traced to the same depth

Time did not allow live-tracing all 8. From the pattern alone:
- `888`/`977` look like the same "editor doesn't merge an adjacent pair native does" shape as `1144`
  — plausibly the same `RemoveColinears` mechanism, not independently confirmed.
- `889` (native pre-merge has 10 raw fragments for a stacked wall, editor's post-merge has only 4)
  looks different in kind — worth checking whether native's own CSG fragmentation over-produces
  fragments for this face before merge is even reached, a separate question from `1144`'s.
- `300`/`896` (same fragment count, native keeps 5 verts where editor has 4) could be an unrelated,
  narrower over-strict-colinear-removal question (native keeps a vertex the editor's own
  `RemoveColinears` drops), not obviously the same "reflex merge" story.

## State left behind

- `cargo test --release`: 55/55 (54 prior + 1 new), `docker run ... uedcli-rust-build:latest cargo
  test --release` from the worktree root.
- Fix + test committed in `uedcli-native/src/bspcsg.rs` (the `grouped[j]` removal +
  `merge_coplanars_rescans_a_poly_already_claimed_by_an_earlier_group`), plus a new
  `UEDCLI_BSPCSG_PREMERGE_DUMP=<ilink>[,<ilink>...]` env-gated dump (matches the existing
  `UEDCLI_BSPCSG_*` family) that prints `bsp_build_fpolys`'s output for named surfs before
  `bsp_merge_coplanars` runs — needed to get native's own raw pre-merge fragments for comparison.
- New harness scripts committed: `repart_soup_verts_unatco.py`, `trytomerge_live_unatco.py` (both
  under `dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/`, following the
  existing pattern, cached logs under `logs/`). `removecolinears_live_unatco.py` was NOT committed —
  its breakpoint address, though IAT-corrected, produced inconclusive live data (see above); it is a
  dead end as written, not reusable tooling.
- Full UNATCO node disagreement: **unchanged, still 448** (soup byte-identical to before the fix, so
  the final repartitioned tree is unaffected). No castle fixture exists in this environment (prior
  sessions' finding, unchanged) so the castle-scale gate could not be re-run.

## Not pursued further here

The reflex-vertex hypothesis is not confirmed to instruction level and I did not implement it as a
fix — CLAUDE.md's "don't force a fix that doesn't actually reproduce the editor's behavior" applies:
I have circumstantial, not proven, evidence, and a wrong convexity gate could wrongly block real
non-reflex merges elsewhere. The next concrete step, if picked back up, is a live breakpoint on the
CORRECT (IAT-resolved) `RemoveColinears` address that also filters on the caller's return address
(to isolate the `TryToMerge`-nested call from `FPoly::Finalize` and other callers) rather than
filtering on `iLink` alone.
