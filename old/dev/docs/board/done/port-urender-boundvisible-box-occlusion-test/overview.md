+++
priority = "p2"
kind = "implement"
summary = "Port URender::BoundVisible (box-occlusion visibility test) into native's visible_surfs.rs, gated to the confirmed iNode%16==0 residue, to close UNATCO N26's Light155 divergence faithfully."
spikes = ["dev/docs/spikes/2026-09-05-lightapply-node-flags-verification/"]
+++

# Port `URender::BoundVisible` box-occlusion test into native

## DONE 2026-09-06 — UNATCO N=26 gates byte-exact, no mask

`BoundVisible` (`render.dll 0x10012100`) and `FSpanBuffer::BoxIsVisible` (`0x1001dc10`) are ported in
`uedcli-native/src/visible_surfs.rs`, wired into `traverse` at the editor's own position (before
either child is descended), gated to `iNode % 16 == 0` plus the already-flagged retest rule, and
replayed onto `Model.Nodes[].NodeFlags` in light order by `light::bake`.

The frame constants the port needed were LIVE-MEASURED, not derived (`FSceneNode+0xc8` = 512.0 as the
projection centre, `Proj.Z` = `0x43ffffff`, all four clip slopes `0x3f800001`), and the port is pinned
against 225 real calls captured from a UNATCO N=26 golden build: every one of the 135 accepted calls
reproduces the editor's `FScreenBounds` exactly, and a whole-build trace diff agrees with the editor
on 225 of 225 shared box tests, node 48's reject included. Spike:
`dev/docs/spikes/2026-09-06-boundvisible-port/`.

One gap found and split out, not masked: native still skips `OccludeBsp`'s frustum-cone subtree
reject, so it box-tests 51 subtrees the editor discards and marks one extra node —
`dev/docs/board/inbox/port-occludebsp-frustum-cone-subtree-reject/`.

## Original task

Blocks UNATCO N26 (`light-apply-shadow-rays-read-transient-nf`). The amortization-counter mechanism
gating `NF_BoxOccluded` is now live-confirmed as a real, deterministic, portable property (not
incidental process state): every fresh-process headless golden build (`MAP IMPORT → MAP REBUILD →
LIGHT APPLY → MAP SAVE`) tests box-occlusion only for nodes where `iNode % 16 == 0`, for its entire
`LIGHT APPLY` pass — confirmed across all 5 ladder levels (UNATCO/WanChai/Bar/Island/OceanLab), by
direct instruction-level counter reads at `URender::GetVisibleSurfs`'s entry (see spike.md's
"CORRECTION" section). `URender::DrawWorld` (the only thing that ever bumps the counter) fires once
per build, always AFTER the last light — too late to matter.

## What's missing

Native's `uedcli-native/src/visible_surfs.rs` already has the zone-mask, moving-brush, frustum-cone,
backface, and portal/reachability filters (real, disassembly-ported), plus the per-node render bound
(`Model.Bounds[i_render_bound]`, populated by `passes.rs`) — but no box-occlusion step. UED22's own
box-occlusion test is `URender::BoundVisible(FSceneNode*, FBox*, FSpanBuffer*, FScreenBounds&)`,
`render.dll` file address `0x10012100` (export-table-confirmed:
`?BoundVisible@URender@@UAEHPAUFSceneNode@@PAVFBox@@PAVFSpanBuffer@@AAUFScreenBounds@@@Z`). Live-
resolved as the virtual-call target at the box-check call site (`render.dll 0x100193d5` file-relative,
inside `GetVisibleSurfs`); live-captured arguments are real level-space AABBs, confirming the
identification.

Disassembly (`rdis.py dis Render 0x10012100 0x1bf0`) shows it does a real outcode-style classification
of the box's corners against the frame's view planes, an early-return path for the trivial
"fully visible, no clipping" case (`ret 0x10` at file offset `+0x24c`), and a substantially larger
continuation for the partial-visibility/clipping case — comparable in size and character to
`GetVisibleSurfs` itself and to the `FSpanBuffer` rasterizer WanChai's own N45 item already scopes as
"a real spike, not attempted yet" (`wanchai-n45-spotlight22-light-runs-differ-on-4`).

## Why not done in the same pass

A byte-exact port needs the same rigor already given `GetVisibleSurfs` and the span buffer — full
disassembly, controlled-fixture cross-checks, a review — not a rushed pass. A cheaper stand-in (e.g.
reusing the existing per-zone `SpanBuf::any_visible` check as a "box visible" proxy) would
UNDER-occlude relative to the real per-box screen test: exactly the guessed-approximation
`NATIVE-MATERIALIZE.md`'s prime directive forbids.

## What a build here needs to do

1. Disassemble `BoundVisible` fully (starting point: `/tmp/boundvisible_full.txt`-style dump via
   `rdis.py dis Render 0x10012100 0x1bf0`, not committed — regenerate) — both the early-return
   trivial-accept path and the clipping continuation.
2. Gate native's box test to `node_index % 16 == 0` (matching the confirmed invariant) in
   `visible_surfs.rs`'s node traversal, mirroring the `NodeFlags & 0x10`-already-set stickiness rule
   (always retest if already flagged, regardless of residue).
3. Port `BoundVisible` itself against native's existing `FSpanBuffer`/reachability machinery.
4. Re-verify UNATCO N26 (and any other level/N this affects) with `parity_gate.py` — target: gates
   byte-exact with NO mask (the tie/exclusion machinery already removed per `NATIVE-MATERIALIZE.md`'s
   "point-dedup near-tie" entry stays the model: faithful fix, not a mask).

## No longer blocking UNATCO N26 (2026-09-06)

`a762617` (repartition point dedup: nearest, not first —
`island-n5-n12-pre-existing-model2-orphan-vert-4`) moved UNATCO's geometry, and N=26 now gates
byte-exact against a freshly editor-built ref, as do N=23..25 and N=27. So the `Light155` divergence
this item was filed to close is gone at that N. The engine gap itself is real and unported — keep the
item — but it is no longer what stops the UNATCO ladder; re-target it at whatever N reintroduces a
box-occlusion divergence.
