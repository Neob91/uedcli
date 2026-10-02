+++
priority = "p2"
kind = "debug"
summary = "Done — the empty-stage test runs over a temp board instead of asserting `stale/` is empty."
+++

# master red: stale/ item vs the empty-stage board test

Done. The test asserted `stale/` is empty, which the board does not guarantee — `stale/` exists to
HOLD items ("judged stale, retained not deleted"), and the 2026-08-02 sweep duly put one there. Any
real stage can be filled by unrelated work, so none can carry the assertion. It now runs the shipped
`bin/board` over a temp board with empty stages: `bin/board` resolves its board dir from its own
location, so a copy beside an empty tree gives a genuinely empty stage with no mocking.

`native-full-parity-handoff` stays in `stale/`, where the sweep put it.
