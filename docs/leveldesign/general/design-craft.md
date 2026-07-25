# The craft of a good level  [ENGINE]

Everything else in this area is *how to build*; this is *what to build*. The engine-generic craft —
composition, mood, and flow — that separates a working blockout from a place worth walking through. (The
Deus Ex-specific immersive-sim philosophy — problems-not-puzzles, multi-path, readable stealth — builds
on top of this and lives in [../deusex/](../deusex/).)

## Composition — making a space read

- **Proportion over everything.** Design to the player's size and sketch to scale, floor heights and
  all, *before* you build. A room that's the wrong size can't be rescued by detailing. Start from
  [human-scale.md](human-scale.md).
- **Kill the box.** A bare cuboid room reads as unfinished. Detail every surface: trim the edges of
  platforms and stairs, arch doorways, mount motivated lights in recesses, use shadow to break up flat
  walls. There should be nothing your eye slides across without landing on something.
- **Interconnect — avoid room-corridor-room.** A string of boxes joined by hallways is monotonous.
  Connect spaces across **two or more floors**: balconies overlooking a hall, a catwalk above a room, a
  window between two areas. Interconnection also gives the multi-path structure DX wants.
- **Think in 3D — use verticality.** Height is free space and free interest. Stack, overlook, drop.
- **Break long sightlines, but show the goal.** Long straight views both hurt performance (no zone
  culls, see [zones-and-performance.md](zones-and-performance.md)) and read as flat. Bend and offset the
  path — *but* let the player glimpse where they're heading (a landmark down the hall) so they always
  have a direction.
- **Anchor with landmarks.** A dominant, always-visible feature (a tower, a reactor, a statue) lets
  players orient without a map. Make places **distinct** — visually *and* audibly (lifts, water, and
  pickups each have their own sound; use them).
- **Contrast deliberately.** Open then tight, bright then dark, loud then quiet. Contrast is what makes
  a space memorable; uniform anything is forgettable.

## Mood — lighting and atmosphere

The lighting mechanics are in [lighting.md](lighting.md); the craft is:

- **Motivate the light and never light flat** — a key plus a fill, distinct pools, motivated sources.
- **Use light to guide and to hide** — bright leads the eye toward the route; shadow conceals a secret
  or a dull surface.
- **Colour for identity** — give each zone its own hue so players navigate by feel.

## Flow & pacing — the player's journey

- **Plan the layout — and therefore the gameplay — first.** Sketch the whole level on grid paper before
  you build a brush. Layout *is* pacing; you can't fix a bad plan by detailing.
- **Blockout in primitives, detail last.** Build the whole level in plain cubes and get the flow right,
  *then* detail. This is also the only reliable performance regulator — you can't tell where the poly
  budget went until the shape is settled.
- **Aim for "complicated linearity."** A path with choices and loops that still moves the player
  forward — not a maze, not a corridor.
- **Break up your innovations.** Don't stack every trick — strobe light + fog + a big fight + a moving
  platform — into one open view. Space set-pieces out so each one lands.
- **Place items by risk vs reward.** The better the loot, the more exposed or guarded its spot.
- **Always signal progress; never leave the player lost.** Every space should tell the player they're
  making headway and hint where to go next. Disorientation is the most common level-design failure.
- **Favour interactivity.** Movers, buttons, breakables — "players want to *affect* the level, not just
  pass through it."

## The build loop — see the geometry without the editor

Iterate model-side with **`actor preview`** (the offline wireframe viewer — no editor, no container):
render a quad or a single view of the actors you're working on, judge it, adjust, repeat. It reads
names from the level (or a stdin name list — `actor find --folder castle.stairs | actor preview -`),
or a T3D snippet straight off a generator (`brush build spiral | actor preview --from-t3d -`).

- Brushes are **coloured by CSG op** (added blue / subtracted gold / semisolid pink / nonsolid green /
  mover magenta), so a doorway subtract reads distinctly from the wall it carves.
- **`--highlight BRUSH:idx`** emphasises the exact face you're about to retexture or align (a bare
  actor name highlights a whole brush, or brackets a point actor); **`--frame BRUSH`** frames a whole
  brush and **`--frame BRUSH:idx`** one face (with `--frame-tightness`) tight. `--frame` also takes an
  explicit world box `X0,Y0,Z0,X1,Y1,Z1`.
- **`--layout breakdown`** walks a selection **actor by actor**: an overview pane (whole scene, CSG, no
  labels) then one big **zoomed, focused** pane per actor — a brush with its faces numbered and its name
  on top, a point actor with its marker/sprite — so you read exactly which face each index is without
  numbers piling up. It's a small-selection inspector (point actors now get their own panes too, so
  subset first on a big scene).
- **Point actors** (lights, triggers, decorations) show their editor **sprite** or a labelled marker
  at Location — so you can judge placement — and **`--show collision,light-range,sound-range`** (a
  comma-set) overlays an actor's collision cylinder and its light/sound reach for spacing decisions,
  exactly as UnrealEd's radii view does.

(For a truly-lit first-person shot, that's the separate `level preview --game` verb.)

## Related

- [../deusex/](../deusex/) — the Deus Ex immersive-sim philosophy that extends this craft into multi-path,
  problems-not-puzzles design.
- [human-scale.md](human-scale.md), [lighting.md](lighting.md), [zones-and-performance.md](zones-and-performance.md)
  — the mechanics these principles direct.
