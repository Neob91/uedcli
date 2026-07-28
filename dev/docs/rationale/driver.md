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
