+++
priority = "p2"
kind = "implement"
summary = "GUI: POST /rebuild should run in the background against a trunk snapshot taken at build start, not block the request"
+++

# GUI: POST /rebuild should run in the background against a trunk snapshot taken at build start, not block the request

Owner-raised (2026-09-15). Today `POST /rebuild` blocks synchronously until the CSG+lighting solve
finishes (tens of seconds on a real level) — the HTTP request itself doesn't return until the build
is done, holding a long-running API request open the whole time. Want: the route only TRIGGERS the
build (kicks it off server-side, returns immediately, no long-held connection) — the frontend then
learns of completion either via the existing WS push (extending the `changes_available`-style
message) or via its existing periodic `/status` poll, whichever fits better once designed; either
way the client is never left holding open the `/rebuild` request itself.

**Trunk-snapshot feasibility, first pass:** the build should run against the trunk state as it was
at the MOMENT the rebuild was triggered, not whatever it is when the build happens to finish —
i.e. a concurrent trunk edit landing mid-build must not change what's being built, only what a
LATER rebuild would see. This looks structurally straightforward: `_LoadedTrunk` is already an
immutable snapshot object (`app.py`'s `_get_trunk()`/`_trunk_ref`), and `_build_and_publish_geometry`
already captures its own local `trunk_state` reference before starting the slow solve — a background
task just needs to keep using that same captured reference throughout, never re-reading
`_trunk_ref[0]`. The existing generation-guard discard-and-retry logic (built for the *synchronous*
case) would need to become "run one background job to completion against its snapshot, then decide
whether to publish or discard based on whether something newer already landed" — plus real job-state
tracking (a "building" status, preventing/queuing a second concurrent rebuild request, deciding what
happens to a request that arrives while one is already running).

**Progress reporting, also wanted** (2026-09-15 follow-up): a `%` estimate plus a label for what's
currently being built, matching real UnrealEd's own build progress dialog (BSP/lighting phase
names). Checked: `uedcli/preview_native.py::build_scene()` and the native Rust CSG/lighting solve it
calls have NO existing progress-callback mechanism today — it's one opaque call in, one result out.
Delivering real (not fake/simulated) progress needs phase-level instrumentation added inside the
native solve itself (CSG passes, node-poly extraction, lighting), threaded back up through the
Python bridge and then the async job/WS mechanism above — a bigger piece of work than the
async-trigger change alone, and it touches `uedcli-native` (shared with `level materialize`/
`level photo`, not GUI-only), so it needs its own scoping pass rather than folding in silently here.

Not spec'd or scoped yet — needs its own spec before planning. Related: `dev/docs/board/done/
gui-explicit-rebuild-pinned-build-state-mode/` (the just-shipped Load/Rebuild model this extends).
