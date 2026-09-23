# Spec: `actor relation` (renamed from `brush relation`) + `actor survey`

**Revision note**: this spec's first draft was adversarially reviewed and failed on several points
— factual errors against the shipped `level graph`/`brush relation` code, two worked examples that
broke the spec's own rules, and a genuine design bug (`crosses` as originally defined fired for
every piece of furniture in every room). This revision fixes all of those; see "Revision history"
at the end for what changed and why.

## Goal

Let an LLM reason about a level's spatial relationships from text, without opening the GUI.
`level graph` already gives a cheap, whole-level, raw-geometry graph — computed via SAT on authored
brush shapes, no CSG resolution. It is fast and always computable, but it can be a false positive
(an overlap a later Subtract erases) or miss context a resolved level would show.

This item adds the authoritative counterpart: real CSG/BSP resolution, via the native engine
(`uedcli-native`, Rust), scoped to one named actor at a time. The two stay separate tools rather
than merging into one graph — they answer different questions (spatial layout vs. did this actor's
geometry actually intrude on real, currently-solid matter).

Both commands report **facts, not verdicts**. Neither is an issue-linter: a `touches` or `connects`
result is not inherently bad, it is simply true. No line implies severity.

## Part 1 — `actor relation` (renamed from `brush relation`)

`brush relation` is renamed to `actor relation`. Its three existing subcommands keep their real,
per-subcommand mechanics (verified against `uedcli/cli/parsers/brush.py` and `uedcli/relation.py`),
with one rename and one broadening:

- **`find`** — unchanged. `--relative-to REF[:idx]` (bare `REF` ranks against every one of its own
  polys; `REF:idx` pins one). Candidates: named brushes, `-` for stdin, or omitted entirely to scan
  the whole level. Filters: `--max-gap`/`--min-gap`/`--footprint`/`--plane`. Prints bare
  `candidate:idx` selector lines to stdout (pipeable into `compare`/`set`), counts/near-miss notes
  to stderr, `--json` for scripted consumption (already exists today — kept as-is).
- **`compare`** — renamed from `measure`. `REF_SELECTOR` (bare name = all its polys, or `Name:idx`
  list) against one or more `TARGET_SELECTOR`s, or `-` for stdin. Full numeric/footprint detail:
  plane relationship, normals, distance, `footprint_2d`, deltas. Renamed because `measure` doesn't
  self-advertise that it takes two named sides and returns detail; `compare` does, and reads
  naturally against `find`'s "names out" contract.
- **`set`** — unchanged. `TARGET:idx` (exact face, no bare-name form) translated so it hits a
  `--gap`/`--centroid-u`/`--centroid-v`/`--edge-u-min`/`--edge-u-max`/etc. offset from
  `--relative-to REF:idx`.

**Broadening for non-brush actors, precisely per subcommand:**

`REF`/`--relative-to` stay poly-selector-only everywhere they appear (a face is required to align
something against — this does not change). The broadening is entirely on the *other* side:

- **`find`**: a non-brush actor may appear among the candidates when named explicitly or piped in
  via `-`. The **default** candidate set (no names given, no `-`) stays brush-only, unchanged from
  today — a level-wide point-actor scan is a different, much noisier question than this broadening
  is meant to answer, and changing the default silently would be a large, surprising change to
  every existing no-argument `find` call. The explicit-name path's current
  `skipping non-brush actor: <name>` stderr note is removed for this broadening (a named point
  actor is now a real candidate, not a skip). A matching point candidate has no `idx`, so it prints
  its bare name with no colon-index (`candidate` alone, not `candidate:idx`) — a real, distinct
  output shape a consumer must handle. `--json` emits
  `poly: null` for a point candidate (its `{ref, ref_poly, candidate, poly}` shape is otherwise
  unchanged). The **implicit** filter `find` already applies when `--footprint` is omitted (real
  behavior, `_passes_predicates`: excludes anything whose `footprint_2d` is `none`) does **not**
  apply to point candidates — they are ranked on gap alone in that case, since "no footprint
  overlap" isn't a meaningful exclusion for something with no footprint to begin with. An *explicit*
  `--footprint`/`--plane`, if given, excludes every point candidate (a face-pair predicate has
  nothing to test against a point) — not an error, since a mixed brush/point candidate set is
  normal and a face-pair filter simply narrows to the brush ones. `--max-gap`/`--min-gap` apply to
  point candidates normally (pure distance to the reference plane). Point candidates never
  contribute to the `--max-gap` near-miss count (also footprint-keyed).
- **`compare`**: a non-brush `TARGET_SELECTOR` is a bare actor name (its `Location`). Reports the
  fields still meaningful against a single point: perpendicular `distance` from `REF`'s plane, and
  the centroid-only half of `compute_deltas` (`centroid_u`/`centroid_v`, the point's own position
  in `REF`'s UV frame — not the edge-extent half, since a point has no edge to measure; `set` can
  still target a point by centroid, so `compare` must be able to report the same quantity it lets
  `set` aim at).

  **`footprint_2d` is NOT reused for the point case** — verified against the real function
  (`classify_footprint_2d`) with a degenerate one-point input: `_clip_2d` treats the point as a
  1-vertex clip polygon, whose `inside()` test degenerates to always-true, so every input (dead
  center, on an edge, 900 units away) returns `contains_a_in_b` unconditionally, with the
  containment direction inverted from what's wanted. This needs its own small point-in-polygon
  check, not a call into the existing face-pair function, reporting a new, distinctly-named
  three-value field — not reusing `footprint_2d`'s own vocabulary at all, since `contains` is
  already a taken word there (`--footprint`'s own filter alias, `relation.py`'s
  `_FOOTPRINT_FILTER_ALIASES`/`_FOOTPRINT_2D_RANK`/`_FOOTPRINT_2D_LABELS` all key on it already —
  reusing it for a new point-only value would collide with existing tables, not just existing
  words): `inside` (strictly inside `REF`'s footprint), `on_boundary` (exactly on it, via the
  existing point-on-segment test), `outside`. No `edge`/`coincident` equivalent — `edge` needs a
  positive-length collinear overlap, which a single point cannot have, and `coincident` needs
  matching areas.
- **`set`**: a non-brush `TARGET` is a bare actor name; the command writes its `Location`.
  `--gap`/`--centroid-u`/`--centroid-v` are meaningful, as before. `--edge-u-min`/`--edge-u-max`/
  `--edge-v-min`/`--edge-v-max` **remain meaningful too, and are kept, not refused**: an earlier
  draft of this spec refused them on the claim that they'd collapse into one spelling of
  `--centroid-*` for a point target — false. `_edge_extent` computes `pick(target) − pick(ref)`;
  for a point, `target`'s own pick collapses to one value, but `ref`'s does not, so
  `--edge-u-min`/`--edge-u-max`/`--centroid-u` remain three genuinely different offsets ("align
  this actor 8uu from the reference face's left edge" is a real, meaningful instruction against a
  point target). No `conventions.md` dual-spelling issue exists here; the earlier ruling cited it
  incorrectly.

This broadening is for a different reason than `actor survey`'s non-brush support (below): here it
is about *positioning* (an actor's bare location relative to a face); `actor survey` is about
*does this actor's volume intrude on real solid matter* (its collision cylinder). Keep the two
reasons distinct in the docs.

## Part 2 — `actor survey <name>` (new, standalone)

`actor survey <name>` reports every raw and CSG-resolved spatial fact about one named actor (brush
or non-brush). Not nested under `actor relation` — `relation`'s three subcommands are a
pairwise/scanning toolkit; `survey` is a single-actor comprehensive report, a structurally
different shape. Sits at the top level next to verbs like `actor bbox`/`actor diagram`.

**Scope**: always exactly one named actor, never a multi-candidate scan — this is what keeps
`survey` safe to call after every mutation without the cost risk a flag on `find`/`compare` would
carry. **Cost mechanism is not yet designed** — see "Open items" below; this spec commits to the
one-actor-at-a-time API shape, not yet to a specific bounded-cost algorithm.

### Output shape

One fact per line, prefixed with a tier token (`raw` or `csg`) as the first word — never a section
header, so the guarantee survives `grep`, truncation, or a line quoted mid-context into a later LLM
prompt. Line grammar matches `level graph`'s real, verified grammar
(`uedcli/actorgraph.py::format_text`):

```
<tier> <src>[:idx] [Package.Class Kind] --<relation>[(annotation)]--> <dst>[:idx] [Package.Class Kind]
```

The annotation, where present, is parenthesised and glued to the relation word — `touches(4096uu^2)`
— never a separate space-delimited `key=value` token. `[Package.Class Kind]` for a brush actor,
`[Package.Class]` (no `Kind`) for a non-brush actor or a Mover. `:idx` and the annotation appear
**only** on **raw** `touches` lines that found a real matched face pair; a raw `touches` line with
only a bounding-box area *estimate* (no clean coplanar face match) prints bare names with the
estimate still shown, no `:idx`. Every `csg`-tier line — `crosses`/`touches` included — and every
raw `contains`/`carved_by` line prints bare names, no `:idx`, no annotation (the `csg` tier's own
`:idx` was cut entirely; see that tier's section for why).
Facts print to stdout; a one-line count summary prints to stderr. No `--json` on `survey` itself —
YAGNI, no consumption need shown yet (note: `brush relation find` already has `--json` for its own
reason — piping into `set`/`compare` — that precedent doesn't transfer to `survey`, whose output is
a report, not a selector list to feed onward).

**Directionality**: one rule per relation, stated explicitly, not "usually" anything.

| Relation | Direction |
|---|---|
| raw `touches` | symmetric — the surveyed actor leads (see below) |
| raw `contains` | the container leads — several containers can each emit their own line for the same contained actor (raw has no competition rule) |
| raw `carved_by` | the Add (victim) leads, whichever side is surveyed — matches `level graph` exactly |
| csg `touches` | symmetric — the surveyed actor leads |
| csg `connects` | symmetric — the surveyed actor leads |
| csg `crosses` | the intruding solid actor leads |
| csg `contains` | the container leads — single-owner only, no multi-container case exists at this tier |
| csg `carves` | the Subtract (agent) leads, whichever side is surveyed — **deliberately inverted from `level graph`'s `carved_by`**, see below |

*Symmetric relations* (`touches` at both tiers, `connects`): `level graph` itself has no
subject-actor convention for these (it enumerates every pair via trunk order,
`itertools.combinations`) — but `actor survey` is a single-actor report, so, as a deliberate and
stated deviation from `level graph`'s own pair-enumeration convention, **the surveyed actor always
leads**, purely for single-actor readability. Surveying the *other* actor in the same pair flips
which side leads — that is expected, not a contradiction: it is the same underlying fact, rendered
with whichever actor you asked about first. **For raw `touches` specifically, the flip carries the
`:idx` pair with it, not just the names**: `level graph`'s underlying `Edge` glues `matched_pair`
to `(src, dst)` positionally, so swapping which actor leads must swap `matched_pair`'s two halves
too — a naive rename-only flip renders a real face selector against the wrong brush.

*Fixed-direction relations* — the same actor leads regardless of which side of the pair you survey.
`carves` is a deliberate deviation from `level graph`, not a claim of matching it: `level graph`'s
`carved_by` puts the victim first specifically so `contains`/`carved_by` share one direction rule
(Subtract leads only when it legitimately contains; leads *from* the victim otherwise). `actor
survey`'s `carves` instead always leads with the agent, matching `contains`'s container-leads
convention rather than `carved_by`'s victim-leads one — the owner's explicit choice (see this item's
design history), traded for a simpler single mental model ("the actor that acted leads") over exact
`level graph` parity. Anyone reading raw `carved_by` and csg `carves` for the same underlying pair
in the same `survey` output sees them with `src`/`dst` swapped — confirmed intentional, not an
oversight, and worth calling out once in the user-facing docs so it isn't mistaken for a bug.

### `raw` tier — cheap SAT geometry, auto-discovered, pre-CSG

Reuses `level graph`'s existing shipped vocabulary and computation exactly (`uedcli/actorgraph.py`)
— no new machinery, just auto-scoped to one actor's neighborhood instead of the whole level, with
no explicit reference face required (unlike `actor relation compare`/`find`). **Real vocabulary,
verified against `classify_pair`: `touches`, `contains`, `carved_by`.** (An earlier draft of this
spec invented a fourth word, `overlaps`, for a touch-vs-interpenetration distinction — `level
graph`'s own `cells_touch_or_overlap` collapses that distinction into one boolean and never
reports it separately; there is no `overlaps` relation, and adding one is new geometry work, not
reuse. Dropped.)

- **`touches <X>`** — both actors Subtract, or both Add-or-Mover-adjacent (i.e. neither is a
  Subtract): brush volumes touch or interpenetrate (SAT, `_TOUCH_EPS` tolerance, does not
  distinguish contact from overlap). Carries `:idx` + a `touches(AREAuu^2)` annotation when a clean
  matched coplanar face pair exists; otherwise bare names with a bounding-box area estimate, no
  `:idx`.
- **`contains <X>`** — brush-to-brush: exactly one of the pair is a Subtract, `X` (the non-Subtract
  side) is not a Mover, and the Subtract is *earlier* in trunk order — the one raw relation with a
  built-in causality check (a Subtract cannot have legitimately contained something that didn't
  exist yet). Also brush-to-Mover: a Subtract always `contains` a Mover it touches, regardless of
  trunk order (Movers carry no CSG operation, so order is meaningless for them). Also
  brush-to-point-actor: real point-in-volume containment (`point_in_brush`, not an adjacency
  heuristic) — every brush whose volume contains the point actor's `Location` reports `contains`,
  regardless of that brush's own CSG kind (Add, Subtract, Semisolid, alike; there is no Mover
  exclusion here, since a Mover is itself a brush actor and never appears as a point candidate).
- **`carved_by <X>`** — brush-to-brush, exactly one is a Subtract, the other is not a Mover, and the
  Subtract is *later* in trunk order. `X` is the Subtract; the surveyed Add leads (`level graph`'s
  own convention, unchanged here).

All three are order-heuristic or pure-geometry facts computed **before** full CSG resolution — real
signals, but each can be invalidated by something downstream (a later Subtract carving away the
touching matter; a "contains"/"carved_by" call made wrong by a brush a third, later operation has
since hollowed out). That gap is what the `csg` tier closes.

### `csg` tier — resolved via the native CSG/BSP engine, authoritative

Five relation types. For a non-brush actor, its collision cylinder (`CollisionRadius`/
`CollisionHeight`, from the instance if set, else the class default) stands in for brush geometry
throughout. `bCollideActors = False` or a zero/absent radius means the actor contributes no
`csg`-tier *geometry* of its own: it never appears as a `src` for `crosses` (nothing to test), and
never as the `dst` of a `touches`/`crosses` (no face of its own to be flush against or penetrated)
— but it is entirely unaffected as the `dst` of `contains` (`contains` tests a Subtract's own
authored shape against the actor's `Location`, which every actor has regardless of collision).

- **`crosses <X>`** — **source-restricted, stated positively**: only ever fires from an actor that
  contributes surviving solid matter to the resolved world. Confirmed valid sources: an Add brush,
  or a non-brush actor via a real collision cylinder (`bCollideActors = True` and a nonzero
  radius/height). **Confirmed never a valid source: a Subtract** — it contributes no solid matter
  to test for improper penetration. **Not yet ruled on, and NOT to be treated as valid by default**:
  Semisolid, Nonsolid, Intersect, Deintersect, and Mover — see "Open items", CSG-kind coverage.
  **Scope of the gate, stated explicitly since an earlier draft left it ambiguous and a review
  caught the ambiguous reading exiting the entire command**: this restriction gates only whether
  *this specific actor's own `crosses`-as-source facts* are computed — never the rest of the
  survey. Surveying an actor of one of these unruled kinds still prints its full `raw` tier and its
  `csg` `touches`/`contains`/`connects` facts, and it can still appear as the `dst` of another
  actor's `crosses` line (`crosses` only restricts which actor can be the `src`) — only the
  "does *this* actor's own matter cross into something" computation is skipped for it, silently,
  the same way a non-colliding point actor's `crosses`-as-source is already skipped (not an error;
  a level with actors of these kinds is the normal case, not an exceptional one). `Mover` in
  particular needs this stated plainly: the worked example below shows `DeusExMover9` fully and
  normally, including as the `dst` of `Brush118`'s `contains` line — only a hypothetical
  `DeusExMover9`-as-`crosses`-source fact would be the omitted one, and no such fact appears in
  this design's examples.

  Fires when the source's own contributed solid (or collision cylinder) extends past a resolved,
  surviving face belonging to `X`, into space the source does not itself claim. **No `:idx` at
  either tier boundary — bare names only, same as `connects`/`contains`/`carves`** (see "csg-tier
  `:idx`" below for why this was cut rather than pushed through a third revision).

  This restriction is the fix for a real design bug an earlier draft had: without it, a Subtract's
  *raw authored volume* trivially "crosses" every Add placed inside it (the room's raw shape
  geometrically extends through wherever a later pillar now sits) — firing for every piece of
  furniture in every room. With the restriction, a Subtract never produces `crosses` lines at all;
  what it correctly produces instead for the same scenarios is `contains` (a pillar sitting
  directly in its void — see below) or `carves` (if the Subtract is the one doing the removing —
  see below). `crosses` is reserved for exactly the case neither of those covers: a solid actor's
  own matter genuinely extending somewhere it shouldn't.

  A second, related and **also unresolved**, noise concern for the collision-cylinder arm
  specifically: a cylinder is an axis-aligned bounding approximation of a mesh, and a decoration
  resting on a floor or set against a wall routinely has its cylinder overlap adjacent solid by a
  few units *by design*, not by error — see "Open items", collision-cylinder tolerance.

  **Surface-ownership rule** (`X` can be an Add or a Subtract): `X` is whoever *authored* the
  specific face being crossed — a Subtract's own carved boundary is a real face even though the
  Subtract has no solid of its own. **Strictly local**: always the immediate boundary crossed,
  never a deep transitive owner. Given `Subtract1 → Additive2 → Subtract3 → Additive4`, where
  `Additive4` (a solid Add) pokes through `Subtract3`'s own wall, the fact is
  `Additive4 --crosses--> Subtract3` — never `Additive2`.

  **Attribution mechanism is an open item, not settled here** (see "Open items"): two prior
  revisions of this spec each asserted a specific native-engine field as the answer (a fictional
  "BSP leaf ownership", then `iBrushPoly` alone) and a review found both wrong against the real
  code — real brush attribution needs the paired `(BspSurf.i_actor, i_brush_poly)`, `i_actor`
  indexes a *filtered* CSG brush list (not raw trunk order), and even that pair breaks for a
  coplanar-merged face or a Mover's own private model. Rather than assert a fourth mechanism
  unverified, this spec commits only to the *requirement* (attribute to the immediate face's real
  author) and leaves the *implementation* — which native fields to read, and how to resolve them
  back to a trunk actor name — to be nailed down against `uedcli-native` directly before
  `to-plan/`, not re-derived by further review rounds against this document alone.

- **`touches <X>`** — flush against a resolved poly belonging to `X`, no penetration. Normal, not
  an error (a room's Subtract legitimately stopping exactly at its bounding wall). Same word as raw
  `touches`, disambiguated only by the tier tag — structurally the same kind of fact at both tiers,
  differing only in reliability. Unlike `crosses`, not source-restricted: a Subtract's carve
  legitimately touches the resolved boundary it stopped at, and this *is* worth reporting (it is
  how "this room is bounded by that wall, and the wall is intact" gets stated). No `:idx` — bare
  names, same as every other `csg` relation.

  **Tolerance, shared with `crosses`**: both use the same `_TOUCH_EPS`-class tolerance this codebase
  already applies everywhere real, editor-placed geometry needs float-noise slack (matching
  `actorgraph.py`'s and `relation.py`'s existing named constants) — a face within tolerance of
  coincident is `touches`, not a hair-width `crosses`. This is not a new tolerance to invent; it is
  the same constant class the rest of this module already uses, applied consistently here.

**csg-tier `:idx` — cut, not just simplified, and here's why.** No `csg`-tier relation carries a
`:idx` selector, on either side, ever — every line is bare `Name --relation--> Name`. This is a
scope cut from an earlier draft, made after two straight review rounds found the specific
mechanism asserted for it (first "the resolved BSP leaf the intrusion enters" — fictional, no such
per-brush leaf ownership exists; then `iBrushPoly` alone — real field, but insufficient on its own,
and wrong on a coplanar-merged face or a Mover's private model) each factually wrong against the
real native code. A `Name:idx` token in this grammar is a promise — every other one is a genuine,
pipeable selector into `actor relation compare` (raw `touches` included) — and this spec would
rather promise less at the `csg` tier than promise a selector a fourth review round might also
disprove. Naming *which specific poly* a `csg crosses`/`touches` fact concerns is real, useful
information and a plausible v2 addition, once its mechanism is verified directly against
`uedcli-native` rather than asserted from this document alone — tracked in "Open items", not
solved here.

- **`connects <X>`** — Subtract-only, surveyed actor and `X` both Subtracts: void region continuous
  with `X`'s void, no separating solid poly between them. Not face-anchored — the fact is the
  *absence* of a face. Covers a partial merge and full nesting (a smaller, effectively-redundant
  Subtract carved entirely inside a bigger one's already-void space) alike.

  **Disambiguation from `touches` between two Subtracts sharing a coincident plane** (two adjacent
  box rooms, an extremely common shape): this is `connects`, not `touches`. The rule: `touches`
  requires a *surviving solid face* on at least one side — two Subtracts sharing a plane with
  nothing solid on either side produces no surviving face at all (there is nothing there to be
  flush against), so it can only ever be `connects`. `touches` between two Subtracts specifically
  never fires under this design — it was inherited into the `csg`-tier vocabulary from the raw
  tier's `touches` (which genuinely can hold between two Subtracts, since raw `touches` is not
  face-existence-based) but does not carry over as a live case at the `csg` tier. Kept as a valid
  spelling for a future CSG-kind case (see "Open items", CSG-kind coverage) rather than removed, to
  avoid a second special-case rule.

  Not split by the raw tier's underlying touch-vs-overlap distinction, since that distinction does
  not exist at the raw tier either (see the `raw` tier correction above) — nothing to fall back on
  here, and nothing lost, since raw `touches` never claimed to carry it in the first place.

- **`contains <X>`** — one rule, after two dropped attempts at a second one. `X` (or `X`'s
  `Location`; for a brush or Mover `X`, its own **full extent**, not just its centroid — a strict
  full-containment test, deliberately: see the divergence note below for what this costs) falls
  within the surveyed Subtract's own *authored shape*. **Competition** (this is the same predicate
  applied to `X` in general, point or volumetric — not a point-only special case): when more than
  one Subtract's own authored shape satisfies that predicate for the same `X`, the one with the
  **smallest total authored volume** wins, within a relative tolerance (the same `_close`-style
  relative-comparison convention `relation.py` already uses elsewhere for its own `_AREA_EPS`,
  applied here as its own named constant for *volume* — a plan-time detail, not a borrow of
  `relation.py`'s private one) — it reports `contains`; the others do not. A genuine tie within that
  tolerance breaks toward the later one in trunk order. This is a volume comparison, not a
  strict-subset/nesting test — it stays correct even when a carve brush is deliberately oversized
  past what it carves into (routine, to avoid coplanar faces), which a strict-subset rule would
  silently get wrong. Given `Subtract1 → Additive2 → Subtract3 → Additive4`, `Subtract3`'s authored
  volume is smaller than `Subtract1`'s, so `Subtract3` wins regardless of whether it pokes past
  `Additive2`'s own bounds — `Subtract1` reports nothing about `Additive4`. Given the pillar case (a
  Subtract room with a later Add pillar inside it, and a light at the same point), the Add never
  enters this competition at all — it isn't a Subtract — so the room simply wins uncontested, and
  the light is `contains`-ed regardless of the pillar. A separately colliding actor at that same
  point reports `crosses <the pillar>` on its own; both facts coexist.

  **A second rule for the doorway/multi-parent case was tried twice and dropped both times** — once
  as a transitive `connects`-union (collapsed to "the whole level" on real content) and once as a
  narrow pairwise "seam" rule (turned out geometrically impossible: a point standing in genuinely
  neither Subtract's authored shape is, in a subtractive engine, standing in *unclaimed solid*, not
  a jointly-owned void — the doorway itself has to be carved by *something*, and whatever that is
  already wins the single-owner rule above, correctly and more specifically than a vague joint claim
  would). **The original multi-parent motivating case — "an add is contained within two subtracts
  that are joined, the edge goes to both" — is not reachable through a doorway/seam at all**; it was
  never re-derived against a concrete, buildable T3D example in this design's whole history. No `+`
  grouping exists in this spec. Real cost of dropping it, stated plainly rather than glossed over:
  two Subtracts can genuinely *overlap* (a corridor deliberately oversized past the room it opens
  into, to avoid a coplanar seam — routine, the same reason a niche is oversized in the point case
  above), and an actor sitting in that overlap is `contains`-ed only by the smaller one; the larger
  Subtract stays silent about it. This is not treated as a gap worth a second rule, because it costs
  nothing to recover: the pair also reports `connects` (they genuinely touch/overlap), so a reader
  gets the relationship in one hop regardless, and the smaller volume is the more specific, more
  useful single answer anyway. If a real multi-owner containment case turns up once this ships
  (built from actual content, not reasoned about in the abstract), it gets its own spec revision
  against that concrete example — not a third attempt at the same abstract rule.

  Diverges from raw `contains` in one direction (not the two an earlier draft claimed): raw's
  brush-to-brush trunk-order heuristic has no notion of volume-based competition, so it can say yes
  where a smaller, more specific Subtract should really own the point — a false positive, `csg`
  correcting `raw`. No false-negative direction survives this rule's removal of the multi-parent
  case above — **except** one worth naming rather than hiding: because the volumetric predicate is
  strict full-containment, a large Add or Mover that only *partially* pokes out of a Subtract (a
  floor-to-ceiling pillar, a door swinging a unit past its frame) gets no csg `contains` at all,
  even though raw `contains` (touch-or-overlap, not full containment) reports one. This is the
  deliberate, stated cost of a strict predicate, not an oversight — the alternative (majority-of-
  extent, or centroid-only) was considered and rejected as its own source of ambiguity for a case
  this design has no concrete motivating example for yet.

- **`carves <X>`** — the surveyed Subtract removed part of `X`'s (an Add's) originally-contributed
  solid matter. Not a viewpoint-flip of `crosses` — legitimate carving never leaves a violated
  *surviving* face for `crosses` to name (the boundary retreats to wherever the carve stopped, and
  what remains of `X` sits flush against it — that is `touches`). `carves` records the *history*
  matter that used to extend further, before this Subtract reduced it — the one fact neither
  `crosses` nor `touches` expresses. Active voice, the Subtract (agent) leads regardless of which
  side is surveyed (see the directionality table above for how this differs from `level graph`'s
  own `carved_by`).

  **Total removal**: an Add entirely consumed by a later Subtract still reports `carves` — "part"
  in the definition above means "at least part," not "strictly not all"; complete removal is the
  most valuable case of this fact, not an excluded one. Whatever of `X`'s own original faces still
  physically survives elsewhere (untouched by this Subtract) reports `touches` as normal; if nothing
  of `X` survives anywhere, no `touches` line accompanies the `carves` line for that pair, and that
  is correct — there is nothing left to be flush against.

  A second Subtract subtracting *exactly* the same, already-carved region as a first Subtract does
  **not** report `carves` against the original Add — nothing of the Add's matter remains there to
  remove. It reports `connects` against the first Subtract instead. A second Subtract whose carve
  only *partially* overlaps the first's already-carved region reports both: `connects` for the
  redundant portion, `carves <the Add>` for the portion that is genuinely new removal.

### Worked example

Scenario, fixed once and used for both surveys below: `Brush118` is a Subtract room. `Brush117` is
an Add wall `Brush118` genuinely carves a niche into (`Brush118` is later in trunk order).
`Brush113` is an Add wall `Brush118` merely stops flush against — no real removal ever occurred —
but `Brush118` is *also* later than `Brush113` in trunk order, so the raw order-heuristic cannot
tell the two apart and calls both `carved_by`; only the `csg` tier can. `Brush944` is a second
Subtract room, void-connected to `Brush118` through a doorway. `DeusExMover9` is a Mover sitting
fully inside `Brush118`'s void — `Brush118` is the only Subtract whose authored shape contains its
full extent, so it wins `contains`'s volume competition uncontested (only one candidate at all).

Every line below is derived mechanically from `classify_pair`'s real rules (raw tier) and this
spec's own stated `csg`-tier rules — not composed by feel:

```
$ uedcli actor survey Brush118
raw Brush117 [Engine.Brush Add] --carved_by--> Brush118 [Engine.Brush Subtract]
raw Brush113 [Engine.Brush Add] --carved_by--> Brush118 [Engine.Brush Subtract]
raw Brush118:4 [Engine.Brush Subtract] --touches(640uu^2)--> Brush944:1 [Engine.Brush Subtract]
raw Brush118 [Engine.Brush Subtract] --contains--> DeusExMover9 [DeusEx.DeusExMover]

csg Brush118 [Engine.Brush Subtract] --carves--> Brush117 [Engine.Brush Add]
csg Brush118 [Engine.Brush Subtract] --touches--> Brush117 [Engine.Brush Add]
csg Brush118 [Engine.Brush Subtract] --touches--> Brush113 [Engine.Brush Add]
csg Brush118 [Engine.Brush Subtract] --connects--> Brush944 [Engine.Brush Subtract]
csg Brush118 [Engine.Brush Subtract] --contains--> DeusExMover9 [DeusEx.DeusExMover]
```
```
stderr: actor survey: 4 raw fact(s), 5 resolved CSG fact(s) for Brush118
```

Read together, `Brush117` and `Brush113` show exactly the contrast the whole two-tier design exists
for: **raw calls both `carved_by`, identically — csg tells them apart.** `Brush117` genuinely lost
matter (`carves` *and* `touches`, for what remains of it); `Brush113` never did (`touches` only,
`carves` correctly absent — the raw heuristic's `carved_by` call for that pair was wrong, and `csg`
is what catches it). `Brush118` itself never shows a `csg crosses` line anywhere — it is a Subtract,
and `crosses` is source-restricted away from it.

`Brush117`'s own survey, same level, same pairs, matching the directionality table exactly — the
`carved_by`/`carves` lines are identical (fixed direction, victim/agent unaffected by which side is
surveyed); the `csg touches` line flips to `Brush117` leading (symmetric, surveyed actor leads):

```
$ uedcli actor survey Brush117
raw Brush117 [Engine.Brush Add] --carved_by--> Brush118 [Engine.Brush Subtract]

csg Brush118 [Engine.Brush Subtract] --carves--> Brush117 [Engine.Brush Add]
csg Brush117 [Engine.Brush Add] --touches--> Brush118 [Engine.Brush Subtract]
```
```
stderr: actor survey: 1 raw fact(s), 2 resolved CSG fact(s) for Brush117
```

## Rejected alternatives (naming and shape)

Kept for context so this is not re-litigated without cause:

- **A single merged verb naming** (`clash`, `resolve`, a `geometry`/`csg` middle noun): rejected —
  `clash` implies issue-finding; `resolve` didn't distinguish itself from `measure`/`find`'s own
  unclear naming; a `geometry` qualifier implies brush-only; `csg` as a *command-level* qualifier
  has the same brush-only implication, though it works fine as a per-line tier tag, where it
  describes computation provenance (which side of the resolution pipeline produced this fact),
  not a claim that CSG itself applies to the actor being surveyed.
- **Nesting the new verb under `actor relation`**: rejected — conflates two different tool shapes
  under one word, re-creating the raw/resolved ambiguity the two-tier split exists to prevent, one
  level deeper.
- **`raw`/`resolved` or `raw`/`built` tier tags**: both considered; `csg` chosen for precision and
  because both words pair more evenly (`raw`/`csg`, 3 characters each).
- **Splitting `connects` into `touches`/`overlaps`**: rejected — `connects` is structurally the
  absence of a face, `touches`/`crosses` are structurally the presence of one; forcing them into
  one vocabulary reintroduces ambiguity worse than what it solves. (Note: this rejection stands on
  its own reasoning and does not depend on a same-pair raw `overlaps` line existing to fall back on
  — no such relation exists; see the `raw` tier correction above.)

## Open items (not yet resolved — do not proceed to `to-plan/` until closed)

- **CSG-kind coverage**: this spec is written entirely in terms of Add/Subtract (and Mover, via
  `is_mover`). `query.csg_kind` has six *brush* kinds (a seventh, `"mover"`, is returned separately
  and is handled throughout this spec via `is_mover`, not as a `csg_kind` case) —
  `add`/`subtract`/`semisolid`/`nonsolid`/`intersect`/`deintersect` — and `level graph` already
  tags all of them, Mover included. Needs one ruling per kind before
  `to-plan/` — at minimum whether Semisolid/Nonsolid are treated as Add-like for `crosses`/`carves`
  purposes, and whether `Intersect`/`Deintersect`/Mover are in scope for v1 as `crosses` sources.
  Whichever kinds are ruled out stay **silently skipped as a `crosses` source only** — never an
  exit-2 refusal of the whole `survey` command (the `crosses` section's gate is scoped to that one
  relation; nothing in this spec refuses a whole survey over an unruled kind). Also needs a ruling
  on whether `Intersect`/`Deintersect` can themselves ever be the container side of `contains` (the
  rule as written is Subtract-only), and a Mover's solid-contribution status to world CSG is itself
  unconfirmed (excluded from world CSG entirely, per its own `NodeTag` handling — whether that means
  it never contributes solid to test, or needs a separate private-model check, is not yet decided).
- **`csg`-tier `:idx` (which specific poly a `crosses`/`touches` fact concerns)**: cut from this
  spec entirely (see the `csg`-tier `:idx` section) after two straight review rounds found the
  asserted attribution mechanism factually wrong against the real native code. A real fix needs the
  paired `(BspSurf.i_actor, i_brush_poly)`, `i_actor` resolved through the filtered CSG brush list
  construction `preview_native.py` already uses, and explicit handling for a coplanar-merged face
  and a Mover's own private model — verify this directly against `uedcli-native` before attempting
  it again, not by further reasoning against this document.
- **Collision-cylinder tolerance for `crosses`**: a cylinder is an axis-aligned bounding
  approximation, and a decoration resting on a floor or set against a wall routinely has its
  cylinder overlap adjacent solid by a few units *by design*. Needs either a real tolerance above
  `_TOUCH_EPS` for cylinder sources specifically, or an explicit decision to scope the
  collision-cylinder arm of `crosses` out of v1 pending real-content measurement of how much this
  actually fires.
- **Bounded-cost mechanism**: the "safe to call after every mutation" claim needs an actual
  neighborhood-selection algorithm (which brushes participate in one actor's CSG resolution) with a
  correctness argument for the truncation, not just an assertion — this covers the `csg` tier.
  **The `raw` tier is not automatically safe either**: finding the surveyed actor's neighbours still
  means decomposing every brush in the level for SAT (`decompose_convex` over the whole level), and
  each CLI invocation is a fresh process with no cache carried across calls — so "safe after every
  mutation" needs a cost story for both tiers, not just `csg`. Likely needs a short spike against
  `uedcli-native`'s existing incremental-resolution machinery (`NATIVE-MATERIALIZE.md`'s campaign)
  for the `csg` half, and a measurement of real-level raw-decomposition cost for the other half,
  before `to-plan/`.
- **Error paths**: unknown/ambiguous actor name, degenerate brush (including when the *surveyed*
  actor itself is degenerate — `level graph` has an explicit `skipped` list and
  `DegenerateBrushError`; `survey` needs its own stated behavior, not silent reuse).
- **Docs fallout**: the `relation` subparser (`uedcli/cli/parsers/brush.py`) and its handler
  (`uedcli/cli/commands/brush/relation.py`) move from `brush` to `actor` as part of this rename, not
  just get renamed in place. Also: the rename touches `docs/reference/brush/relation.md`, `docs/reference/brush/
  README.md`, `docs/reference/brush/poly.md`, `docs/reference/level/graph.md`,
  `docs/leveldesign/general/recipes/shapes/mitered-corner.md`, `find --json`'s own help string
  (currently says "pipe into `brush relation measure REF -`"), the four user-visible
  `RelationError` messages in `uedcli/relation.py` (lines 476/641/647/653) and the two in
  `uedcli/cli/commands/brush/relation.py` (lines 70/146) that hard-code the old verb name,
  `uedcli/actorgraph.py`'s own docstring references, `relation.py`'s module docstring and
  section-divider comments, and the `relation` subparser's help text. Also the shipped
  agent-facing plugin skills tree
  (`plugins/uedcli/skills/verifying-brush-relations/SKILL.md`,
  `plugins/uedcli/skills/positioning-a-brush/SKILL.md`,
  `plugins/uedcli/references/brush-relation-basics.md`, `plugins/uedcli/HANDOFF.md`) — in
  particular, `verifying-brush-relations/SKILL.md`'s "Known limitation" section documents
  `brush relation`'s point-actor blind spot and a manual workaround for it; this change removes
  that limitation and the section needs to say so, not just be renamed in place. Same-change
  requirement per `CLAUDE.md`, not deferred to the plan.

## Testing notes (for the eventual plan)

- `raw`-tier logic has genuinely no new computation — reuses `level graph`'s existing
  `classify_pair`/`brush_overlap`/`point_in_brush` exactly, scoped to one actor. New tests cover
  the scoping and auto-discovery (no explicit `REF`), not the underlying math.
- `csg`-tier logic is new and must be backed by `uedcli-native` (per this project's Rust-by-default
  convention). Needs regression coverage for every case this spec's design history surfaced: the
  pillar-in-room `contains`+`crosses` coexistence (the Add never competes for `contains`), the
  4-level nested `contains` volume-competition case (including a deliberately oversized inner
  Subtract, to pin that the rule is volume-based, not strict-subset), a genuine volume tie between
  two competing Subtracts (pins the relative-tolerance tie-break), the redundant-nested-Subtract
  `connects` case, the partial-overlap `carves`+`connects` coexistence case, total-removal `carves`
  with no accompanying `touches`, and the two-adjacent-rooms `connects`-not-`touches`
  disambiguation.

## Revision history

- **Round 1 → Round 2** (adversarial Opus review): raw tier's vocabulary and mechanics corrected
  against real `actorgraph.py` (dropped invented `overlaps`; restored `carved_by`; corrected
  `contains`'s real trunk-order/Mover rules; corrected the annotation grammar to match
  `format_text`'s real output). Fixed a genuine design bug in `crosses` (source-restricted to solid
  actors — see the `crosses` section above) that the two worked examples' contradiction had been
  masking. Added the full directionality table. Made `actor relation`'s non-brush broadening
  precise per subcommand, including a concrete ruling on `set`'s edge flags (refuse, don't alias).
  Added the CSG-kind-coverage, bounded-cost-mechanism, and error-path items to "Open items" rather
  than asserting them. Corrected the `--json` family claim (`find` already has one).
- **Round 2 → Round 3** (second adversarial Opus review): found the round-2 fixes real but the
  rewrite reintroduced the same failure class in two new places (a worked-example line
  `classify_pair` cannot produce; the two examples still disagreeing on a symmetric `csg touches`
  line) — both examples rebuilt mechanically from the stated rules instead of composed by feel.
  Found a genuine fresh contradiction: `contains` had two mutually exclusive boundary definitions
  (authored-shape-never-moves, needed for the pillar case; resolved-BSP-leaf locality, needed for
  the nesting case) that gave opposite answers on the same geometry — replaced with one unified
  domain + locality-competition rule that satisfies the pillar case, the multi-parent case, and the
  nesting case simultaneously, without special-casing any of them separately. Restated `crosses`'s
  source restriction positively (an implementer following the negative form would have wrongly
  admitted Nonsolid/Deintersect) and flagged the collision-cylinder arm's own unresolved noise
  problem rather than let the pillar-case example quietly rely on a non-colliding actor it
  contradicted its own gate for. Replaced the fictional "BSP leaf ownership" mechanism for
  `crosses`'s locality with the real per-surf brush-provenance concept. Reversed the `set` edge-flag
  ruling (they are not redundant against a point target — kept, not refused — the earlier
  `conventions.md` citation was based on a false premise). Filled in `find`'s implicit-filter/
  `--json`/near-miss behavior and `compare`'s real point-footprint vocabulary for point targets.
  Extended the docs-fallout list with the plugin skills tree and `relation.py`'s user-visible error
  strings. Added the collision-cylinder tolerance and raw-tier cost items to "Open items."
- **Round 3 → Round 4** (third adversarial Opus review): found the round-3 `contains` rewrite
  introduced a genuine new defect — defining a Subtract's domain as the *transitive* closure of
  `connects` collapses to "the whole level's void contains everything" on any level whose rooms
  connect through doorways/corridors (which is nearly all of them). Replaced with two separate,
  bounded rules: single-owner containment by smallest-authored-volume competition (also fixing a
  second defect the same review found — the old strict-subset "more local" test failed for
  routinely-oversized carve brushes, and had no tie-break for 3+ candidates; volume comparison
  needs neither), and a narrow, inherently-pairwise seam rule for the doorway/multi-parent case
  that never chains past the one directly-adjacent pair of rooms involved — closing the "3+ member
  ordering" open question by making it moot rather than answering it. Verified `compare`'s
  point-footprint vocabulary against the real `classify_footprint_2d` function (traced by hand,
  not just read) and found it genuinely broken for a degenerate one-point input — replaced with a
  stated need for new point-in-polygon logic and a narrowed three-value vocabulary. Fixed the
  `crosses` exit-2 gate's scope, which an ambiguous reading would have applied to an entire
  `survey` call rather than just that one actor's own `crosses`-as-source computation — confirmed
  against the worked example, which needs `DeusExMover9` (an unruled kind) fully surveyable as a
  `dst`. Fixed the worked example's `Light61` scenario, whose premise (a point in "neither shape
  alone, only their union") was geometrically impossible under the *new* domain rule and needed
  rewriting to the doorway-gap framing the seam rule actually needs. Added the raw-`touches`
  directionality-flip-must-carry-`matched_pair` note, narrowed `find`'s non-brush broadening to
  never touch the default (brush-only) candidate set, and gave the csg-tier `:idx` rule its real
  provenance (`iBrushPoly`) plus a dedup rule for split surfs. Fixed a docs-fallout error-string
  miscount.
- **Round 4 → Round 5** (fourth adversarial Opus review): found two more BLOCKERs, both cases of
  the same lesson — a mechanism stated with confidence that doesn't survive contact with the real
  geometry or the real code. (1) The seam/doorway `contains` rule (round 4's fix for the
  multi-parent case) turned out geometrically impossible: a point standing in genuinely neither
  Subtract's authored shape is standing in unclaimed solid, not jointly-owned void, in a
  subtractive engine — whatever carves the doorway already wins the volume-competition rule, more
  specifically than a vague joint claim would. **Dropped entirely** rather than attempted a fourth
  time — the volume-based single-owner rule alone covers every case this spec has actually needed,
  and the original abstract multi-parent motivating case was never re-derived against a concrete,
  buildable example across this design's whole history. The `+`-grouping mechanism and its open
  question file are removed with it. (2) The csg-tier `:idx` provenance claim (`iBrushPoly` alone)
  was independently found wrong against the real native code — real attribution needs the paired
  `(i_actor, i_brush_poly)`, `i_actor` indexes a filtered brush list, and both a coplanar-merged
  face and a Mover's private model break the "always a valid selector" guarantee. **Cut `:idx`
  entirely from the `csg` tier** rather than attempt a third mechanism — every `csg` relation now
  prints bare names, matching `connects`/`contains`/`carves`'s existing shape; naming the specific
  poly is deferred to a real v2 investigation against `uedcli-native` directly, tracked in "Open
  items". Also fixed: the `crosses` exit-2 gate's scope wasn't carried into "Open items", so a
  future ruling could still land as "refuse the whole survey" despite the body's own narrower gate;
  `contains`'s predicate for a volumetric (non-point) `X` was unstated; the volume tie-break had no
  tolerance, so it would silently decide by float noise instead of the stated trunk-order rule;
  `compare`'s new point-footprint value collided with `footprint_2d`'s own existing `contains`
  filter alias and its backing tables (renamed to a distinct, non-colliding vocabulary); Testing
  notes still referenced the dropped "single domain rule" framing; and a docs-fallout precision
  fix. Both worked examples updated to match — `:idx` removed from every `csg` line, the `Light61`
  seam illustration removed (its premise no longer exists).
- **Round 5** (fifth adversarial Opus review): **zero BLOCKER findings** — the round-4 scope cut
  held; both dropped mechanisms (the seam rule, csg-tier `:idx`) were verified actually gone
  everywhere, not just relocated, and every line of both worked examples re-verified against real
  code one more time. Five small non-blocking fixes landed from this round: the Output-shape
  section still granted `:idx`/an annotation to csg `touches` (missed when `:idx` was cut from that
  tier — now explicit that raw `touches` alone keeps it); the `contains` competition clause and the
  `DeusExMover9` scenario prose were still worded point-only despite the predicate itself already
  covering volumetric `X`; the directionality table's csg `contains` row still said "container(s)",
  residue from the dropped multi-owner mechanism; the `contains` section didn't say what dropping
  the multi-parent rule costs (a genuinely overlapping pair of Subtracts now reports single
  ownership, recoverable via the `connects` line on the same pair) or that the volumetric predicate
  is deliberately strict, not majority-of-extent; and two low-severity precision fixes (six *brush*
  kinds vs. seven `csg_kind`-adjacent values including Mover; the `relation` subparser/handler's
  own module relocation added to docs fallout). **This spec is internally sound.** It remains
  gated from `to-plan/` by its own "Open items" header, which lists six items needing real
  investigation or an owner ruling (CSG-kind coverage, csg-tier `:idx` v2, collision-cylinder
  tolerance, bounded-cost mechanism for both tiers, error paths, and the docs-fallout work itself)
  — that gate is deliberate, not a defect the review process left behind.
