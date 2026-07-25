# The craft of a good level  [ENGINE] + [DX]

Every other file in this `kb/` is about **mechanics** — how CSG, BSP, lighting, zones, movers, and the
actor layer *work*. This file is about **craft**: what makes a level *good* once you can build one at
all. It has two halves:

1. **[ENGINE] — the craft of a good level in general**: composition, lighting-for-mood, and flow &
   pacing. These apply to any UnrealEngine-1 level (Unreal, UT, Deus Ex alike).
2. **[DX] — the Deus Ex immersive-sim design philosophy** (§4): the crown jewel. This is a *different
   kind* of knowledge — how to make a level a **problem-space with multiple valid solutions** — and is
   the core of what "a good **Deus Ex** level" specifically means. It comes from the actual designers
   (Warren Spector's "Rules of Roleplaying", Harvey Smith's "Systemic Level Design", the GDC/Gamasutra
   postmortems), so it is 📖 by provenance but is *design doctrine*, not an engine fact to verify.

> **How this connects to the mechanics.** Craft rules cash out in the verbs and numbers documented
> elsewhere: "design to the player's size" means build to the **[DX] player cylinder** in
> [`human-scale.md`](./human-scale.md); "light for mood" means the `Light` properties in
> [`lighting.md`](./lighting.md); "multiple routes" means vents/ducts/ladders (a **texture-Group
> `Ladder`** surface — [`textures.md`](./textures.md)) and doors ([`movers.md`](./movers.md)) and
> hackable devices ([`dx-classes.md`](./dx-classes.md)) and guard behaviour
> ([`dx-npcs.md`](./dx-npcs.md)). Craft is the *why*; the other files are the *how*.

---

## 1. Composition  [ENGINE]

- **Design to the player's size.** Build to the substrate's actual pawn dimensions, not by eye — the
  **[DX] player cylinder is 40 wide × 95 tall** ([`human-scale.md`](./human-scale.md)). Proportion is
  the first thing the eye reads and the first thing that reads *wrong*.
- **Proportion over everything.** Sketch to scale, with floor heights, before you build. A room that
  is the wrong size can't be fixed by detailing it.
- **Kill the box.** A bare cuboid room reads as unfinished. **Detail every surface**: trim the edges
  of platforms and stairs, arch doorways (which also gives you a motivated place to mount a light),
  break up big flat walls with recesses and pillars. Where the poly budget won't allow more geometry,
  **use shadow to hide the flat surface** instead — an unlit expanse reads as depth, not as a bare
  wall.
- **Interconnect — avoid room-corridor-room.** A string of rooms joined by single corridors is the
  dead pattern. Loop the space back on itself and connect **across two or more floors** ("a snake
  eating itself") so the player re-encounters spaces from new angles.
- **Think in 3D — verticality.** Overlooks, balconies, catwalks, pits, vents overhead. Vertical
  connection is what turns a floor plan into a *space*, and in DX it is also route variety (§4).
- **Break long sightlines, but show the goal.** Long straight sightlines hurt framerate (nothing gets
  zone-culled — see [`zones-performance.md`](./zones-performance.md)) *and* flatten the space. Break
  them with structure — **but** let the player glimpse the objective/landmark ahead so they always
  have a direction (the "show the goal" tension against "break the sightline" is resolved with
  L-bends, windows, and partial reveals).
- **Landmarks — visually AND audibly distinct.** Anchor the space with dominant, memorable landmarks
  the player can navigate by. Make them distinct not just to the eye but to the **ear**: lifts,
  teleporters, water, and pickups each carry a distinct sound, so a player orients by "the room with
  the humming lift" even off-screen.
- **Contrast, deliberately.** Alternate open vs tight, bright vs dark, ornate vs plain. Contrast is
  what makes each space *feel* like somewhere; a level that is uniformly medium everywhere is
  forgettable.

---

## 2. Lighting for mood  [ENGINE]

*(Mechanics — `Light` properties, the bake pipeline, the `LightType`/`LightEffect` split — are in
[`lighting.md`](./lighting.md). This is the craft layer on top.)*

- **Motivate every light.** Each light should have a visible fixture or plausible source (a lamp, a
  window, a fire). Unmotivated light reads as fake.
- **Never light flat.** A single fill light kills all form. Use a **minimum of two** lights per space
  — a hotspot plus a falloff — so surfaces have a gradient. Keep any zone **ambient ≤ ~32**; ambient
  is the enemy of shadow.
- **Radius is the primary tool** for distinct pools of light. The **default `LightRadius` of 64 often
  bleeds** between rooms — drop it to ~5 for a tight tunnel pool, push it to ~175 for open outdoors.
  Distinct pools of light *are* the composition of the lit scene.
- **Light to guide, and light to hide.** Crisp, high-shadow-detail patterns and a beacon spotlight
  pull the eye toward the route or the goal (a leading-line the player follows without being told).
  Conversely, put secrets, enemies, and alternate routes **in shadow** — darkness is where the player
  earns discovery.
- **Colour for zone identity.** Drop `LightSaturation` from 255 toward ~64 for a visible tint (recall
  saturation is **inverted** — lower = more colour). A consistent colour per zone helps the player
  hold a mental map (the "cold blue server room", the "amber lobby").
- **Cost is ~r³.** Prefer many small-radius lights over a few huge ones — cheaper and far more
  controllable.

---

## 3. Flow & pacing  [ENGINE]

- **Plan the layout — and therefore the gameplay — first, on grid paper.** The floor plan *is* the
  gameplay in an environmental game; decide it before you open the editor.
- **Blockout in primitives, detail last.** Build the whole level in plain subtracted boxes, get the
  flow and scale right by walking it, *then* detail. This is both the commercial workflow and **the
  only reliable performance regulator** — you can't fix a fundamentally over-complex space by
  optimising, only by re-blocking it.
- **Aim for "complicated linearity."** The path can be essentially linear while the *how* — the route
  choices, the vertical options, the order of engagement — is rich. Interesting-how beats sandbox-for-
  its-own-sake.
- **Break up your innovations.** Don't stack every cool thing in one open view — a strobe light *and*
  fog *and* high-shadow-detail *and* a big firefight all at once is noise, and it tanks the framerate.
  Keep complex lighting in enclosed, short-sightline areas; space the set-pieces out.
- **Item placement by risk-vs-reward.** The better the reward, the more it should cost to reach —
  guarded, hidden, off the safe path, behind a lock or a hack. A pickup lying free on the main route
  teaches nothing.
- **Always signal progress; never leave the player lost.** Every action should visibly change the
  world or open a way forward. If the player can't tell whether they're making progress, the pacing
  has failed. (In DX specifically this becomes *legibility by architecture* — §4, since there is no
  GPS.)
- **Favour interactivity.** Movers, usable devices, breakables — "players want to *affect* the level,
  not just pass through it." An interactive space feels alive; a static one is a diorama.

---

## 4. The Deus Ex immersive-sim design philosophy  [DX] — the crown jewel

This is the heart of what makes a level specifically a *Deus Ex* level, as opposed to a good UE1 level
in general. It is doctrine from the people who made the game, and it changes what you are even trying
to build: not a route the player traverses, but a **problem-space with multiple valid solutions**.

### 4.1 Problems, not puzzles

**The single most-cited DX maxim.** A DX obstacle is an **obstacle course, not a jigsaw**. A puzzle
has one intended solution and the player's job is to guess it — to *read the designer's mind*. A
problem has many solutions and the player's job is to *choose* one. **Never build an obstacle whose
solution requires the player to intuit what you were thinking.** If there is exactly one way through,
you have built a puzzle, and it is the wrong shape.

### 4.2 Multiple solutions, keyed to the character the player built

Every obstacle should yield to **several approaches, keyed to skills · augmentations · objects ·
weapons** — because the routes that open up *are* the character the player chose to be. The canonical
approach axes:

- **Combat** — fight through (weapons, ammo, aggressive augs).
- **Stealth** — avoid detection (shadow, cover, silent movement, non-lethal takedowns).
- **Hacking** — defeat the electronic layer (keypads, computers, cameras, turrets — see
  [`dx-classes.md`](./dx-classes.md)).
- **Social** — talk your way through (conversations, NPCs who unlock a path — see
  [`dx-npcs.md`](./dx-npcs.md)).

…**plus architectural routes** that are pure level geometry: **vents, ducts, ladders, windows,
catwalks, rooftops, sewers.** A ladder is a **texture-Group `Ladder`** surface
([`textures.md`](./textures.md)); a vent is subtracted geometry sized for the crouching player
([`human-scale.md`](./human-scale.md)); a catwalk is verticality (§1). Even a bare **"left hall vs
right hall" fork** does real work — it sorts players by temperament into their preferred playstyle.

### 4.3 How they actually shipped it — author ~3 real routes per obstacle

**The practical tactic a modder can copy directly.** The tech of the era couldn't fully *simulate*
open-ended solutions, so the designers **hand-authored three explicit routes per problem** — typically
**a skill/stealth path, an action/combat path, and a character-interaction/social path** — and then
let the game's systems add emergent extras on top. **You do not need a full simulation to get the
immersive-sim feel: author roughly three genuine, distinct, keyed routes past each real obstacle and
the player experiences it as freedom.** "Genuine" is the load-bearing word — a fake alternate that
dead-ends, or that just re-joins the main path two feet later, is a lie (§4.4).

### 4.4 Systemic consistency

From Harvey Smith's "Systemic Level Design":

- **Design behaviour by object TYPE, not by instance.** "Things that are the same behave the same, by
  default." Every crate breaks the same way, every keypad hacks the same way, every guard reacts the
  same way.
- **Why it matters: consistency → prediction → planning → agency.** When the world behaves
  predictably, the player can *predict*, therefore *plan*, therefore feel real agency. This is the
  difference between **"playing the game" and "playing the designer."** An inconsistent world forces
  the player to guess your intentions again at every object — back to puzzles (§4.1).
- **Emergence falls out of consistent simple rules.** The famous mine-climbing trick (stick LAMs to a
  wall, climb them) was never designed — it emerged because "mines stick to walls" and "the player can
  stand on things" are consistent rules that compose. You get emergence for free by keeping rules
  simple and consistent; you cannot script it.
- **Do not depict non-functional things.** *(A widely-cited corollary that circulates **around** the
  talk — a community distillation, not a verbatim slide from Smith's deck.)* A door that doesn't open, a
  terminal that does nothing, a drawer that won't — **every "lie" about interactivity erodes the player's
  ability to plan** and teaches them to stop trying. If it looks interactive, make it interactive; if you
  can't, don't depict it as interactive.

### 4.5 Readable stealth as a mechanic

Stealth in DX is **gameplay, not mood**. Light and shadow, cover, and guard sight/sound cones are
*mechanics the player reads and exploits* — not just atmosphere. For that to work:

- **Sound must propagate consistently** and **props must be throwable**, so that *distraction becomes
  a player tool* (throw something to pull a guard off his post — see the `ScriptedPawn` reaction
  blocks in [`dx-npcs.md`](./dx-npcs.md), e.g. `bReactLoudNoise` → seek).
- **Teach affordances diegetically.** Put a crowbar next to the breakable crates; put a shadow next to
  the guarded route. The environment should teach its own mechanics without a tutorial pop-up.

### 4.6 Environmental storytelling

Two channels, and the second is uniquely powerful:

1. **Conversations** — the NPCs and what they say.
2. **In-world text** — datacubes, emails, books, newspapers (see the info-device classes in
   [`dx-classes.md`](./dx-classes.md) and [`dx-conversations-computers.md`](./dx-conversations-computers.md)).
   Crucially this **rewards explorers with both story *and* mechanical payoff** — a datacube that
   delivers lore *and* a door keypad code. The reward for reading is not just flavour; it's a key.

The goal is specificity: don't build "a warehouse" — build **"*this* warehouse, where *these* people
did *this* thing," and let the props, text, and layout tell that story.

### 4.7 No in-game GPS → legibility by architecture

Deus Ex has **no minimap and no objective markers on the world**, so the *space itself* must be
legible. The player navigates by architecture, which puts a hard requirement on the level:

- **Dominant, always-visible landmarks** (§1) the player can orient by from anywhere.
- **Plausible real-world geography** — the space should make sense as a *place*, so the player's
  real-world intuition ("the exit is probably near the lobby") actually works.
- **Light and leading-lines toward routes** (§2) — lighting is navigation, not just mood.
- **A multi-path level needs a readable spine + a strong landmark hierarchy.** This is exactly where
  the immersive-sim goal (many routes, §4.2) fights the legibility goal — and where it fails is
  **"spaghetti"**: lots of interconnected routes with no landmark hierarchy and no clear spine leaves
  the player disoriented and lost. **Pair every multi-path region with a readable central spine and a
  clear hierarchy of landmarks** so the freedom reads as freedom, not as a maze.

### 4.8 Hub structure & reactivity

- **Hub-and-spoke with return visits.** Send the player out from and back to a hub that **persists and
  evolves** between visits — the return is where the world shows it remembered what the player did.
- **Fewer characters = deeper characters.** A handful of well-developed NPCs the player revisits beats
  a crowd of one-liners. (Mechanically: bind them with `BindName`, give them alliances and orders —
  [`dx-npcs.md`](./dx-npcs.md).)
- **Choice without consequence is irrelevant.** A choice that changes nothing is not a choice. But —
- **Consequence must be *predictable* to be fair.** The player must be able to foresee, by real-world
  logic, roughly what a choice will cause. A consequence that comes out of nowhere is a "gotcha," not
  a consequence, and it punishes exactly the planning you spent §4.4 building.
- **Choice + Consequence + Recovery** (a **later** Spector formulation — from his 2020s interviews, not
  the 2000 postmortem, which used just *choice + consequence*). Give the player a **way to recover** from
  a botched attempt — a failed hack, a blown-stealth, a killed-NPC-you-needed should reshape the situation, not
  hard-fail it. Recovery is what makes bold choices *safe to make*, which is what makes the freedom
  real.

---

*Siblings: [`README.md`](./README.md) (index) · [`human-scale.md`](./human-scale.md) ·
[`sources.md`](./sources.md) · [`lighting.md`](./lighting.md) · [`dx-npcs.md`](./dx-npcs.md) ·
[`dx-classes.md`](./dx-classes.md) · [`zones-performance.md`](./zones-performance.md).*
