+++
priority = "p?"
kind = "owner-question"
summary = "Surfs section = the two object-ref fields; PINNED as session artifact + oracle question raised (2026-07-18, `sections/83-surf-ref-order-session-artifact.md`, harness `surf_ref_order_analysis.py`)"
+++

# Surfs section = the two object-ref fields; PINNED as session artifact + oracle question raised (2026-07-18, `sections/83-surf-ref-order-session-artifact.md`, harness `surf_ref_order_analysis.py`)

Re-investigated the Surfs residual (a follow-up asked whether native's actor **export order** is a
deterministic lever for per-surf `iActor`). Finding: the raw Surfs section is **21.2 %**; the mismatched
bytes are **two object-table-INDEX fields** — `iActor` (export index, 0 %) + `texture_ref` (import index,
0 %) — **plus a real ~114 B `pBase` tail** (87 %, owned by the still-open point-pool port, not this layer).
The other 7 surf fields are byte-exact. Both refs resolve to the **right name** 485/485, and the trunk
**carries the names** (95/96 brush names shared with the golden) — so it is purely an index-**ORDER**
problem, not a missing-identity one. Against the golden the order is NOT trunk order, NOT `Actors[]` order,
NOT FName-hash and NOT lexicographic (clustering rules those out; it does NOT by itself prove "session"
— clustering also fits a name-grouped/paste rule). Reachability (full offset sweep; an earlier narrow sweep
under-reported this): deterministic-from-trunk brush order caps at **~40 %**; the editor's own brush ORDER,
compacted, reaches **92.1 %**; editor-EXACT indices 93.3 %, +texture 98.7 %. So the lever is the brush
**ORDER**, worth ~+19 pts deterministically and ~+71 at the editor's order. I did **NOT** land an assembly
reorder — it's premature (see oracle below) and touches ref-bearing sections whose editor bytes are
themselves session-ordered. **TWO decisions for you:** (a) **Oracle (gating)** — the golden used everywhere
is the *hand-authored* `Test_Castle.dx`; `direction.md`'s bar is "UnrealEd's build of the **same trunk**".
A clean editor `MAP IMPORT` of our trunk might number exports in deterministic T3D/trunk order, which would
make the ~40 % deterministic ceiling the WRONG number (true reachable could approach 92 %). Want a `[spike]`
to `level materialize` the castle trunk through the editor and re-run `surf_ref_order_analysis.py` against
*that*? (b) If (a) says trunk order matters, want the assembly reorder (all actors first, then subobjects —
the editor's block structure) landed then? Currently NOT done, pending your call.
