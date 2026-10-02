# Sphere/dome alignment — build it, and with which projection: per-face equirectangular or stacked-rings?

## Context

Planar `--wall`/`--floor` and cylinder `--ring` are already built; the one unbuilt piece this item
names is sphere/dome wrap. No current builder emits a dome — it arrives as a `revolve` of a
semicircle or a hand-built geodesic — so first: is sphere/dome alignment wanted now, or deferred
until a real dome shows up?

If wanted, two methods:

- **A. Equirectangular (recommended).** Per face, build a local tangent frame from the centroid's
  direction off the centre: `TextureU` along longitude (east), `TextureV` down latitude. One rule for
  any tessellation (geodesic or revolve dome); poles are the sole degenerate case. Best-fit
  continuity across facet edges, like `--ring`'s per-chord wrap.
- **B. Stacked rings.** Reuse `--ring` per latitude band, V advancing per band. Exact seams, but only
  valid for a lat-long-tessellated (revolve) dome and needs the caller to group faces per band.

Recommendation: build **A** — one method for any dome, symmetric with `--ring`.

## Answer

<!-- Empty = open. -->
