# Owner-reported findings — the LEVELS, not the tool

**Date:** 2026-07-26 · **Status:** durable evidence, not a plan · **Reporter:** the owner (Andrzej)

The sibling [`agent-reports.md`](agent-reports.md) records **tool friction**: what the building agents
hit while driving `uedcli`. This file records the other half — **what is wrong with the levels they
produced**, judged by playing and inspecting them.

The distinction matters because the two lists barely overlap. An agent reports what *blocked* it; it
cannot report what it never noticed. Every finding below was invisible to the agent that built it:
each level was declared finished, screenshotted, and accepted. `agent-reports.md` already shows why
that happens — a level shipped with ~15 props silently missing and nobody spotted it until a render;
another shipped an unlit map because nothing reports whether lighting baked. **Output quality is
therefore a separate axis from tool friction, and needs its own log.**

## How to read an entry

- **Observed** — the owner's finding, as reported. This is the load-bearing part.
- **Where** — level(s), when known.
- **Status** — `confirmed` (seen directly) · `to confirm` (needs a check, named in the entry).
- **Tool/doc state** — *agent analysis, added after the fact, clearly separated from the observation.*
  Whether the tool could do the right thing, whether the docs say so, and therefore whether the defect
  is a missing capability, a missing check, or an agent that had what it needed and did not use it.

That last line is the one that decides what to fix, and it is where the surprise is: **most of these
are not missing capabilities.**

---

## 1. All doors slide; none rotate

**Observed:** every door in every level is a sliding door. There are no rotating/swinging doors.
**Where:** all three levels.
**Status:** confirmed.
**Tool/doc state:** **not a gap — the capability and the recipe both exist and were not used.**
`mover key rotate <M> 1 --by 0,16384,0` is a first-class verb whose own `usage.md:882` example is
annotated *"swings about the hinge, not the centre"*; `movers.set_key_rot`/`key_rot` write `KeyRot(i)`;
and [`docs/leveldesign/general/recipes/mover-door.md`](../../../../docs/leveldesign/general/recipes/mover-door.md)
opens with *"A door that swings (or slides) open"* and tells you to rotate about the hinge edge for a
swing. So this is an **output-quality/agent-default finding**, not a missing verb.

Worth noting one real incentive toward sliding, from `agent-reports.md`: a slide needs a solid
**pocket** for the leaf, and getting a pocket wrong against curved geometry produced a visible
black slab floating on a platform. A swing door needs no pocket. If anything the tool's easier path is
the *rotating* one, which makes the uniformity more surprising, not less.

**Suggested fix:** this is a docs/brief emphasis problem. The door recipe leads with the mechanism, not
with *"a swing door is the default in an interior; slide doors are for industrial/airlock contexts."*

## 2. Entrances and corridors are far too small

**Observed:** entrances and corridors are very small — cramped to move through.
**Where:** all three levels.
**Status:** confirmed.
**Tool/doc state:** the numbers **are** documented — `docs/leveldesign/general/human-scale.md` and
`docs/leveldesign/deusex/human-scale.md` both exist, and `MaxStepHeight = 25` and the player's standing
box are cited in `agent-reports.md`. So the facts were available and the results still came out tight.
Two plausible contributors, both checkable: an agent sizes an opening to the player's *collision box*
rather than to a comfortable clearance, and nothing measures a built passage afterwards.

**Suggested fix:** NOT a `level doctor` check — see finding 3 for why (owner ruling: doctor cannot
know what a space is *meant to be*). This belongs to an independent reviewing agent, or to the level
brief stating target clearances up front so the number is chosen before the geometry is cut.

## 3. Geometry overlaps entrances, making them hard to pass

**Observed:** geometry protrudes into entrances, obstructing movement through them.
**Where:** confirmed on TubePlatform; suspected more widely.
**Status:** confirmed.
**Tool/doc state:** **independently corroborated in `agent-reports.md`, and it is the single
highest-value missing check.** That log found **four** separate additive brushes occluding subtracted
passages on one level while `level doctor` reported *"no issues found"* throughout: a wall conduit
crossing **all three** wall openings at 20–36 uu above the floor (above `MaxStepHeight` 25, so an
unsteppable bar across every route in the level), two ad panels cutting a 128-uu doorway to 56 uu
(crouch-only), and two crates in front of a vent mouth. The agent found them only by reading `--game`
renders and hand-deriving arc geometry in Python — *"the better part of an hour"* — and two of the four
were invisible in the wireframe preview because `actor preview` draws brush outlines with no notion of
solid-vs-void.

**Suggested fix — and an explicit REJECTION of the obvious one.** `agent-reports.md` proposes a
`level doctor` `occlusion` category (and calls it *"the single highest-value check that could have been
run on this level"*), and an earlier draft of this entry endorsed it. **The owner has ruled it OUT of
`doctor`, permanently** *(2026-07-26)*, and the rationale is decisive rather than a matter of cost:

> `doctor` has no way of knowing whether something **is meant to be a passage**.

A sealed wall and an accidentally-blocked doorway are the *same geometry*; they differ only in authorial
intent, which is not in the trunk. A check that flags one necessarily flags the other, so it would either
cry wolf on every deliberate wall or need a heuristic guess at what each void is for. That is the general
boundary now recorded in `docs/usage.md` and `architecture.md`: **doctor reports only what is wrong
regardless of intent.** This is a rejection, not a deferral — do not revisit it with better heuristics.

So this finding is real and remains unaddressed *by design*. It belongs to **an independent reviewing
agent reading `--game` renders** (open question 1), which is exactly the case for having one: two of the
four TubePlatform cases were invisible in the wireframe preview, so the reviewer must look at game
renders, not schematics.

## 4. Texture alignment is off

**Observed:** textures are misaligned. *"probably due to missing verbs, so justified I guess?"*
**Where:** all three levels.
**Status:** confirmed.
**Tool/doc state:** **half justified, and the split matters.** `agent-reports.md` documents both
kinds:

- **Genuinely blocked — no verb exists.** `builders._tex_basis` computes `v = cross(normal, u)`, so
  **every** face any generator emits (cube, sheet, revolve, extrude) satisfies `U × V = +N`. The engine
  draws that handedness mirrored, so a lettered texture is backwards on every uedcli-built surface.
  `brush poly align --fresh-frame` calls the *same* function and therefore cannot fix it. There is no
  `--flip-u`/`--flip-v`, and no texture **scale** control at all (`--pan-to/--pan-by` and
  `align --wall|--floor|--ring` are the whole surface toolkit).
  > *(Editorial note, 2026-07-27: the scale gap is CLOSED — `brush poly scale --by FU,FV` ships, and
  > `brush poly rotate --by UU` with it; pan is now `brush poly pan --to/--by`. `--flip-u`/`--flip-v`
  > still do not exist.)*

  The only lever found was
  `brush scale --by -1,1,1` + `brush apply-transform`, which also re-orients rotated brushes and needs a
  compensating rotate. **This part is justified.**
- **NOT blocked — fixable with existing verbs, and shipped anyway.** Sheet generators emit `Origin` at
  the sheet's geometric centre, so texel 0 lands in the middle of the panel and each quadrant wraps to
  the opposite side — a visible seam down every sign. One `brush poly set --pan-to <w/2>,<h/2>` fixes
  it. *(Editorial note, 2026-07-27: now spelled `brush poly pan --to <w/2>,<h/2>`.)* Same for a texture larger than its face wrapping into a black "+" cross. **This part is a
  quality miss, not a capability gap** — and it is invisible on tiling concrete, which is exactly why
  it survived.

**Suggested fix:** `--flip-u`/`--flip-v` on `brush poly set` collapses the first group into one command
(named in `agent-reports.md` three separate times). For the second, a sheet whose texture frame started
at a **corner** rather than the centre would need no pan at all — worth considering as the generator
default.

## 5. A scripted pawn in DiveBar does not yield when bumped

**Observed:** a scripted pawn behind the bar does not move away when the player bumps into it, making
it hard to get behind the bar. Unclear whether deliberate or accidental.
**Where:** DiveBar.
**Status:** **to confirm** — is this the pawn's configuration, or stock DX behaviour for this pawn
class/state?
**Tool/doc state:** untouched by `agent-reports.md`; no finding on pawn collision or yielding.
`docs/leveldesign/deusex/npcs.md` and `recipes/npc-patrol.md` exist but have not been checked against
this. **The check:** compare the pawn's class and its `bBlockPlayers`/collision and orders/state
properties against a stock DX barkeep in a retail map. If a scripted/conversation pawn blocks by
design, the fix is placement (don't strand one in a one-tile gap); if it is misconfigured, it is a
recipe gap.

## 6. Deus Ex conversation choices overflow the screen

**Observed:** too many conversation choices push some choices off-screen, and the list does not
scroll — so those choices are unreachable.
**Where:** Deus Ex substrate generally (surfaced via a built level's conversation).
**Status:** **to confirm**, two questions: (a) is this stock DX behaviour or something about how the
`.con` was authored, and (b) **what is the maximum number of choices the retail game ever uses?**
**Tool/doc state:** a real substrate constraint with no home in the docs —
`docs/leveldesign/deusex/conversations-and-computers.md` sets no choice ceiling.

**The check, and it is cheap.** `agent-reports.md`'s `DConImport` work established that this machine
holds **149 distinct `.con` files** after content-dedup, spanning retail DEED-reconstructed
conversations, the DX SDK, TNM/ConEditPlus and Confix — and that the format is understood well enough
to parse events (that work decoded `MissionFile.unrecognized1` as the byte length of the four name
tables, and `DConImport`'s per-Choice audio naming as `Choice<NN><letter>` with `letter = 'a'+index`).
So: **parse every retail `.con`, count `ChoiceOption`s per `Choice` event, and report the maximum and
the distribution.** That gives a defensible ceiling from the shipped game rather than a guess, and the
`'a'+index` audio convention gives an independent cross-check on how many the engine's own tooling
expected. Then state the ceiling in the conversations doc.

## 7. Decoration rotation and placement are broken

**Observed:** decorations are rotated wrongly and placed off their surfaces. Two concrete cases: a
**rectangular flat light rotated 90° off**, and a **subway button floating in mid-air rather than
mounted on the wall**.
**Where:** at least TubePlatform (subway button).
**Status:** confirmed.
**Tool/doc state:** **corroborated — but the rotate half of this analysis was WRONG, and is corrected
here (2026-07-27).** The observation above is unchanged; only the agent analysis below is revised.

- ~~**`actor rotate` pivots about the bbox MIN CORNER, not the actor's centre**, and there is no
  `--about center|origin|X,Y,Z` option.~~ **RETRACTED — it never affected decorations at all.**
  `best_grid_pivot` scored brush world vertices *and point-actor Locations*, so a lone point actor had
  exactly one candidate — its own Location — and already rotated **exactly in place** (verified live:
  `actor rotate BarrelFire --by 0,32768,0` leaves Location byte-identical). A flat light 90° off and a
  button floating off a wall were never caused by a pivot. They were caused by the next bullet: no way
  to learn a mesh's facing or footprint. That is the real defect in this finding.

  The min-corner behaviour was real but applied to **brushes**, and only where a symmetric selection
  made every candidate tie on alignment. The correction appended to `agent-reports.md` also retracts
  the two supporting claims: `--pivot X,Y,Z`, `--pivot-actor NAME` and `--to` all existed at the time,
  and the "float dust on an exactly-on-grid brush" was an `actor bbox` readout — the trunk was exact.
  *(Fixed since: the default pivot is now the `Location` of the member nearest the bbox centre.)*
- **Nothing tells an agent where a decoration's origin sits.** The spec revision for the asset catalog
  addresses precisely this: *"an agent can see a crate and still has to guess its footprint, and
  whether its origin sits at the base or the centre — so decorations sink into floors and
  interpenetrate."* A button floating off a wall is the same missing fact in the horizontal direction.
  `class show` reporting bbox/collision/`PrePivot` is specced but **not built**.

**Suggested fix:** ~~`--about center|origin|X,Y,Z` on `actor rotate`~~ — **dropped**: the flag would
have been a second spelling of the existing `--pivot`, and the pivot was not this finding's cause. What
remains is the already-specced **class placement facts** (`class show` reporting mesh bbox as signed
mesh-local extents, collision, `PrePivot`), which is the whole of it — cheaper than the renders needed
to catch these by eye. Note *detecting* a badly-seated decoration is NOT a `doctor` job — whether a button belongs
on that wall is intent — but giving the builder the origin/bbox facts up front prevents it at authoring
time, which is the better fix anyway.

## 8. Missing trim plates and fine detail

**Observed:** entryways lack the fine detail real architecture has — a door frame or equivalent. The
common way to build one: **make a solid cube, then subtract a slightly smaller cube.** A doorframe may
protrude a couple of uu on both faces of the wall, but it need not.
**Where:** all three levels.
**Status:** confirmed.
**Tool/doc state:** the *technique* is documented — there is an
[`add-subtract-twin.md`](../../../../docs/leveldesign/general/recipes/shapes/add-subtract-twin.md)
shape recipe, which is the pattern described. What is missing is any statement that an **entryway
should have one**. The level-design craft docs cover geometry, BSP, lighting and scale, but nothing
tells an agent that a bare subtracted hole reads as unfinished, or gives the couple-of-uu protrusion
convention. So: **a craft/brief gap, not a capability gap.**

**Suggested fix:** a short "trim and edge detail" section in
`docs/leveldesign/general/design-craft.md` with the doorframe as the worked example — solid cube minus
a slightly smaller cube, protrusion optional, a couple of uu — plus a line in the DX human-scale doc.
This is the cheapest finding here to close and it affects every level.

---

## Cross-cutting: what this list says that the agent log does not

**Six of the eight are NOT missing capabilities.** Findings 1 and 8 are docs/craft gaps where the verb
and even the recipe already existed. Findings 2, 3 and half of 4 are *missing checks* — the tool could
have measured the defect offline and said nothing. Only the mirroring half of 4, and the
`actor rotate` pivot in 7, are true capability gaps.

That is a different conclusion from `agent-reports.md`, which — being written by the agents that were
blocked — skews toward missing verbs and false-success defects. **Both are needed.** An agent cannot
report a level that came out ugly while every command it ran succeeded.

**The recurring shape is: nothing measures the finished level against how a human plays it.** Passage
clearance (2, 3), decoration seating (7) and surface legibility (4) all went unreported, and
`level doctor` said *"no issues found"* on a level with four blocked doorways.

**But `doctor` is NOT the owner of that gap, and saying so is the point of this section.** Owner ruling,
2026-07-26: doctor reports only defects that are wrong *regardless of authorial intent*, because it
cannot know what a space is meant to be — a sealed wall and a blocked doorway are identical geometry.
Two of these findings therefore split cleanly:

- **Doctor's job** (intent-independent, objectively wrong): a light buried in solid geometry lights
  nothing; an `Event` matching no `Tag` fires into the void. Both are still unimplemented — the second
  already exists in `eventgraph.py` as `dangling_event` but is surfaced only by `event graph`.
- **NOT doctor's job** (needs intent): passage clearance and occlusion (2, 3), decoration seating (7),
  trim and finish (8). These need eyes on `--game` renders.

So the honest conclusion is the opposite of "add more doctor checks": **the missing thing is an
independent reviewer**, and doctor's scope boundary is what makes that unavoidable rather than optional.
See `docs/usage.md` "What `level doctor` WILL and WILL NOT find".

## Open questions

1. **Should an agent review the levels independently?** Owner's question, 2026-07-26. Discussed in the
   session; recorded here because the evidence for it is in these two files. Not yet decided.
2. **Finding 5** — is the non-yielding pawn stock DX behaviour or misconfiguration?
3. **Finding 6** — what is the retail maximum choice count? (Method in the entry: parse the 149 `.con`
   files.)
