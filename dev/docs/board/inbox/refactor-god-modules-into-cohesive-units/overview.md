+++
priority = "p3"
kind = "chore"
summary = "Refactor god modules into cohesive units"
+++

# Refactor god modules into cohesive units

Several modules have grown to mix unrelated concerns. Split them along the seams so
each file has one job. No behavior change; tests should pass unchanged.

## Offenders (line counts, `uedcli/`)

- `preview.py` (2714) — the worst. One file holds: annotation-spec parsing, selector
  categorisation, brush classification, projection/iso math, buffer allocation, and a
  full software rasterizer (line/circle/diamond/blit, face fill, textured fill, mip
  selection, UV/affine, occlusion, shading). At least three units: geometry/projection,
  the rasterizer, and the preview orchestration.
- `uprops.py` (1238) — package property decode, class hierarchy walking, UnrealScript
  bytecode walking (`_walk_expr`/`_skip_script`), struct binary decode, float
  formatting, and member-tree render/strip all in one file.
- `utexture.py` (1227) — package loading, texture/mip/palette decode, and the BC1/2/3
  block decoders + layout detection are separable.
- `propedit.py` (1222) — not yet inspected; sits in the same size band.

## Not done here

Only surveyed the main checkout, non-test files. Did not design the target module
layout or check import cycles — that is the spec/plan step. Grep the callers before
moving any symbol; `preview.py` internals (`_`-prefixed) look local but verify.

## Why p3

Pure structure. No user-visible effect, no correctness risk deferred. Do it when it
buys clarity for other work touching these files, not on its own.
