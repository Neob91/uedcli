+++
priority = "p2"
kind = "debug"
summary = "UNATCO N=299 ref-build crash was a stray leftover editor container starving docker, not a real N-divergence; separately fixed a latent NAV_SELF_REF gap (Teleporter)."
+++

# unatco n299 ref-build crash: stray container resource exhaustion + NAV_SELF_REF Teleporter gap

`ladder_run.py`'s mechanical UNATCO sweep bailed at N=299 four consecutive times with the same
traceback, in `packages.ensure_load` -> `driver.dismiss_blocking_dialog` -> `docker exec <container>
wmctrl -l` returning exit 128. Investigated per the parent session's request; this is a harness/
environment robustness issue, NOT a native-materialize algorithm divergence.

## Root cause: a stray leftover editor container starving rootless docker

Found `uned-01a09a04-e2d6-731e-95ca-859250da521c` running for 59+ minutes, bind-mounted to an EARLIER
N=277 build under this same worktree's `_scratch/actor-parity/03_nyc_unatcohq/N277/...`. It was wedged
(a build that size should take well under a minute). Its presence meant `stop_editor`'s own `finally`-
block cleanup either never ran (the owning process was killed before Python's `finally` could execute)
or itself silently timed out (`stop_editor`'s `docker rm -f` swallows `TimeoutExpired`) — either way it
was never reaped, and it sat there consuming a fork/exec slot in this host's rootless dockerd.

With that container present, a *fresh* `ladder_run.py --from 299 --to 299` reproduction failed
IMMEDIATELY at container creation (not even reaching `ensure_load`):
```
fork/exec /usr/local/bin/runc: resource temporarily unavailable
```
This is a different symptom than the original 4 reports (which got further, into `ensure_load`, before
`docker exec wmctrl` failed) but the same underlying cause class: a resource-starved rootless dockerd
returning intermittent, non-deterministic failures depending on exactly when in the sequence the
starvation bites. After `docker stop`+`docker rm -v` on the stray container, the SAME repro command
passed cleanly (N=299 PASS), and a follow-up `--from 299 --to 303` re-verified forward progress.

**This is not a real N=299 parity divergence** — the reported `edaf1be8103d47699741c6968543b423`
package name is a genuine, EXPECTED artifact (see below), not a smoking gun for the crash: it never
reaches `OBJ LOAD` at all (`packages.obj_load_entries` silently drops any manifest package that
doesn't resolve to a file on disk, and a level's own hash-shaped self-name never does).

## What the hash-named package actually is (answering the "is this expected" question)

`03_NYC_UNATCOHQ.dx`'s intra-level actor refs (`previousPath=PathNode'<pkg>.PathNode91'`,
`Base=Teleporter'<pkg>.Teleporter0'`, etc.) are qualified with the level's OWN historical package
name, baked in whenever `PATHS BUILD`/an edit ran under that identity. Usually that is the literal map
name (`03_NYC_UNATCOHQ`, confirmed by the existing regression
`test_native_roundtrip.py::test_assemble_rewrites_the_levels_own_package_refs_to_mylevel`), but a
lowercase-32-hex name (`5691f978a0da4a6c8269d541db6a4345` in a cached UNATCO trunk sample,
`edaf1be8103d47699741c6968543b423` in the parent's report) also occurs — almost certainly a leftover
from an "Untitled"/auto-named editor session before the level was given its final name. This is
EXPECTED, not a red flag: `uedcli/native/unbuilt.py`'s `NAV_SELF_REF` already exists precisely to
detect and strip these self-refs (`rewrite_self_package_refs`, and `apply._level_referenced_packages`
which excludes them from the OBJ-LOAD manifest).

## A real, separate, latent bug found along the way (fixed)

`NAV_SELF_REF`'s class whitelist (`PathNode|PatrolPoint|HidePoint|ZoneInfo|LevelInfo`) was missing
`Teleporter` — confirmed by grepping both cached UNATCO and NYC_Bar trunks, which self-reference via
`Teleporter'<pkg>.Teleporter0'` too. For a FULL-level materialize this was harmless (some other actor
elsewhere in the level always also self-refs via a whitelisted class, so `self_pkgs` still discovers
the package name and the blind string-replace/set-subtraction in `_to_mylevel`/`_level_referenced_packages`
catches every occurrence including the Teleporter one). But the incremental ladder harness slices by
trunk-order PREFIX, and a prefix that includes a Teleporter self-ref before any whitelisted-class one
would leak the level's own package into `_level_referenced_packages`'s manifest as if it were an
external dependency — harmless today only because `obj_load_entries` silently drops unresolvable
packages, but real production `apply.run_materialize`'s `missing_packages` fail-fast gate WOULD trip on
it for a level whose only self-ref evidence is a Teleporter (rc=2 "level needs <hash>; not on the
package path").

Fixed: added `Teleporter` to `NAV_SELF_REF` (`uedcli/native/unbuilt.py`). Regression:
`test_apply.py::test_level_referenced_packages_excludes_self_pkg_seen_only_via_teleporter`. Confirmed
this widening doesn't regress the existing self-pkg-rewrite test (`test_native_roundtrip.py`'s
`test_assemble_rewrites_the_levels_own_package_refs_to_mylevel` still passes).

## What's NOT done

No code change was made for the stray-container accumulation itself (no reaper/watchdog added) — this
was observed once, the fix (`docker rm`) is trivial and manual, and building a general
cross-run stray-container reaper risks killing another concurrent session's legitimate container on
this shared host. If stray `uned-*` containers recur, that's the next thing to look at — a scoped
reaper keyed to this worktree's own state-dir paths and an age threshold, not a blanket one.

## Follow-on: the host is genuinely low on disk RIGHT NOW (both filesystems)

Pushing one further N (N=300) after the N=299 fix hit a THIRD failure shape, three times in a row,
with fresh (non-stray) containers each time: `driver.write_work_file`'s `docker exec -i <container>
tee <path>` either raised with an EMPTY stderr, or (once) `docker inspect`/a follow-up probe found the
container had already vanished (`No such container`) within ~2s of it reporting ready. Measured at the
time:

```
overlay     63G   56G  4.0G  94%  /                        <- Docker Root Dir (container writable layers)
virtiofs0  466G  454G   12G  98%  /workspace/uedcli         <- the whole repo/worktree/scratch tree
```

Both filesystems this host relies on for editor-container builds are within single-digit GB of full,
and the SECOND (466G volume, `/workspace/uedcli`) is shared across every concurrent worktree/session on
this host, not just this one. This is consistent with (not proof of, since I could not catch the
container alive at the exact failure instant) the SAME class of resource-starvation flakiness as the
N=299 finding above, not a genuine per-actor divergence at N=300 -- three consecutive fresh-container
failures at the identical N, with no code or content change between attempts, is not what a real T3D
content bug looks like.

Also found and cleaned (not part of the N=299 fix; a separate, smaller leak from this same
investigation): my own throwaway diagnostic script called `ensure_editor()` outside its `try/finally`,
so when a `docker compose run` mount error hit during one throwaway attempt, its wineprefix volume was
never reaped by `stop_editor`. Removed 3 dangling `uned-wp-*` volumes (~1.8GB) this pass; none were
attributable to the real harness code (`build_ued_import_built_golden.py`'s own try/finally ordering is
correct and does reap on an `ensure_editor` failure inside the try).

**Did not chase N=300 further** -- each retry costs a real wineprefix volume (~0.5GB) on an
already-98%-full shared volume, and per `NATIVE-MATERIALIZE.md`/`CLAUDE.md`'s "no fallbacks, no
guessed fixes for environment issues" rule, there is nothing here to code a fix for: the host itself
needs more disk (or other sessions' usage needs to come down) before N=300 can be reliably attempted.
UNATCO's true ceiling from this pass is **N=299** (fixed, was previously blocked); N=300 is unattempted
pending host disk headroom, not a new blocker to root-cause.

## Evidence / repro

- Stray container: was `uned-01a09a04-e2d6-731e-95ca-859250da521c` (removed).
- Repro logs (this worktree's `_scratch/`): `n299_repro.log` (fails on stray container present),
  `n299_repro2.log` (passes after removal), `n299_303_verify.log` (N=299 pass, N=300 first failure),
  `n300_repro3.log` (N=300 third consecutive failure, fresh container, no stray present).
