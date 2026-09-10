---
name: verifying-brush-relations
description: Use when resizing, widening, or reshaping a UE1/Deus Ex room-shaped brush in uedcli (`brush vertex move`, `brush scale`, `brush apply-transform`) and before calling the edit verified — especially if a rendered decoration looks detached/floating, or you need to confirm the edit's effects stayed on the face you touched.
---

# Verifying Brush Relations After Reshaping

## Overview

Moving one face of a box-shaped brush (e.g. the 4 corners `brush vertex move` drags) also moves
every OTHER face sharing those corners — ceiling, floor, and walls you never touched grow with
it. Checking only the face you edited proves nothing about the others.

**REQUIRED BACKGROUND:** read `../../references/brush-relation-basics.md` for the `find`/`measure`
mechanics used below.

## When to Use

- Any `brush vertex move` / `brush scale` / `brush apply-transform` that changes a room-shaped
  brush's box extent — not a cosmetic single-vertex nudge.
- Before calling a room resize "verified."
- A render shows a decoration looking detached or floating with no backdrop.

Not needed for edits that don't change a brush's box extent.

## Core Pattern

```bash
# BEFORE the edit — the brush's WHOLE relation set, no face pin, EVERY footprint category
# (not just the default) — the default filter drops zero-overlap pairs, and on real levels
# several of the props that end up detached are only visible with the full set below.
uedcli brush relation find --relative-to Brush1 --top all --max-gap 200 \
  --footprint none,vertex,edge,partial,contains,coincident > before.txt
uedcli brush relation measure Brush1 - --top all < before.txt > before_detail.txt

# ... perform the edit ...

# AFTER — identical commands
uedcli brush relation find --relative-to Brush1 --top all --max-gap 200 \
  --footprint none,vertex,edge,partial,contains,coincident > after.txt
uedcli brush relation measure Brush1 - --top all < after.txt > after_detail.txt

# find's output is rank-ordered, not sorted — an UNCHANGED identity set still reorders when
# distances shift, producing spurious diff hunks. Sort before diffing, or trust the stderr
# counts ("N face(s) matched across M candidate(s)") as the real set-level check.
diff -u <(sort before.txt) <(sort after.txt)
diff -u before_detail.txt after_detail.txt
```

**Pass criterion:** every face of Brush1 you did NOT move must show the identical `plane` and
`footprint_2d` against every candidate, before and after (a `distance` shift alone, with no
category change, is fine — see below). Any face you didn't touch changing category is the
failure this check exists to catch.

Capture BOTH `find` and `measure` snapshots before the edit — `measure` reads live geometry, so a
`before_detail.txt` taken after the edit is not a baseline, it's a second AFTER. `--max-gap` bounds
how far away a candidate can be and still show up — pick it generously (bigger than any
face-to-face distance you'd plausibly care about for this brush, e.g. the size of the move plus
the moved brush's own extent); too small silently hides a real regression, since a candidate
outside the bound never appears in either snapshot. Use the SAME value on both the before and
after calls.

**Read the pre-edit `measure` as a headroom budget, not just a baseline.** The smallest positive
`distance` on the face you're about to move is how far it can move before it collides with
something — if the edit's planned distance exceeds that number, the edit is unsafe before you even
run it, not just after.

**Why the full `--footprint` list is in the Core Pattern by default, not an optional extra:** by
default `find` drops any pair with NO footprint overlap (`footprint_2d: none`), regardless of gap —
a neighbor sitting 16uu away with zero overlap is invisible in the BEFORE snapshot no matter how
generous `--max-gap` is. On real levels that's not a rare edge case: on one real-level test, 3 of
8 props that ended up detached by an edit were only visible in the full-footprint snapshot — the
default-filtered one showed no problem at all, before or after. Use the default (narrower) filter
only for a quick look; for an edit you're about to call "verified," use the full list.

`find` reports IDENTITY only (`candidate:poly` lines, no `ref_poly`) — with more than one
candidate or more than one affected face, a diff of this alone can't tell you which of REF's own
faces changed (the same `candidate:poly` line can legitimately appear twice, once per matching REF
face). `measure`'s diff isn't optional detail here — it's how you find out WHICH face is
responsible, not just what the geometry is. `measure` defaults to `--top 1` per candidate —
without `--top all` here it silently shows only the single closest pair per target and drops the
rest, even though `find`'s own snapshot already listed every one of them. Always pass `--top all`
on this step; `find`'s `--top all` above is not enough on its own. `measure` has no `--json`, and
its block order moves with the geometry the same way `find`'s ranking does — on anything but a
tiny diff, key the comparison on `(ref_poly, target_poly)` pairs rather than reading the raw
`diff -u` line-by-line.

An empty `before_detail.txt` is a normal, common baseline — it means nothing related to Brush1 yet
(not a bad invocation). Read every new/changed line in the diff for TWO distinct failure modes,
not just one:

- **Something got engulfed or newly overlapped** — a face you never moved shows up, or its
  `footprint_2d` grows (e.g. `partial` → `contains`). The obvious failure.
- **Something LOST contact with the face you moved** — a pair that was `coplanar`/`distance
  0.000uu` becomes `parallel` with a nonzero gap. This means an object that was built flush
  against the old position (a pillar reaching the old ceiling, a wall built to the old wall) is
  now detached, with a visible gap where it used to be sealed. This is at least as common as
  engulfment on real edits (raising a ceiling routinely leaves a wall-pier or partition wall
  short) and is easy to miss because nothing new appeared — a relation just quietly stopped
  holding.

**`footprint_2d` is the primary signal; `distance` alone can miss the failure entirely.** Widening
a wall moves its corners WITHIN its own plane — every OTHER face's perpendicular `distance` to
that wall is unchanged, because the plane itself didn't move, only its extent did. The only thing
that changes is `footprint_2d` (e.g. `partial` → `contains`, or `none` → some overlap) on faces
that are perpendicular to the one you edited. Read `distance` shifts as informative but not
sufficient; read every `footprint_2d` category change as the check itself.

A `footprint_2d: none` pair doesn't vanish from `measure`'s output — it collapses to one aggregate
line per candidate brush: `<ref> <-> <candidate>: no overlapping face pairs (N candidates, nearest
X.XXXuu apart)`. That `nearest ... apart` number is often the single most useful figure in the
whole report — read it as the real-world clearance to the nearest thing you didn't touch.

Real brushes are not always 6-face boxes — a staircase, an octagonal column, or a curved wall can
carry 10–26 polys. Don't assume a small, guessable set of poly indices; read them from `find`.

This check is scoped to cross-brush RELATIONS — it doesn't cover texture or flag changes (diff
`brush poly list --json` for those) or structural defects (`level doctor`).

## Common Mistakes

- **Pinning to the face you moved** (`--relative-to Brush1:5`). A box brush's corners are shared
  across 3 faces each — moving one face's corners changes the other two sharing them. Always use
  the bare brush name, no `:idx`.
- **Scoping the sweep to "near the edited wall."** Confirmed real incidents moved a face 90° away
  from the one edited — sweep every face, not just nearby ones.
- **Trusting `level doctor`.** It's a static per-brush geometry checker — CSG order, solidity,
  degenerate faces. Nothing in it evaluates cross-brush relations.
- **Assuming an empty BEFORE snapshot means "nothing nearby."** A candidate with zero footprint
  overlap is invisible by default (see `--max-gap` above) even at a small real-world gap — it can
  look like there's nothing there when something is 16uu away and about to be swallowed. Use the
  explicit `--footprint none,...,coincident` form when you want that visibility in advance.

## Known limitation

`brush relation`'s candidates are brush actors only (per its own `--help`). A point-actor
decoration — a mesh, a wall light, a switch — is invisible to the whole family: `brush vertex
move`/`scale` never carries a mounted actor along, so a light flush on a wall you widen stays at
its old coordinates and ends up floating in open space, undetected by anything in this family.

Before the edit, capture the moved face's OLD extent (`brush vertex list Brush1`) — you need it to
sweep the old position after the edit. Then, both before and after, sweep a thin slab through the
face's plane (a few uu of thickness is enough, e.g. ±8uu) spanning that extent:

```bash
uedcli actor find --overlapping-bbox=<face plane ± a few uu, old extent> --kind point
uedcli actor find --overlapping-bbox=<new face plane ± a few uu, new extent> --kind point
```

An actor caught in the OLD slab but not the NEW one was mounted on the face you moved and is now
detached — reposition it (or confirm it was never actually mounted) before calling the edit done.

## Real-world impact

Confirmed on two independent real Deus Ex levels: widening Manderley's office (UNATCO HQ) via
its west wall stretched the untouched NORTH face into a reception-room painting mounted on the
shared wall. Widening NYC_Bar's main hall via its west wall stretched the untouched SOUTH face
from partial overlap to fully containing a neighboring room's contents — 90° from the edited
face. A second, independent agent that thoroughly reattached everything flush against the moved
wall, diffed `level doctor` against a fresh reimport, and rendered a wireframe still missed it —
none of that checks the room's other faces.
