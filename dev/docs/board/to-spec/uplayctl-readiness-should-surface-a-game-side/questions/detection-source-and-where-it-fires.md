# Crash detection: log-scan, window-title, or both — and travel poll only or the boot poll too?

## Context

A game-side `Critical Error` can be detected two ways in-container: scanning `DeusEx.log` for the
`Critical:`/`Exiting due to error` line + `History:` backtrace (carries the real message), or
`xdotool search --name "Critical Error"` on `:99` (cheap liveness, no message). The waits that go
blind today are `preview_batch.travel` (all three phases, up to 480s) and `preview_game._wait_ready`
(boot, up to 900s); the entrypoint boot loop also only reports a generic `link never bound`.

Decisions:

- Source: (a) log-scan only, (b) window-title only, (c) both — log for the message, window as a
  fast secondary signal.
- Scope: (a) travel poll only, (b) travel + `_wait_ready` boot poll, (c) also the entrypoint boot
  loop (`link never bound` → dump the crash tail).

Recommendation: source (c) both, log as the primary (it is the only source of the actual error text
the operator needs); scope (b) travel + boot poll in `preview_batch`/`preview_game`, and additionally
have the entrypoint dump the `DeusEx.log` crash tail on `link never bound` so a boot-time crash is
never reported as a bare timeout. This covers every place the recorded symptom appeared without a
large surface change.

## Answer

<!-- Empty = open. -->
