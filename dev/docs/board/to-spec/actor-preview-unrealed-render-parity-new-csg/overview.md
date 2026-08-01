+++
priority = "p1"
kind = "implement"
summary = "actor preview: UnrealEd render parity — new CSG-solved `world` face mode + black bg for all --faces modes."
depends-on = ["incremental-bspbrushcsg-core"]
+++

# actor preview: UnrealEd render parity

## Owner ruling (2026-08-01)

Prompted by a `--faces textured` demo that rendered three isolated add cubes floating in grey space.
The owner ruled: **the render needs UnrealEd parity.** Two decisions, via the AskUserQuestion widget:

1. **New CSG-solved mode**, not a redefinition of `textured`. A new `--faces` value runs the native
   CSG engine over the brush set and draws only the world surfaces that survive the solve — so an
   additive brush that is not inside subtracted (empty) space is invisible, matching UnrealEd's 3D
   viewport. `--faces textured` is unchanged: it stays the CSG-free per-brush UV inspector (its
   documented purpose — check a single built brush's alignment/pan/tiling offline).
2. **Black background for all `--faces` modes** (`wire`, `flat`, `textured`, and the new mode), not
   just the new one. The current light-grey ground (`BG = 224`, `preview.py:485`) and the wire/flat
   palettes were tuned for grey, so those palettes must be re-tuned for a black ground.

Neither reverses the isolation rulings in board item `four-actor-preview-faces-rulings-need-a-durable`
(opaque solid brush, no x-ray) — those govern `flat`/`textured`, which keep per-brush rendering. The
black-bg change **does** supersede the grey-ground tuning those rulings assumed; note it there when
this lands.

## Why parity needs a real solve (evidence)

UnrealEd starts from a solid world; `Subtract` carves empty space; `Add` puts solid back **into**
empty space. A brush face renders only where solid meets empty. So "adds don't show unless inside a
subtract" is **not** a per-brush facing rule — it needs global spatial containment, i.e. a CSG solve
over the whole set, then render the resulting surfaces. Today `textured` approximates visibility
per-brush (subtract → far faces, add → near faces; `preview.py` cull) but never hides an add by
containment, because it has no world solve. The native engine that does the solve already exists
(`uedcli-native/src/bspcsg.rs`, exposed at `lib.rs`), and `level preview --native` already renders a
built world — so the mode is feasible offline; it largely reuses an existing native path.

## Pre-spec — design sketch (needs a real spec + owner gate before build)

- **Mode name.** Proposed `--faces world` (the built world, vs per-brush `flat`/`textured`).
  Alternatives: `--faces solid`, `--faces csg`, `--faces built`. Naming is the owner's call
  (question filed).
- **Render path.** Almost certainly reuse the `level preview --native` pipeline (native CSG solve →
  textured surface render) rather than a second renderer. Open: does `world` share `level preview`'s
  code and just re-target it at an ad-hoc actor set (incl. `--from-t3d`), or does `level preview`
  grow the actor-set input? Overlaps board item `level-preview-native-*`.
- **Non-add CSG kinds under the solve.** How movers, semisolids, non-solids and point actors appear
  in a world render (a mover carries no CsgOper, so it is not part of the BSP world — draw it as an
  overlay? a semisolid adds faces without splitting; a non-solid sheet). Needs enumerating.
- **Black bg + palette re-tune.** `wire` and `flat` colours (`preview.py` ~92-141) assume `BG=224`;
  re-tune for black while keeping the add/subtract wire cues (blue/gold) and the flat facing cue
  legible. The wire golden (`preview_wire_golden_*`) and flat golden re-bless.
- **Texture source.** `world` needs the same decoded-texture seam `textured` uses
  (`rendering.preview_textures`), so it inherits the games-config/texture-resolver requirement — a
  brush-only `wire`/`flat` still needs no game content.

## Open questions (filed under questions/)

- `mode-name` — the `--faces` value for the CSG-solved render.
- `world-render-path` — new mode reuses `level preview --native`, or `level preview` grows an
  actor-set input.
- `non-add-kinds-in-world` — how movers / semisolids / non-solids / point actors render under the
  solve.

## Not started. Recording the ruling before it scrolls away; build needs a spec + owner gate + a
worktree.
