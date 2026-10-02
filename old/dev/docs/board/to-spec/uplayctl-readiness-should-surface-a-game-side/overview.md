+++
priority = "p2"
kind = "implement"
summary = "uplayctl readiness should surface a game-side `Critical Error` instead of a generic \"level never became X\" timeout"
+++

# uplayctl readiness should surface a game-side `Critical Error` instead of a generic "level never became X" timeout

p2. The whole earlier symptom — `session start` logging `link up;
traveling to Test_Castle (level-name-gated)` then `level never became Test_Castle (last=None)`,
followed by `ConnectionRefused` on every `shot`/`GetCurrentLevelName` — was NOT a "link doesn't
survive map travel" bug. The game had popped a modal `Critical Error: Failed to spawn player actor`
dialog and the process was wedged on it (link socket never re-listens on 7777). The readiness poll
should detect the `Critical Error` window (or grep the crash in the log) and fail fast with the
actual engine error + backtrace, instead of a content-free timeout that sends the operator down the
wrong path (I spent a long time suspecting the link/travel mechanism). Cheap detection: `xdotool
search --name "Critical Error"` on :99, or tail the crash line the engine writes. Andrzej,
2026-07-12.
