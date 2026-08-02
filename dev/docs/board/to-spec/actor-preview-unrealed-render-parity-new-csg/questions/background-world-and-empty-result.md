# What world does `--faces world` solve an ad-hoc actor set against, and what happens when the solve leaves no surface?

## Context

The native CSG solve starts from a **solid** world (`uedcli-native/src/build.rs:5-6`, `:785` —
`root_outside=false`: Subtract carves empty space, Add fills it). A brush face survives as a world
surface only where solid meets empty. That is the whole basis for the parity ruling: an additive
brush not inside subtracted space is buried in solid and draws nothing.

For a **real level** (the full trunk, or a `--from-t3d` snippet that carries its own subtracts) this
is exactly right — the level's subtracts carve rooms and the adds inside them show.

But `actor preview` usually runs over an **ad-hoc SET** — a name selection, or a `--from-t3d` snippet
(`actor preview --from-t3d -`, `uedcli/cli/parsers/actor.py:439`). Two consequences the owner has not
yet ruled on:

1. **A subset is solved in isolation, not in context.** `actor preview WallA DoorB` solves only those
   two brushes, not their appearance inside the full level. An add that IS inside a subtracted room in
   the real map renders **blank** under `--faces world` unless the enclosing subtract is also in the
   selected set. So "world parity" over a subset is parity of *that subset's own solve*, not of how the
   subset looks in the finished level. Is that the intended contract, or should `--faces world` solve
   the selected set against the full level's world (needs the whole trunk, does not fit `--from-t3d`)?

2. **An adds-only set survives as nothing.** The three floating cubes that prompted this whole item
   are adds against a solid world, so the honest world render is **empty**. Options:
   - **(a) legitimate blank** — render the empty frame, print a clear stderr note ("no surface survives
     the solve: every brush is additive against solid space — nothing would be visible in UnrealEd
     either; use `--faces textured` to inspect brushes in isolation"). Faithful, but a blank PNG.
   - **(b) exit 2 naming the cause** — treat "the set carves no empty space, so the render would be
     blank" as a refusal, per `conventions.md` (no silent half-answer; a stderr note that scrolls away
     is the anti-pattern). The message points at `--faces textured` for isolated-brush inspection.
   - **(c) synthesize a different background for an ad-hoc set** (e.g. auto-wrap the set in an implied
     subtract so adds show) — this re-introduces exactly the "adds always show" behaviour the parity
     ruling rejected, so it is listed only to be ruled out explicitly.

`generators.md` sets the precedent that background polarity is a real, per-operation choice here:
`brush intersect` assumes background **empty**, `brush deintersect` assumes background **solid**
(`direction/generators.md`, "the set merge"). `--faces world` needs its own stated assumption.

Recommendation: background stays **solid** (only that gives the ruled parity); a subset is solved **in
isolation** (matches how every other `actor preview` mode treats its set — no hidden whole-level
context); and a zero-surface result is **(b) exit 2 naming the cause**, since a blank image plus a
scrolling stderr note is the half-answer `conventions.md` forbids. Owner to confirm all three.

## Answer

<!-- Empty = open. -->
