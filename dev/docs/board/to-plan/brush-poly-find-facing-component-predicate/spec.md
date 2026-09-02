# Spec — `brush poly find --facing` selector grammar (component predicates on the visible normal)

**Status:** revised 2026-07-24 after two cold reviews (findings resolved inline; see "Review resolutions").
Ephemeral; fold decisions into `decisions.md` and `dev/docs/unrealed/t3d.md` (the subtract-normal fact) on
land.
**Decisions:** `decisions.md` 2026-07-24 16:27 UTC (grammar) + 16:28 UTC (`poly find` set input).

## Problem

`brush poly find --facing` today (`polyalign.find_faces`, `query._poly_facing`) takes ONE geometric axis
token: `+X | -X | +Y | -Y | +Z | -Z | slant`. It snaps a face's **geometric outward normal** (Newell,
`_face_normal`) to the nearest world axis. Three defects:

1. **World-frame-dependent, so unreadable.** Which compass direction `+X` is depends on the individual
   map — nothing tells you `+X` is the north wall vs the east wall.
2. **Zero flexibility.** Exactly 6 axes + `slant`; a face at 45° is `slant` with no way to target it.
3. **Polarity-blind — a latent correctness bug.** `_poly_facing` never consults `CsgOper`. Rooms are
   almost always `CSG_Subtract` brushes, whose playable surfaces face **opposite** the geometric outward
   normal. So on a subtract room, `--facing +Z` returns the **ceiling** and `--facing -Z` the **floor** —
   inverted. "Give me the floors" silently returns ceilings. (Confirmed by both reviews against
   `tests/fixtures/brush_subtract.t3d`.)

## Design — component predicates on the *visible* unit normal

Replace the single axis token with a small predicate grammar over the face's **visible normal**
components `(nx, ny, nz)` (definition below). Presets name common orientations; raw predicates give full
versatility.

### Grammar

Delimiter *discipline* analogous to the batched pose grammar (`preview_shots.parse_shot`: split on the
top-level separator, then key:value), **extended with `..` for ranges** and **without `@`**; not a literal
reuse (see Review resolution R-O):

```
--facing 'TERM[;TERM…]'                 # a SINGLE param; ';' = AND across terms
    TERM  = PRESET | AXIS:SPEC
    PRESET ∈ flat | wall | ramp | floor | ceiling
    AXIS  ∈ nx | ny | nz                 # components of the visible unit normal, each ∈ [-1, 1]
    SPEC  = v | lo..hi | v[,v…]          # ',' = OR value/range list on that ONE axis; '..' = range
```

Parse: split on `;` into terms; a colon-less term is a **preset** (looked up, expanded to its predicate —
error if unknown); a `AXIS:SPEC` term splits once on `:`; `SPEC` splits on `,` into alternatives, each a
scalar or a `lo..hi` range. `,` only ever splits a SPEC; `..` only ever a range. A leading `-` in a value
(`nz:-1`, `nz:-0.95..-0.05`) is unambiguous — `-` is not a delimiter, and `"-0.95..-0.05".split("..")`
→ `["-0.95","-0.05"]` since intra-number dots are single (verified by both reviews).

- **`;` = AND** across terms. `'wall;ny:0.7..1'` = vertical **and** north-ish.
- **`,` = OR** value/range list within one axis. `'nz:-1,1'` = flat.
- **`:` = axis:spec.** No `=`: `nz:0..0.5` reads "nz *in* 0..0.5"; `=` would read "*equals* the range."
- A bare **`v`** (`nz:0`) means "**near** v within a component tolerance ε" (see ε below); a **`lo..hi`**
  range is an **inclusive** band.

**Parser rules (each raises `ValueError` → clean exit 2, naming the offending token; each gets a test):**
- unknown axis (`nq:0`), unknown preset (`floot`), malformed spec (`nz:`, `nz:a`, `nz:1..`, `nz:1..2..3`)
- empty term — a trailing `;` or `nz:0;;nx:1` — is an error (unlike a valid empty *result*)
- **duplicate axis** (`nz:0;nz:1`) is allowed and simply ANDs (may yield an empty result — that's fine)
- whitespace around terms/axes/values is stripped

A syntactically valid spec that can match nothing (`'wall;nz:1'` = `nz≈0 ∧ nz≈1`) is **not** an error — it
is a legal query that returns 0 faces, exit 0 (find legitimately matches nothing). Only a *parse* failure
is exit 2. (Review R-K.)

### Presets

Named by **surface-plane orientation** (polarity-INVARIANT — see Review R-A) with **half-open** bands so
they exactly partition (no boundary overlap; Review R-G). Cutoffs are stated as an **angle** off
horizontal/vertical for uniform angular meaning, then given as the equivalent `|nz|` component cut:

| Preset | Angle def | `|nz|` cut (half-open) | Meaning |
|--------|-----------|------------------------|--------|
| `wall` | within `θ_w` of horizontal | `|nz| < sin θ_w`      | vertical surface (axis-aligned AND diagonal) |
| `ramp` | between                    | `sin θ_w ≤ |nz| < cos θ_f` | sloped surface |
| `flat` | within `θ_f` of vertical   | `|nz| ≥ cos θ_f`      | horizontal surface — floor **or** ceiling |

`flat`/`wall`/`ramp` are the default convenience because they carry **no** floor/ceiling confusion and are
**polarity-symmetric** (invariant under full sign flip — see below).

Two **polarity-AWARE refinements** (they distinguish the up/down *role*, so they depend on the visible-normal
sign):

| Preset | Predicate | Meaning |
|--------|-----------|--------|
| `floor`   | `nz ≥ cos θ_f`   | the up-facing playable surface (walkable) |
| `ceiling` | `nz ≤ -cos θ_f`  | the down-facing playable surface (overhead) |

`θ_w`, `θ_f`: default **5°** each (pin during build; tunable constants, not user flags in v1).

### Versatility

The visible normal is a point on the unit sphere; a query carves a region:
- **Any single direction**: tight predicate, `'nx:1'` or `'nx:0.7;ny:0.7;nz:0'`.
- **Any band**: a range, `'nz:-0.5..0.5'`.
- **Azimuth ∩ elevation in ONE param** via `;`-AND: `'nz:0;ny:0.7..1'` = north wall band.
- **OR on one axis** via `,`: `'nz:-1,1'` = flat.
- **OR across different axes** (rare) → two `find`s concatenated.

Azimuth is only ever named by an explicit `nx`/`ny` predicate (opt-in). Deliberate: **pitch has a canonical
zero (gravity → vertical); yaw does not** — so `nz` (elevation) drives the presets frame-free, while
`nx`/`ny` (azimuth) are the world-frame escape hatch.

### Visible normal (definition, transform, polarity)

```
visible_normal(actor, poly):
    n_local = outward unit normal of the poly in the brush's LOCAL frame,
              from the winding (CCW-from-outside, t3d.md:145 ✅) via Newell
    n_world = normalize( inverse_transpose(actor_linear(actor)) · n_local )   # correct for
              # rotation, non-uniform scale, shear, AND reflection (Review R-B/R-C)
    return n_world · (−1 if csg_is_subtract(actor) else +1)                   # polarity (Review R-A)
```

- **Transform (Review R-B/R-C).** The correct world normal is the **inverse-transpose** of the actor's
  linear map applied to the *local* outward normal — NOT Newell recomputed on world verts (wrong direction
  under non-uniform scale) and NOT the vertex matrix. Inverse-transpose maps the outward normal correctly
  even under a **negative-scale reflection** (the target fixture carries `SheerAxis=SHEER_ZX`, so shear is
  in-scope). When `actor_linear` is identity (the common unrotated/unscaled builder brush) this is just
  `n_local` — no matrix math. This **unifies** `list_polys` and `find_faces`, which today compute facing
  from *different* transforms (`list_polys` full scale via `actor_linear`; `find_faces` rotation-only via
  `actor_matrix`); both switch to `visible_normal`, and the tests asserting each old behavior migrate
  (below).
- **Polarity (Review R-A/R-I).** `csg_is_subtract(actor)` = `_csg_oper(actor).casefold() == "csg_subtract"`
  — **case-insensitive on the value** (`_csg_oper` matches the key case-insensitively but returns the raw
  value; an imported map may spell it `csg_subtract`). `CSG_Add`, `CSG_Intersect`, `CSG_Deintersect`, and
  any non-CSG actor → **no flip** (documented v1 limitation: intersect/deintersect visible-sense is not
  modeled). A base Mover / point actor has no brush and never reaches here.

**Polarity symmetry — corrected (Review R-A).** The flip negates **all three** components, so a predicate
is flip-INDEPENDENT only if it is invariant under full negation: `wall` (`nz:0`), `flat` (`nz:-1,1`), and
symmetric bands (`nz:-0.5..0.5`). **Every *asymmetric* predicate is flip-DEPENDENT** — `nx:1`, `nz:0.5`,
`floor`/`ceiling`, and az predicates like `ny:0.7..1` select the *opposite* physical face on a subtract
brush. So the correctness of the flip gates **all asymmetric queries**, not just `floor`/`ceiling` (my
earlier "only floor/ceiling" claim was wrong).

**The flip is verified — pin it before shipping.** Both cold reviews independently computed the top face of
`tests/fixtures/brush_subtract.t3d`: Newell `nz` sum `> 0` → outward `+Z` (matches stored `Normal +Z`),
vertices at `Z=+192` = room ceiling, so `visible = −Z = ceiling = nz:-1`; the bottom face → `floor = nz:1`.
The evidence is in-tree today. So the flip is treated as **established**, and the deliverable is the
**committed engine-facts regression** that re-asserts it against the fixture (per the Spikes rule),
back-referencing this spec + `t3d.md`. `flat`/`wall`/`ramp` and symmetric predicates hold even if that
regression ever breaks; only the asymmetric/role behavior depends on it.

### Output of the `facing` column / field (Review R-E, resolves old Open Q2)

- **`brush poly list` text table** (`format_polys`, `query.py:74`): the `facing` column reports the
  **polarity-free orientation** `flat` / `wall` / `ramp` (≤6 chars, fits; always defined; no flip
  dependency in the always-on output). Column stays `<6`.
- **`--json`** (both `list` and `find`): replace the single `"facing"` string with `"normal": [nx,ny,nz]`
  (the visible unit normal, rounded to 4 dp), `"orientation": "flat"|"wall"|"ramp"`, and `"role":
  "floor"|"ceiling"|null` (the flip-dependent role). Scripts get the exact vector; humans get the label.

## `brush poly find` — accept a brush SET (`nargs`/`-`), warn-not-error on non-brushes

Per the "verbs over a set" CLI philosophy, mirroring `poly set` exactly:

- **Positionals become `nargs="+"`** (NOT `"*"` — Review R-H: `"*"` would make a forgotten brush arg a
  silent no-op; `"+"` matches `poly set` and argparse-errors on a bare invocation). `find WALL TOWER ROOF`
  searches every named brush.
- **`-` reads the set from stdin** (bare names, or the `BRUSH:idx` lines a prior `find` prints — the
  handler strips `:idx` to the brush component), the **sole** names source, mutually exclusive with other
  positionals (if `-` is present it must be the only token); **empty stdin = clean no-op, exit 0**.
- **Dedup + order (Review R-L):** the resolved brush set is **deduped preserving first-seen order**
  (`find WALL WALL` must not double-emit); output is `BRUSH:idx` lines ordered by input-brush then poly idx.
- **Non-brush inputs WARN, don't error** (Andrzej): an actor with no `.brush` prints a stderr warning
  naming it (`skipping non-brush actor: <name>`) and is skipped; the command still succeeds for the
  brushes. `find_faces` keeps raising `PolyAlignError` on a non-brush (its contract is unchanged); the
  **dispatch handler** catches/skips-with-warning rather than propagating (so `test_find_faces_non_brush_raises`
  stays valid; a new dispatch-level test covers the warn path).
- **Unknown** name → hard error exit 2 (a typo must not pass silently).
- `--json` shape is unchanged by the warn path (skipped actors simply contribute no rows).

## Code changes

- `query`: new `visible_normal(actor, poly) -> (nx,ny,nz)` (local Newell → inverse-transpose(actor_linear)
  → normalize → CSG flip) and `csg_is_subtract(actor) -> bool` (casefolded). New `facing_spec.py`:
  `FacingSpec` + `parse_facing_spec(text)` (the grammar above, presets pre-expanded) + `match_facing(normal,
  spec) -> bool` + `orientation(normal) -> "flat"|"wall"|"ramp"` + `role(normal) -> "floor"|"ceiling"|None`.
  Remove `query._poly_facing` and its `polyalign` import.
- `polyalign.find_faces`: `facing: str` → `facing: FacingSpec | None`; filter = `match_facing(visible_normal(
  actor, poly), spec)`. Keep `item`/`texture` AND filters.
- `dispatch` `poly find` handler (`dispatch.py:3468`): drop the `valid_facing` set check (parser validates);
  parse the spec; `name` → set input (`nargs="+"` + `-`/stdin, dedup, warn-skip non-brush, hard-error
  unknown); iterate matches across the deduped brush set.
- `query.list_polys`/`format_polys`: facing column → `orientation(visible_normal(...))`; `--json` fields per
  above.
- `cli.py` `pfind` (`cli.py:981` — corrected from the earlier `903` miscite): `name` → `nargs="+"` + `-`;
  rewrite `--facing` help to the new grammar with examples. **Remove the now-dead `_FACING_NEG` regex and
  its `_CoordArgumentParser` leading-dash handling** (`cli.py:29,55`) — only the old `-X/-Y/-Z` tokens
  needed it; the new grammar's negatives live inside a quoted value, never as a bare argparse token.

## Tests to migrate / add (Review R-D/R-M — this is a PLAN, not an open question)

**Migrate (break on this change):**
- `test_query.py:262-265, 325-330, 338-339` — assert facing column/keys `+X…`; retarget to
  `flat`/`wall`/`ramp` and the new `--json` normal/orientation/role fields.
  `test_list_polys_applies_actor_rotation_to_facing_and_centroid` → assert the rotated *orientation*.
- `test_polyalign.py:67-145` — call sites passing `facing="+Y"/"+Z"` incidentally: pass a `FacingSpec`
  (e.g. `parse_facing_spec("ny:1")`) or select by `item`/index instead.
- `test_polyalign.py:308-312` — direct `polyalign._poly_facing(...)` call: retarget to `visible_normal`.
- `test_polyalign.py:351/362` — `args.name="…"` singular → a list (`nargs="+"`).
- `test_cli.py:60-68` `test_parser_facing_accepts_leading_dash_space_form` — deleted (the `-X/-Y/-Z` tokens
  and `_FACING_NEG` are gone); replace with a test that the new grammar's `--facing 'nz:-1,1'` parses.

**Add (per CLAUDE.md "cover each error path with a regression"):**
- parser: unknown axis, unknown preset, malformed spec, empty/trailing-`;` term, duplicate-axis-ANDs,
  each `ValueError` → exit 2 naming the token.
- preset expansion (each preset → expected predicate/faces on a known brush).
- `match_facing` / `orientation` / `role` unit tests, incl. a **rotated** brush and a **negatively-scaled /
  sheared** brush (the inverse-transpose path).
- the **subtract-flip engine-facts regression** against `tests/fixtures/brush_subtract.t3d` (floor=`nz:1`,
  ceiling=`nz:-1`), back-referencing this spec.
- dispatch set-input: multi-brush search, `-`/stdin, empty-stdin no-op, **warn-and-skip** non-brush (still
  exit 0), unknown-name hard error (exit 2), duplicate-brush dedup.

## Docs to update on land

- `docs/usage.md` — `brush poly find`/`list` reference: new `--facing` grammar, presets, set input, warn,
  the `--json` normal/orientation/role fields.
- `docs/leveldesign/` — retexture-by-orientation workflow (floor/wall/ceiling) via presets.
- `dev/docs/unrealed/t3d.md` — the verified subtract-normal-flip fact (✅ marker + fixture/test ref).
- `decisions.md` — the two entries (correct the symmetry framing + the `cli.py:981` citation).
- `board/` — cross off the facing item; the flip regression is a `[chore]` folded into the build.

## Review resolutions (index)

R-A symmetry claim corrected (all asymmetric predicates flip-dependent; flip verified, pin it). R-B/R-C
visible_normal uses inverse-transpose(actor_linear), unifying the two callers; handles scale/shear/reflect.
R-D/R-M full test migration + added error/engine-fact tests enumerated. R-E output column = orientation
(text) + normal/orientation/role (json). R-F ε stated honestly as a *component* tolerance with non-uniform
angular meaning; presets defined by *angle* (θ_w/θ_f) for uniform meaning. R-G half-open preset bands (no
overlap). R-H `nargs="+"` not `"*"`. R-I `_csg_oper` value casefolded; intersect/deintersect = no-flip
(documented). R-J/R-O parse discipline "analogous," not literal reuse; colon-less=preset, dup-axis=AND,
empty-term=error enumerated. R-K valid-but-empty result = exit 0 (only parse errors exit 2). R-L dedup +
ordering of multi-brush output. R-N `cli.py:903` → `cli.py:981` fixed here and in both decision entries.
