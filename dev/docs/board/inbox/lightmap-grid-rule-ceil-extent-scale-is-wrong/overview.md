+++
priority = "p2"
kind = "docs"
summary = "spikes/2026-07-15-native-materialize/sections/20-lighting-bake.md §22 states the editor's lumel grid dim is ceil(extent/lumel_scale), fitted 484/484 on Test_Castle. On UNATCO that form misses 263 of 6868 axes; ceil((extent-0.25)/lumel_scale) fits 6868/6868 and still satisfies every boundary §22 lists. The doc needs correcting (owner approval required)."
+++

# Lightmap grid rule `ceil(extent/scale)` is wrong on real content

`sections/20-lighting-bake.md` §22 finding 1 says the editor's stored `UClamp`/`VClamp` is
`Clamp(ceil(extent / lumel_scale), 2, 256)`, fitted 484/484 against `Test_Castle.dx`. `light.rs`
shipped that form.

Refitted against the editor's own `LIGHT APPLY` output on `01_NYC_UNATCOHQ` (3434 lit records, 6868
axes), predicting each record's stored dim from that record's own surf extent
(`spikes/2026-08-27-native-light-apply-parity/harness/grid_formula_fit.py`):

| candidate | axes exact |
|---|---:|
| `ceil((extent - 0.25) / scale)` | **6868 / 6868** |
| `ceil(extent / scale)` (§22) | 6605 / 6868 |
| `round(extent / scale)` | 6379 / 6868 |
| `trunc((extent - 0.25)/scale - 0.5) + 1` (§4) | 6116 / 6868 |
| `trunc(extent / scale) + 1` | 4454 / 6868 |

The two top forms differ only where the extent sits within 0.25 **above** an exact multiple of the
lumel scale — e.g. UNATCO surf 7, extent 160.001831 at scale 32: `ceil(5.00006) = 6`, editor stores
5. `Test_Castle`'s axis-aligned geometry never produces such an extent, which is why §22's form
scored 484/484 there and only broke on real level content. Every boundary §22 cites still holds under
the corrected form (extent 64 at 32 → 2, 1024 at 32 → 32, 80 at 32 → 3, 16 at 32 → clamped to 2).

Also re-confirmed unchanged on the same oracle: `Pan == min - 0.125` on 3434/3434 records, and the
texel scale `(extent + 0.25)/(size - 1)` on 6866/6868 axes (the 2 residuals are records whose surf
base/TextureV differ from native by f32 — the upstream Points/Vectors gap, not this rule).

`light.rs` is fixed and the Rust regression `axis_grid_matches_editor_ceil_rule` now carries the two
UNATCO teeth cases. The DOC still states the superseded rule; correcting it needs the owner's yes.
Proposed replacement text for §22 finding 1 is the table above plus the surf-7 example.
