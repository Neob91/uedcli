+++
priority = "p3"
kind = "debug"
summary = "RESOLVED false finding: Island N5-N12 are byte-exact; the reported +4 orphan-vert failure was a stale editor ref in an isolated agent worktree, not a real bug."
+++

# Island N5-N12 "orphan-vert +4" was a stale-ref false finding

An isolated-worktree agent reported Island (`01_nyc_unatcoisland`) N5-N12 failing the parity gate with
a +4 world-`Model2` orphan-vert / +1 point overcount (native 511 vs editor 507 at N8), found while
corpus-validating the OceanLab N3 Pass-D fix.

DISPROVEN 2026-09-05: in the main worktree a FRESH editor ref build for Island N8 gates **PARITY: YES**
against fresh native, and so does the cached ref; cached N5/N6/N8/N12 also pass. Island N1-16 are
byte-exact. The agent's failing ref was a stale/corrupt build in its isolated `_scratch` — the same
isolated-worktree ref hazard seen earlier this session. No code change; no orphan-vert bug.

Lesson: re-verify an isolated agent's parity FAIL against a fresh ref in the main worktree before
treating it as real.
