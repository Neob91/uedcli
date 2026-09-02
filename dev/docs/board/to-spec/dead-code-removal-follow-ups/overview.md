+++
priority = "p3"
kind = "chore"
summary = "Dead-code removal follow-ups"
+++

# Dead-code removal follow-ups

(from the 2026-07-19 store-deletion dead-code removal):
(a) drop `dispatch._apply_set`'s now-unused `packages=` positional param + its two call sites
(stash-apply, prefab-apply) — deferred from the removal because it's a 4-touch-point `dispatch.py`
edit; do when `dispatch.py` is quiet. (b) Docs/comment sweep: `export_and_qualify` mentions survive
in `apply.py`/`stub.py`/`packages.py`/`driver.py`/`architecture.md` (+ a couple of tests), and
`dispatch.py`'s "no editor_lock" comment references the now-deleted helper — prose only, no live code.
