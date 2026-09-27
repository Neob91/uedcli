+++
priority = "p1"
kind = "debug"
summary = "actor survey csg `crosses` fires from an Add whose matter a later Subtract carved away"
+++

# actor survey: crosses false-positive when a later Subtract carves the source's matter away

## Observed

In `19_Multiport`, `uedcli actor survey Brush184` reports:

```
raw Brush184 [Semisolid] --touches(6.554e+04uu^2)--> Brush196 [Add]
csg Brush196 [Add] --crosses(9.19e+03uu)--> Brush184 [Semisolid]
```

## Expected (owner)

- csg: **no relation** between Brush196 and Brush184.
- raw: **Brush196 contains Brush184** (Brush196's authored volume fully envelops Brush184), not
  `touches`.

## Trunk (confirmed from `order_value`)

Order `Brush190 (Subtract) → Brush196 (Add) → Brush269 (Subtract) → Brush184 (semisolid Add)`.

- Brush269 is a Subtract *later* than Brush196, so it carves Brush196's matter.
- Brush269 `contains` Brush184 (full authored enclosure — the survey's own raw fact).
- So Brush269's void fully encloses Brush184 and is carved out of Brush196. In the resolved world
  Brush196 has **no surviving matter adjacent to Brush184** — carved void lies between them.

(Brush190 is *before* Brush196 in the trunk, so it does not carve it and is not the cause.)

## Root cause (csg side — the clear defect)

`crosses` tests the source's **authored** geometry, never its resolved matter:

- `_source_cells` (`uedcli/actor_survey.py:975-977`) returns `actorgraph.decompose_convex(actor)` —
  authored convex cells, with no resolved-matter filter.
- `penetration_depth` (`uedcli/actor_survey.py:1052-1149`) straddle-tests those authored vertices; a
  cell with a point past the target face on the solid side and one on the void side qualifies. Since
  Brush196's authored box envelops Brush184, it straddles every Brush184 face → `crosses` fires, with
  the depth just measuring Brush196's authored extent.

The source-restriction the spec added (`.../actor-survey-and-actor-relation-csg-resolved/spec.md:279-286`)
is only a **kind gate** — it excludes Subtract as a source to kill the mirror bug ("a Subtract's raw
authored volume trivially crosses every Add in its void"). An Add is an eligible kind, so it passes,
and the identical "authored volume extends through a void where the actor has no resolved matter"
pathology recurs for an Add a later Subtract carved.

`resolved_matter_of` (`uedcli/actor_survey.py:1267-1315`) already encodes "an Add's matter survives
except where a later Subtract removed it" and is used by the `touches` tier (`_matter_side`), but is
never applied to the `crosses` source.

## Fix direction (not yet approved)

- csg: filter the `crosses` source's straddle/footprint by `resolved_matter_of` so a carved-away Add
  contributes no matter at the crossing. Regression fixture on this Brush196/Brush184 shape.
  - Subtlety: `resolved_matter_of` of an Add is "authored body minus later subtracts" — possibly
    NON-convex. So do this as a point-membership filter on `penetration_depth`'s straddle points /
    footprint, not by reshaping the source convex cells (which would break `_convex_hull_2d`'s
    per-cell convex footprint logic, `actor_survey.py:986-1017`).
- raw: the owner expects full authored envelopment to read as `contains` (Brush196 contains
  Brush184 in raw). This is part of the broader reshape now tracked in board item
  `actor-survey-csg-tier-resolved-geometry-and` (raw becomes pure authored geometry: no ordering,
  raw `carves` removed). Ruled 2026-09-26.
