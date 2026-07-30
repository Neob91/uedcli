+++
priority = "p2"
kind = "owner-question"
summary = "`--wall` vs `--floor` distinction I chose:"
+++

# `--wall` vs `--floor` distinction I chose:

follow-ups from build #5 (poly align, item 11)` — DEFERRED pieces + interpretations
from `polyalign.py` (design: decisions.md 2026-07-18 21:40 UTC). Flagging for your eyes:
1. **`--wall` vs `--floor` distinction I chose:** the two flags are mathematically identical
   (adopt-seed is axis-agnostic; `_tex_basis` handles both fresh cases), so I gave each a concrete
   ORIENTATION GUARD — `--wall` requires the coplanar set to be vertical (normal ≈ ±X/±Y),
   `--floor` horizontal (normal ≈ ±Z). This makes the two flags catch mistakes (aligning a floor
   with `--wall`) instead of being redundant. Say if you'd rather they behave identically (one flag
   with an alias), or want the guard relaxed for near-vertical/near-horizontal slants.
2. **`--fit-perimeter` offline meaning:** with no texture loaded, "integer number of texture
   repeats" isn't computable (needs the pixel width). I implemented it as snapping the around-ring
   density so the TOTAL U texel count is the nearest integer — the sub-percent scale nudge the seam
   needs. A true pixel-tile-seamless meet (period = texture width) is a follow-up once the catalog
   can supply dimensions to the aligner.
3. **Scaled textured brushes:** continuity math uses the rotation-only frame transform (matching
   `texframe.world_uv_frame`), NOT `actor_linear` (which includes MainScale/PostScale). For
   a SCALED textured brush the written frame will be slightly off. Out of v1 scope (builders emit
   unscaled brushes); follow-up if scaled-brush texturing becomes a real need.
4. **DEFERRED modes (v2, per the decision):** `--face` fit-one-texture-to-a-surface (single-poly,
   closer to `brush poly set`); turning (non-coplanar) wall runs (per-face accumulate-along-run,
   like `--ring` unrolled); sphere wrap (needs per-vertex UV the flat per-poly frame can't express);
   an explicit `--seam <brush:poly>` anchor (v1 seam = first face in input order).
5. **`brush poly find` is single-brush** (`<brush>` positional, like `poly list`). A cross-brush
   coplanar/adjacency `find` (`--coplanar <seed>`) is the natural next producer — would let a wall
   run be discovered by geometry rather than by folder — but it's its own spec.
