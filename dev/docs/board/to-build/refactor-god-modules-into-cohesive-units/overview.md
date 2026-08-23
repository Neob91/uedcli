+++
priority = "p3"
kind = "implement"
summary = "Refactor god modules into cohesive units"
+++

# Refactor god modules into cohesive units

Several modules mix unrelated concerns. Split them so each file has one job. No behavior change;
tests pass unchanged. Target layout and constraints in `spec.md`, slices in `plan.md`.

## Offenders (line counts at `fc8e7fc`)

- `uprops.py` (1238) — package property decode, class hierarchy walking, UnrealScript bytecode
  walking (`_walk_expr`/`_skip_script`), struct binary decode, float formatting, and member-tree
  render/strip, all in one file.
- `propedit.py` (1222) — token parsing, path resolution, struct-text read/write, the typed fields,
  and the plan/apply orchestration.
- `utexture.py` (1227) — the BC1/2/3 block decoders and layout detection separate cleanly from the
  rest. Its PACKAGE layer is out of scope: `migrate-utexture-py-dxpkg-py-onto-the-unified` owns it.

## `preview.py` is NOT in scope

The original survey named it the worst offender at 2714 lines; `6d8f770` removed the legend and name
machinery, so it is 2290 now. `consolidate-level-preview-native-onto-the-actor` owns it — that
item is actively rewriting it (one `Projection` seam extracted, then a perspective camera and a near
clipper ADDED), so splitting it here would collide — and that item does not decompose the file. This
item therefore discharges three of the four named modules; `preview.py`'s split is tracked separately
as `split-preview-py-after-the-preview`.

## Why p3

Pure structure. No user-visible effect, no correctness risk deferred. Worth doing when it buys
clarity for other work touching these files.
