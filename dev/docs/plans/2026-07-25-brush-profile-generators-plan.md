# Plan — `brush build extrude` + `brush build revolve` + the builder-angle units retrofit

**Status:** PLAN. Ephemeral per-feature scratch. **Date:** 2026-07-25.
**Cold-review gate: PASSED (2026-07-25, two reviewers, all findings folded).** The gate caught a
shipped-geometry error (the revolve near-cap hint, §0c), a `TypeError` that would have made B2
unbuildable (§0d), an import cycle, three incomplete test inventories, a gate that breaks an existing
green test, and a documentation-timing violation. Details in `decisions.md` 2026-07-25 02:30 UTC.
**Spec (own gate passed, commit `fe5bdbbdf`):**
[`../specs/2026-07-25-brush-profile-generators.md`](../specs/2026-07-25-brush-profile-generators.md).
**Decisions:** `decisions.md` 2026-07-25 00:14 UTC (D1–D9), 01:05 UTC (D10), 01:40 UTC (spec review),
02:30 UTC (this plan's review + D11/D12 below).
**Board item:** [`to-build.md`](../board/to-build.md) — moved there from `to-plan.md` when this plan
passed its gate (that move is **step B0**, not an assumption).

Section references like `spec §4.5` point into the spec; this plan does not restate it.

---

## 0. Corrections this plan makes to the spec

Found while pinning line-level detail and during this plan's own review. All four are folded back
into the spec so the two documents never disagree; **D11/D12 are recorded in `decisions.md`** so the
rationale survives both documents' deletion.

**0a (D11) — the units retrofit narrows the CLI surface ONLY; builder signatures are untouched.**
Spec §7 originally said `builders.spiral_staircase`'s parameter is renamed and implied
`cylinder`/`cone` lose `angle_offset`. Do **not**: four call sites pass those parameters **by
keyword** to produce goldens captured against the real editor — `builder_parity_cases.py:87`
(`cylinder(..., angle_offset=30)`), `:95` (`cone(..., angle_offset=25)`), `:100-101`
(`spiral_staircase(..., degrees_per_step=30|45)`), and `native/csg_golden.py:88`
(`cylinder(..., angle_offset=15)`). Three of those offsets are **not** half-segments, so they cannot
be expressed as `--align-to-side` at all. Renaming would force a needless editor re-bless.
`cylinder`/`cone` keep `angle_offset: float` (degrees); `spiral_staircase` keeps
`degrees_per_step: float` — accurate names for a degrees-valued internal API.

**0b (D12) — `spiral_staircase`'s range check moves to the boundary; a defensive one stays.**
`builders.py:373-375` raises `"spiral staircase needs 0 < degrees_per_step < 180, got …"`. Post-
retrofit that names a deleted flag in units the user never typed. The **user-facing** check moves to
dispatch in UU (`0 < angle_per_step < 32768`, naming `--angle-per-step` and the UU value); the builder
keeps its guard as an **internal-API** error naming the *parameter* in degrees, so the four direct
callers above still get a clear message. Because the CLI can no longer reach it, **B6's gate calls
`builders.spiral_staircase(..., degrees_per_step=200)` directly** — otherwise the retained guard is a
second thing to keep true with nothing enforcing it.

**0c — the revolve NEAR-cap outward hint does not rotate.** Spec §5.7 originally gave it as "the
profile-plane tangent at `θ=0`, not `−w`", spelled `−v̂ × t̂(0)`. Wrong twice: the tangent at `θ=0`
**is** `+ŵ`, and that cross product evaluates to `−û`. Under §4.2's sweep map the `θ=0` cap lies in
the `(û,v̂)` plane with the solid growing toward `+ŵ`, so its outward is **`−ŵ`, identical to
extrude's**. Only the **far** cap rotates (`+ŵ` rotated by `angle`; `−û` at 90°) and the side quads
(by their segment mid-angle). Implemented as originally written, `_face` would have inverted the near
cap and `_tex_basis` would have derived texture axes from a non-face normal. Spec §5.7 is corrected.

**0d — profile coordinates are `Decimal` for validation, `float` at the builder boundary.**
`builders._newell` starts `nx = ny = nz = 0.0` and would raise
`TypeError: unsupported operand type(s) for +: 'decimal.Decimal' and 'float'` on the first side quad
(cap faces survive; side quads die). Revolve is trig and cannot stay exact at all. The
Decimal-preservation rationale was moot anyway: `emit.clean`'s `_to_decimal` is `Decimal(str(value))`
(`emit.py:23-26`), so a float round-trips to the authored decimal. Spec §2.1 is corrected.

---

## 1. Sequencing

**Seven steps, seven commits** (B0 is the board move). Each lands green — the suite passes at every
step, so a bisect never lands mid-feature. **Each commit carries its own doc updates**, per
`CLAUDE.md` ("update the user-facing docs *in the same change*"); B7 is only the cross-cutting sweep.

```
B0  board move            — to-plan.md → to-build.md                        (no code)
B1  profile.py            — parsing + cleanup + validation, CONVEX ONLY     (no CLI, no brush)
B2  extrude               — geometry, winding, anchor, CLI verb, cap loop   (the shared spine)
B3  cap tiling            — the ear-clip/merge decomposition + concave tests
B4  revolve               — segments, ROTATED far-cap/side hints, closed turn
B5  advisories            — off-grid-solid + poly budget
B6  units retrofit        — spiral flag rename + cylinder/cone bool         (alone)
B7  cross-cutting docs    — kb, architecture, README lists, board
```

**B1 first** — pure, offline, no `Brush`/T3D dependency; the algorithms are far cheaper to get right
against plain tuples. **B2 before B3**: B1 ships `convex_pieces` as *convex-passthrough only*
(raising `ProfileError` for a concave or >16-vertex profile), so B2 genuinely proves the convex
winding path before tiling can mask a bug; B3 then swaps in the real decomposition behind the same
signature. *(This resolves a contradiction both reviewers caught: the original B1 gate demanded the
full Hertel–Mehlhorn algorithm, which left B3 an empty commit and made §1's own rationale vacuous.)*
**B4 after B3** — revolve caps reuse the tiling, and B2/B3 settle the `(u,v)→world` helper B4 rotates.
**B6 last and alone** — a units change that breaks three existing verbs must not hide inside a
feature commit.

---

## 2. B0 — move the board item

Move the `brush build extrude`/`revolve` line from `dev/docs/board/to-plan.md` to
`dev/docs/board/to-build.md`, restating it in `to-build.md`'s format (a `## N.` heading with
**Status / Plan / Spec / Decision** links, matching the existing entries). One home per item
(`board/README.md`) — delete it from `to-plan.md` in the same commit.

---

## 3. B1 — `uedctl/profile.py` (new)

Pure 2D; no `Brush`, no `Polygon`, no world coordinates, no T3D.

- **`WELD = 1e-3` lives HERE**, and `builders.py` imports it from `profile` (keeping its own name
  bound for `_dedup_ring`). It must **not** go the other way: `builders.WELD` is defined at
  `builders.py:40`, *below* its import block, so `profile` importing it while `builders` imports
  `profile` is a genuine cycle that fails at load — breaking every `uedctl` invocation, not just the
  new verbs. Where `builders` needs `profile` at call time, follow the pattern already used at
  `builders.py:256` (`from .surface import encode_flags`) and `:458` — a **function-local import**.
- `class ProfileError(geometry.GeometryError)` — subclassing is what buys the clean exit: `dispatch()`
  catches `GeometryError` (`dispatch.py:3080`) and has **no bare `ValueError` arm**, so a plain
  `ValueError` subclass would traceback and fail B2's own "exit 2, no traceback" gate.
- `parse_point(token) -> tuple[Decimal, Decimal]` — exactly two comma-separated numeric fields.
  Raises `ProfileError` naming the token. **Called from dispatch, NOT as an argparse `type=`**:
  argparse catches `ValueError` and replaces the message with
  `argument --point: invalid parse_point value: '128'`, destroying the wording spec §2.1 mandates.
  (`cli.parse_coord:84-98` sidesteps this by raising `ArgumentTypeError`; we need the message
  verbatim, so dispatch owns it.)
- `clean_profile(points)` — spec §5 steps 1–3: weld consecutive + wrap-around near-duplicates at
  `WELD`, drop collinear vertices, require ≥3 distinct after both.
- `check_simple(points)` — spec §5 step 4: reject any non-adjacent edge pair that intersects **at
  all** (crossing, touching at an endpoint, collinear overlap) **and** any vertex value repeated
  anywhere in the ring, naming the offending indices.
- `normalize_winding(points)` — spec §5 step 5: signed area; exactly zero → `ProfileError`; negative
  → reverse.
- `convex_pieces(points) -> list[list]` — **B1 ships the fast path only**: a convex ring of ≤16
  vertices returns `[points]`; anything else raises `ProfileError("concave/oversized profiles land in
  B3")`. B3 replaces the body.

**Gate B1** (new `uedctl/tests/test_profile.py`, offline):
- `parse_point` rejects `128`, `1,2,3`, `a,b`, each with the token in the message.
- `clean_profile` welds a repeated final point, drops a collinear midpoint, rejects a 2-distinct ring.
- `check_simple` rejects a bowtie (crossing), a **pinch** (non-adjacent edges sharing an endpoint), a
  collinear-overlapping pair, and `A B C A D E` (repeat, non-consecutive) — the last is what a
  consecutive-only weld plus a strict crossing test both miss.
- `normalize_winding` returns CCW for both input orders; rejects a zero-area ring.
- `convex_pieces`: a square → exactly `[points]`; an L and a 17-gon → `ProfileError` (B3 flips these).
- `ProfileError` is an instance of `geometry.GeometryError` (pins the exit-2 route).

---

## 4. B2 — extrude

**`uedctl/builders.py`** — add after `sheet`, before the staircases:

- `_uv_axes(axis) -> (u_world, v_world, w_world)` — spec §2.2's right-handed cyclic table; the single
  place the mapping is written.
- `extrude(points, depth, axis, texture=None, flags=0) -> Brush` — **converts `points` to `float` on
  entry** (§0d). Near cap outward `−w`, far cap `+w`, side quad of edge `k` outward `(dv, −du)` mapped
  through `_uv_axes`. Caps loop over `profile.convex_pieces(...)` from the start — one `Polygon` per
  piece — so B3 needs no structural change. `ItemName`s: `Cap`, `Side<k>`.

**`uedctl/cli.py`** — `bextrude = bshape.add_parser("extrude", …)` inside the `bshape` block
(`cli.py:846-910`): `--point` (`action="append"`, `metavar="U,V"`, **no `type=`**), `--depth`
(`type=float`, required), then `_common_build_opts(bextrude)`. Every flag needs a real `help=` —
`test_help_completeness.py` walks the live argparse tree and rejects a `help=` that is missing,
echoes the flag name, or is under 10 characters.

**`uedctl/dispatch.py`** — `_build_brushes` (`:42`) gains an `extrude` branch. **The profile pipeline
runs here, in this order**, each failure raising `_SelectionExit` naming the offending value:
`parse_point` per token → arity ≥3 → `clean_profile` → `check_simple` → `normalize_winding` → arity
re-check → `--depth > 0`. Update `_build_brushes`'s own docstring (`:43-47`), which enumerates each
shape's return shape.

**Do NOT touch:** `emit.emit_actor_t3d`, `make_brush_actor`, `_apply_generator_rotate` (`:2105`),
`_apply_generator_org`, `_validate_ingest_actors` (`:2751`). The generator tail already handles
naming, `--prop`, `--rotate`, folder/label carriers and class/texture validation for any shape.

**Docs in this commit:** `usage.md` extrude entry; the `--at` help rewrite naming all three exceptions
(`cli.py:794` — including the **currently missing** spiral one, spec §2.3); the `--rotate`-pivot note.

**Gate B2:**
- **Cube oracle** — a square profile extruded along each of `x`/`y`/`z` vs `builders.cube(...)`,
  compared as vertex sets **after translating the extrude by `−depth/2` along `--axis`** (cube is
  origin-centred, `builders.py:182-185`; extrude sweeps `0..depth`, so the raw sets can never match).
  Pin the dimension mapping per axis too — for `--axis y`, `u→Z` and `v→X`, so the oracle is
  `cube(width=v_extent, breadth=depth, height=u_extent)`, which is easy to get backwards.
- **Anchoring** — profile `(0,0)` lands on `--at` for all three axes (spec §2.3's worked bbox).
- **Winding-agnostic** — `points` vs `list(reversed(points))` emit byte-identical T3D. State the
  limit: only *exact reversal* is invariant; a CW spelling starting elsewhere normalizes to a cyclic
  rotation, which renumbers every `Side<k>`. `Side<k>` numbering is user-visible and frozen by B4's
  golden, so this is a documented property, not an accident.
- **`doctor` clean** — zero `degenerate` (which carries `category="convex"`) and `watertight`
  findings for a box profile.
- **Rejections, exit 2 + no traceback** — malformed `--point` (three forms), 0/1/2 points,
  `--depth 0`, `--depth -5`, a bowtie, a pinch.

---

## 5. B3 — cap tiling

Replace `profile.convex_pieces`'s body with ear-clip + Hertel–Mehlhorn merge across diagonals while
each piece stays convex, capping every piece at 16 vertices. `builders.extrude` already loops over
the result (B2), so **no builder change is needed** — B3 is `profile.py` plus tests.

**Gate B3:**
- Convex ≤16-vertex profile → still exactly `[points]` → 2 cap faces total (guards the simple case
  against a tiling regression).
- A concave L and a 17-gon → >1 piece, every piece convex and ≤16 verts, union of vertex sets ==
  input, and every piece boundary edge is an original edge **or a diagonal** (the no-T-junction
  property, spec §6).
- The same two profiles through `brush build extrude`: `doctor` reports zero `convex` and zero
  `watertight` findings; face count is `n + (2 × pieces)`.
- The B1 gate's two `ProfileError` cases flip to success.

---

## 6. B4 — revolve

**`builders.revolve(points, angle_deg, segments, axis, …) -> Brush`.** Build in the `(u,v,w)` sweep
frame — where the revolve is a rotation about `v̂` — then map to world once via `_uv_axes`. (The
existing `_rotate_z` is Z-specific; do not force it into service.) Floats throughout (§0d).

**The outward hints are the load-bearing part** (spec §5.7, corrected per §0c) — `_face` FLIPS a ring
that disagrees with its hint (`builders.py:129-130`):

| Face | Outward |
|-----------------------------|---|
| near cap (`θ=0`)            | `−w` — **unrotated, same as extrude** |
| far cap (`θ=angle`)         | `+w` rotated about `v̂` by `angle` (`−û` at 90°) |
| side quad, edge `k`, seg `m`| `(dv, −du)` mapped to world, rotated by the segment **mid**-angle `θ_m + Δ/2` |

> **SUPERSEDED 2026-07-26.** This formula is NOT the quad's true normal — de-rotated that is
> proportional to `(dv, −du·cos(Δ/2))`, so the two agree only for an axis-parallel profile
> edge. It shipped, and the error landed in the TEXTURE BASIS (the editor preserves
> `TextureU`/`TextureV`), not in the winding. `builders.revolve` now computes each quad's own
> Newell normal. See the correction in spec §5.7.

`ItemName`: `Side<k>` keyed to the **profile edge**, identical across segments (spec §4.4); caps
`Cap`. Closed turn (`angle == 65536`): omit both caps, weld the last ring to the first.

**`cli.py`:** `--angle` (`type=int`, required), `--segments` (`type=int`, default `None` → computed),
`_common_build_opts`; real `help=` on both (`test_help_completeness.py`).
**`dispatch.py`:** the same profile pipeline as B2, then — in this order — `--angle` in `(0, 65536]`
on the **raw int**; `--segments` default `max(1, floor(angle/4096 + 0.5))` (spelled `floor(x+0.5)`,
**not** `round()`, which is banker's rounding); `--segments >= 1`; `angle/segments < 32768`;
`segments >= 3` when `angle == 65536`; every profile `u > 0`. Then `degrees = angle * 360.0 / 65536.0`
— **never** via `rotation.uu_field`/`uu_to_deg`, which wrap mod 65536 and would turn a full turn into
zero (spec §7).

**Docs in this commit:** `usage.md` revolve entry, the Item-labels bullet (`Cap`/`Side<k>`), the
off-grid-solid and `--native` concave caveats.

**Gate B4:**
- **`doctor` clean at `--angle 16384`, `32768`, `65536`** — zero `watertight` findings. Write this
  gate **first** and confirm it goes **red** when fed the unrotated far-cap/side hints; note the full
  turn omits both caps, so the *cap* hints are only exercised by the two partial sweeps.
- **Full turn is not degenerate** — `--angle 65536` emits a closed solid, no caps, non-zero volume
  (proves the conversion did not wrap to 0).
- **Segment default** — `--angle 16384` → 4; `--angle 65536` → 16.
- **Face count / naming** — `n × s` sides + caps; `Side<k>` appears exactly `s` times for each `k`.
- **Rejections, exit 2** — `--angle 0`, `65537`, `--segments 0`, `--angle 32768 --segments 1`,
  `--angle 65536 --segments 2`, profiles straddling / touching / wholly negative-`u`.
- **Goldens** — one extrude + one revolve snippet in `uedctl/tests/fixtures/`, compared as exact
  text, landing **now** that `ItemName`s are final.

---

## 7. B5 — the two stderr advisories

In the `brush build` dispatch branch (`:3198`), placed **after `_apply_generator_rotate`
(`:3263`)** so rotation-induced off-grid geometry is included (that helper emits its own
rotation-specific warning; both may print, and the plan accepts that — they report different causes).

- **Off-grid-solid** (spec §4.5) — fires only when **`shape in {"extrude", "revolve"}`** *and* any
  emitted vertex is off the integer grid *and* `mover_class is None` *and* the actor is solid
  (`poly_flags == 0`). Reuse `dispatch._offgrid_flags` (`:2071`), not a second implementation.
  - The **shape gate is mandatory, not tidiness**: without it this turns
    `test_generators.py:281-286` red — that test builds a solid 8-gon cylinder (radius 48 → vertices
    at ±33.94…, inherently off-grid) and asserts stderr is **empty**. Spec §4.5 deliberately leaves
    `cylinder`/`cone` alone and files them as a board item.
  - The **mover clause is mandatory too**: a mover rejects `--solidity`, so it lands on
    `SOLIDITY_FLAGS["solid"] == 0` (`dispatch.py:3222`) and would trip a BSP advisory although a mover
    never partitions the world.
- **Poly budget** (spec §4.6) — total emitted faces > 64.

Both to **stderr**; stdout stays a clean T3D snippet; exit status unchanged.

**Gate B5:** a solid off-grid revolve prints the advisory; a semisolid one does not; a **mover**
revolve does not; a **cylinder** does not (`test_generators.py:281-286` stays green); a >64-face
revolve prints the budget advisory; in every case stdout parses as valid T3D and the exit code is 0.

---

## 8. B6 — the units retrofit (alone)

Per §0a, `builders.py` signatures are untouched and **no golden moves**.

| File | Line | Change |
|---------------|-------|---|
| `cli.py`      | `:862`| `bcyl --angle-offset` → `--align-to-side` (`store_true`); help = the flush-face explanation + the `AlignToSide` mapping |
| `cli.py`      | `:871`| `bcone --angle-offset` → same |
| `cli.py`      | `:909`| `bspiral --degrees-per-step` → `--angle-per-step`, `type=int`, default `8192`, help in UU |
| `dispatch.py` | `:42` | cylinder/cone pass `angle_offset = 180.0/sides if args.align_to_side else 0.0`; spiral converts `angle_per_step * 360.0/65536.0` |
| `dispatch.py` | `:42` | spiral range check `0 < angle_per_step < 32768` UU **before** conversion, naming `--angle-per-step` |
| `builders.py` | `:373`| keep the guard; reword to name the *parameter* in degrees, citing the `decisions.md` D12 entry |

**Test migration — the complete inventory** (CLI-level references; the four direct-builder call sites
of §0a stay **unchanged**):

| File | Line | Change |
|---------------------|-----------|---|
| `test_cli.py`       | `:268`    | argv `--degrees-per-step 24` → `--angle-per-step 4096`. **Missing this breaks the test before its assertion** — `parse_args` raises `SystemExit` |
| `test_cli.py`       | `:271`    | `ns.degrees_per_step == 24.0` → `ns.angle_per_step == 4096` |
| `test_cli.py`       | `:254`    | `ns.angle_offset == 0.0` → `ns.align_to_side is False` |
| `test_generators.py`| `:139-147`| **a rewrite, not a rename**: `@parametrize("bad_degrees", [200.0, -30.0])` → UU (`40000`, `-8192`); the kwarg becomes `angle_per_step`; the assertion becomes `"--angle-per-step" in err`; **the test name and its docstring both become wrong** (the guard now fires at the boundary, §0b) — rename to `…_bad_angle_per_step_…` and rewrite the comment |
| `test_generators.py`| other hits| the remaining `degrees_per_step`/`angle_offset` CLI-level uses → the new spellings |

**Docs in this commit:** `usage.md:493-494,:497`; `brush-shapes.md:28,:36,:66,:70`;
`recipes/shapes/octagonal-column.md:30`.

**Gate B6:**
- `--align-to-side` on an 8-gon reproduces the old `--angle-offset 22.5` geometry byte-for-byte; on a
  6-gon it offsets 30°, not a hardcoded 22.5°; absent, the cross-section is unchanged.
- `--angle-per-step 8192` reproduces the old `--degrees-per-step 45` geometry.
- Out-of-range `--angle-per-step` errors naming **that** flag and the **UU** value.
- **The retained builder guard is exercised directly**: `builders.spiral_staircase(...,
  degrees_per_step=200)` raises, message naming the parameter (§0b).
- `--angle-offset` / `--degrees-per-step` no longer parse.
- **`bin/test` fully green, including the offline `test_builder_parity.py`** — the proof §0a held.

---

## 9. B7 — the cross-cutting doc sweep

Per-commit docs are handled above; B7 is what spans them. **Seven six-shape lists exist** — the spec
listed four:

| File | Line(s) | Change |
|---------------------------------------------|-----------|---|
| `uedctl/builders.py`                        | `:1-2`    | module docstring's six-shape list |
| `dev/docs/README.md`                        | `:90`     | six-shape list (moved here from `docs/README.md` in the 2026-07-25 user/dev doc split) |
| `dev/docs/architecture.md`                  | `:89`     | six-shape list + the new `profile.py` module |
| `docs/leveldesign/general/README.md`        | `:18`     | six-shape list |
| `dev/docs/unrealed/leveldesign/kb/csg-bsp.md`| `:25,:328`| six-shape lists |
| `dev/docs/unrealed/leveldesign/kb/geometry-builders.md` | `:7`, §1, §4, §7 | intro list; Revolve now HAS a verb; `AlignToSide` maps 1:1 |
| `dev/docs/specs/2026-07-24-corpus-brush-idioms.md` | `:99` | its generator vocabulary (an ephemeral spec, but it is the *input* to the reverse-mapping work — update it) |
| `dev/docs/specs/2026-07-19-leveldesign-docs-skills.md` | `:59` | same |
| `dev/docs/architecture.md`                  | `:1535-1544` | the staircase native-CSG caveat. **Nuance:** native `materialize` defaults to `core="bspcsg"` (`native/materialize.py:383,:785`), which never calls `point_in_convex` — but the coarse core still does. Reword to "the `--native` preview" (there is no `--core` CLI flag), not a blanket deletion |
| `uedctl/builders.py`                        | `:305-309`| the same stale claim in the `staircase` docstring |
| `docs/leveldesign/general/recipes/README.md`| `:21`     | the inline shape-recipe list |
| `docs/leveldesign/general/recipes/shapes/README.md` | index + `:25`, `:34` | add the four new recipes; **and correct two claims the change falsifies** — "`cylinder --sides N` (the only way to get anything round)" and "'Round' is either a low-side cylinder, or a ring of straight blocks copy-rotated": `revolve` is now a third and more natural way |
| `docs/leveldesign/general/recipes/shapes/`  | new       | L-ledge, arch voussoir, curved corridor (**with `--solidity semisolid`**), moulded cornice — the last must **cross-reference or supersede** the existing `ring-cornice.md`, which solves the same problem by copy-rotation, not sit silently beside it |
| `dev/docs/direction.md`                     | —         | check only: its "Generator pattern" section has **no shape list** (`:260` merely names `brush build spiral` as an example of multi-actor output). Reconcile only if the new verbs change the net target — they do not |

**Board:** delete the item from `to-build.md`; file the three spec §11 verify-live items in
`inbox.md` (cap merge-back, the full-turn torus — the "one builder brush" question is CLOSED,
`kb/geometry-builders.md` §4); short tail to `done.md`.

---

## 10. Risks, and what this plan does not do

- **The ear-clip is the only real algorithm.** If Hertel–Mehlhorn merging proves fiddly, shipping
  plain ear-clip triangles is valid — every B3 gate still passes (more faces, same correctness). Do
  not let it block B4.
- **The rotated outward hints are the likeliest bug** and are invisible without the B4 gate written
  first and seen to fail.
- **The new builders get no editor-blessed oracle.** All six existing shapes are pinned by
  `builder_parity_cases.py` against real-editor captures; this plan adds no case there (adding one
  needs the gated integration run), so B4's goldens pin **drift, not correctness**. A parity case is
  a follow-up, not a build step.
- **The two remaining spec §11 verifications need a live editor** and are follow-up board items.
- **`level doctor` gains no new check** — its per-face convexity and watertight tests already cover
  what these verbs emit.
- **No `--taper`, no path sweep, no axis-touching revolve, no `cylinder --sides` cap fix** — spec §8
  and the `inbox.md` items filed 2026-07-25.
