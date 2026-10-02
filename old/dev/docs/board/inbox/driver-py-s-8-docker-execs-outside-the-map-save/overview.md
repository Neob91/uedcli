+++
priority = "p3"
kind = "chore"
summary = "`driver.py`'s 8 `docker exec`s outside the `map_save` probes are still unbounded waits"
+++

# `driver.py`'s 8 `docker exec`s outside the `map_save` probes are still unbounded waits

`map_save`'s file probes go through `_container_probe`, which bounds each `docker exec`
with `PROBE_TIMEOUT` and turns a `TimeoutExpired` into a `DriverError`. Six driver methods still
do not: `_wine_ctl`, `dexec_bash`, `set_clipboard`, `log_size`, `read_log_since`,
`dismiss_blocking_dialog` (three calls) all call `subprocess.run` with no `timeout=`, so a hung
dockerd parks the caller forever (`CLAUDE.md` "never an open-ended wait"). **Five of those also
pass `check=True`** (`log_size`, `read_log_since`, all three in `dismiss_blocking_dialog`), so a
docker failure reaches the user as a raw `CalledProcessError` traceback instead of a named
`DriverError` — a second rule broken ("never let a Python exception reach the CLI user"). Not
folded into the `map_save` fix because `_wine_ctl exec` drives genuinely long editor verbs (`MAP
REBUILD` can run minutes) and needs its own bound chosen rather than copied — and note
`map_save`'s own `MAP SAVE` line goes out through `_wine_ctl`, so its bounded poll loop is preceded
by one unbounded call. **`xfer.py`'s three subprocesses are DONE** (2026-07-26: `cp_in`/`cp_out`
bounded at `CP_TIMEOUT` and raising `DriverError`, `remove` bounded and swallowed), along with
`editor.py`'s lifecycle calls and `store_export.export_dx_t3d` — only `driver.py` is left.
(2026-07-25, while fixing the `map_save` verification; counts corrected twice by the build
reviews. Deliberately no line numbers — method names are stable, line numbers rot within the
commit that adds them.)
