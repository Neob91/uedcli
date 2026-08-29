+++
priority = "p1"
kind = "debug"
summary = "Native BSP is node-exact against the editor's paste-built golden on 01_NYC_UNATCOHQ (734 brushes) but not on 09_HONGKONG_WANCHAI_MARKET (1304 brushes): nodes 11381 vs 11648, leaves 3240 vs 3371, points 16522 vs 16791, vectors 481 vs 487, surfs 5283 vs 5284. Same pipeline both sides."
+++

# Native BSP matches the editor on UNATCO but not on `WANCHAI_MARKET`

Fixed by `5b0a022` (try_to_merge step-3 neighbour test switched from SAME 0.002 to NEAR 0.015):
Wanchai's remaining gap was a fractional-plane door-seam fusion miss. Wanchai now node-exact
(11648=editor), surfs exact (5284), UNATCO unaffected. Regression test
`try_to_merge_step3_fuses_a_fractional_brush_seam_gap`.
