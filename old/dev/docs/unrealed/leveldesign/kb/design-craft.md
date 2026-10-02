# The craft of a good level  [ENGINE] + [DX]

Other files in this `kb/` cover mechanics — CSG, BSP, lighting, zones, movers, the actor layer. This
file covers craft: what makes a level good. Two halves:

1. **[ENGINE]** — general level craft (composition, lighting for mood, flow & pacing) for any
   UnrealEngine-1 level (Unreal, UT, Deus Ex alike).
2. **[DX]** — the Deus Ex immersive-sim design philosophy (§4): making a level a problem-space with
   multiple valid solutions. From the designers (Warren Spector's "Rules of Roleplaying", Harvey
   Smith's "Systemic Level Design", the GDC/Gamasutra postmortems), so 📖 by provenance but design
   doctrine, not an engine fact to verify.

> **Connection to mechanics.** Craft rules cash out in verbs and numbers documented elsewhere:
> "design to the player's size" means the [DX] player cylinder in
> [`human-scale.md`](./human-scale.md); "light for mood" means the `Light` properties in
> [`lighting.md`](./lighting.md); "multiple routes" means vents/ducts/ladders (a texture-Group
> `Ladder` surface — [`textures.md`](./textures.md)), doors ([`movers.md`](./movers.md)), hackable
> devices ([`dx-classes.md`](./dx-classes.md)), and guard behaviour ([`dx-npcs.md`](./dx-npcs.md)).

---

## 1. Composition  [ENGINE]

- **Design to the player's size.** Build to the substrate's actual pawn dimensions, not by eye — the
  [DX] player cylinder is 40 wide × 95 tall ([`human-scale.md`](./human-scale.md)).
- **Get proportion right.** Sketch to scale, with floor heights, before you build. A wrong-size room
  can't be fixed by detailing.
- **Avoid the bare box.** A bare cuboid reads as unfinished. Detail every surface: trim platform and
  stair edges, arch doorways (also a motivated place to mount a light), break big flat walls with
  recesses and pillars. Where poly budget won't allow more geometry, use shadow instead — an unlit
  expanse reads as depth, not a bare wall.
- **Interconnect; avoid room-corridor-room.** A string of rooms joined by single corridors is the
  dead pattern. Loop the space back on itself and connect across two or more floors ("a snake eating
  itself") so the player re-encounters spaces from new angles.
- **Think in 3D — verticality.** Overlooks, balconies, catwalks, pits, vents overhead. Vertical
  connection turns a floor plan into a space, and in DX it is also route variety (§4).
- **Break long sightlines, but show the goal.** Long straight sightlines hurt framerate (nothing gets
  zone-culled — see [`zones-performance.md`](./zones-performance.md)) and flatten the space. Break
  them with structure, but let the player glimpse the objective/landmark ahead so they always have a
  direction — via L-bends, windows, and partial reveals.
- **Landmarks — visually and audibly distinct.** Anchor the space with dominant, memorable landmarks.
  Make them distinct to the ear too: lifts, teleporters, water, and pickups each carry a distinct
  sound, so a player orients by "the room with the humming lift" even off-screen.
- **Contrast, deliberately.** Alternate open vs tight, bright vs dark, ornate vs plain. A uniformly
  medium level is forgettable.

---

## 2. Lighting for mood  [ENGINE]

(Mechanics — `Light` properties, the bake pipeline, the `LightType`/`LightEffect` split — are in
[`lighting.md`](./lighting.md). This is the craft layer on top.)

- **Motivate every light.** Each light needs a visible fixture or plausible source (lamp, window,
  fire). Unmotivated light reads as fake.
- **Never light flat.** A single fill light kills all form. Use at least two lights per space — a
  hotspot plus a falloff — so surfaces have a gradient. Keep any zone ambient ≤ ~32.
- **Radius is the primary tool** for distinct pools of light. The default `LightRadius` of 64 often
  bleeds between rooms — drop it to ~5 for a tight tunnel pool, push it to ~175 for open outdoors.
- **Light to guide, and light to hide.** Crisp, high-shadow-detail patterns and a beacon spotlight
  pull the eye toward the route or goal. Put secrets, enemies, and alternate routes in shadow.
- **Colour for zone identity.** Drop `LightSaturation` from 255 toward ~64 for a visible tint
  (saturation is inverted — lower = more colour). A consistent colour per zone helps the player hold
  a mental map (the "cold blue server room", the "amber lobby").
- **Cost is ~r³.** Prefer many small-radius lights over a few huge ones — cheaper and more
  controllable.

---

## 3. Flow & pacing  [ENGINE]

- **Plan the layout — and the gameplay — first, on grid paper.** The floor plan is the gameplay in
  an environmental game; decide it before opening the editor.
- **Blockout in primitives, detail last.** Build the whole level in plain subtracted boxes, get flow
  and scale right by walking it, then detail. This is both the commercial workflow and the only
  reliable performance regulator — you can't optimise a fundamentally over-complex space, only
  re-block it.
- **Aim for "complicated linearity."** The path can be essentially linear while the how — route
  choices, vertical options, order of engagement — is rich.
- **Break up your innovations.** Don't stack every effect in one open view — strobe light, fog,
  high-shadow-detail, and a big firefight at once is noise and tanks framerate. Keep complex lighting
  in enclosed, short-sightline areas; space set-pieces out.
- **Item placement by risk-vs-reward.** The better the reward, the more it should cost to reach —
  guarded, hidden, off the safe path, behind a lock or a hack. A free pickup on the main route
  teaches nothing.
- **Always signal progress; never leave the player lost.** Every action should visibly change the
  world or open a way forward. (In DX this becomes legibility by architecture — §4, since there is no
  GPS.)
- **Favour interactivity.** Movers, usable devices, breakables — "players want to affect the level,
  not just pass through it."

---

## 4. The Deus Ex immersive-sim design philosophy  [DX]

What makes a level specifically a Deus Ex level, not just a good UE1 level. Doctrine from the people
who made the game. You build not a route the player traverses but a problem-space with multiple valid
solutions.

### 4.1 Problems, not puzzles

A DX obstacle is an obstacle course, not a jigsaw. A puzzle has one intended solution the player must
guess — read the designer's mind. A problem has many solutions and the player chooses one. If there
is exactly one way through, you have built a puzzle.

### 4.2 Multiple solutions, keyed to the character the player built

Every obstacle should yield to several approaches, keyed to skills · augmentations · objects ·
weapons — the routes that open up are the character the player chose to be. The approach axes:

- **Combat** — fight through (weapons, ammo, aggressive augs).
- **Stealth** — avoid detection (shadow, cover, silent movement, non-lethal takedowns).
- **Hacking** — defeat the electronic layer (keypads, computers, cameras, turrets — see
  [`dx-classes.md`](./dx-classes.md)).
- **Social** — talk your way through (conversations, NPCs who unlock a path — see
  [`dx-npcs.md`](./dx-npcs.md)).

…plus architectural routes that are pure level geometry: vents, ducts, ladders, windows, catwalks,
rooftops, sewers. A ladder is a texture-Group `Ladder` surface ([`textures.md`](./textures.md)); a
vent is subtracted geometry sized for the crouching player ([`human-scale.md`](./human-scale.md)); a
catwalk is verticality (§1). Even a bare "left hall vs right hall" fork sorts players by temperament
into their preferred playstyle.

### 4.3 How they actually shipped it — author ~3 real routes per obstacle

The era's tech couldn't fully simulate open-ended solutions, so the designers hand-authored three
explicit routes per problem — typically skill/stealth, action/combat, and character-interaction/social
— then let the game's systems add emergent extras. You don't need a full simulation for the
immersive-sim feel: author roughly three genuine, distinct, keyed routes past each real obstacle.
"Genuine" is load-bearing — a fake alternate that dead-ends or re-joins the main path two feet later
is a lie (§4.4).

### 4.4 Systemic consistency

From Harvey Smith's "Systemic Level Design":

- **Design behaviour by object TYPE, not by instance.** "Things that are the same behave the same, by
  default." Every crate breaks the same way, every keypad hacks the same way, every guard reacts the
  same way.
- **Why it matters: consistency → prediction → planning → agency.** The difference between "playing
  the game" and "playing the designer." An inconsistent world forces the player to guess your
  intentions at every object — back to puzzles (§4.1).
- **Emergence falls out of consistent simple rules.** The mine-climbing trick (stick LAMs to a wall,
  climb them) was never designed — it emerged because "mines stick to walls" and "the player can
  stand on things" compose. Keep rules simple and consistent and you get emergence for free; you
  cannot script it.
- **Do not depict non-functional things.** (A corollary that circulates around the talk — a community
  distillation, not a verbatim Smith slide.) A door that doesn't open, a terminal that does nothing,
  a drawer that won't — every "lie" about interactivity erodes planning and teaches the player to
  stop trying. If it looks interactive, make it interactive; if you can't, don't depict it so.

### 4.5 Readable stealth as a mechanic

Stealth in DX is gameplay, not mood. Light and shadow, cover, and guard sight/sound cones are
mechanics the player reads and exploits. For that to work:

- **Sound must propagate consistently** and **props must be throwable**, so distraction becomes a
  player tool (throw something to pull a guard off his post — see the `ScriptedPawn` reaction blocks
  in [`dx-npcs.md`](./dx-npcs.md), e.g. `bReactLoudNoise` → seek).
- **Teach affordances diegetically.** Put a crowbar next to the breakable crates; put a shadow next
  to the guarded route. The environment teaches its own mechanics without a tutorial pop-up.

### 4.6 Environmental storytelling

Two channels:

1. **Conversations** — the NPCs and what they say.
2. **In-world text** — datacubes, emails, books, newspapers (see the info-device classes in
   [`dx-classes.md`](./dx-classes.md) and [`dx-conversations-computers.md`](./dx-conversations-computers.md)).
   Rewards explorers with story and mechanical payoff — a datacube that delivers lore and a door
   keypad code.

Aim for specificity: don't build "a warehouse" — build "this warehouse, where these people did this
thing," and let the props, text, and layout tell that story.

### 4.7 No in-game GPS → legibility by architecture

Deus Ex has no minimap and no world objective markers, so the space itself must be legible. The
player navigates by architecture:

- **Dominant, always-visible landmarks** (§1) the player can orient by from anywhere.
- **Plausible real-world geography** — the space should make sense as a place, so real-world
  intuition ("the exit is probably near the lobby") works.
- **Light and leading-lines toward routes** (§2) — lighting is navigation, not just mood.
- **Pair every multi-path region with a readable central spine and a clear hierarchy of landmarks.**
  This is where the immersive-sim goal (many routes, §4.2) fights legibility: many interconnected
  routes with no landmark hierarchy and no clear spine ("spaghetti") leave the player lost.

### 4.8 Hub structure & reactivity

- **Hub-and-spoke with return visits.** Send the player out from and back to a hub that persists and
  evolves between visits — the return is where the world shows it remembered what the player did.
- **Fewer characters = deeper characters.** A handful of well-developed NPCs the player revisits beats
  a crowd of one-liners. (Mechanically: bind them with `BindName`, give them alliances and orders —
  [`dx-npcs.md`](./dx-npcs.md).)
- **Choice without consequence is irrelevant** — a choice that changes nothing is not a choice.
- **Consequence must be predictable to be fair.** The player must foresee, by real-world logic,
  roughly what a choice will cause. A consequence out of nowhere is a "gotcha," and it punishes the
  planning you spent §4.4 building.
- **Choice + Consequence + Recovery** (a later Spector formulation — from his 2020s interviews, not
  the 2000 postmortem, which used just choice + consequence). Give the player a way to recover from a
  botched attempt — a failed hack, a blown stealth, a killed NPC you needed should reshape the
  situation, not hard-fail it. Recovery is what makes bold choices safe to make.

---

*Siblings: [`README.md`](./README.md) (index) · [`human-scale.md`](./human-scale.md) ·
[`sources.md`](./sources.md) · [`lighting.md`](./lighting.md) · [`dx-npcs.md`](./dx-npcs.md) ·
[`dx-classes.md`](./dx-classes.md) · [`zones-performance.md`](./zones-performance.md).*
