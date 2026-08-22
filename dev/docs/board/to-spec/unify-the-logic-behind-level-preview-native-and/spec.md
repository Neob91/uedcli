# Spec — unify `level preview --native` and `actor preview`

## The premise in `overview.md` is out of date — read this first

The item was filed 2026-08-05 and says the two tiers "share only `texframe` and `preview_shots`",
with the CSG solve, texture paint, backface cull and scale gate "each implemented twice". Measured
against the code at `6d8f770`, that is wrong in three places, and the correction changes what this
item is worth doing.

**Already shared.** `actor preview --faces textured` does not solve CSG itself. `cli/rendering.py`
(the `_preview_render_data` path) calls `preview_native.solve_world_surfaces()`, which marshals the
brushes and runs the Rust core — landed 2026-08-03 in `b0c1e1a`, two days before this item was
filed. Texture framing is shared too: `preview.py`, `preview_native.py` and `polyalign.py` all
compute UV through `texframe.world_uv_frame`, which exists precisely so they cannot disagree.

**The real divergence is one level down: the two tiers call two DIFFERENT Rust cores.**

| Tier | Entry point | Rust core | Scale |
|-------------------------------|--------------------------------------|-----------------------------|---
| `actor preview --faces textured` | `preview_native.solve_world_surfaces` | `build_geometry_bspcsg` | core REJECTS it (`bspcsg.rs:2064`)
| `level preview --native` | `preview_native.build_scene` | `build_geometry` | core APPLIES it, but `_reject_scaled` gates every brush out first

Note the asymmetry in the last column is not user-visible: both tiers refuse scaled brushes
Python-side, so the coarse core's scale math is dead code on the preview path.

Both live in `preview_native.py`, 80 lines apart. So the same trunk previewed at the two tiers is
carved by two different CSG implementations — `build_geometry_bspcsg` is the faithful incremental
`bspBrushCSG` port, `build_geometry` the older coarse one. Nothing guarantees they agree, and the
byte-parity work tracked on the board is against `bspcsg` only.

**The stated motivation does not hold.** The item says unification is what lets scale support be
"built once instead of twice". Scale is not waiting on unification — it is already implemented once,
in the coarse core, and missing from the faithful one. Board item `bspcsg-core-apply-scaled-brushes`
(p2) owns exactly that port and names the line to delete. That item, not this one, is what unblocks
scaled brushes; this one cannot deliver it and should not claim to.

## What IS genuinely duplicated

1. **The scale/sheer refusal, in three places with three messages.** All reachable, and the ortho
   textured path passes through two of them in sequence:

   | Site | Message | Fires for |
   |-----------------------------------------|-------------------------------------------|---
   | `cli/rendering.py:_reject_transformed_brushes` | batch, lists every offender + its field | `actor preview --faces textured`
   | `preview_native._reject_scaled` | named error, first offender | both tiers, inside the solve
   | `brushcsg.py` (~line 128) | refuses loudly, cites the core gap | `brush intersect`/`deintersect`

   Each independently re-derives "is this `FScale` the identity", and they disagree on batch-vs-first
   reporting. When the core learns scale, all three have to be found and unwound.

2. **The two rasterizers.** `preview.py` is a pure-Python orthographic rasterizer (z-buffer, mip
   selection, affine UV, occlusion, on-face decals) that is deliberately stdlib-only — no PIL, no
   numpy, PPM/P6 bytes in memory — so `--faces wire` renders with no game install and no compiled
   extension. `uedcli_native.render_frame` is the Rust perspective rasterizer. These are genuinely
   two implementations of "fill a textured polygon".

3. **Backface cull.** Per-view in `preview.py` (`_is_front`, `_solved_scene`); inside `render_frame`
   for the native tier.

## Scope — decided (owner, 2026-08-22)

**S1 — one scale/sheer policy.** Collapse the three refusals onto one predicate and one message
shape, so the policy has a single home and the core-port item has a single place to unwind. Keeps
today's behavior: every path still refuses.

**S2 — both preview tiers on `build_geometry_bspcsg`.** Point `build_scene` at the same core
`solve_world_surfaces` already uses, so one trunk carves one way. **Ruled: use the core implemented
later, which is `bspcsg`** — the incremental `bspBrushCSG` port, and already materialize's default
(`architecture.md` "materialize by DEFAULT … runs `core="bspcsg"`"); `build_geometry` is the older
coarse one (`bspcsg-core-apply-scaled-brushes`: "the older coarse `build_geometry`"; `builders.py`:
"the coarse core behind `level preview --native`"). Repo history cannot date them — the tree starts
at a fresh `Initial` import (2026-07-25) with both already present — so the ordering rests on those
three statements, which agree.

No preview behavior changes: `_brush_inputs` calls `_reject_scaled` on every world brush and
`_mover_actor_world_polys` on every mover, so `level preview --native` already refuses every scaled
brush before `build_geometry` sees one. The coarse core's scale math still matters to materialize,
which selects its core separately.

**S3 — REJECTED: do not merge the rasterizers.** Merging means either putting the Rust extension on
the `--faces wire` path — which today needs neither it nor a game install — or reimplementing
perspective in Python. `--faces wire` is the tier that works when nothing else is available, and
that property outweighs removing the duplication. Recorded in `rationale/preview.md` so it is not
re-proposed.

## Sequencing

S1 → S2, independent of `bspcsg-core-apply-scaled-brushes`. That item was previously thought to gate
S2; it does not, because neither tier renders a scaled brush today. It remains the item that actually
unblocks scaled brushes, and when it lands S1's single gate is the one place to unwind.
