# Offer `--to` (move face centroid to a point) in v1, or ship `--by` only?

## Context

`--by DX,DY,DZ` is the core operation and unambiguous. `--to X,Y,Z` is a convenience: a face has 3+
corners, so "move the face to a point" has to pick an anchor — the centroid is the natural one, and it
matches `brush vertex move --to` (single selector, absolute target). It is pure sugar over `--by`
(`delta = target − centroid`).

- Option A (recommended): ship both. `--to` targets the centroid, single-selector, consistent with
  `brush vertex move`.
- Option B: `--by` only in v1; add `--to` later if wanted. Keeps the first cut minimal and avoids
  committing to "centroid" as the anchor before anyone asks for it.

Recommendation: A.

## Answer

<!-- Empty = open. -->
