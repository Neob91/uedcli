# `surface.py` — per-face texture edits

Why the surface-edit code is the way it is. Sibling of [`emit.md`](emit.md) and [`cli.md`](cli.md);
see [`README.md`](README.md) for the index. Revised in place — agents maintain this freely.

The owner's *product* decisions about these verbs live in `../direction/conventions.md` (once
confirmed) and are parked meanwhile on `dev/docs/board/inbox/`; this file holds only the engineering.

---

## The verb split: attributes vs the frame

`brush poly set` assigns **stored per-face fields** (texture, flags). `pan`, `rotate`, `scale` and
`align` transform the **texture frame**. They were one verb only because pan had nowhere else to
live, and mixing them made `set` a verb with two unrelated jobs.

**Why it is this way.** The frame verbs compose — an author aligns, then nudges, then turns — and a
verb per operation is what makes that pipeline expressible. `set` grew a `--pan-*` flag pair for
want of an alternative, which is exactly the "big verb grown a bespoke flag at a time" that
`../direction/conventions.md` "Verbs compose" rejects.

**Rejected.** *Keeping pan on `set`* — the `--pan-to`/`--pan-by` compound spelling exists only
because it shares a verb; alone it is `pan --to/--by`, matching every other transform in the CLI
(`brush scale --to/--by`, `mover key rotate --to/--by`).

**Refs.** `../architecture.md` "Surface edits"; `uedcli/surface.py`.

---

## `resolve_targets` is ONE resolution path, shared with the CLI

Every per-face verb (`set`, `pan`, `rotate`, `scale`) turns its `BRUSH:SELECTOR` tokens into a
deduped, sorted list of `(canonical_brush_name, poly_index)` pairs through the single
`surface.resolve_targets`. The CLI calls the *same* function to print its `BRUSH:idx` stdout lines,
and the model functions still **return brush names** for `src.save(touched=…)`.

**Why it is this way.** Two separate requirements land on the same computation:

- **Dedup is correctness, not tidiness.** `pan --by`, `rotate --by` and `scale --by` are all
  RELATIVE, so a face reachable from two tokens (`Wall:all Wall:0`) would be nudged, turned or
  scaled twice.
- **stdout must be per-FACE.** A bare brush name means *all* of that brush's faces, so a per-face
  verb printing one would silently widen a two-face edit to the whole brush for the next verb in the
  pipe. Echoing the caller's own tokens back cannot work either: `Wall:all` has to expand,
  `wall:3` has to print the canonical `Wall:3` (brush names resolve case-insensitively), and an
  overlapping set has to collapse.

Sharing the function is what guarantees the printed set IS the mutated set — there is no second
resolution to drift out of step.

**Rejected.** *Changing the mutators to return the pairs.* Marginally tidier, but `touched=` is a
session-store channel over ACTORS (widening a *save* set is harmless where widening a *mutation* set
is not), and it would break every assertion on the return value across four test files for no
user-visible gain — the printed output is identical either way.

**Refs.** `uedcli/surface.py` `resolve_targets`; `uedcli/dispatch.py` `_print_poly_selectors`.

---

## The target grammar is narrower than `align`'s, deliberately

`brush poly align` accepts a bare brush Name meaning all its faces. `pan`/`rotate`/`scale`/`set` do
not — they require `BRUSH:SELECTOR`, so "all of them" is spelled `Tower:all`.

**Why it is this way.** A whole brush is a meaningful unit for an alignment MODE — "wrap this
cylinder", "stamp the world grid on this brush" is what a mode does. A whole-brush pan/rotate/scale
is a blanket nudge of every face the brush has, including the ones the author never looked at, and
the `--by` forms compound it silently. Requiring the explicit `:all` makes that a deliberate act
rather than a name typed one selector short.

The asymmetry has to be **stated in the user docs**, because the per-face verbs' *output* was
unified with `align`'s peers and a reader will otherwise assume the input matches.

---

## `rotate` has no `--to`

**Why it is this way.** An absolute texture angle has to be measured against some canonical
in-plane zero. The codebase does define one (`builders._tex_basis`), so "there is no zero" would be
false — the real reason is that its in-plane orientation is an implementation detail no author can
see or predict, and it varies with the face normal. `--to 8192` would therefore mean a different
visible orientation on every face it touched. Reaching for a *known* orientation is what
`brush poly align` exists for.

The help says this, so nobody adds `--to` on the strength of the wrong argument.

---

## `rotate` reduces its angle MODULO ONE FULL TURN before anything else

**Why it is this way.** `--by` is an argparse `type=int`, so it accepts an arbitrary-precision
integer — any digit string a user types. The Rodrigues path converts it to a float
(`by_uu * 2.0 * math.pi / 65536`), and past about `1e308` that raises
`OverflowError: int too large to convert to float`. `OverflowError` is not a `ValueError`, so the
dispatch guard does not catch it and a **traceback reaches the user** — the one thing `CLAUDE.md`
forbids absolutely. Reproduced through the real binary with a 403-digit value (exit 1). The exact
`n̂ ×` path never converts, so the crash needs a value that is *both* past `1e308` and not a whole
number of quarter turns.

Reducing modulo `65536` is exact in the integer domain and a rotation is periodic, so it changes no
result — it just bounds what reaches the float conversion. It also explains, rather than
coincidentally produces, `--by -16384 == --by 49152`: Python's `%` returns a non-negative remainder.

**Rejected.** *Rejecting an out-of-range angle with a named error.* There is no principled bound to
reject at — every integer angle is meaningful, because a rotation genuinely is periodic — so the
error would be arbitrary, and refusing to answer a question that has an exact answer is worse than
answering it.

**Refs.** `uedcli/surface.py` `_rotator`;
`test_surface.test_apply_rotate_by_an_enormous_angle_does_not_overflow`.

---

## `scale`'s writability guard ASKS the serializer — it never restates the bound

`brush poly scale --by` can drive a texture axis past what the trunk can hold, in either direction.
`surface._axis_is_writable` decides that by running each component through **`emit.fmt_vertex`** —
the exact function `emit._vec_line` uses on the way into the trunk — and reading back what came out.
Nothing about the bound is written down twice.

**Why it is this way.** Restating the bound is precisely how this went wrong, twice in one review
round, and the second time it shipped a **data-corruption bug**:

- **The floor is `CLEAN_EPS = 1e-3`, not `emit`'s six decimal places.** `emit.clean` snaps any
  component *within `CLEAN_EPS` of an integer* to that integer — and zero is an integer — so a
  component of `0.001` is written as `+00000.000000`. A guard written against `5e-7` therefore
  certified as storable an axis the trunk records as **zero-length**, which crashes the CSG rebuild
  (`builders._tex_basis`). Measured end to end: on a unit axis `--by 999` survived and `--by 1000`
  wrote all zeros at exit 0 with clean stdout, and three successive `--by 10,10` invocations walked
  the axis `0.1 → 0.01 → 0.0` and destroyed it with no diagnostic — the failure was reported only on
  the *fourth* call, blaming the frame. Reachable on ordinary content: the cliff sits at
  `|axis|/1e-3`, i.e. `--by 667` on the `0.6667` axes the editor-exported fixtures contain. The
  out-of-plane guard in the same module is derived from this same `CLEAN_EPS`, so the module knew
  the number in one place and forgot it in the other.
- **The ceiling is `fmt_vertex`, not `clean`.** `clean` only reaches `quantize6` when the value is
  *not* within `CLEAN_EPS` of an integer, and every value from `1e22` up is exactly integral in
  `Decimal` terms — so `clean(1e22)` returns it unharmed while `fmt_vertex(1e22)` raises. Checking
  `clean` left the whole band `[1e22, ~1.3e154]` open, where the failure surfaced later from
  `src.save` as a message about *world coordinates and ±32768* — on a texture axis.

**Blame is forked in BOTH directions.** An unstorable axis is either the FRAME's fault (it arrived
that way) or the FACTOR's (this call made it so), and the Gram determinant cannot tell them apart:
it would call a perfectly ordinary orthogonal frame "degenerate" for an absurd factor, and blame an
innocent `--by 1.0` for a monstrous authored axis. Asking about the axis *before* and *after*
scaling separates the two exactly.

**Rejected.**
- *Leaving the Gram check to catch it.* It does catch it — with the wrong cause, which is the
  failure mode `../direction/conventions.md` "No silent half-answers" is about.
- *A hand-written numeric bound of any kind* — a floor, a ceiling, or both. Two were tried and both
  were wrong by orders of magnitude, in opposite directions. The constraint is "what the serializer
  actually produces", so that is the question to ask.
- *Asserting the bound only at the unit level.* The in-memory float at the moment of corruption was
  an unremarkable `1e-3`; only the emitted text showed the zeros. The regressions therefore assert
  through `normalize.canonical_actor_t3d`, scoped to the `TextureU`/`TextureV` lines — a face's
  first vertex is legitimately at the origin, so searching the whole actor for an all-zero triple
  matches a healthy brush.

**Refs.** `uedcli/surface.py` `_axis_is_writable` and `apply_scale`'s blame fork;
`test_surface.test_apply_scale_never_writes_an_all_zero_axis_however_often_it_is_repeated`,
`..._blames_the_FACTOR_not_the_frame_when_a_factor_is_absurd` (which brackets the `999`/`1000` cliff
against `..._accepts_a_factor_whose_result_the_trunk_CAN_carry`), and
`..._blames_the_FRAME_when_the_FRAME_is_the_unstorable_one`. The ANGULAR half of the Gram guard
(`det <= 1e-12·g11·g22`, i.e. `sin²θ ≤ 1e-12`) is scale-invariant by construction and is left alone:
measured, it passes a 1e-5 rad skew and rejects 1e-7. Its `isfinite` half is now a backstop that
should be unreachable — both axes are writable by that point, so every component is under `1e22` and
the Gram entries stay under `3e44` — and is kept because that is a proof about float ranges, not a
test.

---

## `rotate`'s two paths deliberately write a DIFFERENT `Origin`

When `Origin` has a component along the face normal, the exact quarter-turn path drops it (`n̂ × d`
annihilates it) and the Rodrigues path keeps it. Measured on a `+Z` face with `Origin = (3,−2,7)`:
`--by 16384` writes `(12, 3, 0)`, `--by 16385` writes `(12.0002, 3.0007, 7.0)`.

**Why it is this way.** Both are correct, and the test asserts why: each preserves the centroid's
`(U,V)` exactly. A normal component of `Origin` cannot affect `(U,V)` at all, because both texture
axes are perpendicular to `n̂` — so dropping it is free, and keeping the annihilation is what buys
the quarter turn its exactness.

**Rejected.** *Unifying the two paths so they agree on `Origin`.* It would cost the exact path its
exactness for a difference nothing observes. This is pinned by a test precisely because it looks
like an inconsistency to a later reader.

**Refs.** `test_surface.test_apply_rotate_the_two_paths_diverge_on_an_out_of_plane_origin`.

---

## The re-anchor reprojects `Origin` onto the face plane — and a no-op is skipped in BOTH verbs

Both `rotate`'s exact path and `scale`'s Gram solve write an `Origin` that lies in the span of the
two texture axes, so any component the old `Origin` had along the face NORMAL is dropped. Measured:
`Origin = (3, −2, 7)` on a `+Z` face comes back `(3, −2, 0)`.

**Why it is this way.** It is rendering-neutral and therefore not worth avoiding. Both axes are
perpendicular to the normal, so a normal component of `Origin` cannot affect `(U,V)` at all — the
centroid's `(U,V)` is preserved exactly either way, which is what the pins assert. Removing it would
mean carrying a quantity that provably does not matter, and for `rotate` it is what buys the
quarter-turn its exactness (see the divergence entry above).

**But a no-op must not write.** `scale --by 1,1` and `rotate --by 0` both ask for the identity, and
performing the reprojection for them would rewrite `Origin` — and churn the trunk's git diff — on a
call that changes nothing anyone can observe. Both verbs therefore short-circuit their identity case
**after** the validation pre-pass, so a malformed frame is still refused.

**Rejected.**
- *Letting `scale --by 1,1` reproject anyway* (the behaviour before 2026-07-27). It is defensible as
  a canonicalisation, but it made the two verbs disagree about whether a no-op is a write, for no
  user-visible gain. The inconsistency is the cost: a reader who learns `rotate` skips its no-op will
  assume `scale` does too.
- *Skipping validation as well as the write.* Then `scale --by 1,1` would accept a face that
  `--by 2,2` rejects, making the guard's coverage depend on the factor.
- *Preserving the normal component through the re-anchor.* It would need a third basis vector in the
  solve to carry a quantity with no effect on the rendered result, and would cost `rotate`'s exact
  path its exactness.

**Refs.** `test_surface.test_apply_scale_reprojects_origin_onto_the_face_plane`,
`..._by_one_writes_nothing_at_all`, `..._by_one_still_validates_before_skipping`.

---

## `rotate` by a whole number of turns writes nothing

**Why it is this way.** The re-anchor is `Origin' = C − R(C − Origin)`. When `R` is the identity
that is arithmetically `Origin`, but not bit-for-bit in IEEE floats (`0.1 − (0.1 − 0.3) = 0.30000…4`),
so a no-op turn would churn every touched face in the trunk's git diff. The identity case is
short-circuited **after** the validation pre-pass, so `--by 0` still rejects an out-of-plane frame
rather than passing silently.

---

## `rotate` turns against the VISIBLE surface normal

`n̂` is flipped when the brush is subtractive, so `--by 16384` turns the texture the same way as seen
from outside the face in both cases.

**Why it is this way.** An author selects a face they are looking at. Without the flip the verb turns
one way on an added solid and the other inside a room — and room interiors are most of a map's visible
surface. It also makes the verb set coherent: `wall`/`floor` and `run` are invariant under `n̂ → −n̂`
by construction (`proj()` and `d/N.A` both cancel the sign), so `rotate` was the only verb that read
differently indoors.

**Rejected.** *The raw polygon normal.* It avoids a `CsgOper` dependency, which is a real cost — the
sign now depends on a property of the brush rather than of the face. But an author knows whether they
are texturing a room or a pillar, whereas a silent inversion indoors is not discoverable at all.
Owner ruling 2026-07-27 ("pick sane defaults").

**Refs.** board item `brush-poly-rotate-turns-against-the-visible` §9.

### What the ruling left open: a `CsgOper` that is neither add nor subtract

The ruling names two cases. Three more reach the code, and the implementation settles them as
follows (`surface._visible_normal`):

- **`CsgOper` ABSENT ⇒ treated as `CSG_Add`, so unflipped.** This is not a new default: every other
  reader in the codebase already resolves an absent `CsgOper` that way (`brushcsg._oper_of`,
  `preview._csg_color`, `preview_native.build`). It also follows from the ruling as written — such a
  brush is not a subtractive brush, so there is nothing to flip.
- **`CSG_Intersect` / `CSG_Deintersect` / anything unrecognised ⇒ exit 2 naming the value.** These
  have no defined inside or outside, so "the visible surface normal" — the quantity the ruling
  defines the turn against — does not exist for them and no sign can be derived. Guessing one is the
  worst option available, because a wrong turn direction is silent and reads as the author's own
  mistake; `../direction/conventions.md` "No silent half-answers" says refuse and name the value.
  In practice they are near-unreachable: they are live-editor verbs that do not appear in a trunk
  (`preview_native` says the same and skips them).

  **This is the conservative interim, not a ruling.** It is `[OWNER — decide]` on `dev/docs/board/inbox/`:
  fail-closed was chosen because relaxing an error to a default later is harmless, whereas shipping a
  silent default and tightening it later would have mis-textured content in between.

**A MIRRORED brush is NOT addressed by the flip and still reads backwards.** Mirrored means the
scale matrix has a **negative determinant**, i.e. an **odd** number of negative components — the
engine then draws the face with reversed winding, so the visible normal is the opposite of the one
`_visible_normal` computes from the local winding, and the turn inverts again. An **even** number
(`(-1,-1,1)`, determinant `+1`) is a 180° rotation, not a mirror, and is unaffected. An earlier draft
of this note said "a negative component" and was wrong on exactly that case; a reader following it
would have negated the angle and got the wrong result.

**This is a geometric argument, not an observation.** Nothing in uedcli measures it: the frame math
here works in the brush's LOCAL space and never reads `MainScale`/`PostScale` at all, and no fixture
in the corpus carries a mirrored brush. It is stated because the conclusion follows from the
determinant's sign, not because the behaviour has been seen — do not cite it as verified, and if it
ever matters, probe it (`rules/spikes.md`) rather than trusting this paragraph. The ruling covers
solidity only, so this is documented rather than corrected either way.

---

## The centroid re-anchor, and why `scale` needs a Gram solve

`rotate` and `scale` both leave the face's centroid `C` at the same `(U,V)`, so the texture turns or
grows *in place* rather than sliding off the face.

**`rotate`** — `Origin' = C − R(C − Origin)`, where `R` is the same operator applied to the axes.
Then `(C−O')·U' = R(C−O)·R(U) = (C−O)·U` identically. No linear solve, and no float dust beyond `R`
itself, which is what preserves quarter-turn exactness.

**`scale`** — a **2×2 Gram solve**, not the same shortcut:

```
u,v         = D·TU, D·TV                    with D = C − Origin
g11,g12,g22 = TU'·TU', TU'·TV', TV'·TV'     with TU' = TU/fu, TV' = TV/fv
det         = g11*g22 − g12*g12
a,b         = (u*g22 − v*g12)/det, (v*g11 − u*g12)/det
Origin'     = C − (a*TU' + b*TV')
```

**Why it is this way.** T3D does not require `TextureU ⊥ TextureV`, and the shortcut that works for
`rotate` does not transfer: `R` is an isometry so the Gram matrix is invariant under it, but scaling
is not. Scaling the covectors `TU,TV` by `1/fu,1/fv` requires scaling position by the **inverse
transpose** — along the reciprocal vectors, not along `Û`/`V̂`.

**Rejected.** *Scaling the direct-basis components* (`Origin' = C − (fu·a·Û + fv·b·V̂ + c·n̂)`). It is
correct for an orthogonal frame **or** a uniform factor, and silently wrong for the intersection of
skew and non-uniform scaling — the case the formula exists for. Measured counter-example: a 60°
skewed frame with `--by 2,1` and `D = Û` gives `D' = (2,0,0)`, moving the centroid's V from `0.5` to
`1.0`; the Gram solve returns `(2, −0.5774, 0)` and preserves both. Caught in plan review, not by a
test — which is why the skewed-frame non-uniform case is a required regression
(`test_surface.test_apply_scale_preserves_the_centroids_uv_on_a_skewed_frame_scaled_non_uniformly`).

**Refs.** `uedcli/surface.py` `apply_rotate`/`apply_scale`; `../unrealed/t3d.md` "The UV convention".

---

## `rotate`'s out-of-plane guard: `max(3e-3, 1e-2·|axis|)`

A face whose stored axes have a component along the normal is rejected: `n̂ × U` silently annihilates
that component, changing `|U|` and therefore the texel density.

**Why the threshold is absolute-OR-relative.** The two effects it sits between scale differently:

- **the noise is ABSOLUTE.** `emit.clean` snaps any coordinate within `CLEAN_EPS = 0.001` of an
  integer, **each component independently**, and the texture axes pass through it. So the worst
  displacement is `√3·CLEAN_EPS ≈ 1.73e-3` — e.g. `(0.999, 0.001, 0.001) → (1, 0, 0)`, all three
  snapped. It is *independent of the axis magnitude*, which is the load-bearing half.
  At the corpus minimum magnitude `0.6667` the component carrying the magnitude is not near any
  integer and cannot snap, so at most two move there: `√2·CLEAN_EPS ≈ 1.41e-3`, i.e. **2.1e-3
  relative**. (An earlier draft of this doc claimed the magnitude-carrying component can *never*
  snap. That is false near unit magnitude — `0.999` snaps to `1` — and the corrected bound is the
  one above.)
- **the harm is RELATIVE.** `n̂ × U` shortens the axis by `√(1−ε²)` for a relative out-of-plane
  component `ε`, costing `ε²/2` of density — `5e-5` at `ε = 1e-2`, invisible.

A purely relative gate therefore fails on short axes, which `brush poly scale --by` produces on
demand: after `--by 8,8` a unit axis is `0.125` long and the same absolute noise is **1.13e-2**
relative — over a `1e-2` gate. `scale --by 8,8` followed by `rotate` would exit 2 on a frame uedcli
itself wrote, one round trip earlier.

**Measured floor:** `max |axis·n̂|/|axis|` over 942 axes in `../../uedcli/tests/fixtures/**/*.t3d`
(normals via `preview._face_normal`) is **4.135e-07**, on `builder_revolve.t3d` poly 15; 876 of the
942 are exactly zero.

**Rejected.**
- *`1e-3` relative* (the spec's first assertion) — below the `2.1e-3` relative displacement the
  serializer can produce at `0.6667`, the smallest magnitude in the corpus, so it rejects uedcli's own
  output.
- *A purely relative gate at any threshold* — the noise is absolute and the harm is relative, so a
  relative-only rule tightens without limit as the axis shrinks, and `brush poly scale --by` shrinks
  it on demand.
- *Deriving the threshold from the observed ceiling.* A threshold pinned to whatever the current
  corpus contains is only as tight as that corpus is clean; one clean corpus and the gate fires on the
  next map. Choose from the harm side and measure only to confirm the noise floor sits far below.

**Both branches are pinned, and each is BRACKETED from both sides** — an accept-only pin would let
`_OOP_ABS = 1e-2` pass the whole suite. The absolute branch, on the post-`scale --by 8,8` axis where
a relative-only rule fails, is
`test_surface.test_apply_rotate_absolute_branch_brackets_a_short_axis_after_scale_by_8`
(parametrized: `1.4e-3` accepted, `5e-3` rejected); the relative branch is
`..._relative_branch_rejects_a_tilted_long_axis`, which carries its own accepted case.

The check is a **PRE-PASS over the whole deduped set, before any write**, and it names every
offender together — `../direction/conventions.md` "a batch is all-or-nothing": a per-face check
inside the mutate loop would leave face 7 of 12 rejected and faces 0–6 already mutated.

**`scale` deliberately has NO such guard.** Dividing the magnitudes preserves direction, so an
out-of-plane axis is harmless there; do not "unify" the two verbs' validation.

**Refs.** `uedcli/surface.py` `_OOP_ABS`/`_OOP_REL`; `uedcli/emit.py` `CLEAN_EPS`.

---

## `rotate` turns against the VISIBLE surface normal

`n̂` is flipped when the brush is subtractive, so `--by 16384` turns the texture the same way as seen
from outside the face in both cases.

**Why it is this way.** An author selects a face they are looking at. Without the flip the verb turns
one way on an added solid and the other inside a room — and room interiors are most of a map's visible
surface. It also makes the verb set coherent: `wall`/`floor` and `run` are invariant under `n̂ → −n̂`
by construction (`proj()` and `d/N.A` both cancel the sign), so `rotate` was the only verb that read
differently indoors.

**Rejected.** *The raw polygon normal.* It avoids a `CsgOper` dependency, which is a real cost — the
sign now depends on a property of the brush rather than of the face. But an author knows whether they
are texturing a room or a pillar, whereas a silent inversion indoors is not discoverable at all.
Owner ruling 2026-07-27 ("pick sane defaults").

**Refs.** board item `brush-poly-rotate-turns-against-the-visible` §9.

---

## `n̂` comes from the winding, floated first

The normal is computed from the polygon's own vertex winding via `preview._face_normal` (Newell),
normalised — never `poly.normal`.

**Why it is this way.** `../unrealed/t3d.md` "Winding defines the face": the importer ignores the
stored normal and the engine recomputes it, so an authored `(0.707,0.707,0)` re-exports as the true
`(0.541,0.541,0.643)`. `builders._face` marks its own write *advisory*.

Two traps, both measured:

- **Float the vertices first.** `Polygon.vertices` are `Decimal` triples and `_face_normal` seeds its
  accumulators at `0.0`, so passing them raw raises `TypeError`. `polyalign` avoids this only because
  `_world_verts` floats them on the way through.
- **Not a naive 3-vertex cross product.** On a face whose first three vertices are near-collinear it
  produces garbage: measured `1.09e-01` of false out-of-plane residue on `level_small.t3d`, where
  Newell reports exactly `0.0`.

---

## Refs

Code: [`uedcli/surface.py`](../../../uedcli/surface.py) (the verbs and the frame math),
[`uedcli/dispatch.py`](../../../uedcli/dispatch.py) `_print_poly_selectors` (the `BRUSH:idx` stdout
contract), [`uedcli/cli.py`](../../../uedcli/cli.py) `parse_pan`/`parse_factor_pair`.
Tests: `uedcli/tests/test_surface.py`, `uedcli/tests/test_cli_consistency.py`.

Evidence: [`../spikes/2026-07-26-poly-rotate-curved-track/`](../spikes/2026-07-26-poly-rotate-curved-track/README.md)
(the curved-run measurements and `uv_preview.py`, which renders each specified operation) ·
[`../spikes/2026-07-26-unrealed-texalign-semantics/`](../spikes/2026-07-26-unrealed-texalign-semantics/README.md)
(what the editor's own alignment does).

Sibling docs: [`../architecture.md`](../architecture.md) "Surface edits" (what the code IS) ·
[`../unrealed/t3d.md`](../unrealed/t3d.md) (the UV convention, winding, the zero-`Pan` rule) ·
[`emit.md`](emit.md) (why a zero `Pan` is never serialized).
