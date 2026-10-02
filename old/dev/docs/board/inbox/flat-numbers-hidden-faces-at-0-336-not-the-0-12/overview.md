+++
priority = "p2"
kind = "unknown"
summary = "flat numbers hidden faces at 0.336, not the 0.12 floor the spec described"
+++

# `--faces flat` numbers hidden faces at **0.336**, not the 0.12 floor its spec described

**Boarded, not changed: the behaviour is owner-decided** (`--annotate` was ruled "unchanged and left
exactly as-is" for `--faces`, with the wrong-face label listed as an accepted consequence). This item
exists because the accepted consequence was recorded **3× understated**, and its only home is a spec
section that gets deleted when the `--faces` work lands.

## The measurement

A plain additive cube, `--view iso`, default `--annotate`, `--faces flat`, via `_scene_geometry` +
`_occluder_count` + `_decal_opacity`:

| face | occluders in front | decal opacity |
|------|--------------------|---------------|
| 0    | 1                  | **0.336**     |
| 1    | 0                  | 0.560         |
| 2    | 1                  | **0.336**     |
| 3    | 0                  | 0.560         |
| 4    | 0                  | 0.560         |
| 5    | 1                  | **0.336**     |

So a filled cube paints **six** numbers, three of them on faces the fill makes invisible, at **60 % of the
visible ones' opacity** — not at the 0.12 floor. `_decal_opacity(n) = max(0.12, 0.56 · 0.6ⁿ)`, and one
occluder gives `0.56 · 0.6 = 0.336`; the 0.12 floor is only reached at **four** layers deep (`0.56 ·
0.6⁴ = 0.073` → floored), which a single convex brush never produces. On-face numbering is
facing-blind by design, so this is every closed brush in every filled render, not an edge case.

## Why it matters

The spec's `--annotate` row accepted the behaviour on the basis that an occluded face's number sits there
"at a 0.12 floor" — i.e. as a barely-visible artefact. At 0.336 against a visible face's 0.560 the two are
close enough to be confused, so on a filled render a number can read as belonging to the wall in FRONT of
the face it is actually on. That is a materially different cost from the one that was accepted.

## Disposition

- **Not changed.** `--annotate` under `--faces` is owner-decided; if the numbers should be dropped or
  floored on culled/occluded faces under a filled mode, that is a ruling, not a fix.
- **Documented**, so a user is not surprised: `docs/usage.md`'s on-face-numbers bullet now states the
  0.336-vs-0.560 grading under `--faces flat` and points at `--faces wire` or `--annotate none` for a
  clean read.
- **Untested.** No test pins the opacity; the grading itself is pinned only where the `flat` cull changes
  it (`test_flats_decal_opacity_differs_from_wires_where_the_cull_emptied_occluders`). If the owner
  confirms the current numbers are wanted, pin them.
