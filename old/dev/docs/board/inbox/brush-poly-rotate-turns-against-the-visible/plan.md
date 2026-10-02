# Plan — per-surface verbs, step 1: split `pan` out of `set`, add `rotate` and `scale --by`

**Date:** 2026-07-26 · **Spec:** board item `the-per-surface-verb-split`
§2.0–§2.2, §2.5, §3.1 · **Status:** revised after plan review round 1

> **Scope is step 1 of the spec's four-step build order, and ONLY step 1.** Everything about
> `brush poly align` — the subcommand restructure, `wall`/`floor`'s world-space rewrite, `run`,
> `one-tile`, the `--fit-perimeter` tile fix, the texture-catalog plumbing — is out of scope and
> blocked on a spec rewrite (§9). `polyalign.py` is not touched: it imports only
> `parse_poly_selector` and `resolve_polys` from `surface`, neither of which this split changes.

## 1. What this builds

| | |
|---|---|
| `brush poly set` | **loses** `--pan-to` / `--pan-by`; keeps `--texture` / `--add-flag` / `--remove-flag` |
| `brush poly pan (--to \| --by) U,V` | **new** — integer texels, writes the polygon `Pan` |
| `brush poly rotate --by UU` | **new** — rotates `TextureU`/`TextureV` in the face plane |
| `brush poly scale --by FU,FV` | **new** — multiplies the texture's apparent size |

`scale --to` is **not** in this step: it needs the texture catalog (step 4).

## 2. Decisions already made — do not re-litigate

From the spec §3.1 and §2.1/§2.2/§2.5:

1. **Pan moves out of `set`**; `--pan-to`/`--pan-by` are **deleted outright**, no alias, no shim.
2. **Per-face mutators print `BRUSH:idx` selectors**, one per line, and the model functions keep
   returning brush names. See §4.4 — a shared resolver supplies the pairs.
3. **Angles are unreal rotation units** (16384 = 90°).
4. **`rotate` has `--by` only, no `--to`.**
5. **`scale --by` names what the AUTHOR sees**: `--by 2,2` makes the texture look twice as big, which
   *divides* the stored magnitudes (verified against `U = (Vertex − Origin)·TextureU + PanU`).

## 3. The re-anchor, stated as a formula

Both `rotate` and `scale` must leave the face's world **centroid `C`** at the same `(U,V)`, so the
texture transforms in place rather than sliding. "Preserve the centroid's (U,V)" is a goal, not a
mechanic, and **the obvious implementation is wrong**: decomposing `C − Origin` by orthogonal
projection onto `Û`/`V̂` assumes an orthogonal frame, which the spec explicitly does not require
(§2.2: *"Orthogonality of the frame is not required"*).

**`rotate` — exact, frame-agnostic, no linear solve:**

```
Origin' = C − R(C − Origin)          where R is the SAME operator applied to the axes
```

Then `(C−O')·U' = R(C−O)·R(U) = (C−O)·U` identically, orthogonal or not, and it introduces no float
dust beyond `R` itself — which is what preserves the quarter-turn exactness this plan buys elsewhere.

For the quarter-turn path `R = (n̂ ×)` applied `k` times. **Note for the implementer:** `n̂ × d`
annihilates `d`'s normal component, so it is not a rotation of a general vector — it is valid here
only because a normal component of `Origin` cannot affect `(U,V)` at all (`TextureU ⊥ n̂`). Do not
"fix" this.

**`scale` — a 2×2 GRAM SOLVE.** An earlier draft of this plan scaled the *direct*-basis components
(`Origin' = C − (fu·a·Û + fv·b·V̂ + c·n̂)`). **That is wrong** for the very case it was written for:
scaling the covectors `TU,TV` by `1/fu,1/fv` requires scaling position by the *inverse transpose*, so
on a 60°-skewed frame with `--by 2,1` it moves the centroid's V from 0.5 to 1.0. Rotate genuinely
avoids the solve because `R` is an isometry and the Gram matrix is invariant; scale is not, so the
shortcut does not transfer.

Preserve the projections directly. With `D = C − Origin`, `u = D·TU`, `v = D·TV`, and the scaled axes
`TU' = TU/fu`, `TV' = TV/fv`, solve for `D'` with `D'·TU' = u` and `D'·TV' = v`:

```
g11,g12,g22 = TU'·TU', TU'·TV', TV'·TV'
det         = g11*g22 - g12*g12
a           = (u*g22 - v*g12) / det
b           = (v*g11 - u*g12) / det
Origin'     = C - (a*TU' + b*TV')
```

Verified on the counter-example above: it returns `D' = (2, −0.5774, 0)`, preserving `u = 1.0` and
`v = 0.5`. `det == 0` means a degenerate frame — exit 2 naming the face.

The §7 test asserts the centroid's `(U,V)` within a tolerance, **not** exact equality — `C` is
`sum/n` and `Origin` passes through `emit.clean`/`fmt_vertex` on the way out.

## 4. Steps

Each ends green (`bin/test`) and is committed separately.

### 4.1 `surface.py` — split pan out of the attribute edit

- `apply_surface_edit` keeps texture/flags only; its *"at least one of …"* message now names three.
- **new** `apply_pan(level, targets, *, pan_to=None, pan_by=None)` — **exactly** one required, a
  different rule from `set`'s *at least* one, so a **different message**.
- Both **dedupe the resolved target set before applying** (`apply_surface_edit`'s
  `dict[str, set[int]]` accumulation is the pattern) — `--by` would otherwise double-apply.
- `--to 0,0` clears the pan and emits **no `Pan` line**. **Assert at the emitted-text level**, not on
  the model: `emit.py` skips on `tuple(p.pan) != (0,0)`, and `poly list` reads `is None`, so the round
  trip is what makes them agree.

### 4.2 `surface.py` — `apply_rotate`

`apply_rotate(level, targets, *, by_uu)`. Work in the **brush's LOCAL frame** (the stored axes live
there; the vertex centroid commutes with the affine actor transform, so there is no world round trip
to lose).

- **`n̂` is the unit normal computed from the polygon's LOCAL VERTEX WINDING via
  `preview._face_normal` (Newell), normalised — NEVER `poly.normal`.** **Float the vertices first:**
  `Polygon.vertices` are `Decimal` triples and `_face_normal` seeds its accumulators at `0.0`, so
  passing them raw raises `TypeError: unsupported operand type(s) for +=: 'float' and 'Decimal'`
  (verified). `polyalign` only avoids this because `_world_verts` floats them on the way through. `unrealed/t3d.md` "Winding
  defines the face": the importer ignores the stored normal and the engine recomputes it, so an
  authored `(0.707,0.707,0)` re-exports as the true `(0.541,0.541,0.643)`. `builders._face` marks it
  *advisory*, and `polyalign` never trusts it. An unnormalised `n̂` makes `n̂ × U` silently rescale the
  density. A naive 3-vertex cross product is also wrong — it produces garbage on a face whose first
  three vertices are near-collinear (measured: it reports `1.09e-01` of false out-of-plane residue on
  a fixture where Newell reports `4.1e-07`).
- **Exact path when `by_uu % 16384 == 0`**: `U' = n̂ × U`, `V' = n̂ × V`, applied `k` times where
  `k = (by_uu // 16384) % 4` — **floor division**, not `/`, which yields a float. Python's `//`/`%` on
  a negative `by_uu` already give the right non-negative `k`; pin `--by -16384 == --by 49152`.
  On a `+Z` face with `TextureU=+X, TextureV=+Y`, `--by 16384` must yield **exactly**
  `TextureU=+Y, TextureV=−X` (`Ẑ × X̂ = +Ŷ`, `Ẑ × Ŷ = −X̂`).
- Otherwise Rodrigues about `n̂`.
- Re-anchor per §3. Writes `Origin`; `Pan` untouched.
- **The out-of-plane check is a PRE-PASS over the whole deduped set, before any write** — a per-face
  check inside the mutate loop would leave a partially-applied mutation, which
  `direction/conventions.md` forbids ("A batch is all-or-nothing"). It **collects all offenders and
  names them together**, per the same rule.

### 4.3 `surface.py` — `apply_scale`

`apply_scale(level, targets, *, by=(fu, fv))`. Divide `|TextureU|` by `fu` and `|TextureV|` by `fv`,
preserving direction; re-anchor per §3; leave `Pan`. Zero or negative exits 2 naming the value (a
zero-length texture vector crashes REBUILD — `builders._tex_basis`).

**`scale` needs no out-of-plane guard** — dividing magnitudes preserves direction, so an out-of-plane
axis is harmless. Do not "unify" the two verbs' validation.

### 4.4 The `BRUSH:idx` stdout contract — mechanism, not just intent

`apply_surface_edit` returns `sorted(selected)` — **brush names**, which is what `dispatch` prints
today. Nothing in the current return types can produce per-face selectors, and echoing the input
tokens does not work: `poly set Wall:all` must print `Wall:0 … Wall:5`, and `poly set wall:3` must
print the canonical `Wall:3` (`resolve_actor_name` case-folds), and dedup means the printed set is not
the input set.

**Add a shared `surface.resolve_targets(level, targets) -> list[tuple[str,int]]`** — deduped and
sorted deterministically (brush name, then index; `selected` is a `dict[str, set[int]]` and set
iteration order is not a contract). It mirrors `polyalign.resolve_align_targets`, which already
returns exactly this shape for exactly this reason.

**The mutators' return type does NOT change** — they keep returning brush names, per the spec's
ruling 2, whose Rejected column names "changing the model return" explicitly. The mutators call
`resolve_targets` internally, so there is ONE resolution path and no risk of the CLI's pairs
disagreeing with what was mutated:

- stdout: `for b, i in surface.resolve_targets(level, targets): print(f"{b}:{i}")`
- `src.save(touched=…)` — unchanged, brush names.

(Considered and rejected: changing the return to pairs. It is marginally tidier but contradicts a
ruling for no user-visible gain — the printed output is identical either way — and it would break
every assertion on the return value across four test files.)

Each new verb also needs its own `src.save(verb=…)` name and recorded `args`.

### 4.5 `cli.py` / `dispatch.py`

- delete the two pan flags from `poly set` and their `parse_pan` wiring;
- add `pan`, `rotate`, `scale` sub-parsers, each taking `BRUSH:SELECTOR` positionals or `-`, `-` the
  sole source, empty stdin a clean exit 0;
- `pan` and `scale` use a **required mutually-exclusive group**; `rotate` takes `--by` alone;
- **apply `_tree_flag` to all three** — every existing poly sub-parser has it, and without it the new
  verbs cannot address a stash/prefab tree;
- **a new float-pair parser** for `--by FU,FV` (`parse_pan` is integer-only). It raises
  `argparse.ArgumentTypeError`, so a non-numeric input cannot traceback. The zero/negative rejection
  lives in the model (`apply_scale`), so it is enforced for a programmatic caller too;
- change `poly set`'s stdout to `BRUSH:idx` (§4.4);
- add all three verbs to **both** tables in `test_name_not_found_sweep.py` — a positional table and a
  stdin table; covering one is covering half the file's stated purpose.

### 4.6 Guard against tracebacks reaching the user

Each of these is legal in the model and in T3D, and each is a `TypeError`/`ZeroDivisionError` today:

- `poly.texture_u` / `poly.texture_v` is `None` (`emit.py` already guards for it);
- `poly.origin` is `None` — **an error**, exit 2 naming the face. `unrealed/t3d.md`'s polygon
  sub-field table marks `Origin X Y Z` **required** for a brush poly, so an absent one is malformed
  input, not a defaulting case;
- `|axis| == 0` in the out-of-plane ratio;
- a degenerate/zero-area face — `_face_normal` returns zero; reuse `polyalign._world_normal`'s named
  error pattern.

## 5. The out-of-plane tolerance — SETTLED

This overrides the spec's §2.2 assertion of `1e-3`. Recorded here and in `rationale/surface.md`.

**Measured** — `max |axis·n̂| / |axis|` over every poly carrying texture axes in
`uedcli/tests/fixtures/**/*.t3d` (24 files), normals via `preview._face_normal`:

| | |
|---|---|
| axes sampled | 942 |
| **max** | **4.135e-07** (`builder_revolve.t3d` poly 15, `TextureV`) |
| exactly zero | 876 |
| tail | 1e-7 … 1e-9 |

*(A second reviewer counted 930/864 under a slightly different filter; the max and its location
reproduce exactly either way, which is the load-bearing figure. State your glob when re-measuring.)*

**Why not `1e-3`:** `emit.clean` snaps any coordinate within `CLEAN_EPS = 0.001` of an integer,
**each component independently**, and `_vec_line` runs the texture axes through it. The worst
displacement is `√3·CLEAN_EPS ≈ 1.73e-3` absolute — `(0.999, 0.001, 0.001) → (1, 0, 0)` snaps all
three. At `0.6667`, the smallest magnitude in the corpus, the magnitude-carrying component is near no
integer and cannot snap, so at most two move: `√2·CLEAN_EPS = 1.41e-3`, i.e. **2.1e-3 relative**.
Either way a `1e-3` gate rejects frames uedcli itself wrote. (An earlier draft asserted the
magnitude-carrying component can never snap — false near unit magnitude.)

**Why the harm side allows `1e-2`:** `n̂ × U` shortens the axis by `√(1−ε²)`, so tolerating a relative
out-of-plane component `ε` costs `ε²/2` of texel density — `5e-5` at `ε = 1e-2`, invisible. A
genuinely out-of-plane authored frame is `ε ≥ 0.05` (~3° of tilt). That leaves ~1.3 decades between
the serializer's noise ceiling and real breakage, and `1e-2` is its geometric midpoint.

**⚠ A purely RELATIVE test breaks under `scale --by`, which this same step adds.** The noise is
absolute (`√2·CLEAN_EPS`, independent of magnitude) while the harm is relative, so shrinking an axis
raises its relative noise:

| after | `\|axis\|` | relative displacement |
|-------------|-----------|---
| `--by 2,2` | 0.500 | 2.83e-03 |
| `--by 4,4` | 0.250 | 5.66e-03 |
| `--by 8,8` | 0.125 | **1.13e-02 — over a 1e-2 relative gate** |

So `poly scale --by 8,8` followed by `poly rotate` would spuriously exit 2 after one trunk round trip.

**The rule, therefore, is ABSOLUTE-OR-RELATIVE:**

```
reject when   |axis·n̂|  >  max( TOL_ABS, TOL_REL · |axis| )
              TOL_ABS = 3e-3      (above the 1.41e-3 serializer ceiling, with margin)
              TOL_REL = 1e-2      (from the harm side, above)
```

At `|axis| = 1` the relative term dominates (1e-2); at `|axis| = 0.125` the absolute floor (3e-3)
governs and sits comfortably above the noise. **Pin both branches**, including a post-`scale --by 8,8`
case, since that crossover is exactly where a relative-only rule fails.

**Method note:** do **not** derive the threshold from the observed ceiling — a threshold pinned to
whatever the current corpus contains is only as tight as that corpus is clean. Choose from the harm
side, measure to confirm the noise floor sits far below. (An earlier draft asserted "~6.5e-4 of
revolve residue"; that figure was invented and is wrong by three orders of magnitude. A later draft
attributed the naive-cross-product failure to `builder_revolve.t3d`; the `1.09e-01` figure is real but
comes from `level_small.t3d`, where Newell reports exactly `0.0`.)

## 6. Files

**Code:** `uedcli/surface.py` · `uedcli/cli.py` · `uedcli/dispatch.py` · `uedcli/query.py` (its
docstring names the `--pan-to`/`--pan-by` target) · `uedcli/emit.py` (comment only).

**Tests that GO RED and must be rewritten, not left to fail** — found by grep, not assumed:

| file | what breaks |
|---|---|
| `tests/test_cli.py` | **three** parser tests on `--pan-to`/`--pan-by` and their mutual exclusion (the fourth test in that block is about an unknown flag name and is unaffected) |
| `tests/test_surface.py` | **7 tests** — three pan behaviours (`pan_to` absolute, `pan_by` relative, `pan_by` accumulating) that must be **re-homed onto `apply_pan`**, and `..._overlapping_targets_edit_each_surface_once`, whose dedup proof is `pan_by=(1,1)` and so moves with them |
| `tests/test_dispatch.py` | asserts the `apply_surface_edit(..., pan_to=…, pan_by=…)` call shape and the `saved["args"]["pan_to"]` write record |
| `tests/test_actor_name_resolution.py` | passes `pan_to=None, pan_by=None` |
| `tests/test_cli_consistency.py` | `test_poly_set_prints_touched_brush_names_to_stdout` asserts `cap.out == "WALL\\n"` — this test **is** the behaviour ruling 2 inverts; rewrite it and keep its docstring honest, since that suite is a named CLI audit's regression record |
| `tests/test_emit.py` | a comment carrying the stale spelling |

**Docs:** `docs/usage.md` · `docs/leveldesign/general/textures-and-surfaces.md` ·
`dev/docs/unrealed/leveldesign/kb/textures.md` · `dev/docs/rationale/emit.md` ·
**`dev/docs/architecture.md`** (its "Surface edits" paragraph describes the model-side pattern for
exactly these fields, and the module map describes the poly verb surface — `CLAUDE.md` requires it
kept current).

**Assertions on the RETURN VALUE are safe** — §4.4 keeps the mutators returning brush names, so
`test_surface.py`'s `touched == ["B1"]` / `["BrushA","BrushB"]` cases and `test_dispatch.py`'s
`saved["touched"]` all survive. Do not "fix" them.

**`dev/docs/rationale/surface.md`** — created 2026-07-26 with the settled content; extend it with
`Why it is this way` / `Rejected` / `Refs`. (The `polyalign` topic is the wrong home: this change is
a `surface.py` split and does not touch `polyalign.py`.) It records the verb split, the re-anchor
formula, and the §5 tolerance with its measurement. **No index row is added to
`rationale/README.md`** — an earlier draft of this line asked for one on a false premise: that README
documents the entry shape, the tree's ownership and the ledger migration, and has no topic table at
all, so there is no row to add and no other topic is indexed there.

**Cite by ANCHOR TEXT, not line number.** Several sessions are editing this tree concurrently and the
spec's numbers have already drifted. In particular: in `textures-and-surfaces.md` the pan references
are the `--pan-by 0,32` example and the `**Pan / scale** with --pan-to X,Y` bullet — the
`brush poly align --wall|--floor|--ring` line near them is **align**, out of scope, leave it. Same in
`kb/textures.md`: edit the `--pan-*` occurrences, not the `align` ones. And `rationale/emit.md` names
`surface.set_surface`, a function that does not exist (`apply_surface_edit` does) — fix while there.

## 7. Docs the spec explicitly requires, which are content and not find-and-replace

- panning a **subset** of a run breaks its continuity — easy to hit, since the idiom is
  `poly find … | poly pan -` and `find` filters;
- **pan comes after align**, never before (align stamps `Pan` on every face);
- the deliberate target-grammar asymmetry: `align` accepts a bare brush name, `pan`/`rotate`/`scale`
  take `BRUSH:SELECTOR` only;
- `rotate` gives **no continuity guarantee**, and its help must say why there is no `--to`;
- **scale before `align run`, not after** — put it beside the pan-after-align rule.

## 8. Tests — every one fails before its step

- **`pan`**: `--to`/`--by`; `--to 0,0` emits no `Pan` line **and `--to 7,3` emits `Pan U=7 V=3`**
  (both at the emitted-text level). The second re-homes
  `test_align_still_carries_a_non_zero_seed_pan_into_the_trunk`, which the spec deletes: `pan` is the
  only verb left that writes a non-zero pan, so without it `emit_polygon`'s non-zero half is
  unguarded. Exactly-one-of — state
  which layer the message test asserts, since a required mutually-exclusive argparse group fires
  first with argparse's own text and the model message is unreachable from the CLI; **dedup**.
- **`rotate`**: the `+Z` quarter-turn identity, **exactly**; 180°/270° as repeated `k`; `--by -16384`
  ≡ `--by 49152`; centroid `(U,V)` preserved within tolerance on both an orthogonal **and a skewed**
  frame (the skewed case is what §3's formula exists for); `Pan` untouched; out-of-plane rejection on
  both sides of `1e-2`, and that it is a pre-pass (nothing mutated when face 7 of 12 trips); dedup.
- **`scale`**: `--by 2,2` halves the stored magnitudes; **non-uniform `--by 2,1` on a SKEWED frame**
  with the centroid's `(U,V)` preserved — this is the case the Gram solve exists for and the one an
  earlier draft would have shipped wrong, so it is not optional; centroid preserved on an orthogonal
  frame too; zero and negative exit 2; a degenerate frame (`det == 0`) exits 2; dedup.
- **`set`**: the two pan flags are gone (argparse rejects them); its message names three.
- **stdout contract**: each verb's output is `BRUSH:idx` lines that `-` re-consumes — assert the
  **round trip**, and cover `BRUSH:all` and a case-folded `brush:3` input, which is where an
  echo-the-input implementation passes wrongly.
- **unknown-name sweep** for all three verbs, both tables.

## 9. Known residuals — logged, not silently left

- **`poly set`'s stderr summary must change with its stdout.** `dispatch.py` prints
  `f"set on {len(touched)} brush(es)"`, and `test_cli_consistency.py` asserts `"set on 1 brush(es)"`
  for a two-poly, one-brush edit. Once stdout is per-face the summary should count **faces** — decide
  the wording (`"set on N face(s) across M brush(es)"` reads honestly) and update the assertion.
- **`poly align` keeps printing brush names** until step 2/3, so `usage.md`'s "Output streams for
  mutators" paragraph must say `set`/`pan`/`rotate`/`scale` and `align` now differ. The whole
  rationale for ruling 2 is that a per-face verb printing a bare brush name silently widens the
  downstream set — `align` will keep doing that in the interim. **Log to `board/inbox/`.**
- **`rotate`'s turn direction on a subtractive brush or a negative `MainScale`.** `n̂` from local
  winding is the *polygon* normal; the visible **surface** normal is reversed on a subtract, and a
  negative scale flips handedness, so `--by 16384` turns the texture the opposite way from what the
  author sees — on a room interior, i.e. most of a map. **RESOLVED 2026-07-27 (owner): flip `n̂` on a
  subtractive brush, so the verb turns against the VISIBLE surface normal.** An author selects a face
  they can see, and the texture should turn the way that face turns from where they stand. The
  `CsgOper` dependency is real but is the lesser evil — an author knows whether they are texturing a
  room or a pillar, whereas a silent inversion indoors is not discoverable at all. It also makes the
  verb set coherent, since `wall`/`floor` and `run` are invariant under `n̂ → −n̂` by construction.
  **Pin both cases:** the same `--by 16384` on an additive and on a subtractive face must turn the
  texture the same way as seen from outside each. See `dev/docs/rationale/surface.md`.
- Steps 2–5 are specced and queued on `dev/docs/board/to-plan/`; the spec's gate is closed. (An earlier
  draft said they were "blocked on the spec rewrite" over cap detection, terminal faces and
  connectivity validation — all three are now decided in the spec.)
