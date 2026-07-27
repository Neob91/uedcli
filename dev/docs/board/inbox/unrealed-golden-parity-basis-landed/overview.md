+++
priority = "p2"
kind = "chore"
summary = "UnrealEd-golden parity basis landed (spike §89) — TWO follow-ups"
+++

# UnrealEd-golden parity basis landed (spike §89) — TWO follow-ups

The correct
native-parity basis is now UnrealEd's OWN build of the SAME trunk, not the shipped `.dx`
(`harness/build_ued_golden.py`; proven on UNATCO). Findings: (a) UnrealEd BUILDS our trunk headless
fine, deterministically (~30 s), BUT `apply.run_materialize` cannot do it at scale — its editor
driver `wine_ctl exec` is fire-and-forget (~0.3 s, no wait-for-completion), so `MAP SAVE`/`docker cp`
race the still-running rebuild and fail "nothing written". The harness works around it with a CPU
idle-barrier. **Should this barrier fold into production `run_materialize`/`driver`?** (I did NOT
touch the concurrent-session file.) (b) vs the golden, native's geometry SOUP is near-exact
(Points −0.07 %, Bounds +0.2 %, LeafHulls −0.6 %) but native **over-splits Leaves 3.6×** (2759 vs
762) and over-produces Vectors/Verts ~+24 % — native builds a less-merged BSP than UnrealEd's `GOOD`
batch rebuild of the identical brushes. That is the sharpest geometry target now; chase against the
golden, not the shipped map. (Methodology validated: UnrealEd batch-rebuild vs the incrementally-
authored shipped map differ +21.7 % nodes / −66 % leaves on the SAME 734 brushes — most of §84's
native-vs-shipped gap was that, not native.) **[SUPERSEDED re: Leaves by §91 — the "over-splits
Leaves 3.6×" was a CORRUPT GOLDEN, not a native defect; see the §91 item below. Vectors +24 %
stands as a real residual; re-measure Verts once the golden is re-cached un-truncated.]**
