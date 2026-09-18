+++
priority = "p2"
kind = "investigate"
summary = "confirm whether the selected-brush pivot cross renders per-brush under multi-select, and check/implement a UED22-style visibility toggle"
+++

# Selected-brush pivot cross: multi-select rendering + visibility toggle

The red cross rendered on a selected brush (likely its pivot marker) has two open questions:

1. **Multi-select rendering**: with multiple brushes selected at once, does the cross render
   separately for EACH selected brush, or only once/incorrectly? Owner's hunch: it does NOT render
   per-brush currently. Confirm directly (select 2+ brushes, check if each gets its own cross) before
   assuming.
2. **Visibility toggle**: does UED22 have a way to toggle this marker's visibility on/off? If so,
   implement an equivalent GLOBAL toggle affecting all viewports in this GUI.

## Why this needs UED22 confirmation (part 2 only)

Part 1 is a pure investigation of OUR OWN current behavior, no RE needed. Part 2 (does UED22 have a
toggle) is a `GUI-PARITY.md` RE question -- confirm via source/disassembly or a live UED22 capture
before implementing a guessed toggle mechanism.

## Where to look

Likely `web/src/scene/SelectionMarkers.tsx` or wherever the pivot-cross marker is drawn -- check
whether it's rendered once per `selectedNames`/`selectedSurfaces` entry (correct) or keyed to some
singular piece of state (the bug, if the owner's hunch is right).
