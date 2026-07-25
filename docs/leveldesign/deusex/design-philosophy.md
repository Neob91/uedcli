# The Deus Ex design philosophy  [DX]

This is the highest-value knowledge in these guides — the craft that makes a level feel like *Deus Ex*
rather than a generic shooter map. It comes from the game's own designers (Warren Spector's "Rules of
Roleplaying", Harvey Smith's "Systemic Level Design", and the GDC/Gamasutra postmortems). Where the
[general craft guide](../general/) covers composition and flow that apply to any level, **this is the
immersive-sim layer** — how to build a *problem-space with multiple valid solutions*.

The mechanics guides tell you how to build geometry that works. This tells you what to build.

---

## Problems, not puzzles

**The single most-cited DX maxim.** Design each obstacle as an *obstacle course*, not a jigsaw. A puzzle
has one intended answer the player must guess — reading the designer's mind. A problem has many valid
solutions the player discovers by thinking about the space and their character. Never gate progress
behind a single mechanism.

## Multiple solutions, keyed to the character

The routes that open up for a player *are* the character they built. Provide obstacles that reward
different investments:

- **The four canonical approaches:** **Combat · Stealth · Hacking · Social.**
- **Plus architectural routes:** vents, ducts, ladders, windows, catwalks, rooftops, sewers.

Even a plain "left hall vs right hall" fork sorts players into playstyles. A crawlspace over a guarded
door rewards the stealth build; a keypad rewards the hacker; a talkable guard rewards the social build;
a `BreakableWall` (tuned crowbar-weak — lower its `minDamageThreshold`, since the default 20 blocks a
~6-damage crowbar) rewards the one who carried a crowbar.

**How they actually shipped it (practical for a modder):** the tech couldn't fully simulate every
solution, so the designers **hand-authored three explicit routes per problem — a skill path, an action
path, and a character-interaction path** — then let the systems add emergent extras. *You get the DX
feel by authoring ~3 real, keyed routes per obstacle. You don't need a full simulation.*

Tie the routes to concrete DX tools: keypads and hackable devices ([`gameplay-wiring.md`](gameplay-wiring.md)),
`BreakableWall`/`DeusExMover` locks with `lockStrength`/`doorStrength` tuned against the [device
strengths](human-scale.md), ladder textures for vertical routes ([`classes.md`](classes.md)), and
talkable NPCs ([`conversations-and-computers.md`](conversations-and-computers.md)).

## Systemic consistency

Design behavior **by object TYPE, not by instance** — "things that are the same behave the same by
default." Consistency lets the player *predict*, which lets them *plan*, which is what produces the
feeling of agency ("Playing the Game" instead of "Playing the Designer"). Emergence — the famous
mine-climbing trick — falls out of a few consistent simple rules.

The corollary: **never depict a non-functional door, item, or affordance.** Every "lie" about what's
interactive erodes the player's ability to plan, and once trust is gone they stop experimenting. If a
ledge looks climbable, it should be.

## Readable stealth as a mechanic

Light and shadow, cover, and guard sight/sound lines are **gameplay, not mood.** Place lights and shadow
pools deliberately so the player can read where they're hidden. Give consistent sound propagation and
throwable props so **distraction becomes a player tool.** Teach affordances diegetically — a crowbar
lying by breakable crates teaches what the crowbar is for. (Place guards and lights with this in mind —
see [`npcs.md`](npcs.md).)

## Environmental storytelling

Tell the story with the space, through two channels:

- **Conversations** with characters.
- **In-world text** — datacubes, emails, books — that rewards explorers with story *and* mechanical
  payoff (a datacube that carries a door code). See [`conversations-and-computers.md`](conversations-and-computers.md).

Build "*this* warehouse, where *these* people did *this*" — specific, consequential places, not generic
rooms.

## Legibility by architecture — there is no in-game GPS

DX has no minimap and no objective markers, so **the space itself must be legible.** Make it navigable
with:

- **Dominant, always-visible landmarks** the player can orient by.
- **Plausible real-world geography** — spaces that make sense as places.
- **Light and leading lines** that point toward routes.

This is where multi-path design fails: many routes with no landmark hierarchy is "spaghetti" — players
get lost. **Always pair choice with a readable spine and a strong landmark.**

## Hub structure and reactivity

- **Hub-and-spoke with return visits** to a world that persists and evolves as the player acts on it.
- **"Fewer characters = deeper characters."**
- **Choice without consequence is irrelevant** — and the consequence must be *predictable* (follow
  real-world logic) to be fair.
- **Choice + Consequence + Recovery** (the "+ Recovery" is a *later* Spector formulation, not from the
  2000 postmortem) — always give the player a way to recover from a botched attempt, so a failed approach
  becomes a new problem rather than a dead end.

Use the [flag database](gameplay-wiring.md) (`FlagTrigger`, permanent flags) to make consequences
persist and cross-reference across the level, so the world remembers what the player did.

---

## See also

- [`../general/`](../general/) — engine-level composition, flow, and pacing craft.
- [`gameplay-wiring.md`](gameplay-wiring.md) — the flags/triggers that make choices persist.
- [`npcs.md`](npcs.md) · [`classes.md`](classes.md) · [`human-scale.md`](human-scale.md) — the pieces you
  build the routes from.
- [`recipes/`](recipes/) — concrete walkthroughs that apply these principles.
