+++
priority = "p1"
kind = "debug"
summary = "actor survey's csg tier dies on a neighbour brush the raw tier skips and records."
+++

# csg tier raises on a degenerate neighbour brush where raw skips it

`raw_facts_for` skips a neighbour whose `PolyList` does not bound a valid solid and records it in
`RawFacts.skipped`, exactly as `actorgraph.build_graph` does. The csg tier has no such skip: every
path that decomposes a neighbour (`_source_cells`, `brush_bounds`, `plane_slices`, `contact_planes`)
lets `actorgraph.DegenerateBrushError` propagate, so ONE bad brush anywhere in the neighborhood
kills the whole survey.

Not theoretical and not rare. Measured on the shipped `wanchai` trunk (2288 actors), surveying
`Brush110`:

```
raw tier: 6 facts, skipped: [Brush189, Brush192]   ("brush does not bound a valid solid")
csg tier: DegenerateBrushError: Brush189
```

Roughly a third of randomly sampled brushes in that level hit it. Pre-existing — reproduced
identically against `40b251ba` and against the round-6 `touches` rewrite, so it belongs to Task 11/12,
not to either.

The fix is presumably the raw tier's own shape: skip the brush, record it, and surface the skipped
list in the report (Task 18 owns the output). Whether a degenerate SURVEYED actor should still raise
(the raw tier says yes — a single-actor report has nothing left to say) is the same question answered
the same way.

It also bites slightly more often than it used to. Round 6's `touches` decomposes every near brush
(for its own planes and its own AABB) where the shipped-round-5 predicate reached some of them only
through the resolved face set. The defect and its blast radius are the same — one bad brush anywhere
near the surveyed actor kills the survey — but a marginally larger set of surveys now reaches it.

**Raised to p1** (final whole-branch review of `actor-survey-and-relation`): the CLI handler exits
2 cleanly with the brush named, so no correctness rule is broken -- but on the shipped `wanchai`
trunk this kills roughly a third of surveys outright. That is a bigger practical limitation on the
feature's actual usability than the neighborhood-selection performance item below, which only makes
surveys slow, not unusable.
