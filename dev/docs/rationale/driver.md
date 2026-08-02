# The editor driver's surface: what it keeps and why

Engineering decisions about `uedcli/driver.py` (the `Driver` class that types console commands into
a running UnrealEd inside a container) and the container-lifecycle helpers around it. The bounds on
its `docker` subprocesses are covered in [`containers.md`](containers.md).

## `Driver` keeps methods whose only callers are spike harnesses and integration tests

The driver is one Python method per UnrealEd console command — click a viewport pane, take a
screenshot, select an actor by name, export a brush to a `.t3d`, re-pose the camera. It is the only
way anything in this repo talks to the live editor.

Roughly seventeen of those methods are no longer called by any uedcli *command*. This is expected:
uedcli pivoted to a model-side architecture (every read and mutation computes against the git-tracked
T3D trunk; the editor is touched only to build or preview), and the editor-screenshot preview flow
was deleted 2026-07-16. The methods are still used, by two caller populations a `grep` over
`uedcli/` does not see:

1. The committed spike harnesses under `dev/docs/spikes/` and `uned/spikes/`, the evidence behind the
   engine facts in `../unrealed/*.md` (`dev/docs/rules/spikes.md` "Commit the harness"). They
   `import` the driver, so deleting a method makes them raise `AttributeError` when re-run to
   re-verify a claim.
2. The integration suite (`uedcli/tests/test_*_integration.py`, `builder_parity_cases.py`), which is
   `@pytest.mark.integration` and deselected by default in `pytest.ini`. A green `bin/test` proves
   nothing about these callers, so they are easy to delete by accident.

Measured 2026-07-26 (`grep -rn '\.<method>('` across `uedcli/`, `dev/docs/spikes/`, `uned/`):
`dexec_bash` 17 spike callers, `selectname` 16 spike + 1 integration, `screenshot` 13,
`camera_align` 9, `actor_delete` 9, `click` 6, `xfer.cp_in` 6, `jumpto` 4, `select_none` 3,
`map_load_dx` 2, `rmode` 1, `brush_moveto` 1, `brush_import`/`brush_export` 2 integration callers
each. All are retained.

Deleted (owner ruling 2026-07-26, option A of four through the question widget): only the symbols
with no caller anywhere — `Driver.select_inside`, `Driver.edit_copy`, `Driver.map_sendto`,
`Driver.select_by_csg`, `editor.novnc_url`, and the `EditorBusyError` class with its two unreachable
`except` clauses in `apply.py`/`dispatch.py` (nothing ever raised it). `edit_copy`, `map_sendto` and
`select_by_csg` had tests, but only tests of themselves in `test_driver.py`, not a caller in the
sense that matters.

A future codebase review will flag the retained methods as dead again. That is why this entry
exists: their callers are in two places the review's grep did not cover, and the ruling was to keep
them. Re-run the measurement above before proposing the deletion a second time.

**Rejected:**

- **Deleting the full ~17 and rewriting every caller** against a preserved snapshot of the driver —
  it turns evidence scripts into forks of a frozen copy that will not track the real driver, so the
  next engine-fact re-verification runs against something uedcli no longer uses.
- **Deleting them and letting the spike harnesses rot** — the harnesses exist so a claim about an
  undocumented, crash-prone editor can be re-checked; a harness that cannot run is not evidence.
- **Copying the methods into a new spike harness before deleting them** (the board item's original
  remedy) — the existing harnesses `import` the driver rather than carrying their own copy, so a new
  harness would keep none of them runnable.
- **Deleting only the docstrings' claims** — two docstrings (`click`, `camera_align`) asserted live
  use by the preview flow removed 2026-07-16, which made the methods look like live code with a
  missing caller. Corrected in place to say no uedcli verb calls them and where their real callers
  are.

**Refs:** `uedcli/driver.py` · `uedcli/editor.py` · `uedcli/xfer.py` (`cp_in`) ·
`dev/docs/rules/spikes.md` · `pytest.ini` (the `integration` deselect) ·
`../architecture.md` "Editor driver"

## `map_save` verifies a container-side write with four stacked signals

**Why it is this way:** `MAP SAVE` reports nothing over the console and `exec` is fire-and-forget, so
the only signal that a save finished is the file itself — and a naive size poll conflates three
outcomes: finished, stalled, container-dead. Two defects were measured live: an exit-code liveness
rule can't tell a dead container from an absent file (a stopped or missing container and a permission
error all make `docker exec` exit 1, the same code `stat` uses for "no file"), so every real
container death was reclassified as "not written yet" and stalled the full timeout; and the poll's
`subprocess.run` had no `timeout=`, so the 600 s bound wasn't real. So `map_save` stacks four
independent signals, each answering the question it actually can:

1. **A pre-`MAP SAVE` stat the file must differ from** — kills "a complete map from an earlier run is
   sitting at that path". Dormant for the uuid-path production callers (`before` is `None`); it guards
   the fixed-path spike callers.
2. **N equal readings across a minimum settle window** (`stable_reads`, `settle`) — kills "the writer
   paused for one poll".
3. **A package-header structural check** (`package_problem` → `package_header_problem`: magic + the
   three object-table `(count, offset)` pairs landing inside the file) — the only signal that could
   separate *finished* from *stalled*, since no amount of stability can.
4. **Liveness from a `printf` sentinel plus a per-probe `subprocess` timeout** (`_container_probe`) —
   positive proof the container ran the command, replacing the ambiguous exit code, and bounding a
   hung dockerd.

Only defects (a) exit-code liveness and (c) the missing subprocess timeout are load-bearing — both
were measured. Signal #3 is insurance, not a demonstrated fix: whether a truncated file can reach the
destination is unproven (the editor serializes into `Save.tmp`, patches the header last, then moves it
onto the path; rename-vs-copy undetermined) and no truncated destination has ever been observed. It
costs one 36-byte read and also rejects a stale non-package at the path, so it stays as cheap defence
in depth. The boundedness claim covers the poll loop only — the `MAP SAVE` line itself still goes out
through unbounded `_wine_ctl`.

**Rejected:**

- *Keep the exit code and just widen the "docker failed" set (125/126/127)* — the failures land on 1,
  so any exit-code rule is guessing; the sentinel is positive proof of liveness, not a blacklist of
  failure codes.
- *Raise as soon as a stable file fails the structural check* — a slow flush would false-fail; an
  incomplete-but-stable file is "not accepted yet", so polling continues to `timeout` and then reports
  the structural reason.
- *Verify by fully parsing the package (`load_package`)* — it needs the bytes on the host (the file is
  container-local until `docker cp`) and judges content, not completeness; the header check stays
  inside the driver's container-only dependency.
- *Keep the size-only `container_file_size`* — "did this file change?" needs the mtime, so the probe
  returns `(size, opaque mtime token)`.

Engine facts (`Save.tmp`, the header window) are in [`../unrealed/commands.md`](../unrealed/commands.md)
"`MAP SAVE` writes `Save.tmp`" and `spikes/2026-07-25-map-save-mechanism/` — cited, not restated.

**Refs:** `uedcli/driver.py` (`map_save`, `package_problem`, `_container_probe`, `container_stat`,
`container_file_head`, `package_header_problem`) · [`../unrealed/commands.md`](../unrealed/commands.md)
· `spikes/2026-07-25-map-save-mechanism/` (harnesses, pinned by `test_engine_facts.py`) ·
`uedcli/tests/test_driver.py`
(`test_map_save_accepts_a_file_only_once_it_is_stable_AND_structurally_complete`,
`test_map_save_reports_a_dead_container_at_once_instead_of_polling_a_corpse`,
`test_map_save_bounds_every_probe_and_reports_the_elapsed_time`,
`test_package_header_problem_catches_a_truncation_INSIDE_the_last_table`)
