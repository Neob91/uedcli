# `brush relation` — a family for cross-brush geometric relationships

## Motivation

`brush measure relation` (built 2026-08-29,
`dev/docs/superpowers/specs/2026-08-29-brush-measure-design.md`) reports the exact plane/footprint/
delta relationship between every poly pair across N named brushes. Two gaps in practice:

- No way to **search**: "which of these brushes sit within 8uu of this wall" requires eyeballing a
  full N-ary report and manually scanning for the pair that matches, rather than getting a filtered
  selector list back.
- No way to **act**: once you know two faces should sit at a specific gap, or share a centroid,
  there's no verb that moves a brush there — only the manual arithmetic of computing a `--by` delta
  for `actor prop set Location` by hand.

This spec adds `brush relation find` (search/filter, producer) and `brush relation set` (move a
brush into a target relationship), and promotes the existing verb to `brush relation measure`
(same job, new home, restricted to exactly 2 poly selectors instead of N brush names). All three sit
on the same `uedcli/relation.py` math (`plane_relationship`, `project_to_plane`,
`classify_footprint_2d`, `compute_deltas`).

## What we want

### Family shape

`brush relation` becomes a new top-level verb group, peer of `brush poly`/`brush vertex`, with three
sub-verbs: `measure`, `find`, `set`. `brush measure relation` is renamed to `brush relation measure`
— an outright rename, not an alias (uedcli is unreleased; no back-compat cruft). The `brush measure`
subtree currently has exactly one sub-verb (`relation`); once it moves, `brush measure` has none and
is removed from the parser entirely. (`brush measure alignment`,
sketched in the 2026-08-29 spec, is still deferred and unbuilt; where it eventually lands — back
under a re-added `brush measure`, or folded into `brush relation` too — is that spec's call to make
when it's actually built, not this one's.)

Why `set` can't live under `measure`: `uedcli/cli/commands/brush/measure.py`'s own docstring states
the contract — "pure geometric measurement sub-verbs (no mutation, no verdicts)". `set` mutates
(moves a brush). Promoting the whole family to `brush relation` keeps `measure`'s no-mutation
contract intact and gives `find`/`set` a natural home next to it.

### `brush relation measure REF_SELECTOR TARGET_SELECTOR [--top N|all] [--allow-self]`

Same report as today's `brush measure relation`, restricted from N bare brush names (all-pairs) to
**exactly 2 selectors**:

- A selector is a bare `Name` (all of that brush's polys) or `Name:SELECTOR` (`SELECTOR` = `all` or
  comma-separated poly indices) — the same token grammar `brush poly align`'s targets already use:
  `Name:SELECTOR` splits via `parse_poly_selector`/`resolve_polys` in `uedcli/surface.py`, and a bare
  `Name` resolves to `all` in `uedcli/polyalign.py`'s `resolve_align_targets` (which collection
  measures/`find` reuse as-is rather than re-deriving).
- The two selectors must resolve to 2 **distinct** brush names by default (self-comparison rejected —
  the existing "naming the same brush twice" guard, generalized from bare names to selectors, still
  catches the common case: a typo or copy-paste left the same name on both sides). **`--allow-self`**
  (opt-in, default off) lifts this, permitting both selectors to name the same brush — e.g. `brush
  relation measure Wall:3 Wall:5 --allow-self` checks whether two faces of the SAME brush are
  flush/parallel. Even with `--allow-self`, the exact same `(brush, poly)` pair on both sides is
  always skipped (a poly compared to itself is never a meaningful relation — not something this flag
  is meant to unlock).
- The poly×poly candidate search happens only over the two selectors' resolved index sets — `brush
  relation measure Wall Floor` still ranks every poly of `Wall` against every poly of `Floor` (today's
  behavior, unchanged when both sides are bare names); `brush relation measure Wall:5 Floor:4` pins
  the search to exactly that one pair, skipping the ranking entirely. **Mixed shapes are legal**:
  `brush relation measure Wall Floor:4` ranks every poly of `Wall` against exactly `Floor`'s poly 4 —
  each side's index set is resolved independently, so any combination of bare/pinned is well-defined,
  not just the two illustrated extremes.
- Report format and `--top` are otherwise unchanged from today's verb; `format_report`'s `disjoint`
  line was already a single `disjoint: {A, B, C}` line for any N (`relation.py`'s `format_report`),
  so this doesn't change shape at 2 selectors — with only one pair possible, the count is 0 (the pair
  related) or 2 (it didn't, so both names show — never exactly 1, since there's no third brush either
  could relate to instead).
- **Drops `-` (stdin) support.** Today's verb reads a newline-separated brush-name list from stdin for
  its N-ary `names` argument; the new grammar is exactly 2 fixed positional selectors, so there's no
  variable-length list left to read from stdin. Deliberate, not an oversight — flagged explicitly per
  "no silent half-answers."

This is a **report verb**: full detail on stdout always, never a producer, modeled — per the
2026-08-29 spec — on `level status`/`project show`, not `actor find`. It exists for the case where
you already know the two faces you care about and want the numbers, not a search. It stays even
though `find` (below) covers a similar query, because the two verbs have different, non-overlapping
output contracts (see "Why keep both `measure` and `find`" below) — not because of a functional gap
`find` can't reach.

### `brush relation find <candidates...> --relative-to REF[:idx] [predicates] [--top N|all] [--json] [--allow-self]`

A **producer**: prints matching faces as pipeable selectors, mirroring `brush poly find`.

- `candidates`: zero or more bare brush Names, or the single token `-` to read a newline name list
  from stdin (`uedcli/cli/targets.py`'s `resolve_target_names` — unchanged; `-` is the sole source,
  not mixable with names; empty stdin is a clean no-op, exit 0). **Omitting `candidates` entirely**
  (no names, no `-`) defaults the candidate set to every OTHER brush actor in the level (every actor
  with `actor.brush is not None`, excluding REF's own canonical name — the same self-exclusion
  `--overlapping ACTOR` already uses in the spatial-find spec). This default is the handler's job,
  applied before `resolve_target_names` is ever consulted (the function is only invoked when a token
  including `-` was actually given — see Design decisions); `resolve_target_names` itself doesn't
  change. A non-brush actor named explicitly is warned and skipped, matching `poly find`'s existing
  rule for its own `names`. Naming REF's own brush explicitly among `candidates` is a clean exit 2 by
  default, same guard as `measure`.
  **`--allow-self`** (opt-in, default off) lifts both restrictions: REF's own brush is included in the
  default level-wide candidate set, and may be named explicitly — e.g. `brush relation find Wall
  --relative-to Wall:0 --allow-self` finds other faces of `Wall` itself related to face 0. As with
  `measure`, the reference poly index itself is always excluded from its own results regardless of
  this flag (comparing a poly to itself is never a meaningful match).
- `--relative-to REF[:idx]` is **required**. Bare `REF` ranks against every poly of REF (the
  best-matching REF poly per candidate wins, same ranking `measure`/today's `relation.compute` use);
  `REF:idx` pins to exactly one reference poly. Single index only — no comma-list here (a search
  reference is one anchor, not a set to further rank within).
- Predicates, all optional, AND together:
  - `--max-gap N` / `--min-gap N` (float, ≥ 0; `--min-gap` > `--max-gap` when both given is a clean
    exit 2) — bound `abs(plane.distance)`.
  - `--footprint LIST` — comma-separated from `none`, `vertex`, `edge`, `partial`, `contains`,
    `coincident` (`contains` matches either internal direction, `contains_a_in_b` or
    `contains_b_in_a` — direction is bookkeeping, not something a candidate search needs to
    distinguish). Omit = no filter.
  - `--plane {coplanar,parallel}` — omit = either.
  - A poly pair whose normals aren't parallel/anti-parallel has no `plane.distance`/`footprint_2d` at
    all (today's `compute()` already drops such pairs before this point) — so predicates are
    implicitly scoped to plane-related pairs; there's no separate flag needed to express that.
  - **REF is always `actor_a`** in the underlying `plane_relationship`/`compute_deltas` calls, for
    every candidate — the same convention `set`'s precondition uses. This keeps `distance` sign and
    the U/V deltas REF-relative and directly comparable across every shown match, and consistent with
    what a downstream `relation set - --relative-to REF:idx` expects.
- Output:
  - **stdout**: bare `candidate:idx` lines, one per shown (candidate, poly) pair, best pair first per
    candidate (`relation.py`'s existing `_candidate_sort_key`). `--top N` (default 1) / `--top all`
    controls how many pairs are shown per candidate. This is the pipeable contract — feeds `brush
    relation set -`, `brush poly align -`, `brush poly move -`, etc. No match anywhere → exit 0, no
    output (matches `actor find`: no match is not an error).
  - **stderr**: one human-readable relation summary line per shown match (plane/gap/footprint) — the
    "Producer/query verbs print their result to stdout … human summaries … go to stderr" rule
    (`CLAUDE.md`).
  - **`--json`**: stdout instead emits a JSON array of full structured relation objects (plane,
    normals, distance, footprint_2d, deltas) per shown match. Unlike `poly find --json` (which keeps
    its human summary line on stderr regardless), this **suppresses the stderr summary**: the array
    on stdout is exact data, so a summary line beside it is redundant — a deliberate divergence from
    `poly find`'s JSON behavior, not a shared convention.

### Why keep both `measure` and `find`

Real overlap exists in the narrow case of one known candidate with no predicates
(`brush relation find Target --relative-to Ref:5 --top all --json` gets close to `brush relation
measure Ref:5 Target:idx`). Keeping both anyway:

- `measure`'s contract is fixed: full report on stdout, always, never conditional on how many
  selectors or candidates you passed. `find`'s contract is equally fixed the other way: terse,
  pipeable stdout, always; detail is secondary. Merging them means one verb's stdout shape would vary
  by argument count/flags — the same "behavior by shape" smell the no-branching rules reject.
- `measure` exists specifically for the case the original 2026-08-29 spec was built to fix (a
  known pair, wants the full report, not a search) — dropping it pushes that case through `find`'s
  search/predicate machinery (`--relative-to`, `--json`) it doesn't actually need.

### `brush relation set TARGET:idx --relative-to REF:idx [--gap N] [--centroid-u N | --edge-u-min N | --edge-u-max N] [--centroid-v N | --edge-v-min N | --edge-v-max N]`

Moves `TARGET` into a target relationship with the fixed `REF`.

- `TARGET:idx` is an **exact** `Name:idx` — a single poly index, not a bare name (= all) or a
  comma-list. A translation target can't be ambiguous. `--relative-to REF:idx` is **required** and is
  likewise an exact `Name:idx`. `TARGET` and `REF` must resolve to distinct brush names.
- `TARGET` is the sole positional (the thing acted on, matching `brush poly move <targets> --by`'s
  "the thing you're operating on comes first" convention); `REF` arrives as a flag, the same
  `--relative-to REF:idx` anchor `find` uses, so one anchor spelling serves both the search and the
  move. REF never moves. REF stays the reference for direction/sign regardless — same convention
  `plane_relationship(actor_a, poly_a, actor_b, poly_b)` already uses internally (distance signed
  along `normal_a`); the call passes REF as `actor_a`. `measure` keeps its opposite surface order
  deliberately: its first selector is the reference (a query verb, ordered by "which one anchors the
  report"), whereas `set` puts the thing that moves first. Not an inconsistency to reconcile — the
  two verbs order by different, equally-established conventions.
- **stdin:** `TARGET` may instead be the single token `-`, reading a newline list of `TARGET:idx`
  selectors from stdin — the same name-list convention as `poly align -`/`poly move -`. The list is
  the sole source of targets (not mixable with a positional `TARGET`); `--relative-to REF:idx` stays
  on the command line; empty stdin is a clean no-op (exit 0). This is what closes the pipe:
  `brush relation find <cands> --relative-to REF:idx … | brush relation set - --relative-to REF:idx --gap N`
  moves every found face into the specified relationship with the same REF.
- **Precondition:** `plane_relationship(REF_actor, REF_poly, TARGET_actor, TARGET_poly)` must not be
  `None` (normals must be parallel or anti-parallel within the plane-parallel tolerance
  `_PARALLEL_EPS` — see "Required precursor" under Module shape) — otherwise there's no defined normal
  direction or in-plane U/V frame to move along, and the verb exits 2 naming both selectors and
  explaining why. In practice this pair usually comes straight from `brush relation find`'s output
  (which only ever emits plane-related pairs) or a prior `brush relation measure`.
- Every flag takes an **explicit target distance**, not a boolean "align it": omitting a flag leaves
  that degree of freedom untouched (TARGET doesn't move on that axis at all).
  - `--gap N` — sets `plane_relationship(...).distance` (signed, along REF's normal) to exactly `N`.
    Negative allowed (TARGET on the opposite side of REF's outward normal). `--gap 0` = flush/coplanar.
  - `--centroid-u N` / `--centroid-v N` — sets `compute_deltas(...).centroid_u`/`centroid_v` (the
    footprint centroid offset, in REF's own U/V frame) to exactly `N` on that axis. `0` = centroids
    aligned on that axis.
  - `--edge-u-min N` / `--edge-u-max N` — sets the offset between TARGET's U-min (or U-max) extent
    and REF's corresponding extent to exactly `N`. Unlike `compute_deltas`'s reporting behavior (which
    auto-picks whichever of min/max is currently closer), `set` needs BOTH extents computed, not just
    the closer one, so the caller can pick either explicitly — a small addition alongside
    `compute_deltas`, not a new algorithm. `--edge-v-min N` / `--edge-v-max N` analogously on V.
  - `--centroid-u` and `--edge-u-{min,max}` are mutually exclusive (same U degree of freedom); same
    for `--centroid-v`/`--edge-v-{min,max}` on V. `--gap` is independent of both (a different, normal
    axis) and combines freely with either or both in-plane picks.
  - There are **three true degrees of freedom** — the normal (`--gap`), U, and V — each independently
    optional. U is set via exactly one of three mutually exclusive flags (`--centroid-u`,
    `--edge-u-min`, `--edge-u-max`); V analogously (`--centroid-v`/`--edge-v-min`/`--edge-v-max`);
    seven flags total. At least one flag (of the seven) is required — argparse can't express ">=1
    across these groups" as a single mutually-exclusive group, so the handler validates and exits 2
    with a clear message if none are given (a no-op call is a usage error, not a silent no-op, per
    "no silent half-answers").
- **Mechanism:** translates `TARGET`'s actor **Location only** — the brush keeps its shape, `REF`
  never moves. Because this is a rigid whole-actor translation (not a per-vertex edit like `brush poly
  move`), it can never push a face non-planar and needs no planarity guard; it CAN cause the brush to
  interpenetrate other geometry, which is expected (the same way `brush scale`/`actor prop set
  Location` don't second-guess where you place something).
  - Compute REF's world unit normal and its `(U, V)` world-space basis vectors (`relation.py`'s
    `_plane_basis`, already used internally by `project_to_plane` — exposed for this reuse) once.
  - `delta_n = (requested_gap − current_gap)` along the normal, if `--gap` given, else 0.
  - `delta_u = (requested_u_target − current_u_value)` along the U basis vector, from whichever of
    `--centroid-u`/`--edge-u-min`/`--edge-u-max` was given, else 0. `delta_v` analogously.
  - Translate `TARGET`'s Location by `delta_n·normal + delta_u·U + delta_v·V` (converting the in-plane
    deltas from the 2-D UV frame back to a world-space vector via the same basis).
- **Output:** prints the touched brush name (`TARGET`'s canonical Name) to stdout, plus a stderr
  confirmation line with the resulting gap/deltas after the move (reusing `relation.py`'s `_fmt`),
  mirroring `poly align run`'s worst-seam-shear stderr note. The brush name, not a `Name:idx`
  selector, because what moved is the whole brush: `set` translates the actor, whereas `poly
  move`/`poly align` print per-face selectors precisely because a bare brush name on a per-face pipe
  would silently widen the set (`_print_poly_selectors`'s docstring in `poly.py` states this). That concern has no analog
  here — `set` moves whole brushes, so the brush name is the exact statement of what changed.
  (Owner decision.)

## Design decisions and why

- **Renaming `brush measure relation` is a breaking change, deliberately.** uedcli is unreleased —
  the "no back-compat cruft" rule applies; there's no deprecated alias, no dual spelling.
- **`find`'s candidate default (every other brush in the level) doesn't clash with the existing
  empty-stdin-is-a-no-op invariant.** They're different states: omitting the positional entirely
  (argparse sees zero tokens, no `-`) means "no explicit selection, default to everything"; passing
  `-` with genuinely empty stdin means "an explicit empty candidate list," which stays a clean no-op.
  The handler distinguishes them before calling `resolve_target_names` (which is only invoked when a
  token — including `-` — was actually given); `resolve_target_names` itself doesn't change.
  Extending this default-to-everything behavior to the *existing* `brush poly find` (`names` becomes
  optional there too, same default) is in scope for this change per the owner's explicit request
  during design — `poly find`'s tests/docs need updating alongside `relation find`'s.
- **`measure`/`find` gate self-comparison behind `--allow-self` rather than allowing or forbidding it
  outright.** The distinct-brush requirement was inherited from the old N-ary verb's dedup guard (a
  convenience against naming the same brush twice by mistake), not a deliberate rule against
  comparing two faces of one brush — a legitimate query the underlying math already handles (owner
  decision during design: allow it, but opt-in, so the mistake-guard stays the default). `set` has no
  such flag: it structurally requires 2 distinct brushes, since translating one rigid body can't
  independently reposition two of its own faces.
- **`set` requires exact `Name:idx` selectors, not `measure`'s richer bare-name/comma-list grammar.**
  A move target must be unambiguous; letting `set` accept "all polys" or several indices would need a
  rule for which one actually drives the translation math, which is exactly the ranking-and-picking
  job `find`/`measure` already do upstream. `set` assumes that work is done and takes the answer.
- **`set`'s REF arrives as the `--relative-to REF:idx` flag rather than a second positional.** This
  reverses the design phase's explicit pick of two positionals (`TARGET:idx REF:idx`) — flagged in
  review as a real gap (a two-positional grammar can't compose with `-`: stdin is `set`'s sole source
  of targets and can't mix with other names on the command line, so a piped target list left no
  channel for REF) and confirmed by the owner afterward, not decided in the original design pass.
  Moving REF onto the same flag `find` already defines keeps one anchor spelling across the pair and
  makes `find`'s stdout a complete, pipeable `set` invocation.
- **`--gap`/`--centroid-*`/`--edge-*` are independent, explicit-value flags rather than a single
  "align" mode.** A user might want to fix only the gap and leave in-plane position alone (or vice
  versa), or fix only one in-plane axis — the original ask ("gap, delta from centroid, or any poly
  side") already implied several independent choices, not one mode switch.

## Module shape / touchpoints (implementation-stage detail, not prescriptive)

- **Required precursor:** `uedcli/polyalign.py` no longer defines `_PARALLEL_EPS`/`_PLANE_EPS`
  (deleted by the poly-align rewrite in commit 252c4ad), yet `uedcli/relation.py:41,48` still
  dereference them, so `relation.compute()`/`plane_relationship` are currently red on master
  (`AttributeError: module 'uedcli.polyalign' has no attribute '_PARALLEL_EPS'`; verified 2026-09-05:
  12 of 27 tests in `test_relation.py` fail on this). Restoring the two tolerance constants is step
  zero of any build — the existing relation suite going green is the gate before any new verb lands.
- `uedcli/relation.py`: keep `plane_relationship`/`project_to_plane`/`classify_footprint_2d`/
  `compute_deltas`/`_candidate_sort_key` as-is; expose `_plane_basis`'s world U/V vectors for `set`'s
  translation math; add a small "both extents, not just the closer one" variant alongside
  `compute_deltas` for `set`'s `--edge-*` flags; add the 2-selector `measure` entry point, the
  candidate-ranking `find` entry point, and the translation-computing `set` entry point.
- `uedcli/cli/parsers/brush.py`: remove the `measure`/`measuresub` subtree; add a `relation` subtree
  with `measure`/`find`/`set` subparsers, argument definitions as specced above.
- `uedcli/cli/commands/brush/measure.py`: removed; replaced by `uedcli/cli/commands/brush/relation.py`
  dispatching the three sub-verbs.
- `uedcli/cli/parsers/brush.py`'s existing poly-`find` `names` argument: `nargs="+"` → `nargs="*"`,
  same "omitted → every brush in the level" default as `relation find`'s candidates.

## Test strategy (host-native `bin/test`, per `dev/docs/rules/tests.md`)

1. `measure`: 2-selector restriction (a 3rd name/selector is a clean exit 2); `Name:idx` pins the
   search to exactly that pair, skipping ranking; mixed bare/pinned selectors; self-comparison
   rejected by default, permitted under `--allow-self`, with the identical-`(brush,poly)` pair still
   always skipped even then; report/`--top`/disjoint-message unchanged from today's behavior
   otherwise.
2. `find`: omitted candidates → every other brush, REF self-excluded; naming REF explicitly among
   candidates rejected by default, permitted under `--allow-self`; `-` with empty stdin → clean
   no-op; each predicate (`--max-gap`/`--min-gap`/`--footprint`/`--plane`) in isolation and ANDed
   together; a non-parallel pair never matches any predicate; `--top`/`--top all` per candidate;
   stdout selector format; stderr summary present by default, suppressed under `--json`; `--json`
   structure matches `relation.py`'s dataclasses and is REF-relative (REF as `actor_a`) for every
   match.
3. `set`: precondition failure (non-parallel pair) → exit 2 naming both selectors; missing
   `--relative-to` → exit 2; each flag in isolation moves exactly the expected axis, others
   untouched; `--centroid-u`/`--edge-u-*` mutual exclusion (and the V equivalent) enforced by
   argparse; zero flags given → exit 2; `-` with empty stdin → clean no-op, piped `TARGET:idx` list
   moves each in turn; the move is a pure Location translation (poly-relative vertex positions inside
   TARGET's own frame unchanged); REF's Location never changes; touched-brush stdout + stderr
   confirmation format.
4. `brush poly find`'s new optional-candidates default: a regression test alongside the existing
   suite in `tests/test_...` for that verb.

Test files: extend `uedcli/tests/test_relation.py` (the `relation.py` core), rename/extend
`uedcli/tests/test_cli_brush_measure_relation.py` → `test_cli_brush_relation_measure.py`, add
`test_cli_brush_relation_find.py` and `test_cli_brush_relation_set.py`.

## Docs to update on build

- `docs/reference/brush/measure.md` → replaced by `docs/reference/brush/relation.md` covering all
  three sub-verbs (per `dev/docs/rules/documentation.md`'s "keep the matching reference page current
  with the CLI, same change" rule).
- `docs/reference/brush/README.md`'s index table: the `brush measure relation` row (line 14) → the
  moved `brush relation measure` under `relation.md`.
- `docs/leveldesign/general/recipes/shapes/mitered-corner.md` (line 63): the prose example that uses
  `brush measure relation` → the new spelling.
- `docs/reference/brush/poly.md`: the `poly find` `names`-now-optional behavior change.
- Any "See also" cross-links to the old `measure.md` path (`docs/reference/brush/poly.md`'s current
  one, at minimum).

## Out of scope / deferred

- **`brush measure alignment`** (bbox/centroid/offset-from-a-reference-plane query, no mutation) —
  still deferred per the 2026-08-29 spec; unaffected by this change beyond losing its originally
  intended `brush measure` home, which its own future spec will need to re-settle.
- **`--json` for `measure`** — out of scope here, same as the original spec's v1 call; `find` gets
  `--json` because its predicate-driven search is exactly the scripting use case that was the
  original spec's stated bar for adding it.
- **Rotating `TARGET` to make normals parallel in the first place** — `set` only translates; a pair
  that isn't already plane-related (per the precondition) needs a separate rotation step first (not
  designed here — no request for it in this round).
