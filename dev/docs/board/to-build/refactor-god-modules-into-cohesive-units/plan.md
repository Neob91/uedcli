# Plan — split the god modules

Three independent slices. Each is a separate commit, each leaves the suite green, and any one can
ship without the others. Order is by ascending risk.

## Slice 1 — `utexture_codec.py` (lowest risk)

1. Move the block decoders and layout detection out of `utexture.py` into `uedcli/utexture_codec.py`:
   `_rgb565`, `_bc_colours`, `_bc2_alpha`, `_bc3_alpha`, `_decode_block`, `_decode_bc1`/`_bc2`/`_bc3`,
   `_decode_linear1`, `mip0_to_rgb`, `Layout`, `DetectionFailure`, `_fitting_classes`,
   `detect_layout`.
2. `utexture.py` imports them and re-exports every name it exposes today.
3. Gate: `bin/test -k texture` green with no test edited, and the texture-corpus goldens unchanged.

The decoders take `Mip` and a palette and return bytes — no back-reference into `Package` — which is
why this slice is first. Confirm that by grep before moving, not after.

## Slice 2 — `uedcli/uprops/`

1. Create the package; move `schema.py` first, then `script.py`, then `values.py`, running the suite
   between each move so a break is attributable to one move.
2. `__init__.py` re-exports the current public surface. Compare `dir(uprops)` before and after — the
   public set must be identical, not merely sufficient for the tests that happen to exist.
3. Gate: full `bin/test` green, no test edited.

`values.py` is the one with real coupling — it calls into both siblings. If a cycle appears, the fix
is to pass the resolver in rather than to import upward; do not add a lazy in-function import to
paper over a bad edge.

## Slice 3 — `uedcli/propedit/`

1. Create the package; move `tokens.py`, `paths.py`, `structtext.py`, `fields.py` in that order.
2. Leave the orchestration (`plan_edit`, `Plan`, `get_lines`, `dump_all_lines`, `effective_value`,
   `effective_match`, `values_match`, `zero_value`, `validate_leaf_value`) in `__init__.py`.
3. Gate: full `bin/test` green, plus `actor prop get`/`set`/`unset` exercised by hand on a real
   trunk — `propedit` is the write path, and a golden-free regression here is a silent data bug.

`ScaleField` is load-bearing for `MainScale`/`PostScale` round-tripping (`architecture.md` "STORE").
Its move is the single riskiest step in this plan; run the scale round-trip tests specifically.

## After the slices

- Propose the `dev/docs/architecture.md` module-map edits in
  `questions/architecture-module-map-after-the-split.md` — exact find→replace rows, owner's yes
  required before any edit. Do not edit the file in the build.
- Note in the item that `preview.py` remains unsplit and is owned by
  `consolidate-level-preview-native-onto-the-actor`, so the "god modules" title is only three-quarters
  discharged.

## Not doing

- No renames, no signature changes, no dead-code deletion — each is its own proposal.
- No `preview.py` work, and no `utexture.py` package-layer work (both owned elsewhere; see `spec.md`).
