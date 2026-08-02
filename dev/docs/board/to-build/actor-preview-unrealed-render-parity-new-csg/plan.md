+++
status = "draft"
date = "2026-08-02"
+++

# actor preview: UnrealEd render parity — plan

Buildable from `spec.md`. Build in a **feature worktree** off `master`
(`rules/worktrees.md`), committing per slice; squash-merge as ONE commit at the end
(`rules/building-features.md`). Tests run via `bin/test` (`rules/tests.md`), never bare pytest; the
bspcsg core needs the native extension built (`maturin develop`, or one `bin/test` run) — a run without
`cargo` skips the native tests and exercises less than it looks.

Slices are ordered so the highest-risk unknown — does the bspcsg solve render a carved room correctly
through the ortho pipeline — is proven FIRST, by eye, before any CLI or golden work.

## Slice 1 — `solve_world_surfaces` via the bspcsg core, proven by eye

Add `solve_world_surfaces(actors, index, search_files=None)` in `preview_native.py` (spec "Design →
`solve_world_surfaces`"): adapt `_brush_inputs`'s marshalling to an ad-hoc actor list, call
`uedcli_native.build_geometry_bspcsg` (`lib.rs:220`, NOT `build_geometry`), then `serialize_model` →
`parse_model_body` → `_node_polys` → source-poly join, returning `world_surfaces` (list of
`(actor, source_poly|None, world_verts)`) and `mover_polys` (from `_mover_world_polys`). No `preview.py`
wiring yet.

- **Tests:** a unit test that `solve_world_surfaces` over a subtract-room-with-interior-add set returns
  surfaces for the room's interior walls AND the add's faces where they border empty, and NOT the
  buried add faces; `(None, None, verts)` for any unjoined node. Assert it calls `build_geometry_bspcsg`
  (patch/spy), guarding the core choice.
- **Verify (EYEBALLED, before anything else):** a throwaway harness that dumps the solved fragments and
  renders ONE carved room through the existing ortho projection to a PNG; open it and confirm the
  interior shows and a buried add is hidden. This is the go/no-go for the whole approach — if the ortho
  pipeline cannot draw world-space fragments faithfully, stop and re-plan before slice 2.

## Slice 2 — feed solved surfaces into `_scene_geometry` (the B3 plumbing)

- Add the solved-payload field to `FaceData` (`preview.py:297`) and build it in `_preview_render_data`
  (`rendering.py:617`).
- In `_scene_geometry` (`preview.py:1867`), under `textured`, iterate `world_surfaces` instead of the
  per-actor/per-poly loop: **skip `local_offset`** (`:1973-1974`, verts are world-space), **force
  `cull_front = False` and `mirrored = False`** (`:1962`, `:1968` — the solve already resolved
  visibility), emit `fills` + `tex_faces` off the SOURCE poly (`world_uv_frame`, `_poly_texture_ref`,
  `masked`), and draw the per-poly index **once per `(actor, source_poly_idx)`** on the largest-area
  fragment (spec B3.4). `wire` path unchanged.
- Grey path for `(None, None)` fragments (M5): `mips = None` → the existing `DEFAULT_GREY` branch
  (`preview.py:2253`).

- **Tests:** `_scene_geometry` over a solved set produces the expected `fills`/`tex_faces` count and
  world verts (no `local_offset` applied — assert a known world coordinate); a subtract room's interior
  walls are PRESENT (regression against re-culling); one source poly split into N fragments yields ONE
  index label.
- **Verify:** render the slice-1 carved room through `actor preview --faces textured --from-t3d` (still
  on grey bg / old palette here) and confirm interior walls and correct add visibility in the real CLI
  output.

## Slice 3 — redefine `--faces textured`, delete `flat` + stale refs

- `_arguments.py:219`: choices → `["wire", "textured"]`, default `wire`; rewrite the `--faces` help
  (spec CLI block) and drop the `--faces flat` mention in `--brush-colors` help (`:238`).
- Delete the `flat` MODE branch and its `_fill_face` call at `preview.py:2248` (KEEP `_fill_face` `:823`
  — used by the grey fill at `:2255`).
- Drop stale `flat` references (M1): `rendering.py:630`, `:664`, `preview_movers`/`preview_textures`
  docstrings (`:555-556`, `:675/678/685`).
- Update `docs/usage.md` + `docs/leveldesign/` for the two-mode `--faces` in the same change
  (`rules/documentation.md`).

- **Tests:** `--faces flat` now exits 2 (unknown choice); `_reject_explicit_brush_colors` /
  `_reject_transformed_brushes` messages no longer say "flat"; delete the `flat`/old-`textured`
  behaviour tests and their goldens (`preview_flat_golden_iso.png`, `preview_textured_golden_iso.png`).
- **Verify:** `actor preview --faces -h` reads correctly; `--faces flat` errors cleanly.

## Slice 4 — black background + `wire` palette re-tune + golden re-bless

- `BG = 0` (`preview.py:485`); invert `FRONT` to a light default and make `BACK` a dimmer partner of the
  hue (`:94-95`); re-check `DIVIDER/CAPTION/MARKER` (`:96-98`) and label knockout boxes on black.
- Re-bless the `wire` goldens (`preview_wire_golden_iso.png`, `preview_wire_golden_quad.png`) AFTER
  eyeballing each (`UEDCLI_BLESS_GOLDEN=1`).

- **Tests:** the re-blessed `wire` goldens pass; palette-wiring tests still pass (re-check any that
  hardcode a shade rather than derive from `BG`).
- **Verify:** open both re-blessed `wire` PNGs and the textured render on black; confirm legibility of
  lines, labels, and the legend.

## Slice 5 — mover overlay + point overlay + non-add kinds

- Composite `mover_polys` as **filled magenta** through `_fill_face` against the shared `zbuf` (M3), no
  wireframe; confirm point-actor sprite/marker overlay (`PointRender`) draws over the solved world;
  confirm semisolid/nonsolid brushes go through the solve and draw textured (`poly_flags_flat`).
- Confirm `actor preview` feeds actors in effective CSG order (`(order_value, name)`); if not, board a
  separate finding (M4) — do not silently re-sort here beyond what parity needs.

- **Tests:** a mover behind a wall is occluded (depth), a mover in front occludes; a semisolid brush's
  faces draw textured; a point actor renders its marker over the solved world.
- **Verify:** render a scene with a door mover + a point light in a carved room; confirm magenta mover,
  sprite, and correct occlusion.

## Slice 6 — empty / zero-surface guards + error paths (B4)

- Pre-solve guard in `_preview_render_data` (`rendering.py:599`, before `solve_world_surfaces`):
  empty set → exit-0 no-op; no world-CSG brushes (point/mover-only) → overlays over black, exit 0;
  brushes present but zero surviving surfaces → exit 2 naming the cause.
- Move texture resolution AFTER the solve (M2): resolve/refuse only refs the SURVIVING surfaces need.
- Error paths: `uedcli_native` missing → exit 2; unreadable needed texture / broken config / outside a
  project → named exit 2; scaled/sheared → up-front refusal; `--size` cap → `PreviewAbort`. No traceback
  on any path.

- **Tests:** empty stdin → exit 0, no file; point/mover-only → exit 0 with overlays; adds-only → exit 2
  naming the cause; an unreadable texture on a CULLED face does NOT refuse (M2), on a surviving face DOES;
  a scaled brush → named exit 2.
- **Verify:** run each error path and read the message.

## Slice 7 — the parity tests (goldens + continuity + guards)

Fold in the remaining regression guards from spec "Tests":

- **`textured` world golden** (subtract room + interior add), eyeballed then byte-blessed — the parity
  guard.
- **Doorway/overlapping-subtract test** — the opening shows through, which only the bspcsg core produces
  (guards the core choice against a silent revert to `build_geometry`).
- **UV-continuity test** — a wall cut by a subtract keeps one continuous, aligned texture across the
  split.
- (Zero-surface / point-mover-only / empty already covered in slice 6; keep them green.)

- **Verify:** full `bin/test` green (with the native extension built); read the diff; run
  `actor preview --faces textured` on a real trunk level and confirm it reads like UnrealEd's viewport.

## Close-out

Formatter/linter/type-checker + `bin/test` green; read the whole diff; one subagent reviews
`git diff base...HEAD` and its confirmed findings are fixed (re-review if large). Then `git mv` the item
to `done/`, cut `overview.md` to a one-line record, fold the durable knowledge into `dev/docs`
(architecture "Preview internals"; a `rationale/` entry for the decal-once rule and the bspcsg-core
choice), raise the `[OWNER — confirm]` `direction/` home item, update
`four-actor-preview-faces-rulings-need-a-durable`, update the base to `origin` latest, and squash-merge
as one commit.
