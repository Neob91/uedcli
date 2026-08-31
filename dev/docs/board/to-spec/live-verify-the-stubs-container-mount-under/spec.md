# Spec — live-verify the `/stubs` container mount under the env-fed source

## Goal

Confirm on a live editor container that a real `level materialize`/`level photo` mounts the v69
stub cache at `/stubs` from the env-fed source and actually `OBJ LOAD`s the stubs from there. The
`${HOME}`-interpolation / stripped-env concern is already closed in code (a board chore, 2026-07-18);
the one remaining leg is the end-to-end confirmation, which is substrate-gated.

## Current state

The wiring is in place and offline-inspectable:

- `editor.ensure_editor` sets `UEDCLI_STUB_CACHE = str(config.stub_cache_root(create=True))` — an
  absolute path — in the compose env (`uedcli/editor.py:337`), feeding the compose file's `/stubs`
  volume source `${UEDCLI_STUB_CACHE:-${HOME}/.uedcli/cache/stubs}`. `stub.ephemeral_build_container`
  passes the same env.
- `/stubs` is FIRST on the generated `[Core.System] Paths` (`container_assets.paths_ini_lines` →
  `Paths=/stubs/*.u`, `uedcli/container_assets.py:88`), so a v69 stub shadows a same-named v68 `.u`.
- Host-resolved stub files remap to `/stubs/…` in `packages._remap_to_container`
  (`uedcli/packages.py:214`), and `ensure_load` `OBJ LOAD FILE=`s each resolved package
  (`packages.py:270`).

Unverified live: that a materialize/photo whose level references a stubbed package actually finds
and loads the stub from `/stubs` inside a real container (the mount is populated, visible, and the
`OBJ LOAD FILE=/stubs/<pkg>.u` binds).

## Design (the verification — a spike)

Live unknown → moves to `to-spike/`; harness committed under `dev/docs/spikes/<slug>/`.

1. With a retail install (`UEDCLI_TEST_INSTALL`) and a per-user stub cache built for one referenced
   code package, run a real `level materialize` of a level referencing that package.
2. Inspect the live container: `docker inspect` shows the `/stubs` bind source == the resolved
   `config.stub_cache_root()`; `docker exec <c> ls /stubs` lists the built `.u`; the editor's
   `[Core.System] Paths` (the bind-mounted `unrealtournament.ini`) leads with `Paths=/stubs/*.u`.
3. Confirm the stub is the package the editor actually loaded — capture the `OBJ LOAD FILE=/stubs/…`
   the drive issues, and that it did not fall through to a v68 `.u` (which `unloadable_v68_packages`
   would have refused up front anyway, `packages.py:111`).
4. Vary `$UEDCLI_HOME` and re-check the mount source follows `stub_cache_root()`, not a hardcoded
   `${HOME}` default — the specific regression the 2026-07-18 chore fixed.

## Edge cases & errors

- Empty/absent `/stubs`: if the referenced package has no stub, the level references a v68-only
  package with no v69 stub → `packages.unloadable_v68_packages` must refuse it with the named error
  BEFORE any `OBJ LOAD` (`packages.py:128`), never a silent v69-loads-v68 wedge. Assert that path too.
- Editor flakiness: hang-detector discipline (`rules/background-work.md`).

## Tests / how it's pinned

- OFFLINE regression (CI): assert `ensure_editor` puts `UEDCLI_STUB_CACHE == stub_cache_root()` into
  the compose env (mock the `docker compose run` seam and read the env), and that it follows
  `$UEDCLI_HOME`. This pins the wiring that the live check exercises — the part that can rot.
- The live mount/`OBJ LOAD`-from-`/stubs` result is a committed spike finding; an OPTIONAL
  substrate-gated integration test re-runs it where an install + built stub are present. Not in CI.

## Open questions

- Whether the offline wiring assertion plus a one-time documented live confirmation closes the item,
  or the owner wants a standing substrate-gated live test. See `questions/`.
