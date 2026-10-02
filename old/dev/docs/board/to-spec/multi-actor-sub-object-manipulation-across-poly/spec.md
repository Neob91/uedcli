# Spec — multi-actor sub-object manipulation across `poly`/`vertex`/`clip`

DRAFT. Surfaces the owner decision(s); do not build past an unanswered question.

## Goal

Make the sub-object verbs (`poly`, `vertex`, `clip`) consistently operate over a SET of brush actors,
fed by the `find → mutate -` pipe, so no sub-object edit is stuck single-brush.

## Current state

- `brush poly set/pan/rotate/scale/align` — **already multi-actor**, via the `BRUSH:SELECTOR`
  positional grammar + `-` stdin (`cli/parsers/brush.py:416-435,442-541`; `surface.resolve_targets`,
  `surface.py:108-134`). Nothing to do here.
- `brush vertex move` — **single-brush**: one positional `name` + repeatable `--at` world coords
  (`cli/parsers/brush.py:388-397`; `cli/commands/brush/vertex.py:59-90`).
- `brush clip` — **single-brush**: one positional `name` + a plane (`cli/parsers/brush.py:63-74`;
  `cli/commands/brush/edit.py:356-399`).
- `brush scale` / `brush apply-transform` — **already multi-actor**, via a NAME LIST +`-` stdin
  through `targets.resolve_target_names` (`cli/commands/brush/edit.py:193-353`). This is the existing
  precedent for a whole-brush set verb.

## Design — the reframing (read the question first)

The board overview proposes making `BRUSH:SELECTOR` (e.g. `Wall1:3,5 Wall2:all`) "the consistent
pattern" for `vertex` and `clip` too, and generalizing its parser into a shared helper. Investigation
says that is the wrong unification:

- `BRUSH:SELECTOR` is a per-**face** grammar — the `:SELECTOR` is a poly-index list. `poly` has poly
  indices; **`vertex` selects corners by coordinate and `clip` selects nothing sub-object** (it cuts a
  whole brush by a plane). Neither has an index list to put after the colon, so `BRUSH:SELECTOR` does
  not fit them.
- The unification that already exists and fits is the **name-list stdin set**
  (`targets.resolve_target_names`, the `find → mutate -` convention) that `brush scale`/
  `apply-transform` use. "A verb over a set takes the set" (conventions.md).

So the recommended shape:

- **`brush clip`** — take a name SET: `names… | -` instead of one `name`. Apply the SAME world plane
  to every brush in the set; the per-brush "plane missed → left unchanged" message already exists
  (`edit.py:384-389`) and stays a per-brush no-op, not an error. Resolve via
  `targets.resolve_target_names` → `query.resolve_actor_names`, dedupe (like `_scale`).
- **`brush vertex move`** — take a name SET the same way, applying the shared `--at`/`--by` world
  coords to each named brush. `--at`/`--to`/`--by` are already world-space, so they carry across
  brushes unchanged.
- **`poly`** — unchanged (already multi-actor via `BRUSH:SELECTOR`).
- **No new "generalized selector parser."** The shared helper the board asks for is
  `targets.resolve_target_names`, already shared. `BRUSH:SELECTOR` stays poly-specific in
  `surface.parse_poly_selector`.

Recommended help changes:

    clip:   name → names  ("brush actor Names to clip, or - to read a name list from stdin;
            the same world plane is applied to each")
    vertex move: name → names  (same wording; --at/--by apply to every named brush)

### How the set-input applies across actors — the vertex edge case

`clip` is clean: a world plane either cuts a brush or misses it (per-brush no-op message). No policy
call.

`vertex move` needs one: `--at X,Y,Z` is a world corner, and a named brush may have **no corner
there**. Single-brush today raises `ValueError` → exit 2. Across a curated set the choice is:

- Option A (recommended): all-or-nothing — any named brush lacking a corner at an `--at` → exit 2
  naming it (no silent half-answer, per conventions). The user curated the set, so a miss is an
  error worth surfacing. Adjacent brushes that genuinely share a welded world corner all move it.
- Option B: skip a brush that lacks the corner (best-effort). Rejected by the no-silent-half-answer
  rule, but see the question — float-exact shared corners are rare, which is a real ergonomic pull
  toward B or a tolerance.

## Edge cases & errors

- `clip` over a set: empty stdin `-` → no-op exit 0; unknown name → exit 2 (`resolve_actor_names`);
  non-brush in the set → exit 2 naming it (existing per-actor check, applied to each); plane misses a
  brush → per-brush stderr note, that brush unchanged, exit 0 overall.
- `vertex move` over a set: empty stdin → no-op; unknown/duplicate names → `resolve_actor_names`
  dedupe + exit 2; non-brush → exit 2; missing corner → per the question's policy; degenerate result
  on any brush → `GeometryError` exit 2 (all-or-nothing — resolve/validate before writing any brush,
  matching `_scale`).
- Command-log `record_mutation`/`save(touched=…)` carries the full brush set (like `_scale`).

## Tests

- `test_clip.py` / `test_cli.py`: `actor find --kind brush | brush clip - --axis z --offset 0` clips
  every matching brush; a brush the plane misses is reported and left intact; unknown name → exit 2.
- `test_cli.py`: `brush vertex move -` over a two-brush set applies `--by` to both; a brush missing an
  `--at` corner follows the chosen policy; non-brush → exit 2.
- Refresh `tests/fixtures/parser_baseline/*` — `clip`/`vertex move` positionals change name → set.

## Open questions

See `questions/unify-on-name-set-not-brush-selector.md` and `questions/vertex-move-missing-corner-policy.md`.
