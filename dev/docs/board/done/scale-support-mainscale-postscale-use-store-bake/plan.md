# Scale support — implementation plan (ephemeral)

Implements [`spec.md`](spec.md); §10 of the
spec overrides conflicting prose. Grounding spikes: `spikes/2026-06-25-scale-transform-mechanics.md`,
`spikes/2026-06-25-mainscale-postscale-applytransform.md`. Decisions: `decisions.md` 2026-06-25 +
2026-07-18 14:03.

Transform (spike-verified): `world = Location + PostScale·R·MainScale·(v − PrePivot)`.

## The scale/transform algebra module — `uedcli/transform.py` (NEW)
- `FScale` dataclass — `scale: Vec3=(1,1,1)`, `sheer_rate: Decimal=0`, `sheer_axis: str="SHEER_ZX"`;
  `.is_identity()`. `IDENTITY = FScale()`.
- `parse_fscale(text)` — nested `(Scale=(X=,Y=,Z=),SheerRate=,SheerAxis=)` → `FScale` (absent axis
  defaults 1.0; absent rate 0; absent axis SHEER_ZX).
- `emit_fscale(fs)` — the §5 byte-match emission: a `Scale` axis iff ≠1.0, `SheerRate` iff ≠0.0,
  `SheerAxis` ALWAYS; omit `Scale=(...)` when all axes 1.0; 6-dp.
- `sheer_coeff(rate)` — the disassembled piecewise snap (deadzone ≤0.05, `|r|−0.05`, snap-to-0.5 band
  0.55–0.65, `|r|−0.15` beyond). **Pinned as an engine-fact test.**
- `fscale_matrix(fs)` — the linear 3×3 point map `Sheer·Scale` (scale first, then shear on the scaled
  coords; `B += k·A` for `SHEER_AB`). det = product of scale axes. **Combined scale+sheer ORDER is
  the offline choice** — single-effect cases match the live spike; combined is integration-validated.
- small matrix helpers reuse `rotation.matmul/matvec/transpose/inverse`.

## USE — the world-vertex path (`rotation.py`)
- `actor_main_scale(actor)` / `actor_post_scale(actor)` — read the typed model fields (identity if
  None).
- `actor_linear(actor)` — full linear part `PostScale·R·MainScale`, or `None` when rotation AND both
  scales are identity (preserves the exact-Decimal fast path for every existing unscaled brush).
- `world_vertices` — use `actor_linear`.
- `world_to_local_point`/`_delta` — `L⁻¹` (true inverse, incl. scale). `world_to_local_normal` —
  `transpose(L)` (the world→local pullback of a normal; reduces to today's `Rᵀ` under pure rotation —
  see NB below).
- Consumers switch `actor_matrix`→`actor_linear`: `query.list_polys/list_vertices`,
  `writes.actor_bounds`, `preview.render_*`, `doctor._world_polys`, dispatch preview zoom.

**NB on `world_to_local_normal`:** §10 says "inverse-transpose", but the inverse-transpose of a pure
rotation R is R (not Rᵀ), which would contradict today's tested `Rᵀ`. The correct WORLD→LOCAL normal
pullback is `transpose(L)` (verified: a world plane `x+y=c` under `diag(2,1)` has local normal `(2,1)`,
which `transpose(L)` gives, not inverse-transpose). Implemented as `transpose(L)`, documented.

## STORE — structured fields
- `model.Actor` gains `main_scale`/`post_scale` (`FScale | None`).
- `model._parse_actor` parses `MainScale`/`PostScale` OUT of `props` into the typed fields
  (nested-struct parse via `transform.parse_fscale`).
- `emit.emit_actor` skips the `MainScale`/`PostScale` prop keys and re-emits SOLELY from the typed
  field after Location (de-dup, mirroring Location) — non-None only.
- `builders.make_brush_actor` sets the identity typed fields (not props).
- Every prop-string reader updated to the typed field: `preview_native._reject_scaled`,
  `doctor._has_nonidentity_scale`, `native/materialize` (re-injects the fields at the serialize
  boundary). `native/materialize._build_brush_input` still passes identity scale to Rust (unchanged
  gap — Rust rejects non-identity scale).
- `propedit`: `ScaleField` (FScale-aware typed field) + `MainScale`/`PostScale` in `TYPED_FIELDS`;
  call sites pass `getattr(actor, tf.attr)`; `Plan` generalized to `typed_updates: dict[attr,value]`.

## BAKE — `actor apply-transform` (`transform.bake` + dispatch)
- `v'=L·v`, `PrePivot'=L·PrePivot`, `Location` unchanged, fields→identity, `Rotation` removed;
  **reverse each poly's winding when det(L)<0**; `clean()` to grid.
- Texture-lock (default ON): transform `Origin`/`TextureU`/`TextureV` by `L`; OFF leaves them.
- Guards: mover → reject (exit 2); PostScale≠identity → warn (destructive/irreversible).

## CLI (`cli.py`/`dispatch.py`)
- `actor scale <names…|-> (--to|--by) SX,SY,SZ [--pivot X,Y,Z|--pivot-actor NAME]` — sets MainScale.
  `--to` in-place (Location unchanged, excludes `--pivot`); `--by` multiplies + orbits Location
  component-wise `Loc' = P + S∘(Loc−P)` (default pivot `best_grid_pivot`). Guards: zero/sub-epsilon →
  exit 2; mover → allow+warn; non-uniform `--by --pivot` on a rotated brush → warn.
- `actor apply-transform <names…|-> [--lock-textures|--no-lock-textures]` (lock ON default).
- `actor rotate` gains `--to P,Y,R` (mutually-exclusive required with `--by`; `--to` in-place, sets
  the Rotation field absolutely, excludes `--pivot`).
- `mirror` = `actor scale --by -1,1,1` (no sugar verb).

## Tests (offline; editor-parity is `-m integration`)
`test_transform.py` (matrix combos, round-trip, bake+winding+field-reset, texture-lock incl.
mirror+shear own cases, emission byte-match+de-dup, guards); engine-fact `sheer_coeff` + emission in
`test_engine_facts.py`; CLI/dispatch guard tests. `bin/test` offline suite must pass.

## Docs
`architecture.md` model-side scale section (drop "Scale is still NOT applied"); board
`board/to-plan/`→`board/done/`.
