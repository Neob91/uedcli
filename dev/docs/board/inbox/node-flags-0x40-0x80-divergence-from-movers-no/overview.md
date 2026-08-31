+++
priority = "p3"
kind = "docs"
summary = "node_flags 0x40/0x80 divergence from movers: no editor setter found, likely uninitialized-memory noise not a real occlusion algorithm"
+++

# node_flags 0x40/0x80 divergence from movers: no editor setter found, likely uninitialized-memory noise not a real occlusion algorithm

Follow-up to `texture-ref-i-actor-divergence-traced-to-golden` Round 2's `node_flags` finding
(862/6314 UNATCO world nodes differ between the movers-excluded and movers-included widened
goldens). That item asked "is this render occlusion (`quirks.md`'s `NF_PolyOccluded`/
`NF_BoxOccluded`) reacting to a bigger scene, or something else" and left it open. This item is the
follow-up characterization; homed separately since the mechanism turned out to be about
`node_flags`/occlusion specifically, not `texture_ref`/`i_actor`.

**Bottom line up front:** two-thirds of the divergence (bits `0x40`/`0x80`) is a NEW, previously
uncharacterized phenomenon with no disassembly-confirmed editor setter anywhere — most likely
uninitialized-memory noise from a mover-specific allocation pattern, not a real algorithm. The
remaining third (bits `0x08`/`0x10`) is fully explained by the ALREADY-confirmed render-viewport
occlusion leftover (`node-flags-8-is-nf-polyoccluded-a-render-only`, done/). Neither supports
switching the default golden to movers-included — if anything this strengthens the case for masking
`node_flags` out of geometry-content comparisons entirely, regardless of golden actor set.

## Setup

Rebuilt from `/tmp/uedcli-widen-test/` (files still present, dated 2026-08-31, matched the prior
round's description on inspection — not rebuilt from scratch, but cross-checked against a fresh
determinism control below): `unatco_widened.dx` (movers-excluded, 6314/3616/762), `unatco_all.dx`
(movers-included, `--allow-brush-bearing`, same counts), `unatco_widened_run2.dx` (a second
independent movers-excluded build, for the determinism control).

World `Model` extracted via `parity_compare.parse_dx_model` (largest `Engine.Model` export by
serial size) from each `.dx`; nodes compared positionally by index (valid since node COUNTS are
already confirmed identical — this is not a tree-shape question, `bspcsg`/`build_geometry_bspcsg`
positional indexing already established this).

## 1. Reproduced, and confirmed determinism holds

`unatco_widened.dx` vs `unatco_widened_run2.dx` (both movers-excluded, independent builds):
**0 node_flags diffs** — the harness is deterministic, matching the prior round's claim.

`unatco_widened.dx` vs `unatco_all.dx`: **862/6314 (13.7%) node_flags diffs**, reproduced exactly.

## 2. Which bits — a clean split into two families, one old and one new

Per-node XOR of the 862 diffs, counted by bit:

| bit | name (if known) | # nodes flipped |
|---|---|---:|
| `0x08` | `NF_PolyOccluded` (confirmed render-only, done/) | 337 |
| `0x10` | `NF_BoxOccluded` (confirmed render-only, done/) | 34 |
| `0x40` | unknown | 346 |
| `0x80` | unknown | 218 |

`0x40`/`0x80` never appear ANYWHERE in the movers-excluded build (its full set of observed
`node_flags` values is `{0,1,2,3,4,8,9,10,11,12,13,16,17,20,24,28}` — no bit above `0x10`). They
appear only once movers are added. Union of nodes touching either `0x40` or `0x80`: **564** — almost
two-thirds of the whole 862-node diff, and MORE than the `0x08`/`0x10` union (364).

**Isolating the general-actor-population effect (not mover-specific) confirms the split.** The
existing shared parity cache holds a `03_NYC_UNATCOHQ` golden built by the PRE-widening (original
narrow, `Brush+LevelInfo+lights` only) filter (`/tmp/uedcli-parity-cache/485ea1.../golden.dx` —
counts match, `content_hash`-keyed, dated same day). Diffed against `unatco_widened.dx` (the
movers-excluded WIDENED golden, decorative/non-brush actors added, no movers): **20/6314 diffs,
every single one bit `0x10` only.** Zero `0x08`, `0x40`, or `0x80` at this smaller scale — this
exactly matches the "smaller same-direction effect" the prior round flagged as unexplained, and now
it's explained: general (non-mover) actor-population growth perturbs ONLY the already-known render
bit, at a small scale (0.3%). The jump to `0x08`(new, 337)+`0x40`(346)+`0x80`(218) happens
specifically when the ADDED actors are movers — brush-bearing, own private Models, real CSG/paste
work per actor, unlike a plain light or decoration.

## 3. Static disassembly: no setter for 0x40/0x80 anywhere

Repeated the exact method the original `node_flags=8`/`NF_PolyOccluded` finding used (`capstone` +
`pefile` over `/workspace/uedcli/uned/UED22/*.dll`, scanning for any instruction touching
`FBspNode.NodeFlags` at struct offset `+0x37`), widened to catch ANY mnemonic (`or`/`and`/`xor`/
`bts`/`btr`/`mov`/`movzx`) and ANY addressing form, across `Editor.dll`, `render.dll`, `core.dll`,
`Engine.dll`, and `unrealed.exe`:

- **`Editor.dll` — literally zero instructions touch offset `+0x37` in any form.** Extends the prior
  "Editor.dll sets neither `0x08` nor `0x10`" finding to EVERY bit, not just those two: the entire
  deterministic build path (`csgRebuild`/`bspBrushCSG`/`bspRepartition`/`bspRefresh`/
  `TestVisibility`, all here) never touches `NodeFlags` post-creation. Whatever ends up in this byte
  is set once, at `bspAddNode` time, from its explicit `NodeFlags` argument — never patched
  afterward by anything in `Editor.dll`.
- **`render.dll`** — only the already-known 4 instructions: `or [.+0x37],0x10` ×2 (`NF_BoxOccluded`
  set), `or [.+0x37],8` (`NF_PolyOccluded` set), `and [.+0x37],0xf7` (`NF_PolyOccluded` CLEAR, not
  previously logged — the occlusion walk's own reset step), plus a `mov cl,[edi+0x37]` /
  `mov [edi+0x37],cl` save/restore pair immediately adjacent to the same function. All 6
  instructions are part of ONE function (the confirmed occlusion-walk), none set `0x40`/`0x80`.
- **`core.dll`, `unrealed.exe`** — zero hits.
- **`Engine.dll`** — 2 candidate hits (`movzx eax,[edi+0x37]; mov [esi+0x37],al`, twice) — checked
  against the export table, both land inside `TLazyArray<BYTE>`'s constructor/assignment operator
  (mangled `??0?$TLazyArray@E@@...`/`??4?$TLazyArray@E@@...`), a generic lazy-array template
  completely unrelated to `FBspNode` — coincidental offset collision, not a real hit.

**No binary anywhere sets bits `0x40`/`0x80` on `NodeFlags` via a single-byte OR/AND/copy.** Either
they're set via a block copy (`memcpy`/`rep movs` of a whole `FBspNode`, which wouldn't show up as a
targeted `+0x37` instruction — not ruled out) or they are never deliberately set at all.

## 4. Structural correlation: real but far too small to be the mechanism

Extracted all 28 `DeusExMover*` `Location`s from the UNATCO trunk
(`_scratch/bsp-parity-proj/maps/unatco/actors/`) and walked the movers-excluded tree's own
`i_front`/`i_back` plane-side descent from the root for each mover's point — the only structurally
plausible "movers touch these specific nodes" mechanism (point classification against the world BSP
to resolve a mover's zone/leaf).

- Paths are short (tree is shallow near the root): **9-10 nodes per mover**, union across all 28
  movers = **24 distinct nodes total** — nowhere near the 564 nodes flipping `0x40`/`0x80`.
- Real but weak enrichment: every mover's own path DOES hit several diff nodes (3-5 out of 9-10, a
  33-55% hit rate vs the 13.7% base rate) — 4x above chance. But this only explains 9 of the 564
  `0x40`/`0x80` nodes (and 0 of the `0x08`/`0x10` nodes) by direct overlap.
- No zone-clustering either: `0x40`/`0x80` nodes' zone-pair distribution tracks the level's overall
  per-zone node population proportionally (top zones `(0,2)`/`(2,2)` dominate both the diff set and
  the full node population in the same order) — scattered level-wide, not concentrated near mover
  placements. Matches the ORIGINAL 0x08 finding's own "598 nodes, scattered, uncorrelated with zone"
  characterization.

**Verdict: "movers get filtered into the tree, touching nodes on the way" is a real but minor
contributor, not the primary mechanism.** Something with a much bigger footprint is responsible for
the bulk of the 564-node `0x40`/`0x80` set.

## 5. Best-supported (not live-confirmed) explanation: allocation-history noise, not a real algorithm

No confirmed mechanism this round — flagging the leading hypothesis and why, per the standing "don't
guess a fix" rule.

`native-materialize-findings.md` already established (2026-08-30, live-verified,
`nodesnum_watch.py`/`node_content_before_after.py`) that the editor's Nodes array grows past its own
`Nodes.Num` into un-zeroed scratch slots during every `bspRepartition` subtree call, later trimmed
back by `FArray::Remove` — i.e. the array's backing memory is reused as working space without
necessarily being zeroed on grow. Movers are brush-bearing: `_re_add`/`EDIT PASTE` does real
per-mover CSG/paste work building 28 separate private Models — categorically more and different
allocation activity than pasting an equal number of plain point actors (lights, decorations), which
is exactly the actor class the `0x40`/`0x80` divergence is gated on (§2's isolation: non-mover
actor-population growth moves ONLY `0x10`; add movers specifically and `0x08`/`0x40`/`0x80` all
appear).

If `NodeFlags` for a surviving node was set once at creation (§3) and never touched again, and if
that creation-time value can, for some code path, read from not-yet-written memory (a real node
allocated into a slot the allocator handed back without clearing, e.g. after `FArray::Realloc`
without a zero-fill) — the observed pattern (present only with the actor class that changes
allocation patterns most; scattered, not clustered; a set of bits with no confirmed setter anywhere)
is a better fit for uninitialized-memory content than for a deliberate scene-aware computation. This
is a hypothesis, not a finding — no live capture (heap dump / watchpoint on the specific surviving
nodes' `NodeFlags` byte across the whole session) was done this round to confirm it.

## What this means for "should movers be in the default golden"

**Does not support switching to movers-included.** The `0x08`/`0x10` share is fully explained by the
existing confirmed-excluded render-viewport mechanism — real, but already known and already handled
(native correctly never derives it either way). The `0x40`/`0x80` share, the larger of the two, looks
like noise uncorrelated with the editor's real deterministic build (no setter found; weak/scattered
structural correlation) rather than a real algorithm a movers-included golden would let native
faithfully reproduce. If the noise hypothesis is right, there is nothing here to "port" — the
opposite of the round's motivating question. **Recommendation (not a decision — the owner's or
coordinating session's call, same as Round 2 left it): extend the existing `node_flags`
comparison-exclusion (`82b-ground-truth-byte-diff.md`, "masking BOTH bits makes the editor's
build-time flags EQUAL native's exactly") to cover `0x40`/`0x80` too, in any future geometry-content
comparison tooling** — the field is not a reliable signal for parity work under EITHER golden
variant, for two independent reasons now instead of one.

## Left undone (budget)

- No live gdb capture — the leading hypothesis (§5) is not confirmed. Would need a watchpoint on the
  specific surviving nodes' `NodeFlags` byte across a real movers-included `MAP REBUILD`/`EDIT PASTE`
  session, or a heap-history dump, to settle memcpy-of-a-whole-node vs uninitialized-memory vs a
  setter this static method can't see.
- Not checked whether `0x40`/`0x80` correlate with node CREATION ORDER (index in the final array as
  a proxy) beyond the coarse mean/median already computed (both diff families sit slightly
  lower-index than the full population's mean — 2538-2748 vs 3157 — a weak signal, not chased).
- Not checked on any level other than UNATCO (budget; UNATCO was the only widened-with-movers golden
  available this round per the prior round's own scope).

## Reproduction

Throwaway scripts, not committed (`/tmp/nodeflags-investigation/`, recipe only):
`parity_compare.parse_dx_model` on the three `/tmp/uedcli-widen-test/unatco_*.dx` files + the cached
narrow golden, positional `node_flags` XOR + bit histogram; mover locations via a regex over
`_scratch/bsp-parity-proj/maps/unatco/actors/DeusExMover*/actor.t3d`'s `Location=` line;
root-to-leaf descent via the movers-excluded tree's own `plane`/`i_front`/`i_back`. Disassembly scan:
`capstone`+`pefile` over `/workspace/uedcli/uned/UED22/*.dll`/`.exe`, matching `or`/`and`/`xor`/
`bts`/`btr`/`mov`/`movzx` instructions whose operand string contains `+ 0x37]`.
