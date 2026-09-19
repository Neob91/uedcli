# `level graph` — a connectivity/containment graph over the level's actors

## Motivation

`brush relation measure/find/set` (`dev/docs/superpowers/specs/2026-09-05-brush-relation-family-design.md`)
answers questions about a KNOWN pair of faces, or ranks candidates against ONE reference face. Two
gaps surfaced this session, both real agent failures, not hypothetical:

- An agent told to "raise the ceiling" of a room that turned out to be built from several adjacent
  `CSG_Subtract` brushes raised only the one it was looking at, breaking the ceiling — nothing told
  it the room was segmented, and nothing finds "every other piece of this same room" in one query.
- `dev/docs/board/inbox/resize-edits-miss-cross-room-relations-from/` — an agent verified an edit's
  effect against one pinned face and missed that the SAME edit silently stretched a sibling face,
  which then overlapped a neighboring room's decoration.

Both are the same underlying problem: nothing exposes level structure — what's connected to what,
and what's inside what — at a level an agent can reason over directly. This spec adds `level graph`,
a queryable graph over every actor in the level, built purely from brush geometry (no native BSP
build, no authored zoning required).

An earlier version of this design tried to expose `uedcli-native`'s own zone/portal/leaf
connectivity (`uedcli-native/src/zones.rs`'s `assign_leaves_and_zones`/`build_connectivity`, RE'd to
byte-parity for the native-materialize lighting campaign). That data is real and already computed as
part of every native build — but it requires the native CSG/BSP solve to run first, and zone
identity requires authored `ZoneInfo`/portal-brush content to mean anything. The owner explicitly
wants this decoupled from both (2026-09-19); see "Design decisions and why".

## What we want

### Nodes

Every actor in `$UEDCLI_LEVEL` is a node: every brush (`CSG_Add` or `CSG_Subtract`; movers included —
they carry a `PolyList` like any brush) and every non-brush actor (lights, pickups, triggers, NPCs,
everything). No filtering to "just rooms" — this is a full actor graph, not a room graph (owner
correction, 2026-09-19).

### Edges

One geometric test — does volume A touch or overlap volume B — labeled by the two nodes' KINDS and,
for two brushes, which was placed LATER in `level.order` (CSG order), not two different algorithms:

| Endpoint kinds              | CSG order         | Edge       | Direction         |
|------------------------------|--------------------|------------|--------------------|
| Subtract, Subtract           | (irrelevant)       | `touches`  | undirected         |
| Add or Mover, Add or Mover   | (irrelevant)       | `touches`  | undirected         |
| Subtract, Add                | Subtract earlier   | `contains` | Subtract → Add     |
| Subtract, Add                | Subtract later     | `carved_by`| Add → Subtract     |
| Subtract, Mover              | (see below)        | `contains` | Subtract → Mover   |
| Brush (any), non-brush actor | n/a                | `contains` | Brush → actor      |

**Movers are Add-like for labeling, and never appear in a `carved_by` edge.** A mover "carries a
`PolyList` like any brush" (above) but generates no `CsgOper` at all — `uedcli/builders.py:735`'s own
comment states it plainly: "a mover does not participate in world CSG." It can neither carve a
Subtract nor be carved by one; it just sits in the world as solid geometry, exactly like an Add. So a
Mover is only ever the CONTAINED side of a `contains` edge, or either side of an undirected `touches`
edge against another Add/Mover — never a `carved_by` endpoint in either direction.

- A brush overlapping SEVERAL others gets one edge per overlapping pair, not just one: an Add
  straddling two already-touching Subtracts gets a `contains` edge from BOTH; a Subtract carving
  through two different Adds gets a `carved_by` edge to BOTH (owner examples, 2026-09-19).
- A non-brush actor whose Location falls inside more than one brush's volume (nested/overlapping
  brushes) gets a `contains` edge from EVERY containing brush, not just one — same multi-edge rule.
- **No clustering, no "room" grouping, no threshold deciding whether a connection "counts."** An
  earlier draft of this design pre-grouped connected Subtracts into named `Room[N]` objects; the
  owner rejected this (2026-09-19) — whether a wide-open two-subtract seam and a one-subtract room
  a wall happens to divide both "count as one room" is a judgment call about design intent, not a
  geometric fact this tool can decide. The flat graph, plus each edge's size (below), gives the
  reader — human or LLM — what it needs to decide that itself.

### Detection algorithm

- **Touching/overlap test**: separating-axis test (SAT) against the brush's actual world-space
  polyhedron — faces from its `PolyList`, transformed by Rotation/MainScale/PostScale/Location the
  same way `polyalign._world_verts`/`_world_normal` already do. Exact for two CONVEX brushes, but
  face normals of both shapes alone are not sufficient in general (two convex prisms/cylinders at
  certain relative rotations can be genuinely disjoint with no separating FACE normal, only a
  separating axis along the cross product of one edge from each) — the candidate-axis set is every
  face normal of both brushes PLUS every cross product of an edge from brush A with an edge from
  brush B (the standard exact test for two convex polytopes), not face normals alone.
- **A touching tolerance is required and must be a named, stated constant** — this codebase's own
  convention (`relation.py`'s `_PARALLEL_EPS`/`_PLANE_EPS`/`_TOUCH_EPS`/`_GAP_EPS`, each a labeled
  epsilon with a stated reason) applies here too: real editor-placed brushes carry sub-uu float noise
  (`dev/docs/unrealed/t3d.md`'s "Fractional vertices"), so "touches" means within a small tolerance
  band, not exact zero-gap contact. The exact value is implementation-stage detail; that it exists
  and is named/documented is not.
- **Non-convex brushes** (freeform, staircase-shaped, CSG-modified): SAT is not exact here regardless
  of which axis set is used. Fall back to a coarser bounding-box-overlap + sampled-point check, and
  flag the result `⚠ approximate` in the output — never present an approximate answer as exact
  (matches this project's existing convention of labeled masks rather than hidden ones). A brush's
  convexity is decided once and reused, not re-derived per edge.
- **Containment test** (brush → non-brush actor): point-in-polyhedron test of the actor's `Location`
  against the brush's volume — well-defined for a valid closed manifold regardless of convexity, so
  it needs no approximate fallback the way the non-convex touch test does. **Caveat**: a
  self-intersecting or non-manifold freeform brush (a malformed or hand-authored edge case, not the
  common case) can make even parity-based point-in-solid ambiguous; this is a real but rare open edge
  case, flagged here rather than silently assumed away.
- A brush too degenerate to test (the same zero-area-face failure `polyalign._world_normal` already
  raises on) is reported as a named, skipped node — never a crash (no exception reaches the user).

### Known limitation — this WILL produce false positives, and that's accepted

Pure geometric touch/overlap is not the same question as "is this a walkable passage," and the
owner explicitly accepted the gap between them (2026-09-19) rather than paying for a full post-CSG
BSP solve to close it (see "Design decisions and why"). Concretely: a small, PURELY DECORATIVE
subtract — a bevel or a structural notch cut into a wall, never meant to let a player through — can
still geometrically touch volumes on both sides of that wall, and this design has no way to tell that
apart from a genuine doorway cut through the same wall. Both show up as a `touches` chain bridging
two rooms; only one of them is real. This is the direct cost of not running the full CSG solve, and
it is a deliberate, accepted tradeoff, not an oversight — surfaced here so a reader of the graph knows
to sanity-check a surprising connection rather than trust it blindly.

### Output format

Flat, ONE EDGE PER LINE, as a subject–relation–object statement. Never a nested/indented tree (a
tree implies a hierarchy this graph doesn't have — cycles and shared nodes are normal). Never JSON
in v1 — YAGNI (owner ruling, 2026-09-19; the new CLAUDE.md convention this session added).

This isn't a novel format for this codebase — it's the same shape `uedcli/eventgraph.py::format_text`
already renders for `event graph` (`"{src} ({cls}) --{event}--> {dst} ({cls})"`), for the same reason:
one line per edge is directly grep/scan-able for "everything connected to X" with no need to
reconstruct adjacency from separate node/edge arrays. `event graph` also already has a working
`format_dot` (Graphviz) alongside its text form — a real, cheap-to-mirror precedent if a DOT rendering
is ever wanted here (see "Out of scope"), not speculative new work:

```
Subtract_Lobby        --touches-->         Subtract_HallwayDoor
Subtract_HallwayDoor  --touches-->         Subtract_ConfMain
Subtract_ConfMain     --touches(112uu²)--> Subtract_ConfBay
Subtract_Lobby        --contains-->        Add_FrontDesk
Subtract_Lobby        --contains-->        NPC_Receptionist
Add_FrontDesk         --carved_by-->       Subtract_DoorCutout
```

- The optional `(...)` on a `touches` edge is a rough size of the touching/overlapping area: EXACT
  when a single matched face pair exists, a bounding-box-intersection estimate otherwise.
  `relation.classify_footprint_2d` itself only returns a shape LABEL (`"partial"`/`"coincident"`/…) —
  its actual area math is the private `_shoelace_area` helper it calls internally, not a public
  function this design can call as-is. So the exact-case area needs a small new function built the
  same way `classify_footprint_2d` already computes area internally, not a call to an existing public
  API — a real but small addition, not a reuse. `contains`/`carved_by` edges carry no size —
  containment is boolean, not a matter of degree the way a gap/overlap is.
- A `touches` edge between two brushes, where a single clean matched face pair exists, additionally
  names that pair as `Name:idx` selectors — `brush relation measure`'s own grammar — so the edge
  pipes straight into it for full plane/footprint/gap/offset detail:
  `Subtract_ConfMain:5 --touches--> Subtract_ConfBay:2`. A `touches` edge with no clean face pair (a
  genuine 3-D volume overlap, not a shared flat boundary) carries bare brush names; drilling in falls
  back to `brush relation measure BrushA BrushB`, ranking every poly pair.
- `contains`/`carved_by` edges have nothing to drill into — `relation measure` compares two FACES,
  not a point-in-solid test, so there's no second geometric relationship to ask for beyond "yes, it's
  inside." The light-graph line is the whole answer.

### CLI grammar

`uedcli level graph [--from NAME --hops N|all] [--tree KIND/NAME]`

- **No `--from`**: the whole queried actor set's graph, every node, every edge — mirrors `brush
  relation find`'s existing "omit candidates → search every brush in the level" default; not a new
  convention. This is also the expensive case: detection is pairwise (every brush tested against
  every other), so `--from`/`--hops` exists specifically to let a real level with hundreds of actors
  be queried around one area of interest instead of paying for the whole level every time.
- **`--from NAME --hops N|all`**: scoped to the connected neighborhood reachable from NAME within N
  hops (or unbounded — `--hops all` mirrors `--top N|all`'s existing spelling for "no cap"). `--hops`
  is REQUIRED when `--from` is given: an omitted count is ambiguous (one hop? unbounded?), and this
  project's convention is no silent half-answers. Conversely, **`--hops` given without `--from` is a
  clean exit 2** — a hop count has nothing to scope without a seed, and a flag that can't act where
  it's passed is an error here, not a silently-ignored no-op (same rule, same direction).
- NAME may be any node — brush or non-brush actor — there is no privileged "room" node type.
- **`--tree KIND/NAME`**: analyze a named T3D tree (level/stash/prefab) instead of the ambient
  `$UEDCLI_LEVEL`, via the existing shared `_tree_flag` helper (`uedcli/cli/parsers/_arguments.py`) —
  the same mechanism `event graph` and most other read/analysis verbs already use. `level graph` is
  exactly that shape of verb; there's no reason for it to be live-level-only when the mechanism to
  avoid that already exists and is standard here.
- No `--json` in v1 (owner ruling, 2026-09-19 — YAGNI).

## Design decisions and why

- **This supersedes the zone/portal/BSP-leaf graph idea raised earlier in the same design
  conversation.** That data is real and mostly already built (RE'd to byte-parity for the
  native-materialize lighting campaign) — but needs a native build to run and authored zoning to mean
  anything room-wise. The owner wants neither dependency (2026-09-19). Noted here so it isn't
  rediscovered from scratch if a future need specifically wants the ENGINE's own build-time room
  split; not pursued now.
- **Folding "find the rest of my segmented room" into `brush relation find` (a smaller proposal
  raised earlier in the same conversation) is superseded, not built alongside this.** This design's
  `touches` edges over Subtract nodes answer that exact question TRANSITIVELY, which one `relation
  find` call structurally can't. Building both duplicates the same detection logic behind two
  interfaces — YAGNI.
- **CSG order picks the label, not a second algorithm.** Whether a Subtract/Add pair is `contains` or
  `carved_by` is decided purely by which one is later in `level.order`; the geometric test (do these
  two volumes touch/overlap) is identical either way.
- **The U/V-axis blindness and missing rotate-to-align primitive in `brush relation set`** (flagged
  earlier this session) are NOT addressed here. This design discovers structure; it doesn't move
  anything. Those remain open, separate gaps in a different sub-verb.

## Module shape / touchpoints (implementation-stage detail, not prescriptive)

- New module `uedcli/actorgraph.py` (mirrors `relation.py`'s shape: pure Python, model-side, no
  editor, no native CSG) — the SAT touch/overlap test, the point-in-polyhedron containment test, and
  `contains`/`carved_by`/`touches` edge classification.
- Reuses `polyalign._world_verts`/`_world_normal` for a brush's world-space geometry rather than
  re-deriving actor-transform math.
- A new small area-computation function, built the same way `classify_footprint_2d` computes area
  internally (see "Output format"), for the exact-case `touches` size annotation; a new helper for
  the bounding-box-intersection fallback otherwise.
- `uedcli/cli/commands/level.py` is a single flat file (786 lines, a `run(args)` dispatcher + per-verb
  `_level_*` functions) — NOT a package the way `brush`'s command family is. This design adds a new
  `_level_graph` function there, matching the existing convention, not a new `level/` subpackage.
  `--from`/`--hops`/`--tree` parsing lands in `uedcli/cli/parsers/level.py` alongside the other
  `level` sub-verbs.
- A brush-convexity predicate — reuse one if this codebase already has it, otherwise add one — decides
  exact-SAT vs. approximate-fallback per brush, once.

## Test strategy (host-native `bin/test`, per `dev/docs/rules/tests.md`)

1. **Touching/overlap detection**: two convex brushes sharing a flat face (zero gap); two overlapping
   convex brushes with no shared flat face; two convex brushes near but not touching (no edge); a
   non-convex pair, flagged `⚠ approximate`.
2. **Edge labeling**: Subtract-Subtract and Add-Add always `touches`, undirected; Subtract-then-Add is
   `contains`; Add-then-Subtract is `carved_by`; same geometry, label flips purely on CSG order.
3. **Multi-edge fan-out**: an Add straddling two touching Subtracts gets `contains` from both; a
   Subtract carving two different Adds gets `carved_by` to both; a non-brush actor inside two
   overlapping brushes gets `contains` from both.
4. **Containment**: a non-brush actor's Location inside a convex brush, inside a non-convex brush
   (exact — no approximation needed for point tests), and outside every brush (no edges).
5. **CLI**: `--from`/`--hops N` scopes to the exact hop count (no off-by-one); `--hops all` is
   unbounded; `--hops` omitted with `--from` given is exit 2; `--hops` given WITHOUT `--from` is
   ALSO exit 2 (the reverse case); no `--from` dumps the whole level; a degenerate brush is a
   reported, skipped node, never a crash.
6. **Output format**: exact line shape per edge kind; `Name:idx` selectors present only when a single
   clean face pair was found; size annotation present only on `touches`.
7. **Movers**: a Mover touching an Add or another Mover gets `touches`; a Mover inside a Subtract gets
   `contains` (Subtract → Mover); a Mover is never a `carved_by` endpoint even when geometrically
   positioned where that label would otherwise apply to an Add.
8. **`--tree`**: `level graph --tree stash/NAME` analyzes a stash's actor set instead of the live
   level, same as other `_tree_flag`-bearing verbs.

## Docs to update on build

- New `docs/reference/level/graph.md`.
- `docs/reference/level/README.md`'s index table: add the `graph` row.
- `docs/reference/brush/relation.md`: cross-link — "for connectivity/containment discovery across
  multiple brushes, see `level graph`."

## Out of scope / deferred

- **`--json`** — explicit YAGNI (owner ruling, 2026-09-19; see the new CLAUDE.md line this session
  added). Add only once a real script/agent workflow needs structured output.
- **A DOT rendering** for human visualization — `eventgraph.py::format_dot` is a real, working
  precedent one file away (same graph-verb family, already handles a mover as a distinct node shape),
  so this would be cheap to mirror later, not speculative new work. Not built now because nobody has
  asked for it — the LLM-facing text form is what this design targets.
- **The zone/portal/BSP-leaf graph** (`uedcli-native`'s `Zone`/`BspLeaf`,
  `zones::assign_leaves_and_zones`/`build_connectivity`) — real, mostly already built, but needs a
  native build + authored zoning content. See "Design decisions and why".
- **`brush relation set`'s U/V-axis blindness and missing rotate-to-align primitive** — separate,
  pre-existing gaps in a different sub-verb, unaddressed here.
- **Add ↔ Add edges beyond plain `touches`** — included per the owner's explicit ask (2026-09-19), but
  no request yet for anything richer than the same touching test every other brush pair gets; revisit
  only if a real need (e.g. "which decorations overlap which other decorations") surfaces.
