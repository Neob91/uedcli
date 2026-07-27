+++
priority = "p?"
kind = "unknown"
summary = "Lightmap `PF_Portal` over-cull fixed — portals now get records"
+++

# Lightmap `PF_Portal` over-cull fixed — portals now get records

— BUILT 2026-07-18
(spike §20 §21). `light.rs::PF_NO_LIGHTMAP` wrongly included `PF_Portal`, so native skipped the
4 two-sided water-portal surfaces the editor lightmaps. Corrected to the editor's exact skip-mask
`0x400081 = PF_Unlit|PF_FakeBackdrop|PF_Invisible` (grounded in the oracle `Test_Castle.dx` +
disasm `Editor 0x100a6031`; pinned by Rust test `lightmap_skip_mask_matches_editor_disasm`).
Raw bytes: `LightMap` 480→**484 recs / 14528 B == editor**; `LightBits` 48015→48431 B (gap
1498→1082); `Lights` 3928→3955. Remnant: the far-larger `Lights` gap (→11392) is the missing
per-leaf permeating region — see the `[spec]` item in `board/inbox/`.
