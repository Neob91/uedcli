# Driving containers — why the docker calls are shaped this way

Engineering decisions about the code that shells out to `docker`: `uedcli/editor.py` (the ephemeral
editor container's lifecycle), `uedcli/xfer.py` (host↔container file copies), and
`uedcli/store_export.py` (the offline UCC export). The *rule* these serve is
[`../rules/background-work.md`](../rules/background-work.md) — never leave a wait open-ended.

## Every `subprocess.run` that talks to docker carries a `timeout=`

**Why it is this way:** `subprocess.run` with no `timeout=` waits forever. A docker daemon that
stops answering — and on this machine that is not hypothetical — therefore parked the whole verb
with no output, indistinguishable from a slow editor, until the operator killed it. The bound turns
that into a named failure in bounded time.

One case is worse than merely slow, and is the reason this is not cosmetic: `editor._wait_ready`
polls `docker exec … wine_ctl status` inside a `deadline` loop. With the exec unbounded, a single
hung poll blocked *inside* one iteration, so the loop's own deadline could never be reached — the
readiness timeout was decorative and `ensure_editor`'s crash-retry (`start_attempts`) never fired
on exactly the failure it exists for.

**The bounds are per KIND of call, not one global number**, because the calls do different work:

| Site                           | Bound | Why that size
|--------------------------------|-------|---
| `editor.PROBE_TIMEOUT`         | 60 s  | `docker ps` / `rm -f` / `volume rm` / one status poll — sub-second work, so a minute already means the daemon is not answering
| `editor.LAUNCH_TIMEOUT`        | 600 s | `docker compose run` creates a volume and a container, and may pull; too tight a bound would abort a legitimate cold start
| `xfer.CP_TIMEOUT`              | 300 s | one `docker cp` of a whole map package through the daemon
| `xfer.REMOVE_TIMEOUT`          | 60 s  | `rm -rf` inside a container that is about to die anyway
| `store_export._SHELL_TIMEOUT`  | 60 s  | `mkdir -p` / `cat` in the container
| `store_export._EXPORT_TIMEOUT` | 900 s | one `UCC.exe batchexport` of a whole level under wine — minutes for a large retail map

**A timeout on a TEARDOWN path is swallowed; anywhere else it raises.** `_reap_container`,
`stop_editor` and `xfer.remove` run from failure paths and `finally:` blocks, where raising would
replace the real error with a cleanup error — the same call the sibling `preview_game.stop_game`
already made. Everywhere else a `TimeoutExpired` becomes a `DriverError` naming the operation and
the bound. `DriverError` is deliberate rather than letting `subprocess.TimeoutExpired` escape:
`apply.run_materialize` catches `RuntimeError`/`DriverError`/`CalledProcessError` but **not**
`TimeoutExpired` (a `SubprocessError`, which is not a `RuntimeError`), so a raw timeout would have
reached the user as a traceback.

**A bound is not a retry budget.** `ensure_editor`'s `ready_timeout` and `start_attempts` still
govern how long the *editor* may take to come up; these bounds only stop *docker itself* hanging.

**Rejected:**

- **One global `DOCKER_TIMEOUT`** — a value large enough for a cold `docker compose run` or a
  minutes-long UCC export is useless as a hang detector on a `docker ps`.
- **Raising on a teardown timeout** — it masks the failure the caller was already reporting.
- **Letting `subprocess.TimeoutExpired` propagate** — it is not a `RuntimeError`, so it slips past
  the materialize guard and reaches the user as a traceback.
- **Making `_wait_ready` fail on a hung poll** — a poll is allowed to be slow; the readiness
  deadline is the thing that decides the editor is dead, and treating one wedged probe as fatal
  would abort starts that the next poll would have accepted.

## The UCC export's work dir is removed in a `finally:`

**Why it is this way:** `store_export.export_dx_t3d` creates `/work/ucc_export-<uuid>` in the
container, runs the export into it, reads the result, and deletes it. With the delete after the last
call, *any* failure — a non-zero UCC exit, a wedged wine, a missing output file — skipped it and
stranded the tree for the container's lifetime. Its sibling `texture.batchexport_textures` already
used `try/finally`; this now matches. The `mkdir` stays outside the `try:` on purpose: if creating
the dir failed there is nothing to clean up.

**Rejected:**

- **Cleaning up only on success** — the previous behaviour, and the reason stale export trees
  accumulated in long-lived containers.
- **Relying on the container being ephemeral** — true for `level materialize`, but the same
  function runs against reused/standing containers in spikes and integration tests.

**Refs:** `uedcli/editor.py` · `uedcli/xfer.py` · `uedcli/store_export.py` ·
`uedcli/preview_game.py` (`stop_game`, the pattern) · `../rules/background-work.md` ·
`uedcli/tests/test_editor.py`, `test_xfer.py`, `test_store_export.py`
