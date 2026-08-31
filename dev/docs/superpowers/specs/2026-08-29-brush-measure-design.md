# `brush measure` — exact geometric facts instead of visual guesses

## Motivation

Agents self-check built geometry by rendering a preview and reading it. This fails even when a
defect is human-obvious: a desk built with a floating leg (a visible gap) and a decorative panel
placed off-center both passed the builder agent's own visual review of the render. This isn't
model-specific — precise *metric* spatial judgment from pixels ("is this gap 0 or 4uu", "is this
centered or off by a few percent") is a general weakness of current multimodal LLMs, not something
a stronger model reliably fixes.

`level doctor` already draws the relevant line: it flags only what's objectively, mechanically
wrong, and by owner ruling never guesses author intent — "whether a decoration is well placed,
correctly oriented, or seated on its surface" is explicitly out of scope, left to "a human or an
independent reviewing agent looking at renders" (`docs/usage.md:293-323`). That reviewing-agent
mechanism doesn't exist yet; the desk incident is it failing in practice.

**Fix:** wherever a geometric relationship is objectively computable from the model, expose it as
an exact number instead of asking an agent to eyeball it from an image. The tool states facts; the
agent still judges whether a fact is a problem — the same boundary `doctor` already draws,
generalized to relative-positioning questions `doctor` was never meant to answer.

## What we want

Two verbs under a new `brush measure` family. `brush`, not `actor`, because both are inherently
PolyList concepts (faces, planes) — same namespace tier as `brush poly`/`brush vertex`; `actor` is
the generic point-or-brush namespace.

### `brush measure alignment <selectors…>`

No required flags — the fewer decisions an agent has to make up front to get useful output, the
better; extra output is a cheap trade for that.

- A **selector** is a bare brush name (whole actor) or `BRUSH:idx` (one face; `:all` expands, same
  grammar `brush poly` already uses). Accepts `-` to read a newline selector list from stdin, same
  convention as `actor bbox`/`actor find`.
- For every selector, print its world bbox `min`/`max` per axis (X, Y, Z) — the same math
  `actor bbox` already does, just per-item instead of unioned into one box — and, **for face
  selectors only**, its area-weighted centroid.
- If **any** selector given is a face selector, the **first one is the reference plane**. Every
  *other* selector then additionally gets, relative to it:
  - `offset_in_plane (U, V)` — its point projected into the reference's own local 2-D frame,
    relative to the reference's centroid.
  - `distance_from_plane` — signed perpendicular distance from the reference plane, along its
    normal. Sign convention: **positive = same side as the face's outward normal** (this project's
    existing winding-defines-face invariant already fixes what "outward" means — state it plainly
    here rather than make an agent guess; see Comprehension testing below for why this matters).
- `--type {min,max,centroid}` / `--axis {X,Y,Z}` exist only as optional narrowing flags for later
  scripted use — never required. `--type centroid` on a bare brush name is a clean exit 2 naming
  the problem (undefined for a whole solid, not a guess).
- Pure measurement: no pass/fail, always exit 0 unless a selector fails to resolve.

Example (the motivating bug):

```
$ uedcli brush measure alignment WallFace:3 Panel:0
WallFace:3   X:[0,512]   Y:[512,512] Z:[0,96]    centroid=(256,512,48)   (reference)
Panel:0      X:[100,196] Y:[511,511] Z:[20,76]   centroid=(148,511,48)
             offset_in_plane: U=-108.000  V=0.000
             distance_from_plane: -1.000
```

### `brush measure relation <names…>` (2 or more bare brush names)

Searches all faces of every named brush against all faces of every other named brush — the agent
names the parts, not the faces, and gets back the full relationship graph over that set. Accepts `-`
to read the brush name list from stdin, same convention as elsewhere. `--top N` (default `1`) caps
how many ranked candidate poly-pairs are shown per brush pair; `--top all` removes the cap and shows
every qualifying pair (the original, uncapped behavior) — see "Reporting volume" below for why a cap
exists and how candidates are ranked.

For every pair of named brushes, look for a plane relationship between some pair of their faces:

- **`coplanar`** — a poly of A and a poly of B lie on the same plane, within `polyalign.py`'s existing
  `_PARALLEL_EPS`/`_PLANE_EPS` tolerances — the cross-brush, possibly-rotated two-different-actors
  plane comparison `brush poly align --wall` already does, not `geometry.py`'s `PLANAR_TOL` (a
  single poly's vertices checked against its *own* best-fit plane — a different comparison; caught
  during implementation planning, corrected here). `distance` is whatever the actual measured
  perpendicular offset is — usually very close to `0.000uu` but not artificially forced to it; the
  tolerance decides which bucket a pair falls into, never what number gets printed.
- **`parallel`** — no exact match, but some pair of faces are parallel and their footprints face
  each other (project onto either plane — see `footprint_2d` below). `distance` is the signed
  perpendicular distance between them (see the `distance` field below for the sign convention —
  it's what makes interpenetration, not just separation, show up as an exact number). This is what
  makes a floating part (parallel to, but not touching, the surface it should rest on) show up with
  an exact number instead of falling into an undifferentiated "not touching" bucket — restores what
  a gap-only pairwise check already gave before this was generalized into a graph, now folded into
  the same shape as the coplanar case.
- **Neither** — the pair's normals aren't parallel or anti-parallel at all (e.g. faces at right
  angles). Omitted entirely. A brush with *no* relationship (coplanar or parallel, to anything) in the
  set is called out separately as **disjoint** — this is what makes it a graph rather than a flat
  pairwise check.

**`footprint_2d: none` is a real, reported value for both `coplanar` and `parallel` — it is NOT
grounds for exclusion.** A `parallel` pair whose footprints don't overlap at all is still a fully
valid, useful answer: naming two brushes specifically to check whether they align (a floor marking
under a ceiling fixture, say) and getting back `none` *is* the answer to the question that was asked
— dropping it would silently discard the one case where the answer is "no." The only pair that's ever
excluded is "Neither" above (not parallel at all) — decided after briefly reconsidering and reversing
an earlier, narrower version of this rule that excluded `parallel`+`none`.

**Reporting volume — capped per brush pair, not per face pair.** The naive version of "report every
qualifying face pair" doesn't scale: two ordinary 6-sided cubes produce up to 12 candidate poly-pairs
(each of A's 6 faces is parallel to exactly 2 of B's 6 faces), and that's *per brush pair* — so
`C(N,2)` brush pairs among N named cubes means up to `12·C(N,2)` blocks (72 for 4 cubes, 180 for 6),
almost entirely incidental noise from box side-walls that share an axis for no reason related to
what's actually being checked. Fix: **report at most the top `K` candidate poly-pairs per brush pair**
(default `K=1`; `--top N` or `--top all` overrides it — see Command surface below), ranked:

1. **`footprint_2d` quality, primary**: `coincident` > `contains` > `partial` > `edge` > `vertex` >
   `none` — full/partial containment resolves the relationship unambiguously; touching-only is a
   weaker signal; no overlap is weakest. (Not "most area to least" — a tiny `contains` can share far
   less area than a huge `partial`; the ranking is about how unambiguous the match is, not its size.)
2. **`distance` magnitude (`abs(distance)`), ascending** — among equally-good footprint matches,
   prefer the physically closer pair.
3. **centroid-delta magnitude, ascending** — final tie-break.
4. **`(poly_a index, poly_b index)`, ascending** — deterministic fallback so a genuine multi-way tie
   (routine for centered geometry — a beam centered in a wall's thickness, a light centered over a
   table) always picks the same pair, not an arbitrary one.

**Known, accepted limitation** (found in independent Opus review, not fixed here): this ranking can
pick a coincidentally-coplanar, low-significance pair over a more substantive one when two brushes
*interpenetrate* along multiple axes at once — e.g. a pillar embedded in a wall's end, where the
wall's and pillar's top faces are exactly level (an incidental, `distance=0` fact from both being
built to the same height) while the pillar's actual embedding into the wall's side is the more
significant fact. A fix (ranking by relative overlap area as an earlier tie-break) was designed and
reviewed but deliberately not adopted for v1 — accepted as a known gap rather than adding the
complexity now; revisit if it proves to matter in practice.

When every candidate for a brush pair is `none` (nothing worth detailing), collapse the whole pair to
one summary line instead of a full block — see the report format below.

**No "closest pair" selection *within* what gets shown — every candidate up to the `--top` limit is
a real, ranked entry, never a synthesized "best."** A brush pair can have more than one genuine
relationship (e.g. two separate faces facing two different faces of a neighboring brush, at different
distances) — the default `--top 1` may compact this, but the block header always states how many
candidates existed in total (`N of M candidates shown`), so nothing is ever silently dropped, only
compacted with the fact of compaction always visible. `--top all` recovers full detail.

Each reported pair's header is the two face selectors themselves (e.g. `Inset:0 <-> Frame:0`), not
an opaque index — `<->`, matching the brush-level header and this codebase's own precedent for
pairing two related things (`docs/usage.md:1102`, "poly index ↔ face"); `/` was considered and
rejected — elsewhere in this codebase `/` reads as alternation (`min/max`), not pairing.

Fields per pair, always present regardless of `coplanar` vs `parallel` (uniform shape, nothing
conditional to guess about):

- **`plane: coplanar | parallel`**
- **`normals:`** — each face's own normal, as a world-space unit vector, indented one per face
  (never a cardinal `X|Y|Z` label — this engine has rotated/curved brushes with non-axis-aligned
  faces, e.g. `revolve`-built geometry, so a normal isn't always cardinal). Showing both actual
  vectors instead of a computed `same|opposite` verdict removes a real ambiguity: a single shared
  `normal` field would need to pick one of the two faces' conventions as "the" direction, which is
  arbitrary when they disagree. Reading the two vectors directly also removes an inference step a
  comprehension-test agent otherwise had to make correctly on its own (guessing "U↔X, V↔Z" from
  context) — `(0.000, 0.000, 1.000)` vs `(0.000, 0.000, -1.000)` is immediately legible as "opposite,
  ordinary floor/ceiling pair" without a label saying so.
- **`distance`** — signed. `0.000uu` when `coplanar`. When `parallel`: **positive = separated** (real
  empty space between the two faces, the floating-leg case), **negative = interpenetrating** (the two
  solids overlap along the normal), measured along the *first-named* face's own outward normal
  (already shown under `normals:` — same "first is the reference" convention `alignment` and
  `brush poly align --wall` (`docs/usage.md:665`, "the first face is the seam/seed") already use, so
  there's no second sign convention to learn). No separate
  `interpenetrating: yes/no` field — the sign of `distance` already says it unambiguously, and a
  redundant boolean would just be a second claim that could drift from the number, the exact failure
  mode the `alignment` label and the single `normal` field were already dropped for. Direction beyond
  the sign is in `normals`, not jammed into this field as text (a cardinal-axis phrase like "along Z"
  doesn't generalize to a non-axis-aligned normal anyway).
- **`footprint_2d`** — the 2-D relationship between the two faces' footprints, always evaluated as a
  projection onto the shared/parallel plane (trivial, zero-distance projection when `coplanar`; across
  the gap/overlap when `parallel` — same computation either way, which is why one taxonomy covers
  both):

  | value | meaning |
  |---|---|
  | `none` | no touching or overlap at all |
  | `vertex` | touch at a single point |
  | `edge` | touch along a line segment, zero area overlap |
  | `partial` | real area overlap, neither fully contains the other |
  | `contains (X:i in Y:j)` | one fully inside the other's footprint — direction always stated |
  | `coincident` | identical footprint both ways — usually duplicate/stacked geometry, a different mistake than `contains` |

- **`deltas:`** — always both, never a computed judgment (see Design decisions for why). Both are
  **second-named minus first-named** (e.g. for `Inset:0 <-> Frame:0`, `Frame:0`'s value minus
  `Inset:0`'s) — the same first-is-reference convention as everything else here, stated explicitly so
  it never has to be reverse-engineered from an example:
  - `centroid: U=…uu V=…uu` — offset between the two footprints' area-weighted centroids.
  - `edge: <U-min|U-max>=…uu <V-min|V-max>=…uu` — per axis, independently, whichever of the two
    bounding-box edges (min or max) is closer to matching, labeled which one. Tie-break: prefer `-min`.

No `alignment` label (`centroid-aligned`/`edge-aligned`/`none`) — an earlier draft had one, and
comprehension testing caught it going stale relative to the numbers it was supposed to summarize (see
Comprehension testing). Always showing both exact deltas removes the possibility of a label
disagreeing with the numbers, because there's no separate claim left to disagree.

Output is a human-readable grouped report, one block per pair (Option B from brainstorming) — this
is a report verb, like `level status`/`project show`, not a pipe-friendly producer like
`actor find`. No `--json` in v1.

**A trailing `checked: N brushes, M pairs, every face` summary line**, `M` always `N·(N-1)/2` (every
combination of the named brushes). This states the search was exhaustive — every named brush against
every other, every face — instead of leaving it to be inferred. Comprehension testing raised this
independently, three separate times, without prompting: agents reading the report cold couldn't tell
whether a short list of relationships meant "exhaustive, this really is everything" or "only the
first/best match got reported," and one agent assumed the names were compared pairwise by position
rather than every combination. The report already *is* exhaustive; this line is the only thing that
was missing to say so.

Full example — every `plane` × `footprint_2d` combination, so this also serves as the implementation's
reference fixture set. Shown as one concatenated block per relationship type for reference, not a
single real invocation (a real call only ever includes the brushes you actually name); a real
invocation always ends with the trailing `checked:` line for that specific call, omitted here since
these 27 demo brushes across 13 unrelated pairs would make for a `checked: 27 brushes, 351 pairs`
line that adds nothing to the taxonomy reference this block exists for (every brush here has exactly
one real relationship — its own pair partner — so `Lamp` is the only entry that would actually appear
in `disjoint`, same as shown below):

```
SlabA <-> SlabB  (1 shared plane)
  SlabA:0 <-> SlabB:0
    plane:      coplanar
    normals:
      SlabA:0:  (0.000, 0.000, 1.000)
      SlabB:0:  (0.000, 0.000, -1.000)
    distance:   0.000uu
    footprint_2d:  none
    deltas:
      centroid: U=300.000uu  V=0.000uu
      edge:     U-min=300.000uu  V-min=0.000uu

CornerA <-> CornerB  (1 shared plane)
  CornerA:0 <-> CornerB:0
    plane:      coplanar
    normals:
      CornerA:0: (0.000, 0.000, 1.000)
      CornerB:0: (0.000, 0.000, -1.000)
    distance:   0.000uu
    footprint_2d:  vertex
    deltas:
      centroid: U=100.000uu  V=100.000uu
      edge:     U-min=100.000uu  V-min=100.000uu

WallSegL <-> WallSegR  (1 shared plane)
  WallSegL:3 <-> WallSegR:1
    plane:      coplanar
    normals:
      WallSegL:3: (1.000, 0.000, 0.000)
      WallSegR:1: (-1.000, 0.000, 0.000)
    distance:   0.000uu
    footprint_2d:  edge
    deltas:
      centroid: U=100.000uu  V=0.000uu
      edge:     U-min=100.000uu  V-min=0.000uu

TileA <-> TileB  (1 shared plane)
  TileA:0 <-> TileB:0
    plane:      coplanar
    normals:
      TileA:0:  (0.000, 0.000, 1.000)
      TileB:0:  (0.000, 0.000, -1.000)
    distance:   0.000uu
    footprint_2d:  partial
    deltas:
      centroid: U=50.000uu  V=50.000uu
      edge:     U-min=50.000uu  V-min=50.000uu

Inset <-> Frame  (1 shared plane)
  Inset:0 <-> Frame:0
    plane:      coplanar
    normals:
      Inset:0:  (0.000, 0.000, 1.000)
      Frame:0:  (0.000, 0.000, -1.000)
    distance:   0.000uu
    footprint_2d:  contains (Inset:0 in Frame:0)
    deltas:
      centroid: U=0.000uu  V=0.000uu
      edge:     U-min=-40.000uu  V-min=-40.000uu

BigPanel <-> Badge  (1 shared plane)
  BigPanel:0 <-> Badge:0
    plane:      coplanar
    normals:
      BigPanel:0: (0.000, 0.000, 1.000)
      Badge:0:    (0.000, 0.000, -1.000)
    distance:   0.000uu
    footprint_2d:  contains (Badge:0 in BigPanel:0)
    deltas:
      centroid: U=30.000uu  V=-30.000uu
      edge:     U-max=-10.000uu  V-min=10.000uu

Decal <-> Decal2  (1 shared plane)
  Decal:0 <-> Decal2:0
    plane:      coplanar
    normals:
      Decal:0:  (0.000, 0.000, 1.000)
      Decal2:0: (0.000, 0.000, 1.000)
    distance:   0.000uu
    footprint_2d:  coincident
    deltas:
      centroid: U=0.000uu  V=0.000uu
      edge:     U-min=0.000uu  V-min=0.000uu

ShelfA <-> ShelfB  (no shared plane — parallel)
  ShelfA:0 <-> ShelfB:0
    plane:      parallel
    normals:
      ShelfA:0: (0.000, 0.000, 1.000)
      ShelfB:0: (0.000, 0.000, -1.000)
    distance:   60.000uu
    footprint_2d:  none
    deltas:
      centroid: U=300.000uu  V=0.000uu
      edge:     U-min=300.000uu  V-min=0.000uu

PostCapL <-> PostCapR  (no shared plane — parallel)
  PostCapL:0 <-> PostCapR:0
    plane:      parallel
    normals:
      PostCapL:0: (0.000, 0.000, 1.000)
      PostCapR:0: (0.000, 0.000, -1.000)
    distance:   12.000uu
    footprint_2d:  vertex
    deltas:
      centroid: U=100.000uu  V=100.000uu
      edge:     U-min=100.000uu  V-min=100.000uu

LedgeL <-> LedgeR  (no shared plane — parallel)
  LedgeL:0 <-> LedgeR:0
    plane:      parallel
    normals:
      LedgeL:0: (0.000, 1.000, 0.000)
      LedgeR:0: (0.000, -1.000, 0.000)
    distance:   8.000uu
    footprint_2d:  edge
    deltas:
      centroid: U=100.000uu  V=0.000uu
      edge:     U-min=100.000uu  V-min=0.000uu

PanelX <-> PanelY  (no shared plane — parallel)
  PanelX:0 <-> PanelY:0
    plane:      parallel
    normals:
      PanelX:0: (1.000, 0.000, 0.000)
      PanelY:0: (-1.000, 0.000, 0.000)
    distance:   2.000uu
    footprint_2d:  partial
    deltas:
      centroid: U=50.000uu  V=50.000uu
      edge:     U-min=50.000uu  V-min=50.000uu

LegFoot <-> FloorPad  (no shared plane — parallel)
  LegFoot:0 <-> FloorPad:0
    plane:      parallel
    normals:
      LegFoot:0:  (0.000, 0.000, -1.000)
      FloorPad:0: (0.000, 0.000, 1.000)
    distance:   4.000uu
    footprint_2d:  contains (LegFoot:0 in FloorPad:0)
    deltas:
      centroid: U=0.000uu  V=0.000uu
      edge:     U-min=-40.000uu  V-min=-40.000uu

StickerA <-> StickerB  (no shared plane — parallel)
  StickerA:0 <-> StickerB:0
    plane:      parallel
    normals:
      StickerA:0: (0.000, 0.000, 1.000)
      StickerB:0: (0.000, 0.000, 1.000)
    distance:   16.000uu
    footprint_2d:  coincident
    deltas:
      centroid: U=0.000uu  V=0.000uu
      edge:     U-min=0.000uu  V-min=0.000uu

disjoint: {Lamp} shares no plane and has no parallel-facing relationship with anything else named
```

`coincident` with both normals pointing the same way (`Decal`/`StickerA` above) is a strong "this is
probably a stray duplicate" signal — a real copy-paste would preserve facing direction — versus
`contains` with opposing normals, which reads as an ordinary solid-to-solid mate.

**The `--top`/collapsing behavior**, on a brush pair with several candidates (default `--top 1`):

```
Wall <-> Pillar  (1 of 4 candidates shown)
  Wall:2 <-> Pillar:1
    plane:      parallel
    normals:
      Wall:2:    (0.000, 1.000, 0.000)
      Pillar:1: (0.000, -1.000, 0.000)
    distance: -8.000uu
    footprint_2d: partial
    deltas:
      centroid: U=0.000uu  V=0.000uu
      edge:     U-min=0.000uu  V-min=0.000uu
```

and a brush pair whose *every* candidate is `none` collapses to one line instead of a full block:

```
LampA <-> LampB: no overlapping face pairs (12 candidates, nearest 340.000uu apart)
```

## Design decisions and why

These came out of real back-and-forth and two rounds of subagent testing — worth keeping so a
future change doesn't undo them by accident.

- **Never emit a verdict.** No pass/fail, no `--check`/`--assert-*` flag, no field that defaults to
  "should be zero." The instant a verb decides two named things *ought* to align, it's taken over
  the judgment call `doctor`'s ruling reserves for the agent. The agent always supplies both
  referents; the tool only measures.
- **Default to printing everything; flags only narrow.** Matches `actor bbox`'s existing
  default-dump-then-`--field` pattern. Fewer required decisions up front beats a leaner default
  output.
- **Area-weighted centroid, not vertex-average.** This codebase already has both, for different
  purposes: `preview.py`'s `_poly_centroid_2d` (shoelace, area-weighted — correct for a general
  polygon) vs. `builders.py`/`polyalign.py`/`doctor.py`'s `_centroid` (plain vertex average — wrong
  for a poly with uneven vertex density). Reuse the former's math, generalized to a face's own 3-D
  plane; a rectangular face makes the two definitions agree, which is exactly why the difference
  wouldn't have shown up by accident.
- **Face-local (U, V) projection, not world X/Y/Z, for centering.** A brush's own face-plane is
  authored geometry, independent of whether it's part of an additive or subtractive brush — CSG
  operator only decides which side is solid, never where the plane sits. So a coplanarity/projection
  check answers "is this centered on that wall" correctly even when the wall is a subtractive
  brush's boundary, with no dependency on `uedcli-native`'s CSG solver at all.
- **`distance_from_plane` is its own field, split from `offset_in_plane`.** First-round
  comprehension testing (below) showed mixing perpendicular distance into raw world coordinates
  next to an in-plane offset caused a model to anchor on the wrong number. Separating and labeling
  them fixed it.
- **Naming: `relation`, not `contacts`, `seam`, or `flush`.** `seam` is already heavily used in this
  codebase's own prose for an unrelated concept (an architectural/interface boundary — `doctor.py`,
  `emit.py`, `polyalign.py`). `flush` was the working name for a while (it has zero collisions and is
  already this team's own word for "faces meet with no gap" — `preview.py` and this repo's own git
  history; not `docs/usage.md`, which doesn't use the word) but the verb outgrew it: most `footprint_2d`
  values (`none`, `partial`,
  `coincident`, and `vertex`/`edge` touching) describe states that aren't flush at all, and the verb
  now reports a full plane-relationship graph, not a touching check. `relation` matches the actual
  current scope; checked for collisions the same way `seam` was ruled out — only `correlation`
  appears elsewhere in this codebase (`qualify.py`), an unrelated word.
- **Report format, not flat pipe-lines, for `relation`.** It's read top-to-bottom like a dashboard,
  not piped into another verb — matches `level status`/`project show`'s precedent, not `actor find`'s.
- **`footprint_2d`, not `topology`.** Same six values, renamed so the field itself states what it's
  answering: a 2-D projected-outline comparison, never a claim about the two faces actually touching
  in 3-D. True uniformly — trivial (zero-distance) projection when `plane: coplanar`, across the gap
  when `plane: parallel` — which is why one taxonomy legitimately covers both instead of doubling the
  vocabulary per plane state.
- **No qualitative `alignment` label — always both exact deltas instead.** An earlier draft computed
  `centroid-aligned` / `edge-aligned: X` / `none` as its own field, separate from the raw numbers.
  Comprehension testing produced an example where the label read `none` while the delta was
  `(0.000, 0.000)` — a direct contradiction, because a computed label can silently drift out of sync
  with the numbers it's supposed to summarize. Removing the label and always printing
  `deltas: centroid / edge` closes that failure mode structurally: there's no second claim left that
  could disagree with the math.
- **`plane`/`normals`/`distance` as their own explicit fields**, not left implicit in prose or in a
  header parenthetical. Each is a fact already available for free from the same plane-fit/normal
  computation the rest of this verb needs — stating `plane: coplanar|parallel` explicitly, and
  printing both faces' actual `normals` vectors, cost nothing and removed guessing that a
  comprehension-test agent otherwise did correctly, but had to do.
- **`gap` renamed `distance`, and signed instead of magnitude-only, instead of adding a separate
  `interpenetrating` field.** A negative `distance` means the two solids overlap along the normal
  instead of being separated — the same fact a boolean flag would state, but as a property of the
  number that's already there rather than a second claim next to it. This is the same principle
  behind dropping the `alignment` label and the single `normal` field: don't add a computed
  true/false restating something a signed number already says unambiguously.
- **The `parallel` fallback, and why it's not "closest pair only."** Generalizing the original
  pairwise gap check into a full plane-relationship graph accidentally regressed it: a pair with no
  *exact* shared plane (e.g. a part floating a few units off the surface it should rest on) fell into
  the same bare `disjoint` bucket as two genuinely unrelated brushes, with no distance reported. A
  comprehension-test agent caught this directly ("off by a hair and off by 500 units look identical
  here"). Fixed by reporting every parallel, footprint-facing face pair even without exact
  coplanarity — not just "the closest" one, since picking a single closest pair needs an arbitrary
  tie-break and can silently hide a second, genuinely different relationship (e.g. a brush facing two
  separate parts of its neighbor at two different gaps). `disjoint` is now reserved for pairs with no
  facing relationship at all, not just "not touching."
- **`normal` as a vector, not a cardinal `X|Y|Z` label.** This engine has rotated/curved brushes
  (`revolve`, octagonal columns) with non-axis-aligned faces, so a cardinal-only field would have no
  correct answer for an angled wall. A vector is always correct and still reads as instantly
  recognizable in the common axis-aligned case (`(0, 0, 1)`).
- **Face-pair header, not an opaque `plane 1:` index.** Naming the actual two faces
  (`Inset:0 <-> Frame:0`) as the block header removes a lookup step; the count in the brush-level
  header (`(1 shared plane)`) still tells you how many such blocks to expect.
- **Trailing `checked:` summary line.** Three independent comprehension-test agents, unprompted, all
  raised the same uncertainty from three different angles: was the search exhaustive, or did the tool
  just report the first/best match? The report already is exhaustive (every face pair, every brush
  pair) — the line states the brush and pair counts so that's verifiable from the output instead of
  trusted on faith or inferred from the spec text a reading agent won't have seen.
- **`<->` separator between paired items, not `/`.** `/` reads as alternation elsewhere in this
  codebase (`min/max` = one or the other). `<->` matches the brush-level header and the existing
  "poly index ↔ face" pairing precedent (`docs/usage.md:1102`).
- **Ranking order for the `--top` cap, and what got rejected.** An independent Opus design review
  (not a comprehension test — a review of the ranking logic itself) confirmed footprint-quality-first
  correctly handles both canonical motivating cases (a small leg on a large floor; a floor/ceiling
  alignment check) that broke the two earlier proposals (distance-first, centroid-delta-first) — see
  those two rejected orderings' own reasoning above. The same review found a real, unfixed weakness
  (interpenetrating brushes, detailed above) and proposed a fix (rank by relative overlap area before
  distance); the fix was understood and deliberately not adopted for v1, to avoid adding ranking
  complexity before real usage shows it's needed. This is a conscious, recorded trade-off, not an
  oversight — revisit if the five-agent build-and-check exercise (below) or later real usage turns up
  a case where it actually bites.

## Comprehension testing

Before writing any code, sample outputs (in the exact shape above) were shown cold — with only a
`--help`-equivalent description, no other context — to independent Opus and Sonnet subagents, asking
them to interpret the geometry and flag anything wrong. (A first pass also included Haiku; dropped
per owner call — not a target model for this workflow.)

- **Validated as-is:** bare-actor `alignment` (a 4-pillar row with one pillar offset on Y) and
  `relation` (a desk with one floating leg) were both read correctly by every model tested — right
  number, right axis, no false positives on the clean cases.
- **Found and fixed a real problem:** an early draft mixed a face's raw world coordinates with its
  projected `(U, V)` offset in one row. Sonnet anchored on a small, likely-intentional perpendicular
  gap (reconstructed by diffing two rows' world Y values) and downgraded the actual 44-unit
  off-center defect to a maybe-not-a-bug footnote. Splitting `distance_from_plane` out as its own
  explicitly labeled field, separate from `offset_in_plane`, fixed this — both Opus and Sonnet then
  correctly led with the in-plane offset and treated the small perpendicular distance as an
  incidental, likely-intentional standoff.
- **Residual, out of scope:** a weaker model can still read a correct, clearly nonzero number and
  rationalize it away as intentional. Output shape can't fully solve for a model that's too lenient
  — not something this spec attempts to fix. (Haiku showed this failure; not a target model for this
  workflow per owner call, so not tracked further.)
- **Third round, no `--help` text at all** (just the command and a one-line scenario, testing whether
  the output is self-explanatory without documentation): `alignment` was read correctly cold by
  Sonnet with no help text — confirms its explicit field labels carry enough meaning on their own.
  `relation`'s *un-labeled* dash-separated format (`— contains (...) — none — U=... V=...`, the
  pre-`footprint_2d`/`deltas` shape, when the verb was still named `flush`) did not fare as well: Sonnet
  had to guess whether a bare `none` was the alignment field or an empty warnings slot, and — the
  finding that mattered most — flagged that a `disjoint` pair carries no distance at all, which is
  what drove the `parallel`-fallback fix above. Labeling every field explicitly
  (`plane:`/`normals:`/`distance:`/`footprint_2d:`/`deltas:`) is the direct response to this round.
- **Fourth round, three Sonnet agents each given a different slice of the reference example cold**
  (coplanar `vertex`/`edge`/`partial`; `coincident` with same-direction `normals` plus a bare
  `disjoint` case; `parallel` `contains` — the real bug — next to a `parallel` `none` that's actually
  fine): every genuine defect was diagnosed correctly and confidently, including reasoning about the
  `normals` vectors to confirm a comparison made physical sense (e.g. anti-parallel normals
  corroborating a leg's underside meeting a floor's top face), and hedging appropriately on the one
  case that was genuinely ambiguous (a large horizontal offset between two shelves not meant to
  touch) rather than asserting a verdict the geometry alone can't support. All three agents also,
  independently and unprompted, raised the same uncertainty — was the search exhaustive, or just the
  first/best match — which is what the `checked:` line above responds to.
- **Fifth round, closing both gaps from the fourth round.** Three more cold Sonnet reads: (1) a
  realistic `LegFoot`/`FloorPad`/`Tabletop` call with a trailing `checked:` line — read exactly as
  intended, verbatim: *"without this line I'd have assumed the tool might sample only likely-facing
  faces... with it, I'm confident the sweep was exhaustive"*; (2) a genuinely interpenetrating pair
  (`distance: -12.000uu`, `footprint_2d: partial`) with **no help text on the sign convention at all** —
  correctly read as "the two brushes overlap/interpenetrate by 12uu... intersecting solid brushes
  cause CSG artifacts," inferred purely from the field name and the anti-parallel `normals`, not
  prompted toward that reading; (3) a `coincident`/`disjoint` case repeated with the `checked:` line
  present, confirming no regression. Residual, expected, and addressed by real `--help` text rather
  than format changes: a single *positive* `distance` example can't by itself prove the field is
  signed (correctly flagged as uncertain, not guessed wrong), and the sign's reference face (first-
  named) was inferred correctly but flagged as assumed rather than confirmed.

## Out of scope / deferred

- **`brush measure alignment` implementation.** Fully designed and reviewed in this spec (see above),
  but **v1 build scope is `relation` only** (owner call) — `alignment` ships in a later phase. One
  open point to resolve before that phase's plan is written, raised in review: its reference-plane
  selection is underspecified for a selector list that mixes bare brush names with face selectors, and
  for a `:all`-expanded first selector (which expands to *several* faces, not one plane).
- **Volumetric containment** (fully/partially-inside-the-solid, not just in-plane footprint) needs
  real solid-vs-solid intersection — a materially harder problem than plane-fitting. This codebase's
  existing volumetric CSG (`brush intersect`/`brush deintersect`) is documented convex-only, the same
  limitation already known to bite `level photo --native` on concave brushes. Worth a separate,
  explicitly-scoped spec later; not blocking this one.
- **`--json` for `relation`.** Ship the human-readable report only for v1; add structured output if a
  real scripting need shows up.
- **An independent-reviewer workflow** — a fresh agent, not the builder, critiquing a render against
  a defect checklist — is the right lever for defects that aren't objectively computable (e.g.
  "wrong proportions"). Separate follow-up; log to the board inbox rather than fold in here.
- **A level-wide layout/adjacency verb** (top-down, folder-colored, room-connectivity graph) — a
  different, macro-scale comprehension problem raised early in brainstorming, not the one this spec
  fixes. Log to the board inbox.
