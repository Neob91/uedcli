+++
priority = "p3"
kind = "debug"
summary = "native preview add_poly crashes (AttributeError) on an out-of-range surf owner"
+++

# native preview `add_poly` crashes on an out-of-range surf owner

`preview_native.build_scene.add_poly` computes `flags = (poly.flags or 0) | …` at its TOP, before the
`if actor is not None and poly is not None:` guard. The out-of-range-owner / out-of-range-poly branches
call `add_poly(world_verts, None, None)` (a BSP surf whose `i_actor`/`i_brush_poly` falls outside the
join range → renders flat grey, §4.4). With `poly=None`, `poly.flags` raises **`AttributeError`** — a
bare traceback to the user, which the repo rule ("never let a Python exception reach the user")
forbids.

**Latent, not yet fired**: the maps rendered so far (Wanchai, UNATCO HQ, NYC Bar) produce no
out-of-range surf owners, so the None branch is never hit. A level/build whose BSP references an
out-of-range owner would crash `level photo --native` outright.

**Fix**: guard the flag read — compute `flags` INSIDE the `poly is not None` branch, or
`flags = (poly.flags if poly is not None else 0) | (poly_flags_int(dict(actor.props)) if actor else 0)`.
Cover the None-owner path with a regression test.

Pre-existing on master (not introduced by the masked-texture change). Surfaced independently by two
correctness reviews, 2026-08-24.
