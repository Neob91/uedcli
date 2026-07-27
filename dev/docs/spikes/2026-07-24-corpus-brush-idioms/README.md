# Corpus brush-idiom study — spike harness

Durable evidence + harness for the study specced in
board item `brush-identify-classify-a-real-brush-s-shape`
(extract brush-construction idioms from real DX/UE1 levels). This dir holds the committed harness
code; throwaway output (wireframe PNGs, real map T3D exports) stays in `_scratch/`.

## `feature_cluster.py` — per-feature brush selection (spec option **B**)

**Problem it solves.** A real imported map has hundreds of opaquely-named brushes (`Brush`, `Brush0`,
…). The study's qualitative pass needs to look at ONE *feature* (an arch, a stairwell, a room + its
detail) as a CSG-colored wireframe — but there's no way to say "give me the arch's brushes." The
parked `find-spatial` spec (`--near`/`--within-bbox`/`--overlapping`) is the eventual proper tool; for
the pilot this harness picks feature brush-sets without needing it built.

**Method.** Each brush's axis-aligned world bounds come from the SAME `writes.actor_bounds` the
`actor bbox` verb uses (full transform honoured). Two brushes are joined when their AABBs overlap
after padding each by `--gap` uu; connected components (union-find) over that relation are the
features. That is exactly the `--overlapping`/`--within-bbox` relation of the parked `find-spatial`
spec — so **this harness prototypes that verb**; if it proves useful it graduates into it rather than
being throwaway.

**Usage.**

```
feature_cluster.py MAP.T3D --list                    # what features are there (id, brush count, bbox)
feature_cluster.py MAP.T3D --names 0 | actor preview -   # CSG-colored wireframe of the biggest feature
feature_cluster.py MAP.T3D --json                    # structured, for the harness pipeline
feature_cluster.py --selftest                        # dependency-free check (no editor/CLI/real map)
```

Input is a whole-level T3D (a `MAP EXPORT` / `batchexport` of a real `.dx`), or `-` for stdin.

**Known coarseness (honest limits).** AABB connectivity is a proxy for real geometric adjacency:

- A subtractive room brush overlaps the additive detail inside it → room + contents cluster together
  (good). But a door-shaped subtract spanning two rooms will **merge** them, and a large `--gap`
  over-merges a whole connected interior into one blob. Tune `--gap` **down** (0 = only face-touching
  join; negative = require genuine overlap of `-gap` uu) when features fuse; "biggest connected
  sub-volume, then drill down" is the pilot workflow.
- A future refinement (and the real `find-spatial` `--within-brush`) would test actual poly overlap,
  not the AABB.

## Status / result (2026-07-24): NEGATIVE — the global-CC design does NOT fit; do not use as-is

Two cold-review gates (per `LUM/CLAUDE.md`) found this approach **unfit for the study**, and the
finding is worth keeping as evidence:

- **Fatal (fitness):** on a real DX interior, AABB-overlap connected-components collapses to **one
  blob at any `--gap`** — DX carves space by SUBTRACTION, so for two rooms to connect their
  subtractive brushes must overlap/adjoin *by construction*; union-find over that relation returns the
  whole navigable interior as one component. Additive detail sits inside a room subtract's AABB, so it
  joins the blob too. `--gap` isn't a real control (overlap is what CSG *maximizes*, not incidental
  proximity), and there is no scale at which "connected component" equals what a human calls a feature
  (an arch is deliberately embedded in its wall/room/corridor). The flagship `--names 0 | actor
  preview` would preview the entire level.
- **Correctness bugs found (real, but moot given the above):** `--gap` pads BOTH boxes, so it bridges
  `2×` its documented distance, and the self-test's fuse constant silently encodes that 2×; unguarded
  file read throws a raw traceback (violates the CLI convention); O(n²) in Decimal will crawl on a
  real map; Movers (brush actors, `cls != "Brush"`) get clustered as "brushes".
- **Also:** the study spec (board item `brush-identify-classify-a-real-brush-s-shape` §7.4) already prescribes
  **hand-selection** for the 4-map pilot, and the qualitative wireframe pass is the *secondary*
  deliverable — so this harness automated (badly) a step the spec chose to do by hand.

**What DID hold up** (kept for a future redesign): the union-find + stable sort are correct; routing
synthetic test data through `emit_actor → parse_t3d` is the right way to test (it caught the
Decimal-vertex requirement); `parse_t3d_actors` + dup-name warning is the right ingest.

**Recommended path (decision pending Andrzej):**
1. For the pilot, **drop auto-clustering; hand-pick feature brush names from an annotated `actor
   preview` overview**, exactly as the spec already says. Zero risk.
2. If automated selection is wanted for the *scaled* run, redesign around what actually works:
   **op-aware** (subtractive brushes = rooms to drill into; cluster only ADDITIVE detail among
   itself, which is sparse and does segment) and/or a **seeded** query ("brushes near POINT /
   overlapping BRUSH") — which also correctly matches the parked `find-spatial` verb's semantics
   (a seeded one-hop query, NOT a global partition). The current global-CC framing does not prototype
   find-spatial.

The code below is retained as the record of what was tried, not as a working tool.
