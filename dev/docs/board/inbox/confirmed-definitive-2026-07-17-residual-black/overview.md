+++
priority = "p1"
kind = "debug"
summary = "CONFIRMED DEFINITIVE (2026-07-17): residual black = game BSP render-traversal skips present, baked-LIT surfaces; not lighting, not solidity, not normals"
+++

# CONFIRMED DEFINITIVE (2026-07-17): residual black = game BSP render-traversal skips present, baked-LIT surfaces; not lighting, not solidity, not normals

p1 **CONFIRMED DEFINITIVE (2026-07-17): residual black = game BSP render-traversal skips
  present, baked-LIT surfaces; not lighting, not solidity, not normals.** Geometry-matched value-level
  lightmap diff (NOT array-index — the two 485-surf Models order surfs differently) + exact-game-camera
  raycast settle it. (A) native vs editor render-dark = 54 vs 54; of 459 geometry-matched twins, exactly
  ONE native-dark-editor-lit regression (surf#278). (B) Raycast of the 4 task poses into native geometry:
  100 % lit surfaces in view, **0 % baked-dark, 0 % void** — yet the game renders s76 32 %/s34 14 %/s69
  18 %/s07 16 % black. So under every black pixel there IS a present, lit native surface the ENGINE
  doesn't draw. Structural diff pins it: native `node.i_zone (0,0)×450` + node_flags ~all-0 vs editor's
  rich `NF_*` (8/13/16/24) + `(0,2)×1058`; interior zone renumbered. The task's "zones ruled out" was
  the Visibility MASK (all 0xff, never computed even on real maps — §70 §0), NOT the node-level
  portalization, which IS the mechanism. Fix = the zone/leaf/node-flags **portalization** port
  (`zones.rs`/`passes.rs`/`build.rs`/`model_write.rs` — the concurrent WIP), NOT `light.rs` and NOT the
  bspcsg surf-normal. Evidence + harness: spike §20 §19, `harness/blackcause_*.py`. **`light.rs` needs no
  change for the residual black.**

<!-- ── layout-reorg review round 1 (2026-07-18) ── -->
