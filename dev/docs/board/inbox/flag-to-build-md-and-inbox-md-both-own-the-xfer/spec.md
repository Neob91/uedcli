# Spec: map coordinates are uniformly `Decimal` in the model

**Status:** specced, **review-gated** (rounds 1–2 resolved — 3 cold reviewers each; this file is the
post-round-2 revision. A fresh round follows). Round 2 verified the producer enumeration COMPLETE, the
byte-safety sound, and no wrongly-excluded parse; the changes below correct two overstated justifications
and the acceptance-gate claims. Stays at 3 reviewers.
**Requested by:** Andrzej (2026-07-25, session `uedcli:review`) — "Switch parsing from float to decimal
everywhere we work with map numbers", off a finding that `model._parse_polygon` parses poly
Origin/Normal/TextureU/TextureV as `float` while the `Polygon` dataclass declares them `Decimal`.
**Ephemeral:** scratch; deleted once the work lands. Durable record: `decisions.md`, `architecture.md`,
the tests in §5.

**This document is SELF-CONTAINED.** The binding decision, its rejected alternatives, the float-vs-Decimal
seams, the type inconsistency it removes, and the acceptance gate are stated here. Source may be read; no
other document need be opened.

---

## 0. Terms

- **`Vec3`** — `model.py` type alias `tuple[Decimal, Decimal, Decimal]`. The `Polygon`/`Actor` coordinate
  fields are all declared `Vec3 | None`.
- **Authored value** — a coordinate from a `.t3d` the user wrote (or that uedcli wrote and must
  reproduce). Fidelity: exact round-trip.
- **Computed value** — a coordinate uedcli calculates (centroid, rotated normal, rasterizer coord).
  Float-precision by nature; no authored text to preserve.
- **`Decimal(str(x))` boundary** — the correct float→Decimal coercion (stringify first;
  `Decimal(str(3.1))` = `Decimal("3.1")`, not `Decimal(3.1)`).
- **`emit.clean`** — the single emit-side normalizer (via `fmt_vertex`/`fmt_loc`, calling helper
  `emit._to_decimal`). `_to_decimal` **passes an existing `Decimal` through unchanged** and coerces a
  non-Decimal via `Decimal(str(v))`; `clean` then integer-snaps within `CLEAN_EPS` and quantizes to 6 dp.
  **Every coordinate reaches the emitted map through `clean`**, whatever its in-model type. (There is no
  `emit._dec`.)

## 1. Problem

The model's coordinate fields are **declared** `Decimal` but **populated inconsistently**:

- **Parse produces `float`** for four of the five poly attributes. `model._parse_polygon` uses `_vec`
  (returns `float`) for `Origin`/`Normal`/`TextureU`/`TextureV`, and `_vec_decimal` (`Decimal`) only for
  `Vertex`. A parsed poly violates its own declared type on four fields. This is the reported finding.
- **Producers store `float` into `Vec3` fields.** `builders.py` (`_face`/`translate_brush`/`_rotate_z`),
  `clip._make_cap`, `polyalign._write_world_frame`, and `transform.bake` all leave `float` in
  `origin`/`normal`/`texture_u`/`texture_v`. (Their `vertices`/`location` are already `clean()`'d to
  Decimal — so the split is specifically the four non-vertex attributes.)
- **The float/Decimal split is a latent type inconsistency.** `builders.translate_brush` computes
  `x + dx` over `p.vertices` (`dx: float`) and `builders._rotate_z` computes `x*c - y*s` (`c,s: float`);
  parse vertices are `Decimal`, so those helpers would `TypeError` on a parsed brush (`Decimal op float`).
  **This is not currently reachable** — `translate_brush`/`_rotate_z`'s only callers are
  `spiral_staircase`, which passes freshly-built *float* brushes; and downstream CSG (`brush intersect`)
  re-`clean()`s every poly to Decimal in `brushcsg.merge` before `brushcsg.recenter` runs, so no live
  path today crosses a model `float` into a `Decimal`-op. The hazard is that the model carries two types
  for one declared type, so any *future* wiring (a caller feeding a parsed brush to `translate_brush`, or
  a Decimal poly to a float-only op that lacks a read-coerce) would crash — a type-robustness bug, not a
  live crash.

Net: the declared type is aspirational, not enforced, and the model is one wiring change from a type
crash.

## 2. Decision

**D1 — every coordinate stored in the model is `Decimal` (the declared `Vec3`). `float` exists only as a
transient inside a computation and is coerced back at the store; a consumer that needs float math coerces
with `float(c)` at the read boundary.** This makes the declared type the enforced type and removes the
type split. *Rejected: "only parse is Decimal, computed stays float"* — leaves the dataclass a half-truth
and the type split live. *Rejected: "make everything float"* — throws away authored round-trip fidelity
the byte-identity build goal needs. *Rejected: compute in Decimal* — trig/normalization want float.

### Two coercion conventions — use the right one per site

- **FINAL producer stores** (the value that lands in the model and is emitted): use the **existing
  `clean()` idiom** — the same the builders already apply to `vertices`. **Extend the existing `clean()`
  coverage** in `builders.make_brush_actor`, `clip._make_cap`, and (see below) `transform.bake` to include
  `origin`/`normal`/`texture_u`/`texture_v`; and `polyalign._write_world_frame`. Do NOT hand-roll a
  different coercion at these sites.
  - **`transform.bake` specifics:** `origin` is `apply_point(...)` which **already returns `clean()`
    Decimal** — the bug is only the redundant `float(c)` **re-wrap**; the fix is to **delete that
    `float()` wrapper** (store the Decimal `apply_point` already produced), NOT to add a second `clean()`.
    `texture_u`/`texture_v` come from `apply_dir` (raw float) and DO need `clean()` added. (`normal` is set
    to `None` by bake — unchanged.)
- **INTERMEDIATE transform helpers** (`builders.translate_brush`, `builders._rotate_z`, called by
  `spiral_staircase` before the final `make_brush_actor` `clean()`): **coerce the `Vec3` inputs to `float`
  at entry** (as `clip_brush` already does before it builds the cap — otherwise `x + dx` still throws before
  any result wrapping), compute in float, and store the result as **`Decimal(str(x))` — full precision, no
  6-dp quantize**. Full-precision intermediates keep the single final `clean()` authoritative; this is a
  deliberate, defensive choice for any *future composed* transform chain (today each helper is a single
  transform immediately before the final `clean()`, so an intermediate quantize would NOT drift the
  current spiral — but `Decimal(str())` is the safe convention regardless).

### The change, by seam

- **C1 — parse.** `model._parse_polygon`: use `_vec_decimal` for `Origin`/`Normal`/`TextureU`/`TextureV`;
  delete `_vec` (its only caller). **C1 is byte-INVISIBLE** (§3); its purpose is the type contract +
  removing the latent type split, not any observable text change.
- **C2 — builder producers.** Extend `make_brush_actor`'s `clean()` to the four attributes; fix
  `translate_brush`/`_rotate_z` per the intermediate rule (input-coerce + `Decimal(str())`). Audit all of
  `builders.py` for `Vec3`-field arithmetic.
- **C3 — clip / polyalign / transform producers.** `clip._make_cap`, `polyalign._write_world_frame`, and
  `transform.bake` (delete the origin `float()` re-wrap; `clean()` the two texture axes).
- **C4 — arithmetic-mixing audit.** Verified-known sites: `builders.translate_brush`/`_rotate_z` (C2);
  `brushcsg.recenter` (`p.origin[i] - anchor[i]` — `anchor` is Decimal in every branch, and its `polys`
  come from `merge`'s `clean()` output, so it is Decimal−Decimal already). Consumers that read-coerce to
  float (`preview_native`, `normalize._f32_vec`, `rotation`, `query`, `doctor`,
  `native/materialize._build_brush_input`) are safe and unchanged.

### Explicitly NOT in scope (verified correct in round 2)

- **`FloatProperty` values** (`typedprops._f32(float(t))`, `propedit` float coercions,
  `uprops.format_float`) and the native `props` struct-field parses — a UE1 `FloatProperty` **is** an
  IEEE-754 32-bit float on the wire; float is faithful.
- **Other authored-coordinate parses — confirmed already Decimal:** `Location`, `parse_fscale`
  scale/sheer, `rotation.parse_fvector`, `propedit._parse_scale_vec`. `preview_shots._parse_float` parses
  ephemeral camera poses never stored in the model.
- **`native/` build path.** `native/materialize` float-coerces every poly coordinate at read, so Decimal
  never reaches the Rust core. One note, not a live risk: `native/actor_write.write_fpoly`'s
  `struct.pack("<3f", …)` is fed only hardcoded float literals (`_builder_cube_polys`), never a model
  poly; a one-line `float()` guard would future-proof it.

## 3. Why C1 is byte-invisible, C2/C3 are byte-safe, and what the gate can and cannot prove

- **C1 changes no emitted byte.** Emit funnels every coordinate through `emit.clean` (`Decimal(str(v))` +
  snap + 6 dp), so a field parsed as `float 1234.56789` vs `Decimal("1234.56789")` emits identically.
  Reason it holds for the whole domain: a 6-dp value within map range round-trips through `float`
  (`str(float(s)) == s`), and the only float→str scientific-notation region (|x| < 1e-4) lies inside
  `CLEAN_EPS = 0.001`'s snap-to-integer, so it cannot drift. (Verified empirically too — 2,000,000 random
  6-dp coords, zero differences.) C1's value is the **type contract** + removing the latent split, NOT a
  visible-drift fix.
- **C2/C3 are byte-safe when done right.** "Compute in float, store via `clean()`/`Decimal(str())`"
  reproduces the same float and hence the same bytes (`clean(Decimal(str(f))) == clean(f)`; `float(...)`
  round-trips).
- **What the gate proves — stated honestly.** The §5.1 built-brush emit golden catches a wrong transform
  **result** (a missing / duplicated / mis-computed store — a value change ≥ 1e-6). It does **NOT**, and
  cannot, discriminate a poisoned `Decimal(float)` store from a correct `Decimal(str(...))` one: `_to_decimal`
  passes an existing `Decimal` through and the 6-dp quantize erases the ~1e-11 binary tail, so the two emit
  byte-identically and the type-invariant test (§5.3) sees `isinstance(Decimal(float), Decimal) == True`.
  A `Decimal(float)` botch is therefore **byte-invisible and non-crashing** — there is nothing observable
  to gate; the `Decimal(str(...))` convention is mandated for correctness-in-principle, not because a test
  enforces its form. (This corrects a round-1/round-2 overclaim.)

## 4. Things the reviewers must check

- **No `Decimal op float` remains** anywhere a `Vec3` field is read (C4).
- **The coercion is `clean()` at final producer stores and input-coerce-to-float + `Decimal(str(x))` at
  intermediate transform helpers — never a bare `Decimal(float)`**, and the `transform.bake` origin fix is
  a `float()`-wrap deletion, not a second `clean()`.
- **`transform.bake` is actually in scope** and its post-transform poly is uniformly Decimal.
- **`_vec` is fully deleted** (single caller; no test imports it).

## 5. Test plan / acceptance gate

The existing `test_builder_parity` (world-vertex set match within `PARITY_TOL = 1e-4`, reads only
`vertices`) and `test_csg_golden` (native CSG counts) do **NOT** compare emitted bytes or inspect
`origin`/`normal`/`texture_*` — so they cannot guard C2/C3. The gate adds:

1. **Built-brush emit golden (NEW — the C2/C3 transform-logic gate).** Assert `canonical_actor_t3d` byte
   output is unchanged, capturing the golden BEFORE the change and asserting equality AFTER, for shapes
   that exercise **both** intermediate helpers: a built cube; the **column** (`translate_brush`); and a
   **wedge** (`_rotate_z`) — i.e. golden a whole `spiral_staircase` — covering the
   `Origin`/`Normal`/`TextureU`/`TextureV` lines. (This catches a wrong/missing/duplicated store; it does
   NOT and cannot catch a `Decimal(float)`-vs-`Decimal(str)` form difference — that is byte-invisible per
   §3.)
2. **Cross-path no-crash (the latent type hazard).** Feed a *parsed* (Decimal) brush **directly** through
   `builders.translate_brush` and `builders._rotate_z` and assert no `TypeError` (these crash today on a
   Decimal brush — a real pre/post regression). *(Note: an `apply-transform → brush intersect` path is NOT
   a useful crash test — `brushcsg.merge` re-`clean()`s to Decimal before `recenter`, so it neither
   crashes today nor exercises the hazard.)*
3. **Type invariant.** A helper asserting every `Vec3` field is `Decimal` on every component (skipping a
   `None` field — the four non-vertex attributes are `Vec3 | None`, and the invariant helper, like the
   extended `clean()` stores, must `None`-guard as `emit` already does), applied to a **parsed**, a **built**
   (the `make_brush_actor` OUTPUT, not a raw `_face`/`cube` brush — the `clean()` that Decimalizes the four
   attributes lives in `make_brush_actor`, so a raw builder brush still carries float there), a
   **transformed** (`apply-transform` output), a **clipped** (`clip` output), and an **aligned** (`polyalign`
   output) brush — covering all four C1–C3 producer families so a missed store in any of them fails the
   invariant.
4. **Existing suites stay green** (`test_builder_parity`, `test_csg_golden`, `test_builders`, `test_emit`)
   and the full offline suite via `bin/test`.

## 6. Sequencing note

C1 is the low-risk core (byte-invisible; honors the declared type) and could land first; C2–C4 complete
the invariant and carry the transform-logic risk, gated by §5.1/§5.3. If the build review wants to stage
them, C1 → gate → C2–C4 → gate is acceptable.
