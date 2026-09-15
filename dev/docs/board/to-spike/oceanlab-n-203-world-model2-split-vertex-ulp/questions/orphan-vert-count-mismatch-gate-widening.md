# Widen the orphan-vert exclusion to tolerate a raw COUNT mismatch, not just content

## Context

2026-09-15 session: the real algorithmic bug behind the N=203 bail is fixed (see `overview.md`'s
matching update) — `Model2.points` is now byte-identical to a fresh UED22 build, and every one of
2640 live BSP node rings is coordinate-identical (`ring_diff.py`: `rings: identical=2640 rotated=0
different=0`), live vert count matches exactly (11991 both sides). `parity_gate.py` still reports
FAIL, traced to exactly one remaining difference: native's raw `Model.Verts` array has 35264 entries,
UED22's fresh build has 35265 — one extra ORPHAN entry (unreferenced by any live node ring on either
side), which desyncs `parity_gate.py`'s `_model_tail` token stream and cascades into spurious
"differences" in every later field (zones, lights, etc. — positional shift artifacts, not real
divergences; a subagent review independently confirmed this).

`NATIVE-MATERIALIZE.md`'s existing "Orphan-vert `iVertex`" exclusion already accepts that an orphan
slot's CONTENT can differ between builds ("nothing dereferences it... masked with dynamic per-build
liveness"). Its implementation (`parity_gate.py`'s `_model_tail`) was built and validated only for the
case where both sides have the SAME total vert count — it walks each side's raw array in lockstep by
position, masking an orphan's `iVertex` but still requiring both sides to have the same number of
verts overall. A genuine COUNT difference (this case) was never exercised before and isn't handled:
it isn't masked, it desyncs the comparison.

Whether this one extra orphan slot is itself faithful-and-explainable (UED22's real pipeline produces
it as a byproduct of the SAME dead-node-surf-survives-to-bspOptGeom mechanism the landed fix ports,
via `merge_near_points`'s ring-collapse leaving a stale trailing pool slot) or is some other,
unexplained artifact was NOT traced this session — see `overview.md`'s "Not yet closed" note for the
concrete next step (trace which node's pre-merge `NumVertices` differs between native and a fresh
UED22 capture, the same way the surf/point mechanism was pinned).

Per `NATIVE-MATERIALIZE.md`'s own rule ("Any NEW candidate exclusion needs an opus review confirming
inconsequence + the owner's explicit yes before it counts") and `CLAUDE.md`'s "every decision that is
the owner's to make goes through `AskUserQuestion`" — this needs the owner's call, not a silent gate
edit. `parity_gate.py` was NOT modified this session.

Options (not exhaustive):

- **Widen the exclusion to tolerate a count mismatch** (not just content) in the orphan-vert class —
  `_model_tail` would need to stop walking the raw array positionally and instead derive its token
  stream from live node rings (order-stable) plus an UNORDERED, uncompared bag of orphan entries on
  each side. Mechanical, but touches the one shared parity script every level's every N goes through
  — a real "reference-methodology question" per `NATIVE-MATERIALIZE.md`'s own definition of when to
  ask.
- **Chase a byte-exact orphan count instead** (no gate change) — trace the real mechanism producing
  UED22's extra orphan slot (see `overview.md`) and reproduce it natively. Preferred if tractable
  (closes the item with zero gate risk), but not yet attempted/scoped this session.
- **Something else.**

## Answer

<!-- Empty = open. Write the decision here. -->
