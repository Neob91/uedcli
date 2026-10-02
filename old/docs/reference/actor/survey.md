# actor survey

**`actor survey NAME`** prints every spatial fact uedcli can compute about one actor — brush or not —
against its neighbors, in two tiers with disjoint relation vocabularies: what it touches, occupies,
carves, connects to, and crosses into. Where [`level graph`](../level/graph.md) builds one
connectivity/containment graph for the whole level from cheap authored-shape geometry, `survey` is a
single-actor deep dive that ALSO runs a real CSG solve over that one actor's neighborhood, adding a
second, authoritative tier of facts.

`NAME` is exactly one actor — never a set — because both tiers below are computed over a bounded
neighborhood around that one actor, which is what keeps the cost predictable regardless of level
size.

```
$ uedcli actor survey Pillar_eonouc
Room_6iw11e [Engine.Brush Subtract] --encloses--> Pillar_eonouc [Engine.Brush Add]
Pillar_eonouc [Engine.Brush Add] --overlaps--> Spike_l9ajkj [Engine.Brush Semisolid]

Spike_l9ajkj [Engine.Brush Semisolid] --crosses--> Pillar_eonouc [Engine.Brush Add]
Pillar_eonouc [Engine.Brush Add] --occupies--> Room_6iw11e [Engine.Brush Subtract]
```
```
actor survey: 2 raw fact(s), 2 resolved CSG fact(s) for Pillar_eonouc
```

(`Room` is a Subtract carved into open space, `Pillar` an Add seated fully inside it, and `Spike` a
Semisolid whose box pokes partway into `Pillar`'s own volume. `actor add` always appends a random
`_<rand>` suffix to a name, so `Room`/`Pillar`/`Spike` become `Room_6iw11e`/`Pillar_eonouc`/
`Spike_l9ajkj` — see `docs/README.md`'s "Generators" section.)

## Two tiers, and the line grammar

- **raw** facts are pure authored geometry — each brush a volume, nothing more. They ignore CsgOper,
  trunk order, and Mover-ness entirely, and need no native extension: they read what a human eyeballing
  the level's brushes would call enclosing, overlapping, or touching. A raw `overlaps` between a
  Subtract and the Add it later carves is expected and common, not an anomaly — raw's job is showing
  authored intent, not resolution.
- **csg** facts are what the engine actually built after every Add/Subtract/Semisolid resolves in
  trunk order. Only this tier cares about CsgOper; it needs a real CSG solve (the native extension).

Every relation name is unique to its tier, so no line carries a `raw`/`csg` prefix — each line
self-identifies by its verb alone. The raw block prints first, then a blank line, then the csg block
(only when both have something to report); that fixed order, not a marker, is what tells the two
groups apart. Each non-blank line reads subject–relation–object, bare — no magnitudes, no poly
indices:

```
<src> [Package.Class[ Kind]] --<relation>--> <dst> [Package.Class[ Kind]]
```

`[Package.Class]` is the actor's fully-qualified class; a brush actor (other than a Mover) gets a
second word in the bracket, its CSG kind — `Add`, `Subtract`, `Semisolid`, `Nonsolid`, `Intersect`, or
`Deintersect` — so `[Engine.Brush Subtract]` names both what the actor is and how it participates in
CSG. A non-brush actor and a Mover print just `[Package.Class]`: a Mover carries no CSG operation of
its own, so it has no kind to add.

A symmetric relation (`meets`, `overlaps`, `coincides`, `touches`, `connects`) always leads with the
actor you surveyed; a directional one (`encloses`, `crosses`, `occupies`, `carves`) keeps its fixed
lead regardless of which side you asked about.

Metrics (an area, a penetration depth) are not this command's job — every line is a bare topology
fact. For the exact size or gap of a contact, pipe the names into
[`actor relation compare`](relation.md).

To isolate one tier from a `survey` transcript, grep by relation word — every name is unique to its
own tier, e.g. `grep -E 'occupies|carves|connects'` selects only csg-tier lines.

## raw relations — pure authored geometry

| Relation    | Direction      | Meaning |
|-------------|----------------|---
| `encloses`  | encloser leads | One volume fully contains the other. |
| `overlaps`  | symmetric      | Interiors intersect; neither encloses the other. |
| `meets`     | symmetric      | Boundaries touch, interiors disjoint — flush contact. |
| `coincides` | symmetric      | Identical volumes — a duplicate or exactly stacked brush. |

A non-brush actor is treated as its bare `Location` point: it can only be the target of `encloses`
(point-in-brush), never `overlaps`/`meets`/`coincides` — its collision extent is a runtime property,
not authored geometry.

## csg relations — resolved matter

| Relation   | Direction      | Meaning |
|------------|----------------|---
| `crosses`  | intruder leads | The source's resolved matter pokes past another actor's resolved face into solid it doesn't own. |
| `occupies` | occupant leads | An actor sits in a Subtract's resolved void — a matter brush (Add/Semisolid) adding matter there, a Nonsolid brush by its authored shape, or a non-brush/point actor just sitting there. |
| `carves`   | subtract leads | A Subtract removed some of another actor's own matter — any amount, including a cavity fully interior to it. |
| `touches`  | symmetric      | Flush resolved-solid contact, no penetration. |
| `connects` | symmetric      | Two Subtracts' resolved voids are continuous — e.g. two rooms open to each other through a doorway. |

`carves` and `occupies` are duals for an Add/Subtract pair: whichever ran last in trunk order wins
that pair's fact — a Subtract before the Add can only `occupies` it, a Subtract after can only
`carves` it — so the same pair never reports both. An Add seated across two Subtracts' voids reports
`occupies` against both — `occupies` is evaluated independently per pair, no single-winner contest. A
Mover is never a matter source for any csg relation, since it never participates in world CSG.

`occupies`+`crosses` and `occupies`+`touches` can both fire for the same pair (an Add can fill a void
and also poke through the far wall, or fill a void and sit flush against its carved walls) — only
`crosses`/`touches` are mutually exclusive for one pair.

## `level graph` and `carves` — different leading side

[`level graph`](../level/graph.md) reports the same underlying Add/Subtract pair as `carved_by`, with
the ADD leading (`Wall --carved_by--> Niche`). `actor survey`'s csg tier reports it as `carves`, with
the SUBTRACT — the agent doing the carving — leading (`Niche --carves--> Wall`). The raw tier has no
`carves` relation at all: raw is pure authored geometry and never reasons about trunk order. Both
describe the same underlying fact; only the word and the leading side differ between the two commands.

## Errors

`actor survey` never lets a Python exception reach you. An unknown actor name, or an actor whose own
brush is too malformed to decompose, exits 2 naming the actor. A placed Intersect or Deintersect brush
contributes nothing to the resolved world at all (the editor treats it as an operation on its own
private model, never the level's), so its csg block is correctly empty and its raw block — which
buckets it as Add-like, since the raw tier has no notion of Intersect/Deintersect at all — should not
be trusted; surveying one prints a stderr warning saying so, rather than failing.
