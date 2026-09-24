+++
priority = "p2"
kind = "debug"
summary = "UNATCO N=299 ref-build crash was a stray leftover editor container starving docker, not a real N-divergence; separately fixed a latent NAV_SELF_REF gap (Teleporter)."
+++

# unatco n299 ref-build crash: stray container resource exhaustion + NAV_SELF_REF Teleporter gap

`ladder_run.py`'s UNATCO sweep bailed at N=299 with `docker exec ... wmctrl` failing — a harness/
environment issue, not a native-materialize algorithm divergence. Root cause: a stray leftover editor
container (`uned-01a09a04-...`, never reaped after an earlier build) was starving rootless docker;
removing it made N=299 (and a `--from 299 --to 303` follow-up) pass cleanly. Along the way, found and
fixed a real latent bug: `NAV_SELF_REF`'s class whitelist (`uedcli/native/unbuilt.py`) was missing
`Teleporter`, which could leak a level's own package into `_level_referenced_packages`'s manifest under
the incremental ladder harness's prefix-slicing; fixed with regression
`test_apply.py::test_level_referenced_packages_excludes_self_pkg_seen_only_via_teleporter`. No
stray-container reaper was added (one-off, trivial manual fix; a general reaper risks killing another
session's live container on this shared host) — flag it if stray `uned-*` containers recur. A follow-on
push to N=300 hit host disk exhaustion (both filesystems >94% full, shared across worktrees) rather than
a content divergence; N=300 is unattempted pending host disk headroom, not a new blocker to root-cause.
UNATCO's ceiling from this pass is N=299, fixed.
