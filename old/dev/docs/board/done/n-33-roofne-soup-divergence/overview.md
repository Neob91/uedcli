+++
priority = "p1"
kind = "debug"
summary = "N=33 `RoofNE` soup divergence — SUPERSEDED, see the N=33 entry above"
+++

# N=33 `RoofNE` soup divergence — SUPERSEDED, see the N=33 entry above

p1 **N=33 `RoofNE` soup divergence — SUPERSEDED, see the `[spike] p2` N=33 entry above.**
The §10.4 "clips against TowerNE's **diagonal** face" diagnosis was WRONG: traced to instruction
level 2026-07-17 (`sections/82 §10.6`), the spurious `x=112.0` is the **axis-aligned** `Merlon_y4jykf`
east face on a **DEAD** node (`node[80]`, `nv=0`), and the split-selection is faithful — the real
divergence is a cumulative incremental-tree-ORDER one, blocked on an editor-tree oracle. No local fix.
