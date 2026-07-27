# Spec: `poly align` — continuous texture alignment across faces (build item 11)

**Status:** DECIDED + BUILT (2026-07-18). The three open decisions below are **resolved** — see
`dev/docs/decisions.md` 2026-07-18 21:40 UTC ("`poly align` v1 scope + face-selection grammar").
Implemented in `uedcli/polyalign.py` (`brush poly find` + `brush poly align`); durable knowledge
folded into `architecture.md` ("Surface texture alignment") + `unrealed/t3d.md` (the UV convention).
This ephemeral spec may be deleted once that fold is confirmed stable.

**Board item:** `dev/docs/board/to-build/` item 11 (origin: `board/to-spec/` "Texture-alignment solver",
AI brainstorm 2026-07-16 endorsed + extended by Andrzej 2026-07-16).

**Ephemeral:** this spec is scratch for designing item 11. Once built, its durable knowledge folds
into `dev/docs/architecture.md` (the surface/texture model) and `dev/docs/unrealed/t3d.md` (the UV
convention), and the load-bearing choices are recorded in `dev/docs/decisions.md` — this file may
then be deleted. **The decisions below are recorded in `decisions.md` once Andrzej answers**
(a new dated entry; this spec links to it — durable docs point at the decision, never at this spec).

---

## What `poly align` is

`poly align` makes one texture **flow continuously** across a *set* of faces instead of restarting
the pattern at every brush edge. It is pure offline texture-vector math — it computes and writes each
selected poly's `TextureU` / `TextureV` / `Pan` so the mapped texture is seamless across the seams
between faces. No editor is touched (model-side, like `brush poly set`). It reproduces the effect of
UnrealEd's `TEXTURE ALIGN` / `poly texalign` family (`dev/docs/unrealed/commands.md:115` —
`TEXALIGN FLOOR|WALLDIR|WALLX|WALLY|ONETILE|CLAMP`, and the 2D UI's "align to surface" wrapping),
but on the T3D trunk, not through the console.

Two headline cases from the board item:

1. **Coplanar (or run-of-) wall/floor faces** (`--wall` / `--floor`): adjacent faces sharing a plane
   (or a wall run) get one shared texture frame so brickwork does not reset at each brush boundary.
2. **Cylinder facet-ring wrap:** the N side faces of a `brush build cylinder` get their U coordinate
   advanced facet-by-facet around the ring so the texture meets seamlessly all the way around.

---

## The UV convention uedcli uses (load-bearing — this is the formula we implement against)

**Evidence (uedcli's own code, not memory):**

- `uedcli-native/src/render.rs:159-165` — the software rasterizer computes per-vertex texel UV as:
  ```
  dp = Vertex − uv_base
  tu = dp · TextureU + PanU
  tv = dp · TextureV + PanV
  ```
  where `uv_base` is the poly's **world-space `Origin`** (`render.rs:21` "world point where (u,v) =
  (pan_u, pan_v)").
- `uedcli/preview_native.py:192-220` (`_world_uv_frame`) builds that frame from the authored fields:
  `uv_base = Location + R·(Origin − PrePivot)`, `axes = R·(TextureU, TextureV)`, `pan = poly.pan`.
- `uedcli-native/src/light.rs:337-352` — the lightmap bake independently confirms the frame is
  **base-relative** (`(vert − Base)·TextureU/V`). **Caveat (reviewer-flagged):** `light.rs`'s `base`
  is the *BSP surf base point* `s.p_base` (a build product), and the `Pan = min(vert−Base)·Tex −
  0.125` relation it verifies is the **lightmap-grid** pan (`axis_grid`, `light.rs:369-370`), a
  *different* quantity from the surface **texture `Pan`** that `poly align` writes. So `light.rs` is
  cited ONLY as corroboration that "UV is base-relative"; it is **not** evidence that the texture base
  is the authored `Origin`, nor evidence for the texture Pan. The authoritative evidence for
  `poly align`'s convention is `render.rs:159-165` (uses the authored `Origin` as `uv_base`, adds the
  surface `Pan`) plus the paste round-trip that preserves `Origin`/`TextureU`/`TextureV`
  (`t3d.md:169-177`, `emit.py`).

So uedcli's canonical UV per vertex is:

> **U = (Vertex − Origin) · TextureU + PanU**   (and V analogously)

**Note on the handoff's `/ TextureU²` form.** The classic Unreal-source formula
`U = (V − Base)·TextureU / |TextureU|² · UScale + PanU` is the *same mapping* under a different split:
there TextureU is a **unit** axis and `UScale` is separate. uedcli folds the scale into the
**magnitude** of `TextureU` — a unit `TextureU` (as `builders._tex_basis` emits, `builders.py:98-107`)
gives **1 texel per world unit**; halving the texture density means halving `|TextureU|`. There is no
separate scale field on the poly. So our implementation uses the no-division form above (matching
`render.rs`), and "texel scale" always means **`1 / |TextureU|` world-units-per-texel**.

**Consequences for alignment math:**
- Alignment is defined in **WORLD space.** Two coplanar faces are seamlessly aligned when they share
  one **world-space** texture frame — same world `uv_base`, world `TextureU`/`TextureV`, and `Pan` —
  so a point on the shared seam maps to the same (U,V) from either face. Sharing the world frame is a
  *sufficient* condition (not the only one — see the per-face-Pan alternative below).
- **CRITICAL — the stored fields are per-brush, not shared (reviewer-flagged correctness bug).** The
  poly's stored `Origin`/`TextureU`/`TextureV` are in the *brush's local* frame; the renderer maps
  them to world via `base_w = Location + R·(Origin − PrePivot)`, `axes_w = R·axes`
  (`preview_native._world_uv_frame`, `preview_native.py:196-219`). So for faces from **different
  brushes** (different `Location`/rotation/`PrePivot`), writing *identical stored* values yields
  *different* world frames → NO continuity. The algorithm must pick ONE **world** frame and then
  **inverse-transform it through each face's own brush transform** to get that brush's stored
  `Origin`/`TextureU`/`TextureV`. "Write the same frame to every face" is correct only for faces of a
  *single* brush; across brushes it is a world-frame-then-inverse-transform. (For a same-brush set —
  e.g. all six faces of one `brush build` — the local and world frames coincide and it reduces to a
  direct copy.)
- `Pan` is **integer** texels (`model.Polygon.pan: tuple[int,int]`, `model.py:48`; parsed/emitted as
  ints). Continuous alignment across faces at *different* world positions needs the offset the seam
  demands, which is generally **fractional** — see the "Pan is integer" hazard below.

---

## Open decisions for Andrzej — DECIDED (see decisions.md 2026-07-18 21:40 UTC)

**RESOLVED.** The recommendations below were adopted, with these Andrzej divergences from the
recommended options: **Q1b** ships BOTH frame sources with the opt-out flag named **`--fresh-frame`**
(not `--synthesize`); **Q3** builds the **`brush poly find` producer** now (option C's shape, not the
`--item`-flag-on-align of option B) AND `poly align` takes positional `(brush,poly)` targets too.
Everything else matches the recommendations. The historical options/tradeoffs are kept below for the
rejected-alternatives record; the binding statement is the decisions.md entry.

### Q1 — Which alignment modes ship in v1?

UnrealEd's `TEXALIGN` menu offers Default, Face (fit-to-surface), WallPan / WallDir / WallX / WallY,
OneTile, Floor, and Cylinder-wrap. Not all map cleanly onto our offline per-poly frame.

**Two independent dimensions are in play — please answer BOTH:**

**Q1a — the geometry mode (which face-set shapes we handle):**

| Mode | What it does | Maps to our model? |
|---|---|---|
| `--wall` | one shared texture frame across a set of **strictly coplanar** vertical faces so the texture is continuous across the seam | yes — one world frame to all |
| `--floor` | same, for horizontal faces (floor/ceiling); differs only in which world axes become U/V | yes |
| `--ring` (cylinder wrap) | advance U by each side face's chord around a facet ring; V runs along the axis | yes — the curved case (Q2) |
| `--face` (fit-to-surface / OneTile) | set one face's frame so the texture fits the face exactly once (or an integer tile count) — a *single-face* convenience, not cross-face continuity | yes, but arguably out of scope (single-poly op, closer to `brush poly set`) |

- **(A) Minimal:** `--wall` + `--floor` only (planar continuity). Ship the cylinder wrap later.
- **(B) Recommended v1:** `--wall` + `--floor` + `--ring`. Covers both headline cases on the board.
- **(C) Broad:** B plus `--face` (fit-to-surface).

**RECOMMENDATION for Q1a: (B).** Both headline cases named on the board (planar run *and* cylinder
wrap) are the point of the item; planar-only would leave the curved case — the one Andrzej explicitly
added 2026-07-16 — unbuilt. Defer `--face` (C): a single-face "fit one tile" is a *different*
verb-shape (one poly, no set, no continuity), better as a `brush poly set` option or its own verb.
Sphere wrap (also mused 2026-07-16) is **out of v1** (needs per-vertex UV distortion the flat per-poly
frame can't express — follow-up TODO). **NOTE:** a *turning* "wall run" (a corridor whose walls change
direction — non-coplanar) is **NOT** a `--wall` case: `--wall` is strictly one plane (see Validation).
A turning run is a separate future mode (per-face accumulate-along-run, like `--ring` unrolled); it is
**out of v1** — capture as a TODO. This removes the coplanar-vs-turning contradiction the reviewers
caught.

**Q1b — the frame SOURCE (where the shared texture frame comes from):** this is the
reviewer-flagged most-common real need and was missing from v1. Given the set of faces, do we —

- **Synthesize** a fresh basis from the plane normal (`builders._tex_basis`, `builders.py:98`),
  discarding whatever the user already set? Simple, deterministic, but throws away existing texturing.
- **Adopt a seed face's frame** — take one already-textured/panned reference face and propagate ITS
  world frame to the rest of the set (this is what UnrealEd's "align to surface" does: continue the
  mapping you already dialled in on one wall)? This is the archetypal workflow ("I textured one wall
  exactly right; make the neighbours continue it").

Options: **(i)** synthesize only; **(ii)** adopt-seed only; **(iii)** both — default = adopt the first
face in the set as the seed, with a `--synthesize` opt-out for a fresh basis.

**RECOMMENDATION for Q1b: (iii), defaulting to adopt-seed.** Continuing an existing, deliberately-set
frame is the far more common intent and preserves the user's scale/pan/rotation choices; synthesizing
is the fallback when no face is textured yet. Adopt-seed is also strictly more powerful (a freshly
`_tex_basis`-seeded face IS a valid seed). The seed defaults to the first face in the input set (ties
Q2's seam choice and Q3's ordering together — the caller controls it by controlling input order).

### Q2 — The per-face U-advance / arc-length model for the curved (`--ring`) case

This applies to `--ring` ONLY (the coplanar `--wall`/`--floor` case has a single plane and one shared
frame — no U-advance). How does U accumulate around a cylinder ring?

**(a) Distance metric — how far U advances per face:**
- **True chord length** — advance U by each facet's own flat width, `chord = 2·r·sin(π/N)` (world
  units → texels via `|TextureU|`). Each side face is *planar*, so its texture maps flat across its
  real width; chord keeps texel density uniform on the flat facet. (`N` = `--sides`; `r` = the
  circumscribed radius at which `builders.cylinder` places vertices, `builders.py:206-207` — pin this
  as an engine-fact regression so a builder change can't silently break the ring math.)
- **Arc length** — advance U by `2πr/N` (the underlying circle's arc). Slightly over-advances vs the
  flat facet (`2πr/N > 2r·sin(π/N)`), so texels compress a hair on each face; correct only if the
  surface were truly curved (it isn't — it's faceted).

**(b) Seam / starting face:** which face is U=0, and which direction is +U? Options: the first face in
the selected set (set order = selection order); the face nearest a given world point/axis; or an
explicit `--seam <brush:poly>` anchor.

**(c) V axis (along the cylinder axis):** all side faces share one V axis (the cylinder axis, world
+Z for a default upright cylinder) and one V origin (a fixed plane, e.g. Z of the shared uv_base), so
the texture does not shift vertically face-to-face. Only U accumulates.

**(d) Non-dividing perimeter:** the texture width rarely divides the perimeter evenly, so the wrap
won't meet exactly. Options: **leave the seam** (honest — one visible seam at the closing edge, exactly
like UnrealEd); or **snap the scale** (uniformly stretch `|TextureU|` so an integer number of texture
repeats fits the perimeter, guaranteeing a seamless meet at the cost of a slightly non-square texel).

**RECOMMENDATION:**
- **(a) chord length** (facets are flat; chord = the face's real width = uniform density). Document the
  geometry.
- **(b)** default seam = the **first face in the input set**, +U advancing in input order; add an
  optional `--seam <brush:poly>` later if needed (NOT in the v1 grammar — see CLI sketch). Composes
  with Q3: the caller controls order by controlling input order.
- **(c)** shared V axis + shared V origin (above).
- **(d) leave the seam by default** (matches UnrealEd; no silent geometry-dependent scale change),
  with an opt-in `--fit-perimeter` (`--ring`-only) that snaps `|TextureU|` to the nearest
  integer-repeat count for a seamless meet. Leaving the seam is the safer default: silently rescaling
  a texture because a cylinder is an odd size is surprising; the user asks for it explicitly.

### Q3 — How the face set is selected

The `CLAUDE.md` core philosophy: *"prefer a stateless query verb that prints matching names for other
verbs to consume, over per-command filter flags,"* and *"mutating verbs read their target set from
stdin via `-`."* Two hard constraints the reviewers surfaced make this **the** load-bearing decision:

1. **`actor find` emits BARE actor names** (`Wall1\nWall2`), and the shared stdin reader
   `_resolve_target_names` (`dispatch.py`) is documented as reading *exactly `actor find`'s output* —
   a **name** list, NOT `BRUSH:SELECTOR` tokens. So the canonical composed loop
   `actor find --folder castle.tower | … -` produces bare names; a `-` that expected `Wall1:0` tokens
   would reject it. Any `-` grammar that isn't "bare brush names" fails to compose with the one
   producer that already exists.
2. **The existing sibling `brush poly set` takes `BRUSH:SELECTOR` positionals only** (`cli.py:645`,
   `surface.parse_poly_selector`) — **no `-`** — and `brush poly list` takes a *single* brush and
   prints a human table (`query.format_polys`), so there is no producer that emits pipe-ready
   `BRUSH:poly` tokens today, and a per-brush `--tokens` could only ever cover one brush.
3. **The poly selector supports only `all` or comma-separated INDICES** (`surface.resolve_polys`) —
   there is **no by-item selection.** So `--ring Tower:all` wrongly includes the cylinder's 2 Cap
   faces (`item="Cap"`, `builders.py:216-217`), which `--ring`'s "normals radial" validation rejects.
   Selecting *just the side ring* today means hand-typing the side indices.

**Options:**
- **(A) Positionals only, mirror `brush poly set` exactly** — `poly align --wall Wall1:0 Wall2:0`,
  `--ring Tower:0,1,2,3,4,5,6,7`. Zero new plumbing, perfectly consistent with its sibling. But does
  NOT compose with `actor find` and forces hand-typed selectors.
- **(B) Positionals PLUS `-` reading BARE actor names** (each = "all polys of that brush"), matching
  `actor find`'s output. Then `actor find --folder tower.walls | brush poly align --wall -` works. `-`
  and positionals mutually exclusive (the `CLAUDE.md` sole-source rule). This composes with the
  producer that exists, at the cost of coarser granularity over stdin (whole brushes, not
  hand-picked polys — but the validation + `--item`/`--facing` narrowing below recover precision).
- **(C) Build the composable primitive now** — add a real cross-brush query verb
  `brush poly find` (`--coplanar <seed>` / `--facing` / `--item side` / `--texture`) that prints
  `BRUSH:poly` tokens, and have `poly align` read them via `-`. The clean long-term shape, but a
  second feature to design/build/test inside this item.

**RECOMMENDATION: (B) for v1**, i.e. positional `BRUSH:SELECTOR` (sibling-consistent) **and** `-`
reading bare actor names, with a **`--item <name>` narrowing flag** (e.g. `--item Side`) so
`--ring Tower --item Side` drops the caps without hand-typing indices — reusing the `item` field
builders already stamp (`Side`/`Cap`/`Base`, `builders.py`). Rationale: (B) honours BOTH the "mutating
verbs read `-`" rule AND composability with the *existing* `actor find`, keeps positional parity with
`brush poly set`, and `--item` is a *query narrowing on an intrinsic face label* (not a redundant
set-flag). **Defer (C)** to a follow-up TODO: `brush poly find` is the right home for coplanar/adjacency
discovery and would let `poly align` drop `--item`, but it is its own spec — building it inside item 11
over-scopes. **Please confirm (B)**, and specifically whether `--item` is acceptable as the v1
cap-exclusion mechanism or you'd rather ship (C)'s `brush poly find` first.

> **Q3 sub-decision — verb placement.** Every existing surface verb is under `brush poly`
> (`cli.py:632`). **RECOMMENDATION: `brush poly align`** (peer of `brush poly list|set`) for grammar
> uniformity; "poly align" stays the informal name. Please confirm.

---

## Detail design (lower-stakes — defaults proposed, adjust freely)

### The alignment computation

Given a resolved set of `(brush, poly_index)` surfaces and a mode:

**`--wall` / `--floor` (coplanar continuity):**
1. Validate all selected faces are **strictly coplanar** within an epsilon (shared plane normal +
   plane offset; reuse the Newell normal in `preview._face_normal` — imported into `query.py:13`;
   `preview_native._newell` is the same math). Error naming the first offender
   (`brush poly align --wall: face Wall2:0 is not coplanar with Wall1:0`). A turning wall run is out of
   scope (Q1a note) — it is not one plane.
2. Establish ONE **world-space** texture frame for the shared plane:
   - **Adopt-seed (default, Q1b):** take the seed face's *world* frame — `uv_base = Location +
     R·(Origin − PrePivot)`, `axes = R·(TextureU,TextureV)`, plus its `Pan` (via
     `preview_native._world_uv_frame`, `preview_native.py:192`). Preserves the user's scale/pan.
   - **Synthesize (`--synthesize`):** derive the basis from the plane normal via
     `builders._tex_basis(normal)` (`builders.py:98`). `--wall` vs `--floor` here select which world
     axis becomes U: a wall's normal is horizontal so `_tex_basis` already yields horizontal-U /
     vertical-V; a floor's normal is vertical so it yields X-U / Y-V. **If both flags would call
     `_tex_basis(normal)` identically for a given face, they are the same operation and we should keep
     ONE flag** — the built doc must state the concrete axis rule and justify two flags or collapse to
     one. (Open sub-point for the implementer; not load-bearing for Andrzej.)
3. Write that ONE world frame into EVERY selected poly by **inverse-transforming it through that poly's
   OWN brush transform** (the reviewer-flagged multi-brush bug): stored `Origin =
   R⁻¹·(uv_base − Location) + PrePivot`, stored `TextureU/V = R⁻¹·axes_world`. For a single-brush set
   the transform is identity and this is a direct copy. Result: identical *world* mapping across the
   plane → seamless. (Alternative: keep per-face Origin and bake the offset into per-face Pan; the
   shared-world-frame route avoids the integer-Pan hazard below, so **prefer it**.)

**`--ring` (cylinder wrap):**
1. Restrict to the *side* faces: `--ring Tower --item Side` (Q3) selects the `item="Side"` faces and
   drops the 2 caps that `:all` would wrongly include (`builders.py:216-217`). Order them around the
   ring (input order per Q2; validate they form a ring — each face's plane normal roughly radial,
   adjacent faces share an edge — and error clearly if a cap sneaks in / the set isn't ring-like).
2. Shared V axis = the cylinder axis (world +Z for a default upright cylinder) with a shared V origin
   (Q2c); per-face U axis = tangent (in-plane, perpendicular to the axis). U **origin** per face
   accumulates the running chord sum (Q2a) so face *i*'s U starts where face *i−1* ended — the offset
   goes in the face's `Origin` (float), keeping `Pan` integer (below). Optionally `--fit-perimeter`
   (Q2d) rescales `|TextureU|` for an exact meet.

### `Pan` is integer — the hazard, and the fix

`model.Polygon.pan` is `tuple[int,int]` (`model.py:48`) and emits as integer `Pan U= V=`
(`emit.py`). A cross-face offset that isn't a whole number of texels can't be expressed as Pan
alone. **Fix:** for planar modes, encode the offset in the **shared `Origin`** (a stored FVector,
float32-preserved — `t3d.md:175-177`; sub-texel precision is ample for a pan offset) rather than Pan,
so Pan can stay integer (typically `(0,0)`).
For `--ring`, if the running chord sum lands fractional, likewise fold the fraction into per-face
`Origin` and keep Pan integer. **The spec's invariant: `poly align` writes float `Origin`/`TextureU`/
`TextureV` for continuity and leaves `Pan` as an integer nudge only.** (Confirm we don't need to widen
`pan` to float — Origin-based offset avoids it. Flagged for the reviewer.)

### CLI grammar sketch

```
brush poly align (--wall | --floor | --ring) [--synthesize] [--item NAME]
                 [--fit-perimeter] [--target KIND/NAME] (BRUSH:SELECTOR ... | -)
```
- Exactly one of `--wall`/`--floor`/`--ring` required (mutually-exclusive group).
- **Selection (Q3, pending confirm):** `BRUSH:SELECTOR` positionals **or** `-` reading **bare actor
  names** from stdin (each = all polys of that brush, matching `actor find`'s output) — mutually
  exclusive per the `CLAUDE.md` sole-source rule; empty stdin = clean no-op exit 0. `--item NAME`
  narrows to faces carrying that builder item label (e.g. `Side`) — chiefly to drop cylinder caps.
- `--synthesize` (Q1b): derive a fresh basis from the plane normal instead of adopting the seed face.
- `--fit-perimeter` is **`--ring`-only** — error if combined with `--wall`/`--floor`.
- `--target KIND/NAME` reuses `_target_flag` (`cli.py`), KIND ∈ `level|stash|prefab` (so aligning a
  stash/prefab brush set comes free); defaults to the selected level.
- `--seam` (Q2b) is **NOT** in v1 — deferred; default seam = first face in input order.
- Every flag gets a real `help=` (CLAUDE.md).

### Output & exit conventions

- Mutates the trunk in place (like `brush poly set`); prints the **touched brush names, one per line,
  to stdout** (consistent with `apply_surface_edit` returning sorted touched names). Note these are
  bare brush names (feedable to a name-taking verb), not `BRUSH:SELECTOR` tokens — `poly align`'s own
  output is not re-feedable to another `poly align` at poly granularity, by design.
- Human summary (count of faces aligned, mode, whether a seam remains) → **stderr**.
- Errors name the offending value and exit non-zero; no Python traceback reaches the user
  (CLAUDE.md; cover each failure path — non-coplanar set, non-ring set, unknown brush/poly,
  zero-area face — with a regression test).

### Validation

- `--wall`/`--floor`: all faces coplanar (epsilon on normal + plane offset). Error names the first
  non-coplanar face.
- `--ring`: faces form a closed (or open) facet strip — adjacent faces share an edge and normals turn
  monotonically. Error if the set isn't ring-like.
- Degenerate (zero-area) face → clear error (reuse the `_newell` length guard).

### Test strategy (offline golden UV continuity)

- **Continuity golden:** build a two-brush coplanar wall pair (or a `brush build cylinder`), run
  `poly align`, then assert **UV continuity across each seam**: for a shared seam vertex, compute
  `(V−Origin)·TextureU + PanU` from *both* adjacent faces (the `render.rs` formula, mirrored in a
  tiny Python test helper) and assert they're equal within epsilon. This directly tests the property
  that matters, independent of the exact frame chosen.
- **Ring wrap golden:** assert the U at the closing seam equals the accumulated perimeter (mod texture
  width, or exactly with `--fit-perimeter`).
- **Round-trip:** the written `Origin`/`TextureU`/`TextureV` survive `emit → parse` unchanged (they're
  preserved FVectors, `t3d.md:169`).
- **Engine-fact regression (per CLAUDE.md "Spikes / pin the finding"):** a test in the engine-facts
  module re-asserting (a) the UV formula `U=(V−Origin)·TextureU+PanU` (anchored to `render.rs:159-165`
  + a committed poly frame whose UVs are checked by hand), and (b) the cylinder chord
  `chord=2r·sin(π/N)` against `builders.cylinder` output (`builders.py:206-207`), so a later change to
  either trips red. (Do NOT anchor the *texture* convention to `light.rs`'s lightmap-grid pan — that
  is a different quantity, per the UV-convention caveat above.)
- CLI/error-path tests: non-coplanar set, non-ring set, unknown brush/poly, empty stdin no-op, both
  `-` and positional target forms.

### Docs to update on landing

- `dev/docs/architecture.md` — the surface/texture model gains `brush poly align`.
- `dev/docs/unrealed/t3d.md` — pin the UV convention (`U=(V−Origin)·TextureU+PanU`, scale in
  `|TextureU|`), currently only implicit in `render.rs`/`light.rs`.
- `dev/docs/decisions.md` — the Q1/Q2/Q3 answers (dated entry; this spec links to it).
- `dev/docs/board/` — move item 11 to done; add follow-up TODOs for the deferred pieces: turning
  wall-run (non-coplanar accumulate-along-run), `--face` fit-to-surface, sphere wrap,
  `brush poly find --coplanar/--item` producer (would retire `--item` here), `--seam`, and
  float-Pan if ever needed.

---

## Summary of assumptions baked in (lower-stakes, reversible)

- UV convention = `U=(V−Origin)·TextureU+PanU`, scale carried in `|TextureU|` (evidence: `render.rs`
  + `preview_native.py`; `light.rs` corroborates base-relativity only). If Andrzej wants the unit-axis
  + separate-scale split instead, that's a bigger model change — flag before building.
- Continuity is defined in **world space** and written back per-brush via each brush's own inverse
  transform (identity for a single-brush set) — NOT identical stored fields across brushes.
- Continuity offset lives in the (float32) `Origin`, keeping `Pan` integer — no widening of
  `Polygon.pan` to float.
- Verb lives at `brush poly align` (peer of `list`/`set`); geometry mode `--wall`/`--floor`/`--ring`
  mutually exclusive; frame source adopt-seed (default) vs `--synthesize`.
- Selection = `BRUSH:SELECTOR` positionals or `-` reading bare actor names, with `--item` narrowing
  (Q3 pending confirmation).
