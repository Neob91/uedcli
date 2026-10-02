# Where do the UnrealEd grid findings go, and should the harness become a test?

## Context

You asked me to confirm, by reverse engineering, that UnrealEd renders a coarser grid when the
selected grid size cannot be drawn. It does — `dev/docs/spikes/2026-08-30-unrealed-ortho-grid-density/`
has the disassembly and a 9/9-passing harness against the tracked `uned/UED22/Editor.dll`.

The spike turned up four facts about the editor, three of which this project did not have written
down anywhere:

| Fact | Evidence |
|---|---|
| Too-fine grid → step doubles until ~4 px per line; the coarser grid is drawn | the `shift` loop in `DrawGridSection` |
| Two tiers: every 8th line at alpha `1.0`, the rest at `0.5` | `((index << shift) & 7) ? 0.5f : 1.0f` |
| The grid is clamped to ±32768 world units | `0xffff8000` / `0x8000` divided by the grid size |
| A fade as density approaches the doubling point | `2.0 - (2·count)/((1<<shift)·limit)` |

Two decisions follow, and both are yours because they land outside the board.

## Proposed edit

**1. A durable home in `dev/docs/unrealed/`.** These are engine facts, and `CLAUDE.md` says engine
findings belong in `dev/docs/unrealed/`, back-referenced from code comments — but I cannot create or
edit anything there without your yes. Proposal: a new short section in
`dev/docs/unrealed/rendering.md` (which already owns viewport/render behaviour and already mentions
`SHOW_Frame` — "the editor grid + axes + chrome"), marked 📖 string-extracted per that file's
confidence convention, ~15 lines, linking to the spike for the disassembly.

The alternative is to leave the findings only in the spike. That is what happens if you say nothing —
but spikes are not the place a later reader looks for "how does the editor draw its grid".

**2. Promote the harness to a regression test.** `rules/spikes.md` wants every checkable finding
pinned by a committed test, "against the real binary where feasible". It is feasible here:
`uned/UED22/Editor.dll` is tracked, and `harness/grid_density.py` already asserts all nine facts.
Proposal: move it into the suite as a `test_engine_facts` case that back-references the spike, so a
different `Editor.dll` or a wrong reading fails loudly instead of rotting.

I did not write that test: this session is speccing, and adding it is a code change.

## Answer

<!-- Empty = open. Write the decision here. -->
