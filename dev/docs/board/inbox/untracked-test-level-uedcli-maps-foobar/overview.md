+++
priority = "p3"
kind = "owner-question"
summary = "Untracked test level `uedcli/maps/foobar/` + the machine-local `current-level` pointer aim at it"
+++

# Untracked test level `uedcli/maps/foobar/` + the machine-local `current-level` pointer aim at it

p3. A round-1 build reviewer flagged it as live-check
  leftovers, but it PREDATES the build (it appears in this session's opening git status), so it was
  not deleted on the never-discard rule — it may be another session's scratch. If it's yours/dead:
  delete `uedcli/maps/foobar/` and re-run `level select` (the stale pointer errors cleanly once the
  dir goes). Review round 1, 2026-07-18.

<!-- ── layout-reorg review round 3 (2026-07-18) ── -->
