+++
priority = "p3"
kind = "unknown"
summary = "proceduraltex.py correctness and duplication findings"
+++

# proceduraltex.py correctness and duplication findings

Surfaced by a `code-review high` pass run against the lighting-in-photo branch (which had merged
master's procedural-texture work in) — none of these are lighting-related; not fixed as part of
that change, logging here instead. All in `uedcli/proceduraltex.py`.

- **`_render_wave` (line 386): only guards an empty `Drops[]`, not every drop having `depth=0`**
  (unlike `_render_fire`'s magnitude check for sparks, line 291-292). A `WaterTexture` body whose
  stored drops are all `depth=0` (a drained/still pool) makes `amp` zero for every drop, collapsing
  the field to a constant `0.5*diffuse_span` shaded texel — reported as a real painted frame instead
  of falling back to the placeholder, per the module's own documented rule. No test exercises
  all-zero-depth drops (existing tests all use `depth=255`).
- ~~`_compact_index` (line 169) is a third hand-rolled copy of UE1's `FCompactIndex` decoder~~ —
  superseded by `unify-ue1-package-read-primitives-into-one-rust`, which retires this onto the
  unified core (fixing the silent-overrun bug as a byproduct). The other three findings below are
  unrelated and still open.
- **Duplicated upsample-index formula** between `_render_wave` (line 413) and `_render_wet` (line
  434): `min(hh - 1, y * hh // h) * hw` / `min(hw - 1, x * hw // w)` computed independently in both;
  a future rounding/edge fix has to be applied by hand in two places.
- **`_wave_field`'s per-drop ripple splat (line 330) is O(MAX_DROPS × MAX_RIPPLE_REACH²) in pure
  Python** — up to ~230K inner-loop iterations per texture frame (49×49 span × up to 96 drops). The
  caps are a deliberate, documented mitigation, but nothing benchmarks/pins the capped worst-case
  latency; a level with several near-max-drop water surfaces could add real seconds.
