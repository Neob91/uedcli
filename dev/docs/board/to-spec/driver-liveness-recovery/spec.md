# Spec — driver liveness recovery

## Goal

Decide and build the higher-level *recovery* layer (restart + resume) around editor-driving writes.
Fast crash *detection* is already done; what is missing is what to do after a detected crash beyond
failing the command.

## Current state — detection is done, recovery is not

Detection, all landing as a clean non-zero exit (no traceback):

- `uned/wine_ctl.py:_assert_alive()` (215) — fast precondition on every driving command: pid check,
  `_crash_dialog_open()` (a "Critical Error" GPF dialog), single-pass window resolve. Raises
  `CtlError`.
- `driver._container_probe` (driver.py:361) — sentinel-based container liveness (exit codes are not
  trusted; a dead/missing/permission-denied container all exit 1).
- The `MAP SAVE` poll loop (driver.py ~308–358) — bounded, distinguishes finished / still-writing /
  stalled / wedged, raises `DriverError` naming the path and elapsed time.

`DriverError`/`CtlError` are caught at `cli/dispatch.py:48` → clean exit. So a mid-sequence wedge
during brush writes (`writes.py:90` `edit_paste` per brush) today just aborts the command; the editor
is left as-is and the user re-runs from the top.

## The gap

No layer restarts a crashed/wedged editor and re-drives the work. For a long brush-write sequence a
transient wedge (the editor is crash-prone) forces a full manual re-run, and against a *standing*
editor it can leave a half-applied session.

## Approach (pending the policy decision below)

`materialize`'s strategy is already FULL RE-IMPORT — `MAP NEW` then re-import the whole trunk in order,
"cheap to reason about, crash-recoverable, cannot leave a stale actor behind" (`direction/materialize.md`).
That makes idempotent replay the natural recovery unit: on a detected crash, tear down the editor,
start a fresh one, and re-drive the operation from a clean `MAP NEW` — never a mid-sequence resume that
must track which brushes already landed.

Whether uedcli should do that automatically, or fail loud and let the user re-run, is the open
decision — and it collides with existing rulings that reject silent automatic retry for the warm
materialize container (`direction/containers.md`, `direction/materialize.md`: "fails with a hint, never
with a silent automatic retry"; "an untrusted container is never left warm"). So this needs the owner.

## Test

Once the policy is set: a regression test that injects a simulated wedge (crash dialog / dead
container / stalled save) mid-write and asserts the chosen behavior (loud failure with hint, or one
clean restart+replay), plus that a crashed editor is never left warm/reused.

## Open questions

See `questions/recovery-policy.md` — automatic restart-and-replay vs fail-loud, and whether any auto
path can be reconciled with the no-silent-retry rulings.
