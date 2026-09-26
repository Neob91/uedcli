# actor survey

**`actor survey NAME`** prints every spatial fact uedcli can compute about one actor — brush or not —
against its neighbors: what it touches, contains, carves, connects to, and crosses into. Where
[`level graph`](../level/graph.md) builds one connectivity/containment graph for the whole level from
cheap authored-shape geometry, `survey` is a single-actor deep dive that ALSO runs a real CSG solve
over that one actor's neighborhood, adding a second, authoritative tier of facts — including two
relations, `connects` and `crosses`, that only make sense once a real solve exists.

`NAME` is exactly one actor — never a set — because both tiers below are computed over a bounded
neighborhood around that one actor, which is what keeps the cost predictable regardless of level
size.

```
$ uedcli actor survey Additive4
raw Subtract1 [Engine.Brush Subtract] --contains--> Additive4 [Engine.Brush Add]
raw Additive4 [Engine.Brush Add] --touches(1024uu^2)--> Additive2 [Engine.Brush Add]
raw Subtract3 [Engine.Brush Subtract] --carves--> Additive4 [Engine.Brush Add]

csg Additive4 [Engine.Brush Add] --crosses(64uu)--> Subtract3 [Engine.Brush Subtract]
csg Subtract1 [Engine.Brush Subtract] --contains--> Additive4 [Engine.Brush Add]
csg Subtract3 [Engine.Brush Subtract] --carves--> Additive4 [Engine.Brush Add]
actor survey: 3 raw fact(s), 3 resolved CSG fact(s) for Additive4
```

## Two tiers, and the line grammar

Every line starts with a tier token — `raw` or `csg` — as its very first word, never a section
header: grep for `^csg `, or quote one line out of context later, and the tier still reads
unambiguously off that line alone. A blank line separates the two blocks when both have something to
report; it is the only line that does not start with a tier token. Each non-blank line reads
subject–relation–object:

```
<tier> <src> [Package.Class[ Kind]] --<relation>--> <dst> [Package.Class[ Kind]]
```

`[Package.Class]` is the actor's fully-qualified class; a brush actor (other than a Mover) gets a
second word in the bracket, its CSG kind — `Add`, `Subtract`, `Semisolid`, `Nonsolid`, `Intersect`, or
`Deintersect` — so `[Engine.Brush Subtract]` names both what the actor is and how it participates in
CSG. A non-brush actor and a Mover print just `[Package.Class]`: a Mover carries no CSG operation of
its own, so it has no kind to add.

**`raw`** facts are cheap geometry over the actors' own AUTHORED shapes — their placed brushes and
Locations as written in the level, before any CSG solve runs. They are always computable, need no
native extension, and reflect what a human eyeballing the level's brushes would call touching,
containing, or carving. They can also be WRONG in a way the CSG solve corrects: authored shapes can
overlap or leave gaps that the resolved geometry does not, once carves and merges are actually
applied.

**`csg`** facts are the authoritative answer: `survey` runs a real CSG solve over the actor's
neighborhood and reads the relations off the resolved world. Where a `raw` line guesses from authored
geometry, a `csg` line reports what is actually true after every Subtract has cut and every Add has
merged.

Both tiers use the same five relation words, but not every relation appears in both tiers — see the
table below.

## The relations

| Relation   | Tiers    | Meaning |
|------------|----------|---
| `touches`  | raw, csg | The two actors' boundaries meet or overlap. A `raw touches` line comes from a cheap authored-shape overlap test, so it can also fire on two brushes that genuinely interpenetrate, not only ones flush against each other — the `csg` tier's version is the corrected, authoritative one: a real solved plane where the two meet with no penetration. A `raw touches` line that found one specific matching pair of faces carries a `Name:idx` selector and a `touches(AREAuu^2)` size annotation on each side — paste that selector straight into `actor relation compare` for the exact geometric detail. A `csg touches` line never carries `:idx` or an area: the fact is decided against a resolved PLANE, not a specific face fragment, so there is nothing indexable to name. |
| `contains` | raw, csg | The container leads, whichever side is surveyed. At the `csg` tier this is real full enclosure: the container's authored shape enclosing the other actor's whole volume (or its bare `Location` for a non-brush actor), with the smallest of several candidate containers winning. At the `raw` tier, containment between a Subtract and an Add is a cheaper stand-in: a Subtract that merely overlaps the Add at all is read as containing it, decided by trunk order (a Subtract placed earlier than the Add it overlaps is read as already having carved the space that Add now sits in) rather than by checking real enclosure — see `carves` below for the other half of that same heuristic. A Mover is different: it never participates in world CSG, so a Subtract overlapping one always reads as containing it, regardless of trunk order — never `carves`. Against a non-brush actor's bare `Location`, both tiers test the same real point-in-volume fact. |
| `carves`   | raw, csg | The agent (the Subtract) leads. At the `csg` tier this is a real removal, confirmed by re-solving the neighborhood without the Subtract and checking that the other actor's surviving face area shrinks without it — "removed" includes total removal: an Add entirely consumed by a later Subtract still reports `carves`, with no accompanying `touches` for that pair, since nothing of the Add survives to be flush against anything. That check is measured on the OTHER actor's own surviving faces, so a Subtract that removes matter entirely interior to the other actor's volume, without ever touching one of that actor's own authored faces, is not detected as a `carves` at this tier. At the `raw` tier this is the other half of `contains`'s own trunk-order heuristic: a Subtract that overlaps an Add but comes AFTER it in trunk order is read as carving it, without confirming that any matter actually left. A Mover is never a raw `carves` target — see `contains` above. |
| `connects` | csg only | Two Subtracts' carved-out voids are continuous, with no surviving solid between them — e.g. two adjoining rooms with an open doorway between them. This is about the ABSENCE of a face, so the line carries no annotation. Two rooms separated by an intact wall `touch` (their solid faces meet) but do not `connect` (their voids do not); an open doorway between them does. |
| `crosses`  | csg only | One actor's own solid matter extends past a resolved, surviving face belonging to another actor, into space that face's owner does not itself claim — real interpenetration, not a flush touch. The intruder always leads, and the line carries the measured penetration depth: `crosses(64uu)`. |

The `raw` tier needs no CSG solve at all — it is pure authored-shape geometry, always computable. The
`csg` tier needs a real solve (the native extension), and prints in a fixed order: `crosses`,
`touches`, `connects`, `contains`, `carves`. `crosses`' tolerance for what counts as "still separate"
is tighter than a hand-measured gap would need, because resolved coordinates are only reproducible to
the CSG engine's own point-dedup precision; nothing finer is a real geometric distinction in a solved
model.

## `level graph` prints the carve the other way around — for now

[`level graph`](../level/graph.md) reports the same underlying Add/Subtract pair as `carved_by`, with
the ADD leading (`Wall --carved_by--> Niche`). `actor survey` reports it as `carves`, with the
SUBTRACT — the agent doing the carving — leading (`Niche --carves--> Wall`). Both describe the same
fact; only the word and the leading side differ. This is a known, temporary difference in wording
between the two commands, not a bug in either one.

## Errors

`actor survey` never lets a Python exception reach you. An unknown actor name, or an actor whose own
brush is too malformed to decompose, exits 2 naming the actor. A placed Intersect or Deintersect
brush contributes nothing to the resolved world at all (the editor treats it as an operation on its
own private model, never the level's), so its `csg` block is correctly empty and its `raw` block —
which buckets it as Add-like, since the raw tier has no notion of Intersect/Deintersect at all —
should not be trusted; surveying one prints a stderr warning saying so, rather than failing.
