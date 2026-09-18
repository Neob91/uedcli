+++
priority = "p2"
kind = "investigate"
summary = "confirmed real fidelity gap: UED22 hides the pivot cross for a single selection, our GUI always shows it -- owner decision needed on whether to match"
+++

# Pivot cross visibility vs selection count -- CONFIRMED real fidelity gap, owner decision needed

Originally filed investigating `brush-pivot-cross-multiselect-and-toggle` (2026-09-18). A first pass
cited a third-party UE1 source and was retracted (owner ruling: only our own `uned/UED22/` binary
counts as GUI-PARITY evidence). This is the redo, from scratch, against our own `Editor.dll`.

**Confirmed 2026-09-18 by disassembly of `uned/UED22/Editor.dll`** (`pefile`+`capstone`,
`dev/docs/spikes/bspspike/` harness; no third-party source used) — real UED22 genuinely hides its
global pivot-cross marker for a single ordinary (non-snap-dragging) selected actor:

- `?SetPivot@UEditorEngine@@...` (RVA `0x46060`) tallies the level's own actor array
  (`ObjectFlags` bit `0x04` = selected → `Count`; bit `0x40` of the same byte → `SnapCount`) and
  writes a global: `GPivotShown = (SnapCount > 0) || (Count > 1)`. For exactly one selected,
  non-snapping actor this is `0`.
- The pivot draw site inside `?Draw@UEditorEngine@@...` (RVA `0x3c440`, VA `0x1003e7a0`) checks that
  exact global and skips the ENTIRE pivot draw + `HGlobalPivot` hit-proxy registration when it's 0.

Full trace and citations: `GUI-PARITY.md` "Pivot-cross multi-select rendering (closed) + visibility
toggle (closed 2026-09-18, real RE)".

**This is now a real, confirmed divergence, not a retracted guess:** our GUI's `PivotMarker`
(`web/src/scene/SelectionMarkers.tsx`) renders unconditionally for every selected brush, including
exactly one; real UED22 shows this marker only once 2+ actors are selected (or during an active
snap/grid-drag). No code change made here — matching this is a product/fidelity decision for the
owner, not something to silently implement. Options if pursued: gate `PivotMarker` to render only
when 2+ actors are selected (or a drag is active), matching UED22 exactly; or keep the current
always-on behavior as a deliberate usability improvement over the original editor. Left in `inbox/`
pending that call.

A supplementary live-screenshot probe (console-driven selection in an ephemeral `uned/UED22`
container, pixel-diffed) did NOT cleanly corroborate this — it found a marker-like pixel cluster even
at a single selection, but its position matched neither selected brush's own location, so it most
likely caught a different, ungated per-brush marker (`DrawLevelBrush`'s own vertex/local-origin dot)
rather than the `GPivotShown`-gated global cross. Recorded honestly in `GUI-PARITY.md` rather than
smoothed over; the disassembly is the authoritative evidence for this finding, not the screenshot.

**Owner's own direct test, real UED22, 2026-09-18 (higher confidence than anything above -- first-
party, hands-on confirmation): with multiple brushes selected, the red cross renders only for the
brush selected FIRST. Later selections in the same multi-select do not get their own cross.** This is
consistent with -- and sharpens -- the disassembly finding: `GPivotLocation`/`GPivotShown` are GLOBAL,
SINGULAR values, not per-actor, so UED22 draws AT MOST ONE cross total regardless of how many actors
are selected, anchored to whichever actor `SetPivot` used to set `GPivotLocation` (empirically: the
first-selected one). This also likely explains the inconclusive screenshot probe above: if it checked
for the marker at a LATER-selected brush's location rather than the first-selected one, it would
correctly find nothing there even when the real global cross was genuinely showing elsewhere.

**Needs disassembly confirmation of the exact "anchored to first-selected" mechanism** (not yet done)
-- likely `SetPivot`'s own `SingleActor`/actor-array-walk logic decides which actor's location seeds
`GPivotLocation` when multiple are selected; confirm whether it's genuinely "first selected" or some
other rule (e.g. lowest actor index, last actor processed in the walk direction, etc.) that happens to
usually coincide with "first selected" in ordinary use.

**The real fidelity gap is now sharper than originally framed**: it's not just "shows too eagerly
below 2 selections" -- it's structural. Real UED22 draws AT MOST ONE global cross ever; this GUI's
`PivotMarker` draws ONE PER SELECTED BRUSH, unconditionally, always. Both the visibility-count
threshold AND the one-vs-many structural difference are real, confirmed divergences from real UED22,
still left as a product decision for the owner (no code changed here).
