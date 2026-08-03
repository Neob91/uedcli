+++
priority = "p2"
kind = "debug"
summary = "actor preview --faces textured: the bspcsg core starts from an EMPTY world, so isolated adds render (visible) instead of being invisible as the spec's SOLID-world premise (and UnrealEd) expect."
+++

# bspcsg solve starts from an empty world, not a solid one

Found while building `actor-preview-unrealed-render-parity-new-csg` (now in `done/`).

## Evidence (measured 2026-08-03, via `preview_native.solve_world_surfaces` + `StubClassIndex`)

- A single add cube, no subtract → **6 surviving surfaces** (renders as a visible cube).
- Two adds 400uu apart → 6 surfaces (only the first; the second contributes 0 — a separate residual).
- A subtract room + an add of the SAME size at the SAME place (fills it back) → **0 surfaces**.
- A subtract room (1024) + interior add + an add BURIED at (4000,0,0) outside the room →
  Room 6, interior add 6, buried add **0** (containment works WITH a subtract present).

So the containment/visibility the spec relies on is correct **when the set contains a subtract that
defines empty space**, but with **no subtract at all** the core behaves as if the world starts EMPTY:
an isolated additive brush borders empty on every face and renders.

## Why it matters

The spec (`spec.md` §"World, empty, and the pre-solve guard (B4)") states the solve "starts from a
**solid** world (`build.rs:5-6`)" and that an **adds-only** set "exits 2 naming the cause" (nothing
survives). That is exactly the motivating demo in this item's `overview.md` — "three isolated add
cubes floating in grey space" — which UnrealEd renders as **invisible** (buried in the initial solid
world). With the current `build_geometry_bspcsg`, those three cubes **render visibly** instead, so the
motivating parity case is not fixed for the no-subtract scene.

The shipped pre-solve zero-surface guard (`rendering._preview_render_data`) is still correct and IS
reachable — pinned by `test_a_real_brush_set_that_solves_to_zero_surfaces_exits_2` using the
subtract-filled-back scene above — but the spec's adds-only example does not trigger it.

## Proposed

Owner call: is the empty-world start acceptable for the preview (adds-only is a rare/degenerate input,
and every realistic scene has a subtracting room), or should the bspcsg core be seeded SOLID for the
preview so an add with no surrounding subtract is invisible (true UnrealEd parity)? Likely related to
the residual in the depends-on `incremental-bspbrushcsg-core` (merge/repartition). Not fixed here —
the item shipped the core "as it stands" per its own overview.
