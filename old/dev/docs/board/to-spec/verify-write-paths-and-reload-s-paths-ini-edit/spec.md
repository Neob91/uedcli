# Spec — verify `write_paths_and_reload`'s `Paths=` ini-edit is redundant

## Goal

Decide, by experiment, whether the live mid-session `[Core.System] Paths=` ini-edit in
`packages.write_paths_and_reload` still does anything, then act per the no-cruft rule: if redundant,
delete it and its dedup check; if load-bearing, keep it and document why.

## Current state

`packages.write_paths_and_reload` (`uedcli/packages.py:166`) `docker exec`s a `sed -i` that appends
any missing `Paths=` lines into the container's `unrealtournament.ini` after boot. It is called by
`packages.ensure_load` (`packages.py:263`) before the `OBJ LOAD` loop, and shared by
`apply._materialize` and `qualify.export_and_qualify`.

Two facts already on record make it look redundant — and reframe the item's premise. The item says
"redundant once `OBJ LOAD` runs"; the sharper statement is that its Paths are ALREADY present before
boot, and a post-launch edit is separately futile:

- `editor.ensure_editor` writes the SAME full Paths set (`container_assets.paths_ini_lines`,
  including `/stubs`+`/opt/UED22`) into the ini PRE-LAUNCH via a byte-exact bind-mount
  (`editor.py:326`, `engine_ini_mount`). `write_paths_and_reload`'s own docstring calls the live
  edit "idempotent belt-and-suspenders" against that.
- The running GUI editor rewrites `unrealtournament.ini` from its boot-time in-memory config and
  ERASES any `Paths=` line added after launch (`unrealed/quirks.md` "Containers / package
  resolution", live 2026-07-01). So the mid-session `sed` edit is not just redundant — it is likely
  already a no-op the editor discards.
- The direct-reference load does not rely on Paths at all: apply resolves each file host-side and
  `OBJ LOAD FILE=<abs>`s it (spike 2 confirmed `OBJ LOAD FILE=<abs>` works with no `Paths=` entry and
  survives `MAP NEW`). Paths only matters for the indirect/by-name/demand-load linker path, which the
  pre-launch bind-mount already covers.

Not proven live: that disabling the mid-session edit changes NOTHING in a real content-map apply —
i.e. no indirect demand-load silently depended on it. Substrate-gated.

## Design (the experiment — a spike)

Live unknown → moves to `to-spike/`; harness committed under `dev/docs/spikes/<slug>/`.

Run a real Deus Ex content-map `level materialize` (a level with qualified `Texture=`/`Class=` refs
across several content packages, exercising both direct binds and any indirect demand-loads) with
`write_paths_and_reload` DISABLED (no-op stub), while KEEPING the explicit `OBJ LOAD FILE=` loop AND
the pre-launch ini bind-mount. Compare the materialized `.dx` + H3 post-verify against a run with it
enabled.

Two outcomes:

- Redundant (build succeeds, post-verify passes, artifacts equal): DELETE `write_paths_and_reload`
  and its dedup (`new = [ln for ln in path_lines if ln not in existing]`), drop the call in
  `ensure_load` and the `path_lines` plumbing it needs, and simplify `packages.py`. No deprecated
  alias, no no-op shim (`conventions.md` no-back-compat). The pre-launch bind-mount stays the sole
  Paths writer. Update the `ensure_load` docstring.
- Load-bearing (something fails to resolve without it): KEEP it, and record in
  `dev/docs/rationale/` exactly which resolution needed a mid-session Paths line that the pre-launch
  mount did not cover (with the spike as evidence), so it is not re-questioned. Pin that resolution
  with a regression where feasible.

## Edge cases & errors

- The experiment must keep the pre-launch bind-mount and `OBJ LOAD FILE=` loop intact — disable ONLY
  the mid-session edit, or the test conflates two mechanisms.
- Cover a level with an INDIRECT content-to-content dependency (e.g. `CoreTexMetal` → `CoreTexDetail`,
  `unrealed/quirks.md`), the case most likely to lean on demand-load, so "redundant" is not concluded
  from direct-bind-only levels.
- Editor flakiness: hang-detector discipline (`rules/background-work.md`).

## Tests / how it's pinned

- The removal (or retention) is exercised by the existing materialize integration path; on the
  delete outcome, an OFFLINE test asserts `ensure_load` issues the `OBJ LOAD FILE=` set with no
  `docker exec … sed` call. On the keep outcome, a pinned regression for the specific resolution that
  needed it.
- The live experiment result is a committed spike finding.

## Open questions

None — the outcome-to-action mapping is fixed by the no-cruft and measure-before-fix rules. Report
the experiment result and apply the matching branch.
