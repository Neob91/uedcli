# On a detected editor crash/wedge mid-write, should uedcli auto restart-and-replay, or fail loud?

## Context

Crash *detection* is done (see spec): a wedge or GPF surfaces as a clean non-zero exit and the command
aborts, leaving the editor as-is. The question is what recovery to add on top.

Stakes: the editor is crash-prone, so a long brush-write / materialize sequence hits transient wedges;
without recovery the user re-runs from the top, and against a standing editor a wedge can leave a
half-applied session.

The tension: your existing rulings reject silent automatic retry for the warm materialize container —
`direction/containers.md` ("Automatically retrying a failed warm build on a fresh container — masks
whether warm reuse is flaky and doubles the cost") and `direction/materialize.md` ("A warm-mode
failure fails with a hint, never with a silent automatic retry"; "an untrusted container is never left
warm"). A general auto-recovery layer would seem to contradict those.

Options:

- **A — Fail loud, no auto recovery.** Keep today's behavior: detect, tear the editor down, exit
  non-zero with a hint to re-run. Consistent with the no-silent-retry rulings; costs a manual re-run.
- **B — Auto restart + idempotent replay, once.** On a detected crash, start a fresh editor and
  re-drive the operation from a clean `MAP NEW` (materialize's FULL RE-IMPORT is already crash-safe
  and idempotent), exactly once, then fail loud if it recurs. Reconcile with the rulings by scoping
  them: they forbid retrying a *warm-reuse* failure on the ephemeral path (a fingerprint/staleness
  concern), which is different from replaying a fresh idempotent build after a *process crash*.
- **C — B, but only for ephemeral/standalone drives, never the warm container.** The warm path keeps
  the strict fail-loud rule verbatim; only per-command ephemeral editors get one restart+replay.

Recommendation: **C** — it gives recovery where it is cheap and safe (fresh, idempotent, ephemeral)
while leaving the warm-container rulings untouched. If the scoping in B/C reads as contradicting the
existing rulings rather than refining them, **A**.

## Answer

<!-- Empty = open. -->
