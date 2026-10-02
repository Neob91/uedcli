# Spec — materialize log noise: `XGetWindowProperty[_NET_ACTIVE_WINDOW] failed (code=1)`

## Goal

Stop the repeated `XGetWindowProperty[_NET_ACTIVE_WINDOW] failed (code=1)` lines from the X stack that
appear on every editor run and bury the real message. Cosmetic (p3).

## Current state

- The full line is `XGetWindowProperty[_NET_ACTIVE_WINDOW] failed (code=1)` — an X-client error raised
  when a tool reads the root `_NET_ACTIVE_WINDOW` EWMH property and the WM (fluxbox,
  `uned/entrypoint.sh:42`) has not set it.
- Emitter not pinned offline. Most likely `x11vnc` (runs `-forever`, polls the active window; its log
  is `/var/log/x11vnc.log`, entrypoint.sh:58); `wmctrl`/`xdotool` active-window queries are the other
  candidates. It surfaced in a real run as "10 minutes of only `XGetWindowProperty…` lines" while a
  command waited (`dev/docs/spikes/levelbuild-friction/agent-reports.md`), and the friction harness
  already filters it as pure noise (`levelbuild-friction/mine.py:31`).

## Approach

Silence at the source once the emitter is confirmed on a live editor:

- If `x11vnc`: add the flag that suppresses its active-window polling / EWMH probing, or redirect its
  stderr so the line never reaches surfaced output.
- Alternatively ensure fluxbox maintains `_NET_ACTIVE_WINDOW` so the query succeeds.

Prefer fixing the emitter over grepping the noise out downstream (no silent filter of a real log).

## Test

None (cosmetic, container-side).

## Open questions

None for the owner. Grounding the exact emitter needs one quiet live editor run — if that is not
cheap inline, this item should pass through `to-spike/` first to pin the source before the fix.
