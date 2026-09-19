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
| Add, Add                     | (irrelevant)       | `touches`  | undirected         |
| Subtract, Add                | Subtract earlier   | `contains` | Subtract → Add     |
| Subtract, Add                | Subtract later     | `carved_by`| Add → Subtract     |
| Brush (any), non-brush actor | n/a                | `contains` | Brush → actor      |

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

- **Touching/overlap test**: convex separating-axis test (SAT) against the brush's actual
  world-space polyhedron — faces from its `PolyList`, transformed by Rotation/MainScale/PostScale/
  Location the same way `polyalign._world_verts`/`_world_normal` already do. Exact for convex
  brushes (cube/cylinder/cone/sheet/most authored shapes).
- **Non-convex brushes** (freeform, staircase-shaped, CSG-modified): SAT's face-normal test is not
  exact here. Fall back to a coarser bounding-box-overlap + sampled-point check, and flag the result
  `⚠ approximate` in the output — never present an approximate answer as exact (matches this
  project's existing convention of labeled masks rather than hidden ones).
  A brush's convexity is decided once and reused, not re-derived per edge.
- **Containment test** (brush → non-brush actor): point-in-polyhedron test of the actor's `Location`
  against the brush's volume. Well-defined regardless of convexity — no approximation needed here.
- A brush too degenerate to test (the same zero-area-face failure `polyalign._world_normal` already
  raises on) is reported as a named, skipped node — never a crash (no exception reaches the user).

### Output format

Flat, ONE EDGE PER LINE, as a subject–relation–object statement. Never a nested/indented tree (a
tree implies a hierarchy this graph doesn't have — cycles and shared nodes are normal). Never JSON
in v1 — YAGNI (owner ruling, 2026-09-19; the new CLAUDE.md convention this session added):

```
Subtract_Lobby        --touches-->         Subtract_HallwayDoor
Subtract_HallwayDoor  --touches-->         Subtract_ConfMain
Subtract_ConfMain     --touches(112uu²)--> Subtract_ConfBay
Subtract_Lobby        --contains-->        Add_FrontDesk
Subtract_Lobby        --contains-->        NPC_Receptionist
Add_FrontDesk         --carved_by-->       Subtract_DoorCutout
```

- The optional `(...)` on a `touches` edge is a rough size of the touching/overlapping area: EXACT
  when a single matched face pair exists (reusing `relation.classify_footprint_2d`'s area math on
  that pair), a bounding-box-intersection estimate otherwise. `contains`/`carved_by` edges carry no
  size — containment is boolean, not a matter of degree the way a gap/overlap is.
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

`uedcli level graph [--from NAME --hops N|all]`

- **No `--from`**: the whole level's graph, every node, every edge — mirrors `brush relation find`'s
  existing "omit candidates → search every brush in the level" default; not a new convention.
- **`--from NAME --hops N|all`**: scoped to the connected neighborhood reachable from NAME within N
  hops (or unbounded — `--hops all` mirrors `--top N|all`'s existing spelling for "no cap"). `--hops`
  is REQUIRED when `--from` is given: an omitted count is ambiguous (one hop? unbounded?), and this
  project's convention is no silent half-answers.
- NAME may be any node — brush or non-brush actor — there is no privileged "room" node type.
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
- Reuses `relation.classify_footprint_2d`'s area computation for a `touches` edge's size annotation
  when a matched face pair exists; a new helper for the bounding-box-intersection fallback otherwise.
- New `uedcli/cli/commands/level/graph.py` + the `level graph` sub-parser (`uedcli/cli/parsers/
  level.py`): `--from`/`--hops` parsing, BFS traversal when scoped.
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
   unbounded; `--hops` omitted with `--from` given is exit 2; no `--from` dumps the whole level; a
   degenerate brush is a reported, skipped node, never a crash.
6. **Output format**: exact line shape per edge kind; `Name:idx` selectors present only when a single
   clean face pair was found; size annotation present only on `touches`.

## Docs to update on build

- New `docs/reference/level/graph.md`.
- `docs/reference/level/README.md`'s index table: add the `graph` row.
- `docs/reference/brush/relation.md`: cross-link — "for connectivity/containment discovery across
  multiple brushes, see `level graph`."

## Out of scope / deferred

- **`--json`** — explicit YAGNI (owner ruling, 2026-09-19; see the new CLAUDE.md line this session
  added). Add only once a real script/agent workflow needs structured output.
- **A Mermaid/DOT rendering** for human visualization — a cheap possible follow-on, not needed for the
  LLM-facing path this design targets.
- **The zone/portal/BSP-leaf graph** (`uedcli-native`'s `Zone`/`BspLeaf`,
  `zones::assign_leaves_and_zones`/`build_connectivity`) — real, mostly already built, but needs a
  native build + authored zoning content. See "Design decisions and why".
- **`brush relation set`'s U/V-axis blindness and missing rotate-to-align primitive** — separate,
  pre-existing gaps in a different sub-verb, unaddressed here.
- **Add ↔ Add edges beyond plain `touches`** — included per the owner's explicit ask (2026-09-19), but
  no request yet for anything richer than the same touching test every other brush pair gets; revisit
  only if a real need (e.g. "which decorations overlap which other decorations") surfaces.
