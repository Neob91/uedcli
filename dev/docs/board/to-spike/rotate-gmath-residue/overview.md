+++
priority = "p3"
kind = "debug"
summary = "Does the GMath rotator residue on a long-lever rotate matter, and against which tolerance band?"
+++

# Does the GMath rotator residue on a long-lever rotate actually matter, and against which tolerance band?

A rotate orbits `Location` through UE1's GMath matrix, whose entries are not
exactly 0/±1, so the stored `Location` picks up `|L−P| × deviation` of dust. Measured on the real
levels and code (build/plan review, 2026-07-26): worst single-entry deviation over all 64 CARDINAL
(pitch,yaw,roll) combos is **1.7484555314695172e-07** at `(49152,16384,16384)` — *twice* the
lone-yaw figure, so dust reaches `emit.CLEAN_EPS` (0.001) at **5719 uu**, not 11438. Live case:
two actors 24,000 uu apart rotated 90° about their midpoint store `X=11999.998951`. Silently.

**What the spike must settle, because a plan built on guesses was refuted:**

1. **Which band is the criterion at all.** `docs/leveldesign/general/geometry-and-bsp.md` calls
   "off-grid coordinates cause BSP holes" **a myth, explicitly false**, and names discrete tolerance
   bands instead — the tightest being the **~1e-4 uu vertex merge**. `CLEAN_EPS` is an *emitter
   cosmetic* band, not a geometric one. Judged against 1e-4 the threshold falls to ~572-1144 uu and
   would fire on ordinary content; judged against `CLEAN_EPS` it barely fires at all. Does a
   0.001-0.011 uu residue change a built `.dx` — vertex merge, coplanarity, node count? Build the
   same level with and without the residue and diff.
2. **Is it detectable exactly rather than by threshold?** For a cardinal delta the exact matrix is
   all `{0,±1}`, so `exact = P + R_int·(L−P)` in `Decimal` is a free ORACLE: compare against
   `rotate_point`, report the real residue. It writes nothing, so it does NOT touch the
   byte-identity-with-UnrealEd constraint that rules out *substituting* the exact matrix. This
   removes the need for any threshold constant.
3. **Scope.** `brush scale --by` has **no** dust — its orbit is pure `Decimal`
   (`dispatch.py`, `Loc' = P + S∘(Loc−P)`), verified exact at 31,000 uu. Only `rotate --by` is
   affected, and only for deltas that are 90° multiples: 8 of the 64 cardinal combos (every mix of
   0 and 49152) are already bit-exact, and a NON-cardinal delta is off-grid by nature at any lever
   arm (`--by 0,6000,0` at 100 uu already stores `83.906031`), which spec §7.4 accepts.
4. **Reachability.** At 5719 uu, whole-level rotates of the real trunks hit 2 actors in
   ContainerYard and 2 in DiveBar (max lever 11392); at 11438, zero. So the band that matters is
   exactly the one a lone-yaw constant cannot see.

Findings fold into `specs/2026-07-26-rotate-pivot-grid-aligned-center.md` §7.4. **Do not write the
warning first** — a plan that assumed the lone-yaw constant, per-axis distance, and `brush scale`
scope was refuted on all three (plan round, 2026-07-26). *(2026-07-26.)*
