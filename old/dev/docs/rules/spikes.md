# Spikes

Run a spike to completion — never defer a check or leave a question open for
later. Keep investigating until the spike is fully figured out, not just until
a plausible-looking answer shows up. When stuck, consult subagents and tell
them to be very creative.

## Commit the harness

Any script, parser, or tool written during a spike belongs in
`dev/docs/spikes/<slug>/` alongside the spike markdown — not left in
`_scratch/` (which is gitignored and wiped). Copy it there before parking or
wrapping up. `_scratch/` is for throwaway output (logs, PNGs, T3D exports),
never for code that someone will need to resume from.

## Pin every checkable finding with a test

A spike is not finished when you find the answer — it's finished when the
answer is pinned so a later change can't silently break it. A finding left as
prose goes stale as the binary, the build, or our own code moves under it.
So whenever a spike lands a checkable fact (an FRotator serialization
convention, a paste grid-snap offset, a `bspBrushCSG` ordering rule, a
byte-layout field order, a `GMath`-table value), also land a committed
regression that re-asserts that fact — against the real binary/editor where
feasible, else against a committed golden — so a violation trips a red test
instead of drifting unnoticed. Keep these engine-facts assertions together
(e.g. a `test_engine_facts` module) and back-reference the spike from the test.
This is the executable half of the `CLAUDE.md` "Documentation" rule that
"every claim about how UnrealEd behaves carries its evidence": the prose cites
the spike, the test enforces it. (A spike whose result is a one-off decision,
not a standing fact, needs no test — use judgement.)
