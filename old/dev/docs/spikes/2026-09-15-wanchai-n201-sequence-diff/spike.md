# WanChai N=201 — the 245-vs-165 sequence diff, done; new, sharper open question

Follow-on to `2026-09-15-wanchai-n201-raster-footprint` (found the 245-vs-165 `OccludeBsp`
rasterize-call-count mismatch for Light431's straight-down face but did not diff it) and
`2026-09-15-wanchai-n201-surf616-getvisiblesurfs-miss` (the original bug: native's `GetVisibleSurfs`
rejects world surf 616 for Light431 where UED22 accepts it). Settles the count question with a real
sequence diff, as scoped. **Not fixed** — the diff narrows the problem sharply and rules out several
hypotheses, but lands on a new, more precise open question (below), not a code change.

## The count mismatch is not one thing — it decomposes cleanly

`harness/diff_call_sequences.py` diffs the real editor's 245 `PRECALL` hits (`raster-callsite.log`,
already isurf-tagged per hit — the probe never needed extending, it was already logging `isurf` for
every hit) against native's own 165-call face-5 trace (`UEDCLI_VISGATE_TRACE_SURF=-1`,
`full_trace_light431.py`), via `difflib.SequenceMatcher` on the ordered isurf sequence:

```
DELETE  real[0:78]  = [a 78-entry block, mostly disjoint from native's own 165-surf set]
EQUAL   real[78:169] == native[0:91]    (91 calls, isurf-for-isurf, IN ORDER)
DELETE  real[169:171] = ['597', '597']
EQUAL   real[171:245] == native[91:165]  (74 calls, isurf-for-isurf, IN ORDER)
```

78 + 2 = 80, the documented gap. Two different things:

- **The 2-call gap is harmless, and explained.** `real[169:171]` are hits 170/171: both `isurf=597`,
  `ret=0`, `miny==maxy` (an explicitly EMPTY rasterize result — the real scanline routine was called
  but returned zero rows). Native's own trace shows the SAME coplanar chain (surf 597, 10 real chain
  members, nodes 663-672) — but native's `rasterize_node` returns `None` ("clipped away / degenerate")
  for chain members 671/672 instead of calling the shared scanline routine at all. Same real-world
  outcome (zero effect on occlusion, zero accepted pixels) reached two different ways — a call-site
  counting artifact of whether the low-level routine gets invoked for an already-known-empty clip, not
  a traversal or footprint bug.
- **The 78-call leading block does NOT touch surf 616 at all.** `grep isurf=616` on the whole 245-hit
  capture finds exactly ONE hit (197), inside the matching `real[171:245]` region. The leading block's
  own surf set has no overlap with 616 whatsoever. Whatever this block is, it cannot by itself explain
  surf 616's accept/reject outcome.

No duplicate light exists at Light431's exact coordinates in the N=201 trunk (checked directly against
the actor T3D) — the leading block is not capture bleed from a second, distinct light actor.

## The matching chain's accept/reject verdict is confirmed across every call, not just two spot-checked nodes

The prior spike's row check covered exactly two nodes (616 itself, 776/sky), comparing raw rows
directly. `harness/replay_matching_chain.py` extends the check to the WHOLE 165-call matching chain,
at the ACCEPT/REJECT granularity (the actual downstream question — whether a surf's span ends up
non-empty, `!accepted.is_empty()`, not the literal pixel-for-pixel span content): take the REAL
editor's own raw per-row rasterized windows (`raster-callsite.log`'s `ROW hit=N y=Y s=START e=END`
lines, already captured for every hit, no probe change needed for this half) for all 165 matching
calls, and replay them — in native's own call ORDER, using each call's own `opaque` classification
(borrowed from native's trace, since surf identity ⇒ `PolyFlags` ⇒ `occludes()` is the same static
property on both sides) — through a straight Python port of `test_and_maybe_subtract`
(`uedcli-native/src/visible_surfs.rs`, itself disassembly-verified against
`FSpanBuffer::CopyFromRaster(Update)`). Result: **zero accept/reject (`accepted_px>0` vs `==0`)
mismatches across all 165 calls**, including surf 616 itself (replay: `accepted_px=0`, matching
native's own `accepted_px=0` exactly).

This rules out, for the ENTIRE relevant chain (not just two nodes) and at the accept/reject
granularity the downstream logic actually consumes: a rasterizer footprint bug, a subtraction-
algorithm bug, and a node-visit-order bug — real's own inputs, fed through native's own algorithm,
reproduce native's own accept/reject verdict on every call. (This is a bucketed boolean check, not a
literal byte-for-byte span comparison — a footprint difference too small to flip any call's
`>0`/`==0` bucket would not be caught by it, though it would also be too small to matter to the
downstream question.)

## A harness bug found and fixed along the way

Extending the row-level check needed a wider `UEDCLI_VISGATE_TRACE_ROWS=<y0>,<y1>` capture
(`visible_surfs.rs`, the `wanchai-n201-raster-footprint` TEMP bisection probe). The row-band branch
was gated only on `row_band.is_some_and(...)`, not also on `trace.is_some()` — so with a wide band
(`0,3000`, needed to catch every row) it fired for EVERY light's own gather in the parallel (rayon)
bake, not just the one light `UEDCLI_VISGATE_TRACE_LOC` targets, interleaving unrelated lights' rows
in the log (millions of extra lines, node identities from all over the map). Fixed: the branch now
also requires `trace.is_some()`. `cargo test` stays green (244 passed, 2 ignored); WanChai N=1..200
re-verified byte-exact with the rebuilt binary (no regression — the change is unreachable on the
default path, gated behind a debug-only env var).

## A new, sharper open question: does something ACCEPT surf 616 at all?

A second, independent live capture from the prior investigation
(`2026-09-15-wanchai-n201-surf616-getvisiblesurfs-miss/logs/raster-order-n201-isurf616-hits.log`,
`raster_order_probe.py`, breakpointing `render.dll 0x10019c1c` — `test %edi,%edi` on
`FSpanBuffer::CopyFromRasterUpdate`'s own return value) shows this EXACT event (isurf=616,
origin=(-1160.74536,-807.899902,220.417908), zaxis=(0,0,-1) — Light431's straight-down face, matched
to full float precision, no tolerance ambiguity) with `edi=1`: UED22's own accept/reject test finds
something left unclaimed and keeps the surf.

That contradicts the replay above. Since the replay already rules out a footprint or subtraction bug
using REAL's own row data, the one variable left unverified is the span buffer's STARTING STATE at
the point the matching 165-call chain begins (real hit 79 / native call 1): native seeds a fresh,
fully-visible `SpanBuf::full()` per light per face (`get_visible_surfs`, a brand-new `ZoneBufs` per
`faces().iter().enumerate()` loop iteration) — the replay above assumes the same. If the real engine's
buffer for this exact zone/face ISN'T fresh at that point — carries some prior state instead — that
would change the true outcome without needing any different rasterization at all.

**Not settled here.** The leading 78-call block is native's or the real editor's — inconclusive:
26-31 of its ~31 disjoint surf IDs are ALSO visited by native's own OTHER 5 cube faces (0/1/2/3/4) for
this same light, which is consistent with either (a) shared architecture legitimately visible from
several directions (expected, not evidence of anything), or (b) the real editor invoking `OccludeBsp`
more than once for the exact same face signature (e.g. once per reachable start zone) — the two are
not distinguished by surf-ID overlap alone.

## Next step (not attempted here — a genuinely new live capture, not more static reasoning)

Settle the buffer-starting-state question directly: extend `raster_callsite_probe.py`'s PRECALL
breakpoint (or a sibling probe) to dump the live `FSpanBuffer`'s own row-interval-list content (the
struct at the captured `span=0x146bd14` pointer) at the FIRST hit of the matching chain (real hit 79,
`isurf=33`) — before that hit's own test. If it is a single `(0, 1024)` interval per row (matches
native's `SpanBuf::full()` seed), the buffer-freshness hypothesis is refuted and the paradox stays
open elsewhere; if it already carries prior subtraction/accumulation, that is the mechanism, and the
real fix is in the LIFECYCLE of the buffer (when the real engine seeds/resets it), not in a per-node
traversal step. `FSpanBuffer::MergeWith`'s layout is already fully decoded
(`2026-08-29-unatco-repart-live-diff/harness/mergewith_live_check.py`) — this probe would reuse that
struct knowledge, not start from scratch.

## Repro

```
dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
    --dx dev/games/deusex/Maps/06_HongKong_WanChai_Market.dx --from 201 --to 201 --keep-native

# the real-editor sequence (already committed, no rebuild needed):
#   dev/docs/spikes/2026-09-15-wanchai-n201-raster-footprint/logs/raster-callsite.log
# native's own whole-traversal trace, from a subset trunk (`actor_parity.make_subset`):
python3 dev/docs/spikes/2026-09-15-wanchai-n201-raster-footprint/harness/full_trace_light431.py \
    <N201 subset trunk maps dir> <project root>            > native-face5-whole-trace.log
UEDCLI_VISGATE_TRACE_ROWS=0,3000 python3 .../full_trace_light431.py <trunk> <project> \
                                                             > native-face5-trace-with-rows.log

harness/diff_call_sequences.py dev/docs/spikes/2026-09-15-wanchai-n201-raster-footprint/logs/raster-callsite.log native-face5-whole-trace.log
harness/replay_matching_chain.py dev/docs/spikes/2026-09-15-wanchai-n201-raster-footprint/logs/raster-callsite.log native-face5-trace-with-rows.log
```
