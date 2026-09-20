# level graph

**`level graph [--from NAME --hops N|all] [--tree KIND/NAME]`** prints the current level's actor
connectivity/containment graph: every brush and every non-brush actor as a node, and an edge between
two nodes wherever their volumes geometrically touch or one contains the other. It answers "what's
connected to what" across the WHOLE level in one pass — replaces manually pairing up
[`brush relation measure`](../brush/relation.md) calls to trace a chain of rooms, or eyeballing which
brush a light sits inside. It's pure and offline: no editor, no native CSG build, just the trunk's own
geometry and CSG order.

## Nodes and edges

A node is every actor in the level — every brush (`CSG_Add`, `CSG_Subtract`, or a Mover) and every
non-brush actor (lights, pickups, triggers, NPCs, everything). There's no "just rooms" filtering; this
is the full actor graph. `CSG_Intersect`/`CSG_Deintersect` brushes are bucketed as Add-like for edge
classification (the same "not a Subtract" bucket as `CSG_Add` and Movers) — deliberate, not an
oversight; there's no separate row for them in the table below.

One geometric test decides every edge: does brush/actor A's volume touch or overlap brush/actor B's
volume. What that edge is CALLED depends on the two nodes' kinds and, for two brushes, which one comes
later in the level's CSG order (its position in the trunk, top to bottom):

| A                    | B                    | CSG order              | Edge        | Direction         |
|----------------------|----------------------|-------------------------|-------------|--------------------|
| Subtract             | Subtract             | (irrelevant)            | `touches`   | undirected         |
| Add or Mover         | Add or Mover         | (irrelevant)            | `touches`   | undirected         |
| Subtract             | Add                  | Subtract comes earlier  | `contains`  | Subtract → Add     |
| Subtract             | Add                  | Subtract comes later    | `carved_by` | Add → Subtract     |
| Subtract             | Mover                | (order never matters)   | `contains`  | Subtract → Mover   |
| Brush (any kind)     | non-brush actor      | n/a                     | `contains`  | Brush → actor      |

The CSG order rule, stated plainly: if a Subtract was placed BEFORE the Add it touches, the Add is
something built into the space the Subtract had already carved out — the Subtract `contains` it (a
desk placed inside an already-hollowed-out room). If the Subtract comes AFTER, it carved into
geometry that already existed — the Add is `carved_by` it (a doorway cut into an already-built wall).
Same geometric touch test either way; only the label and direction change.

**Movers are always Add-like, and never appear in a `carved_by` edge.** A Mover carries a `PolyList`
like any brush, but it generates no `CsgOper` at all — it never carves a Subtract and can never be
carved by one; it just sits in the world as solid geometry. Two Movers, or a Mover and an Add, get an
undirected `touches` edge like any other Add-like pair. A Mover touching a Subtract always gets
`contains` (Subtract → Mover), regardless of which one is earlier in the trunk — CSG order is
meaningless for a Mover, so it's never checked.

**An actor touching several others gets one edge per pair, not just one.** An Add straddling two
already-touching Subtracts gets a `contains` edge from BOTH of them. A Subtract carving through two
different Adds gets a `carved_by` edge to BOTH. A non-brush actor whose Location falls inside more than
one brush's volume (nested or overlapping brushes) gets a `contains` edge from EVERY containing brush.
Nothing is deduplicated or merged into one summary edge.

There's no clustering and no "room" grouping — a two-Subtract seam that's really one open space and a
Subtract that a single wall happens to divide both look the same in the graph (a `touches` edge between
two nodes); deciding whether that counts as "one room" is a judgment call this tool leaves to the
reader.

## Known limitation — this can report false connections

`level graph` tests pure geometric touch/overlap, not "is this an actual, walkable passage." A small,
purely decorative subtract — a bevel or a structural notch cut into a wall, never meant to let a player
through — can still geometrically touch the volumes on both sides of that wall, exactly like a real
doorway would. `level graph` cannot tell the two apart: both show up as an identical `touches` edge
bridging the two rooms. This is a deliberate tradeoff (a full CSG/BSP solve could close the gap, but
this tool doesn't do one) — treat a surprising `touches` connection as worth a sanity check, not as
proof a real passage exists there.

## Output format

One edge per line, `subject --relation--> object`. There's no nested/tree layout and no clustering —
the graph has cycles and shared nodes, so a flat edge list is the only shape that doesn't lie about
structure.

```
$ uedcli level graph
Subtract_Lobby:0 --touches(1.638e+04uu^2)--> Subtract_Hallway:1
Subtract_Lobby --contains--> Add_FrontDesk
Subtract_Hallway --contains--> Mover_HallwayDoor
Subtract_Lobby --contains--> NPC_Receptionist
```

- A `touches` edge between two brushes carries a rough size in parentheses: `touches(1.638e+04uu^2)`.
  When the two brushes share a single, clean flat boundary (one matched face pair), the size is the
  EXACT shared footprint area, and each brush name also gets a `:idx` suffix naming that boundary poly
  — e.g. `Subtract_Lobby:0 --touches(...)--> Subtract_Hallway:1` means poly 0 of `Subtract_Lobby` is
  the matched face against poly 1 of `Subtract_Hallway`. That's the exact selector grammar
  [`brush relation measure`](../brush/relation.md) takes, so you can drill straight in:
  `uedcli brush relation measure Subtract_Lobby:0 Subtract_Hallway:1` for the full plane/normal/gap/
  footprint detail. When the two brushes overlap as a genuine 3-D volume with no single shared face
  (e.g. two Subtracts overlapping diagonally), the size is a bounding-box estimate and neither name
  gets an `:idx` — drill in with a plain `brush relation measure Subtract_A Subtract_B` instead, which
  ranks every poly pair.
- `contains` and `carved_by` edges never carry a size or a `:idx` — containment is a yes/no fact, not
  a matter of degree, and there's no second face-to-face question to ask beyond "yes, it's inside."
  `Subtract_Hallway --contains--> Mover_HallwayDoor` is the whole answer.
- A brush that's too malformed to test (self-intersecting, non-manifold, or a degenerate zero-area
  face) is reported as a skipped node on stderr instead of crashing or being silently dropped:
  `level graph: skipping Bad: brush does not bound a valid solid (a decomposed cell has no volume)`.
  It still appears in the graph as a node with no edges; every OTHER brush is still tested normally.

There is no `--json` output for `level graph` — the flat text format above is the only one, at least
for now (unlike most other producer verbs in this CLI, which pair a human `--json`-free default with
a `--json` structured form).

## `--from` / `--hops` — scoping to one neighborhood

With no flags, `level graph` prints the WHOLE level's graph — every node, every edge.

`--from`/`--hops` filter the PRINTED output only — the full graph is still computed regardless of
scope. Detection tests every brush against every other brush up front, before any scoping is
applied, so a very large level pays the same compute cost whether or not `--from`/`--hops` are
given; they narrow what you have to read, not how long the command takes.

`--from NAME --hops N|all` scopes the output to `NAME`'s neighborhood: an edge prints if at least one
of its two ends is reachable from `NAME` in FEWER than `N` hops (or unboundedly, with `--hops all`) —
a breadth-first walk over the graph treating every edge as undirected for reachability purposes (a
`contains` edge's direction doesn't limit which way the walk can follow it, only how the edge itself
prints). This is an ego-network view, not a full induced subgraph on the reachable node set: an edge
between two nodes that are BOTH exactly `N` hops out is dropped, since neither end is close enough to
have its own edges expanded. `NAME` can be any node, brush or non-brush; there's no privileged "room"
node type.

The two flags are a pair: `--hops` is required whenever `--from` is given (an omitted count is
ambiguous — one hop, or unbounded? — and this CLI never silently guesses), and `--hops` given without
`--from` is a clean error, since a hop count has nothing to scope without a starting node:

```
$ uedcli level graph --from Subtract_Lobby
level graph: --hops is required when --from is given (N, or 'all' for unbounded)

$ uedcli level graph --hops 1
level graph: --hops has nothing to scope without --from
```

Worked example — the same level as above, scoped one hop out from `Subtract_Lobby` (drops
`Mover_HallwayDoor`, which is only reachable through `Subtract_Hallway`, two hops away):

```
$ uedcli level graph --from Subtract_Lobby --hops 1
Subtract_Lobby:0 --touches(1.638e+04uu^2)--> Subtract_Hallway:1
Subtract_Lobby --contains--> Add_FrontDesk
Subtract_Lobby --contains--> NPC_Receptionist
```

An unknown `--from` name is a clean error naming the value: `level graph: no such actor: 'Nope'`.

`--tree KIND/NAME` analyzes a named level/stash/prefab tree instead of the ambient `$UEDCLI_LEVEL` —
the same `--tree` flag [`level doctor`](doctor.md) and most other read verbs already take.

See also: [`brush relation`](../brush/relation.md) (geometric detail on a pair of faces you already
know), [`level doctor`](doctor.md) (per-brush geometry/BSP problems, no cross-actor graph).
