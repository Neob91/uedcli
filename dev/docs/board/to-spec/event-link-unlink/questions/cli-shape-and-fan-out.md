# `event link` CLI shape: which side is the piped set, and how to handle fan-out?

## Context

A trigger wire is directional: SOURCE fires, TARGET receives (`SOURCE.Event == TARGET.Tag`). The
mutating-verb convention gives ONE names slot to `-` (stdin), so only one side can be the piped set;
the other rides a flag.

**Recommended:** `event link --to TARGET  SOURCE…|-` — SOURCEs are the piped/positional set (their
`Event` changes), TARGET is on `--to`. Mirrors `actor folder set --to <path> <names…|->`. Makes
fan-in (`actor find … | event link --to Door01 -`) the natural pipeline.

Rejected: `event link SOURCE TARGET` (two positionals) — cannot use `-`, so `find | link` breaks.

**Fan-out (one source → many targets)** is not expressible in the recommended shape: a source's
single `Event` string equals only one tag, so wiring one source to many targets requires those
targets to share one tag value. Options:

- (a) Do not support fan-out as one command; the user runs `link` per target, or first gives the
  targets a shared tag. Simplest. Recommended for v1.
- (b) Add an explicit `--tag NAME` (see the minting question): `event link --tag Alarm SOURCE
  TARGET…` writes `Event=Alarm` on the source and `Tag=Alarm` on every target — a deliberate
  shared-bus wiring. More capable, larger surface.

Recommendation: ship (a) now; revisit (b) with the `--tag` decision.

## Answer

<!-- Empty = open. -->
