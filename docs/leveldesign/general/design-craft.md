# The craft of a good level  [ENGINE]

This covers the engine-generic craft of composition, mood, and flow. The Deus Ex-specific
immersive-sim philosophy — problems-not-puzzles, multi-path, readable stealth — builds on top and
lives in [../deusex/](../deusex/).

## Composition — making a space read

- **Proportion.** Design to the player's size and sketch to scale, floor heights and all, before you
  build; detailing can't rescue a wrong-sized room. Start from [human-scale.md](human-scale.md).
- **Detail every surface.** A bare cuboid reads as unfinished. Trim platform and stair edges, arch
  doorways, mount motivated lights in recesses, use shadow to break up flat walls.
- **Interconnect; avoid room-corridor-room.** Connect spaces across two or more floors: balconies
  overlooking a hall, a catwalk above a room, a window between two areas. This also gives the
  multi-path structure DX wants.
- **Use verticality.** Stack, overlook, drop.
- **Break long sightlines, but show the goal.** Long straight views hurt performance (no zone culls,
  see [zones-and-performance.md](zones-and-performance.md)) and read as flat. Bend and offset the
  path, but let the player glimpse where they're heading (a landmark down the hall) for direction.
- **Anchor with landmarks.** A dominant, always-visible feature (a tower, a reactor, a statue) lets
  players orient without a map. Make places distinct visually and audibly (lifts, water, and pickups
  each have their own sound; use them).
- **Contrast deliberately.** Open then tight, bright then dark, loud then quiet. Uniform anything is
  forgettable.

## Mood — lighting and atmosphere

The lighting mechanics are in [lighting.md](lighting.md); the craft is:

- **Motivate the light and never light flat** — a key plus a fill, distinct pools, motivated sources.
- **Use light to guide and to hide** — bright leads the eye toward the route; shadow conceals a secret
  or a dull surface.
- **Colour for identity** — give each zone its own hue so players navigate by feel.

## Flow & pacing — the player's journey

- **Plan the layout, and therefore the gameplay, first.** Sketch the whole level on grid paper before
  building a brush. Layout is pacing; detailing can't fix a bad plan.
- **Blockout in primitives, detail last.** Build the whole level in plain cubes, get the flow right,
  then detail. This is also the only reliable performance regulator — you can't tell where the poly
  budget went until the shape is settled.
- **Aim for "complicated linearity."** A path with choices and loops that still moves the player
  forward — not a maze, not a corridor.
- **Break up your innovations.** Don't stack every trick — strobe light + fog + a big fight + a moving
  platform — into one open view. Space set-pieces out so each lands.
- **Place items by risk vs reward.** The better the loot, the more exposed or guarded its spot.
- **Always signal progress; never leave the player lost.** Every space should show the player they're
  making headway and hint where to go next. Disorientation is the most common level-design failure.
- **Favour interactivity.** Movers, buttons, breakables — players want to affect the level, not just
  pass through it.

## The build loop — see the geometry without the editor

Iterate model-side with `actor preview` (the offline geometry viewer — no editor, no container):
render a quad or single view of the actors you're working on, judge it, adjust, repeat. It reads
names from the level (or a stdin name list — `actor find --folder castle.stairs | actor preview -`),
or a T3D snippet from a generator (`brush build spiral | actor preview --from-t3d -`).

- Brushes are coloured by CSG op (added blue / subtracted gold / semisolid pink / nonsolid green /
  mover magenta), so a doorway subtract reads distinctly from the wall it carves.
- `--faces {wire,flat}` picks how faces are drawn. `wire` (the default) is outlines only — the
  schematic. `flat` fills every face solid, nearest first, so you read what occludes what: a
  subtracted room shows its interior, with anything added inside it standing in front. Reach for it to
  answer "does this fit inside that", "is this pillar actually in the room", "does this detail brush
  poke through the wall". It needs a project and the game content available; `wire` needs neither, so a
  bare `brush build … | actor preview --from-t3d -` renders from anywhere. `--focus` fades the other
  brushes' fills as well as their outlines, and fades them only — what hides what never changes.
- `--highlight BRUSH:idx` emphasises the exact face you're about to retexture or align (a bare actor
  name highlights a whole brush, or brackets a point actor); `--frame BRUSH` frames a whole brush and
  `--frame BRUSH:idx` one face tight (with `--frame-tightness`). `--frame` also takes an explicit
  world box `X0,Y0,Z0,X1,Y1,Z1`. Under `flat` a highlight re-colours what is visible; when it is not
  visible at all a stderr note names it (under `--layout quad`, that means no pane showed it).
- `--layout breakdown` walks a selection actor by actor: an overview pane (whole scene, CSG, no
  labels) then one zoomed pane per actor — a brush with its faces numbered and its name on top, a
  point actor with its marker/sprite — so you read which face each index is without numbers piling
  up. It's a small-selection inspector (point actors get their own panes too, so subset first on a
  big scene).
- Point actors (lights, triggers, decorations) show their editor sprite or a labelled marker at
  Location, so you can judge placement. `--show collision,light-range,sound-range` (a comma-set)
  overlays an actor's collision cylinder and its light/sound reach for spacing decisions, as
  UnrealEd's radii view does.

(For a truly-lit first-person shot, that's the separate `level preview --game` verb.)

## Related

- [../deusex/](../deusex/) — the Deus Ex immersive-sim philosophy that extends this craft into multi-path,
  problems-not-puzzles design.
- [human-scale.md](human-scale.md), [lighting.md](lighting.md), [zones-and-performance.md](zones-and-performance.md)
  — the mechanics these principles direct.
