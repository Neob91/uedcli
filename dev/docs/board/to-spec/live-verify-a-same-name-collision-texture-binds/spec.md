# Spec — live-verify a same-name-collision texture binds through a real `apply`

## Goal

Prove end-to-end, through a real `level materialize`, that a brush face whose `Texture=Pkg.Name`
names a package that exists TWICE on the composed path (a project overlay shadowing a same-named base
package) binds to the intended (first-wins) texture object — not the shadowed one, and not unbound.
The only prior evidence is a synthetic `MAP IMPORTADD` probe that found the qualified-`Texture=`
auto-demand-load bug (`unrealed/quirks.md` "T3D format"); no test drives the collision case through
the shipped build path.

## Current state

The apply path decides collision precedence HOST-SIDE, then loads the resolved file explicitly:

- `packages._first_match` (`uedcli/packages.py:147`) is first-wins over
  `editor_search_dirs(dirs)` = `[stub cache, UED22, *composed dirs]` (`packages.py:21`). The first
  dir holding `<pkg>.<ext>` wins.
- `obj_load_entries` (`packages.py:94`) resolves each referenced package to that host file;
  `ensure_load` (`packages.py:239`) `OBJ LOAD FILE=<remapped path>`s each one (`packages.py:270`),
  so only the first-wins file becomes resident.
- `apply._level_referenced_packages` (`uedcli/apply.py:49`) is the set fed in — the packages the
  level's own `Class=`/`Texture=` refs name.
- Precedence for the by-name/demand-load path is separately governed by `[Core.System] Paths` order
  (stubs, UED22, then mounts), live-proven first-wins in `dev/docs/spikes/2026-07-01-paths-precedence/`.

So in theory the collision is already decided host-side and the editor only ever sees the intended
file. What is unverified: that a real `materialize` of a level whose face references the overlaid
package produces a `.dx` where that face binds to the OVERLAY texture object, through the full
drive + H3 post-verify. Substrate-gated; cannot be checked offline.

## Design (the verification — a spike)

This item carries a live unknown, so it moves to `to-spike/`; the spike folds its finding back here
and commits its harness under `dev/docs/spikes/<slug>/` (`rules/spikes.md`).

Setup (ephemeral editor, never the standing container; retail install via `UEDCLI_TEST_INSTALL`):

1. Pick a small base content package `P` holding texture `P.T` with a distinguishable image (as the
   paths-precedence spike did with `CoreTexMetal` → 3 `BP_FX` textures). Build an overlay dir holding
   a same-named `P` whose `P.T` is a DIFFERENT, identifiable image.
2. Compose the config so the overlay dir sorts FIRST (project-shadows-base), base second.
3. Author a one-brush trunk level whose face carries `Texture=P.T` (and a `PlayerStart`/`LevelInfo`
   as materialize needs).
4. `level materialize --out collision.dx` against that composed path.

Assert:

- The build succeeds (rc 0) and post-verify passes.
- The materialized face binds to `P.T` — the object resolved from the OVERLAY package, not the base.
  Confirm by an independent readout of the built `.dx` (offline `upackage`/`utexture` decode of the
  bound texture's pixels, or a UCC `batchexport` of the map's texture set) matching the overlay
  image, not the base image. Never trust the editor's re-export name alone — decode the bytes.
- A control run with the dirs in the OTHER order binds to the base image, proving order decided it.

## Edge cases & errors

- Overlay and base packages MUST be small/simple — a large complex `.u`/`.utx` can crash the editor
  on duplicate load (`Palette … Serial size mismatch`, `dev/docs/spikes/2026-06-19-class-package-collision.md`).
- If `P.T` is not resident when the face imports, it re-exports with NO `Texture=` (unbound) — that
  is the documented failure this proves absent, so an unbound face is a FAIL, not a skip.
- Editor flakiness: run under the hang-detector discipline (`rules/background-work.md`) — tracked
  background job plus a ~20-min fallback timer; never a single open-ended wait.

## Tests / how it's pinned

- OFFLINE regression (runs in CI): assert `packages._first_match` / `obj_load_entries` pick the
  first-listed dir's file under a same-name collision built in `tmp_path`. This pins the host-side
  decision that makes the binding correct — the part that can rot in normal development.
- The live end-to-end result is pinned as a committed spike finding (harness + a golden note under
  `dev/docs/spikes/<slug>/`), and, if a retail install is present, an OPTIONAL substrate-gated
  integration test that re-runs the collision materialize. It does not run in CI (no install).

## Open questions

- Whether a live run is warranted at all, or the item closes as already-covered by the host-side
  resolver plus the 2026-07-01 paths-precedence spike. See `questions/`.
