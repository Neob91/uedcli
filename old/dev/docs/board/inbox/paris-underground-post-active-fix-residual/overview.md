+++
priority = "p3"
kind = "debug"
summary = "After the Round-4 CsgOper::Active fix (vandenberg-gas-csg-active-csgoper-brush-causes), 11_Paris_Underground moves nodes d=-108/leaves d=-4 -> nodes d=+5/surfs+leaves exact, verts d=+40, points d=+1 vs the cached golden. A distinct, smaller over-build mechanism remains; the n=2..272 prefix goldens died with their worktree, so localizing it needs a fresh prefix search."
+++

# Paris Underground post-Active-fix residual: nodes +5, verts +40, points +1

Post-fix offline measure (native `build_geometry_bspcsg` vs cached golden): native 2432/1396/376
(v=34197 p=4199 vec=172) vs golden 2427/1396/376 (v=34157 p=4198 vec=172). Was 2319/1396/372
(d=-108/+0/-4, v d=-1306, p d=-143) before the fix. First divergence is no longer brush n=2
(the 2-brush prefix is now editor-exact, pinned in cargo `active_led_pair_keeps_buried_faces_uncut`);
where it moved to is unmeasured — the spike's prefix goldens (`_scratch/pu-prefix/`) are gone, so a
new prefix search (`dev/docs/spikes/2026-09-03-built-parity-worst-tier/harness/pu_prefix_search.py`)
is needed to localize.

Update: with the Pass-D kill/retarget (done item `pass-d-zone-split-emits-degenerate-zero-area`),
nodes d = **+1** (surfs/leaves exact) — 4 of the +5 were killable ringless fragments.
