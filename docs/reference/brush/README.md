# Brush

Per-surface geometry, brush-level filters, and shape generators. See also
[actor](../actor/README.md) for whole-actor CRUD, [`docs/README.md`](../../README.md) for `--tree
KIND/NAME` (editing a stash/prefab/other level in place), and
[Geometry & BSP](../../leveldesign/general/geometry-and-bsp.md) for the level-design craft this
covers.

| Command | Query/mutate | What it does |
|---|---|---|
| [`brush poly list`](poly.md) | query | per-poly table for a brush |
| [`brush poly find`](poly.md) | query | matching faces as `BRUSH:idx` selectors, for piping |
| [`brush vertex list`](vertex.md) | query | welded brush corners: world coord + the polys sharing each |
| [`brush relation measure/find/set`](relation.md) | query/mutate | exact geometric facts between a reference face and one or more others, filtered search, and move-to-relationship |
| [`brush poly set/pan/rotate/scale/move`](poly.md) | mutate | edit face attributes or texture frame |
| [`brush poly align`](poly.md) | mutate | flow one texture continuously across faces |
| [`brush vertex move`](vertex.md) | mutate | move welded corners |
| [`brush clip`/`brush snap`/`brush replace`](core.md) | mutate | filter/reshape a piped or placed brush |
| [`brush scale`/`brush apply-transform`](core.md) | mutate | scale or bake a brush's transform |
| [`brush build`](build.md) | — | parametric brush primitives (generator) |
| [`brush intersect`/`brush deintersect`](intersect.md) | — | CSG-merge a piped brush set into one brush (generator) |

*query — model-side, instant, no editor; mutate — model-side, rewrite the trunk.*
