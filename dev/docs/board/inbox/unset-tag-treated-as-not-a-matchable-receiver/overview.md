+++
priority = "p3"
kind = "owner-question"
summary = "Unset `Tag` treated as NOT a matchable receiver"
+++

# Unset `Tag` treated as NOT a matchable receiver

follow-ups from build #4 (event graph, item 10)` — three things I decided and want
your eyes on (all recorded in decisions.md 2026-07-18 20:54 UTC):
1. **Unset `Tag` treated as NOT a matchable receiver.** UE1 defaults an unset Tag to the class
   name at runtime; I only wire an edge on an EXPLICIT non-empty Tag (a class-name-default Tag
   never receives). Assumption per the task; flagging it in case you want the class-name-default
   honoured for a specific pattern.
2. **Exit 0 even with lint findings** (`event graph` is a wiring PRODUCER; lint is advisory to
   stderr / in `--json`). No `--strict` non-zero-exit mode yet — say if you want one for CI.
3. **Scope limits:** the edge model reads the single `Event` prop only — multi-event ARRAY props
   (Dispatcher `OutEvents(n)`, Counter, etc.) fire events that currently produce NO edges. And
   the unreachable-mover lint is conservative: it flags a mover with an explicit unused Tag and no
   self-moving `InitialState`, but does NOT flag a tagless mover (bump/loop trigger mechanisms
   aren't reliably knowable offline). Both are candidate follow-ups if you want deeper coverage.
