# The Deus Ex design philosophy  [DX]

The immersive-sim layer, from the game's designers (Spector's "Rules of Roleplaying", Harvey Smith's
"Systemic Level Design", the GDC/Gamasutra postmortems): how to build a problem-space with multiple
valid solutions. The [general craft guide](../general/) covers composition and flow for any level;
this is what to build on top of it.

## Problems, not puzzles

Design each obstacle as an obstacle course, not a jigsaw. A puzzle has one intended answer the player
must guess; a problem has many valid solutions they find by thinking about the space and their
character. Never gate progress behind a single mechanism.

## Multiple solutions, keyed to the character

The routes open to a player are the character they built. Provide obstacles that reward different
investments:

- The four canonical approaches: Combat, Stealth, Hacking, Social.
- Architectural routes: vents, ducts, ladders, windows, catwalks, rooftops, sewers.

Even a "left hall vs right hall" fork sorts players by playstyle. A crawlspace over a guarded door
rewards stealth; a keypad rewards the hacker; a talkable guard rewards the social build; a
`BreakableWall` rewards whoever carried a crowbar (tune it crowbar-weak — lower `minDamageThreshold`,
since the default 20 blocks a ~6-damage crowbar).

The shipped tech couldn't simulate every solution, so the designers hand-authored three explicit
routes per problem — skill, action, character-interaction — and let the systems add emergent extras.
Author ~3 real keyed routes per obstacle; you don't need a full simulation.

Tie routes to concrete DX tools: keypads and hackable devices ([`gameplay-wiring.md`](gameplay-wiring.md));
`BreakableWall`/`DeusExMover` locks with `lockStrength`/`doorStrength` tuned against the [device
strengths](human-scale.md); ladder textures for vertical routes ([`classes.md`](classes.md)); talkable
NPCs ([`conversations-and-computers.md`](conversations-and-computers.md)).

## Systemic consistency

Design behavior by object type, not instance: things that are the same behave the same by default.
Consistency lets the player predict, then plan — which is what produces agency ("Playing the Game",
not "Playing the Designer"). Emergence, like the mine-climbing trick, falls out of a few consistent
rules.

Corollary: never depict a non-functional door, item, or affordance. Every lie about what's
interactive erodes planning, and once trust is gone players stop experimenting. If a ledge looks
climbable, it should be.

## Readable stealth as a mechanic

Light and shadow, cover, and guard sight/sound lines are gameplay, not mood. Place lights and shadow
pools so the player can read where they're hidden. Give consistent sound propagation and throwable
props so distraction becomes a tool. Teach affordances diegetically — a crowbar by breakable crates
teaches what it's for. (Place guards and lights accordingly — see [`npcs.md`](npcs.md).)

## Environmental storytelling

Tell the story with the space, through two channels: conversations with characters, and in-world text
— datacubes, emails, books — that rewards explorers with story and a mechanical payoff, like a
datacube carrying a door code (see [`conversations-and-computers.md`](conversations-and-computers.md)).
Build specific, consequential places — "this warehouse, where these people did this" — not generic
rooms.

## Legibility by architecture — no in-game GPS

DX has no minimap and no objective markers, so the space itself must be legible:

- Dominant, always-visible landmarks to orient by.
- Plausible real-world geography.
- Light and leading lines that point toward routes.

Many routes with no landmark hierarchy is spaghetti — players get lost. Pair every choice with a
readable spine and a strong landmark.

## Hub structure and reactivity

- Hub-and-spoke with return visits to a world that persists and evolves as the player acts on it.
- Fewer characters = deeper characters.
- Choice without consequence is irrelevant, and the consequence must be predictable (follow
  real-world logic) to be fair.
- Choice + Consequence + Recovery: always give a way to recover from a botched attempt, so a failed
  approach becomes a new problem, not a dead end. ("+ Recovery" is a later Spector formulation.)

Use the [flag database](gameplay-wiring.md) (`FlagTrigger`, permanent flags) to make consequences
persist across the level, so the world remembers what the player did.

## See also

- [`../general/`](../general/) — engine-level composition, flow, and pacing.
- [`gameplay-wiring.md`](gameplay-wiring.md) — the flags/triggers that make choices persist.
- [`npcs.md`](npcs.md) · [`classes.md`](classes.md) · [`human-scale.md`](human-scale.md) — the pieces you
  build the routes from.
- [`recipes/`](recipes/) — concrete walkthroughs that apply these principles.
