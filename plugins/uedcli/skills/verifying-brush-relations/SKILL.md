---
name: verifying-brush-relations
description: Use when resizing, widening, or reshaping ANY UE1/Deus Ex brush's box extent in uedcli (`brush vertex move`, `brush scale`, `brush apply-transform`) — a room wall exactly as much as a counter, shelf unit, or any other multi-part assembly — and before calling the edit verified. Especially if a rendered decoration looks detached/floating, or the edit might have grown into an NPC/prop that was already standing nearby.
---

# Verifying Brush Relations After Reshaping

## Overview

Moving one face of a box-shaped brush also moves every OTHER face sharing those corners — ceiling,
floor, and walls you never touched grow with it. Checking only the face you edited proves nothing
about the others.

**REQUIRED BACKGROUND:** read `../../references/brush-relation-basics.md` for the `find`/`measure`
mechanics used below.

## When to Use

- Any `brush vertex move` / `brush scale` / `brush apply-transform` that changes a brush's box
  extent — not a cosmetic single-vertex nudge. Applies to any multi-part assembly (furniture,
  shelving) as much as a room wall.
- Before calling any resize "verified."
- A render shows a decoration looking detached or floating with no backdrop.

Not needed for edits that don't change a brush's box extent.

## Confirm you're moving the right face first

A vague direction ("the south wall") can be ambiguous when a room borders another already-carved
room through a connecting gap — an internal doorway wall can look like a candidate exterior wall
too. Before moving anything, measure each candidate face against the level's OTHER rooms:

```bash
uedcli brush relation measure <target> <neighboring-room> --top all
```

A face that's `coincident`/`contains`-overlapping ANOTHER subtract brush's own volume is an internal
connecting wall, not the exterior boundary — moving it doesn't expand livable space, it intrudes
into the neighbor's already-hollow interior. If a named landmark in the task doesn't match the face
you're about to move, that mismatch is the signal you picked the wrong one.

**Resolve doubt with evidence, don't default to inaction.** A candidate face looking ambiguous is a
prompt to gather more evidence, not a reason to skip the edit: corroborate the `relation measure`
reading with a rendered diagram of the target and its neighbors (`actor diagram ... --highlight`)
and with any reference photos the task provides. These three rarely disagree — when they agree, act
on them. Doing nothing when the task specifies a real edit is itself a failure, not a safe default;
reserve stopping to ask for uncertainty that survives checking all three.

## Core Pattern

```bash
# BEFORE the edit — the brush's WHOLE relation set, no face pin, EVERY footprint category
# (the default filter drops zero-overlap pairs, which can hide a real regression)
uedcli brush relation find --relative-to <target> --top all --max-gap 200 \
  --footprint none,vertex,edge,partial,contains,coincident > before.txt
uedcli brush relation measure <target> - --top all < before.txt > before_detail.txt

# ... perform the edit ...

# AFTER — identical commands
uedcli brush relation find --relative-to <target> --top all --max-gap 200 \
  --footprint none,vertex,edge,partial,contains,coincident > after.txt
uedcli brush relation measure <target> - --top all < after.txt > after_detail.txt

# find's output is rank-ordered, not sorted -- sort before diffing, or trust the stderr
# counts ("N face(s) matched across M candidate(s)") as the real set-level check.
diff -u <(sort before.txt) <(sort after.txt)
diff -u before_detail.txt after_detail.txt
```

**Pass criterion:** every face you did NOT move must show the identical `plane` and `footprint_2d`
against every candidate, before and after (a `distance` shift alone, with no category change, is
fine). Any untouched face changing category is the failure this check exists to catch.

**Read the BEFORE snapshot for companions, not just a baseline.** A candidate showing `coincident`
or heavy overlap against a face you're about to move is very likely a separate piece built flush
against that edge, not an unrelated neighbor. A flush companion usually needs the SAME edit applied
to it — decide this from the BEFORE snapshot, before you move anything.

**A companion doesn't have to touch the SPECIFIC face you're moving.** It can be flush against, or
nested inside, a DIFFERENT face of the same brush entirely (attached to the underside, or resting
against a face perpendicular to the one you're editing). Don't scope the search to "things touching
the one face I'm moving" — read the full sweep (bare brush name, every face, every footprint
category) and treat ANY `contains`/`coincident` relation on ANY face as a companion candidate.

**Companions can have their OWN companions.** Something you find via its relation to the face you
moved may itself be flush against a third piece that never touches that face at all. After finding
a companion, re-run the same `find`/`measure` pass FROM it too, and repeat until a pass turns up
nothing new.

**When a companion, or a cosmetic consequence of the edit (a texture that no longer matches, a
visible seam), can't be cleanly resolved, stop and ask — don't silently ship a guess.** A
confident-looking partial fix is worse than a flagged question: the guess passes casual review, the
question doesn't.

Capture BOTH `find` and `measure` snapshots before the edit — `measure` reads live geometry, so a
`before_detail.txt` taken after the edit is a second AFTER, not a baseline. `--max-gap` bounds how
far a candidate can be and still show up — pick it generously (bigger than the move plus the moved
brush's own extent); too small hides a real regression. Use the SAME value both times.

**Read the pre-edit `measure` as a headroom budget.** The smallest positive `distance` on the face
you're about to move is how far it can go before colliding with something — if the planned move
exceeds that, the edit is unsafe before you even run it.

**Use the full `--footprint` list, not the default.** By default `find` drops any pair with NO
footprint overlap, regardless of gap — a neighbor with zero overlap is invisible no matter how
generous `--max-gap` is. Use the narrower default only for a quick look; for an edit you're calling
"verified," use the full list.

`find` reports IDENTITY only — with more than one candidate or affected face, its diff alone can't
tell you WHICH face changed. `measure`'s diff is how you find that out. `measure` defaults to
`--top 1` per candidate — always pass `--top all`, or it silently drops everything but the closest
pair. `measure` has no `--json`; key any comparison on `(ref_poly, target_poly)` pairs rather than
reading the raw diff line-by-line.

An empty `before_detail.txt` is a normal baseline, not a bad invocation. Read every changed line in
the diff for TWO distinct failure modes:

- **Something got engulfed or newly overlapped** — a face you never moved shows up, or its
  `footprint_2d` grows. The obvious failure.
- **Something LOST contact with the face you moved** — a pair that was `coplanar`/`distance
  0.000uu` becomes `parallel` with a nonzero gap. An object built flush against the old position is
  now detached, with a visible gap. At least as common as engulfment, and easy to miss since
  nothing NEW appears.

**`footprint_2d` is the primary signal; `distance` alone can miss the failure.** Widening a wall
moves its corners WITHIN its own plane — every other face's perpendicular distance to it is
unchanged, since the plane itself didn't move, only its extent did. Only `footprint_2d` changes on
faces perpendicular to the one you edited.

A `footprint_2d: none` pair collapses to one aggregate line per candidate: `<ref> <-> <candidate>:
no overlapping face pairs (N candidates, nearest X.XXXuu apart)`. That `nearest ... apart` number is
the real-world clearance to the nearest thing you didn't touch.

Real brushes are not always 6-face boxes — read poly indices from `find`, don't assume a small
guessable set.

This check is scoped to cross-brush RELATIONS — it doesn't cover texture/flag changes (diff
`brush poly list --json` for those) or structural defects (`level doctor`).

## Common Mistakes

- **Pinning to the face you moved** (`--relative-to X:5`). A box brush's corners are shared across
  3 faces each. Always use the bare brush name.
- **Scoping the sweep to "near the edited wall."** A companion or affected face can be anywhere on
  the brush, or 90° from the one edited — sweep every face.
- **Trusting `level doctor`.** It's a static per-brush geometry checker; nothing in it evaluates
  cross-brush relations.
- **Assuming an empty BEFORE snapshot means "nothing nearby."** A candidate with zero footprint
  overlap is invisible by default even at a small real-world gap. Use the explicit
  `--footprint none,...,coincident` form for that visibility.
- **Sweeping companions only once, from the brush you're editing.** Re-sweep from each new
  companion until nothing new turns up.
- **Picking the nearest/first plausible face for a vague direction without checking neighboring
  rooms.** An internal connecting wall can look just as valid a candidate as the true exterior one.
- **Treating unresolved-looking ambiguity as a reason to make no edit at all**, instead of resolving
  it with a measurement + diagram + photo check first. A task that specifies a real edit is not
  satisfied by doing nothing.
- **Only checking for companions on the face you're moving.** A companion can be attached to any
  other face of the same brush.
- **Silently shipping a partial or guessed fix instead of asking.**
- **Repositioning an engulfed point actor to "somewhere else" without checking the new spot is
  clear.**

## Known limitation

`brush relation`'s candidates are brush actors only. A point-actor decoration (a mesh, a light, a
switch) is invisible to the whole family: `brush vertex move`/`scale` never carries a mounted actor
along, so one flush on a wall you widen stays at its old coordinates.

Before the edit, capture the moved face's OLD extent. Then, both before and after, sweep a thin
slab through the face's plane (a few uu of thickness) spanning that extent:

```bash
uedcli actor find --overlapping-bbox=<face plane ± a few uu, old extent> --kind point
uedcli actor find --overlapping-bbox=<new face plane ± a few uu, new extent> --kind point
```

An actor caught in the OLD slab but not the NEW one was mounted on the face you moved and is now
detached — reposition it (or confirm it was never mounted). **Verify the new position is actually
clear** via `actor find --overlapping-bbox=<new bbox> --kind brush` against nearby solids —
"somewhere else" is not the same as "somewhere clear."

**The same blind spot cuts the other way: growing a brush can push it INTO a point actor that was
already standing nearby, unrelated to the face you moved.** The slab sweep above doesn't catch
this, since it's scoped to the moved face's own plane. Sweep the brush's OWN full bbox instead,
before and after:

```bash
uedcli actor bbox <target>          # BEFORE -- the old volume
uedcli actor find --overlapping-bbox=<old bbox> --kind point > before_engulf.txt
# ... perform the edit ...
uedcli actor bbox <target>          # AFTER -- the new, grown volume
uedcli actor find --overlapping-bbox=<new bbox> --kind point > after_engulf.txt
diff before_engulf.txt after_engulf.txt
```

Any point actor appearing in the AFTER list but not the BEFORE one is newly engulfed.
