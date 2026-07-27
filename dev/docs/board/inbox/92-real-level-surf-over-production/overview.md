+++
priority = "p1"
kind = "owner-question"
summary = "§92 real-level surf over-production (+82/+146) was STALE — current native 3609 vs golden 3616 (−7 under); needs direction on the next parity target (2026-07-19 reconcile)"
+++

# §92 real-level surf over-production (+82/+146) was STALE — current native 3609 vs golden 3616 (−7 under); needs direction on the next parity target (2026-07-19 reconcile)

The "+82 surf / +146 vector
over-production" premise driving §92 §12's staged gdb-grind is obsolete: (a) `unatco_subset.py` had a MOVER
CONFOUND (28 DeusExMovers pushed through world CSG → +221 phantom surfs; fixed `cd56c1ae2`), which
manufactured the "170 axis-aligned over-production in (213,396]" redirect; (b) the +82 figure itself was
measured against STALE pre-current-core `.dx` (3698 surfs). A fresh mover-clean `build_native_unatco.py`
gives **3609 surfs vs golden 3616 = −7 (slight UNDER-production)**, two native paths agreeing. So the "weeks
of gdb-grind for coplanar over-production" plan is retired. Open questions for Andrzej: is the −7 a real hole
or the subtract-into-void baseline; what is the real remaining byte residual (compiled parity is only 19.07%,
mass in Nodes/Verts/LeafHulls — `_scratch/baseline-reconcile/`); the +146 VECTOR delta is NOT stale (all
texture axes, 745 vs 599); the golden-node-basis question is now less critical. Docs reconciled: `PARITY-STATUS.md`, §92 §2/§3/§12 banners, `decisions.md` bspValidateBrush note.
