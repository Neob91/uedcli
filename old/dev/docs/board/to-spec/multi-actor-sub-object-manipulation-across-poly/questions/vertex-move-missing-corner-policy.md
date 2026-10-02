# `brush vertex move` over a set: a named brush with no corner at `--at` — error or skip?

## Context

`--at X,Y,Z` names a world corner. Across a curated brush set, some named brush may have no corner
there. Single-brush today raises → exit 2.

- Option A (recommended): all-or-nothing — a named brush lacking a corner at any `--at` → exit 2
  naming it. Matches "no silent half-answers"; the user curated the set, so a miss is a real error.
  Brushes that share a welded world corner all move it together.
- Option B: skip a brush that lacks the corner (best-effort across the set). Softer, but a
  half-applied move reads as complete. The pull toward B is real: adjacent brushes rarely share a
  float-EXACT corner, so strict all-or-nothing may reject sets a user reasonably expected to work — in
  which case a small weld tolerance, or B, may be wanted.

Recommendation: A (exit 2), unless you want the softer set semantics.

## Answer

<!-- Empty = open. -->
