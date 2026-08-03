# Shared brief — build a detailed Deus Ex level from a reference photo

You are one of **three** agents, each building a different level from a different
reference photo. You work **alone** in your own project dir. Do not touch the other
two agents' dirs, and do not touch anything in the repo outside `_scratch/`.

---

## 1. Your mission

Build an **original, playable Deus Ex level in the spirit of your reference photo** —
its mood, materials, palette, scale and spatial logic. This is **not** a literal
recreation of the photograph. The photo is a mood and layout reference: steal its
atmosphere and its architecture, then make a level that is actually good to move
through. A camera-accurate diorama that plays badly is a failure; a level that feels
like walking into that photo is a success.

Aim for a level a player would spend **3–6 minutes** in.

---

## 2. Read these FIRST — you do not inherit anyone else's reading

You have read none of this project's docs. Read them **before** you build. Skipping
this step is the single most common way this task goes wrong: you will invent CLI
flags that do not exist and mis-scale every room.

**Required, in this order:**

1. `/home/neob91/Documents/Dev/uedcli/CLAUDE.md` — repo rules and conventions.
2. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/README.md` — the composing pattern.
3. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/general/human-scale.md` — **the
   numbers.** Build on a power-of-two grid, 16 uu default. `1 foot = 16 uu`. DX player
   needs ~96–100 uu ceilings. Never build off-grid — it is the main cause of BSP holes.
4. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/general/geometry-and-bsp.md` —
   how to not produce a holey mess.
5. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/general/brush-shapes.md` — the
   shape generators.
6. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/general/lighting.md`
7. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/general/textures-and-surfaces.md`
8. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/general/zones-and-performance.md`
9. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/deusex/design-philosophy.md` —
   **the crown jewel.** Problems-not-puzzles, multiple keyed solutions, readable
   stealth, environmental storytelling. This is what makes it a *Deus Ex* level.
10. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/deusex/human-scale.md`
11. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/deusex/classes.md` — what you can place.

**Read as needed:** `docs/usage.md` (full CLI reference — consult it rather than
guessing a flag), `docs/leveldesign/general/movers.md`,
`docs/leveldesign/general/recipes/*.md`, `docs/leveldesign/deusex/recipes/*.md`,
`docs/leveldesign/deusex/npcs.md`, `docs/leveldesign/deusex/gameplay-wiring.md`.

**The shape recipes are worth your time** —
`docs/leveldesign/general/recipes/shapes/`: `curved-corridor.md`, `arch-voussoir.md`,
`moulded-cornice.md`, `l-ledge.md`, `octagonal-column.md`, `chamfered-box.md`,
`ring-cornice.md`, `triangular-wedge.md`, `add-subtract-twin.md`. Each is a worked
pipeline for a shape that would otherwise take you an hour to derive.

### Two brand-new generators: `extrude` and `revolve`

`brush build extrude` and `brush build revolve` **landed minutes ago** — they sweep a
2D profile you define with repeated `--point U,V` flags into a solid. They are how you
build any shape that is not a box: bends, arches, cornices, ledges, mouldings, curved
walls, pipes, vaults.

```bash
# a 90° bend of a 128x128 passage, subtracted out of rock (see curved-corridor.md)
bin/uedctl brush build revolve --axis x --angle 16384 --csg subtract --solidity semisolid \
  --point 64,0 --point 192,0 --point 192,128 --point 64,128 --at 0,0,0 | bin/uedctl actor add -
```

- `--angle` is in unreal rotation units: **16384 = 90°, 65536 = a closed full turn.**
- `--axis` is the axis the profile plane is **normal** to; `z → U=X,V=Y`, `x → U=Y,V=Z`,
  `y → U=Z,V=X`.
- `--point` at least 3, in ring order, do not repeat the first point last.
- `--segments` defaults to one facet per 22.5°. **Each segment costs a face per profile
  edge** — a high count is a heavy brush for the BSP. Do not sweep a 12-point profile
  through a full turn at high density.

Run `bin/uedctl brush build extrude --help` and `... revolve --help` before using them.

**Never guess a CLI flag.** Every verb has real `--help`. Use it.

---

## 3. Your reference photo

`Read` your assigned image (path is in your individual brief). Look at it properly and
write down, before building: the palette, the light sources and their colour, the
materials, the dominant shapes, the scale cues, and what the space is *for*.

---

## 4. Set up your project

**Your project already exists** — `uedctl.toml` and the pre-seeded `texture-catalog/`
are in place. You only create the level:

```bash
cd /home/neob91/Documents/Dev/uedcli
export UEDCTL_PROJECT=/home/neob91/Documents/Dev/uedcli/_scratch/levelbuild/<your-slug>
bin/uedctl level create <your-level-name>
export UEDCTL_LEVEL=<your-level-name>
bin/uedctl level status          # sanity check
```

Always run `bin/uedctl` from `/home/neob91/Documents/Dev/uedcli` (it bootstraps the
venv). Keep `UEDCTL_PROJECT` and `UEDCTL_LEVEL` exported in **every** bash call — they
do not persist between tool calls.

### Textures — the catalog is ALREADY BUILT for you

**Do NOT run `bin/uedctl texture sync`. It takes 30+ minutes.** Your project is
created with a pre-seeded `texture-catalog/` (copied in for you) covering **4,791
texture refs across 57 Deus Ex packages** — `CoreTex*` plus level-specific ones like
`Dockyard`, `HK_Interior`, `Hangar18`, `NYC*`, `Tunnels`, `Catacombs`, `UNATCO`.

Find textures with:

```bash
bin/uedctl texture list                          # every ref: NAME  WxH  classification
bin/uedctl texture list | grep -i tile           # by name — your main tool
bin/uedctl texture search <text>                 # matches over name/tags/description
bin/uedctl texture search --color blue           # by dominant colour
bin/uedctl texture search --package Dockyard     # everything in one package
```

Two things to know:

- **Every texture is `unclassified`** — nothing has been tagged, so `--tag` and
  description matching find nothing. Discover by **name** (`list | grep`), by
  **package**, and by **colour**.
- **`--color` takes a fixed 12-word vocabulary**, and nothing else: `black, white,
  grey, red, orange, yellow, green, blue, purple, pink, brown, tan`. There is no
  `teal`/`cyan` — ask for `blue` or `green`.

Texture refs are `Package.Name` or `Package.Group.Name`. Sizes are in the listing —
respect them when aligning surfaces.

---

## 5. How you look at your work — BOTH renderers, every milestone

**a. `level preview --game` — the lit, faithful, in-game render.** This is the one that
shows lighting, sky and real materials. It is the picture that matters.

```bash
bin/uedctl level preview --game --out-dir <proj>/shots --size 800x600 \
  "at:X,Y,Z;rot:PITCH,YAW;name:hero1" \
  "at:X,Y,Z;look:@SomeActor;name:hero2"
```

- Angles are **unreal rotation units: 16384 = 90°**. Positive pitch looks up.
- **Batch every shot of a milestone into ONE invocation.** The game container is shared
  by all three agents and serialised by a lock; first boot is ~2 min, later batches are
  much faster. Three agents each firing single-shot previews will crawl.

**b. `actor preview` — the offline schematic (UED-style quad view).** Fast (~1 s), no
container. Use it to check layout and catch geometry mistakes.

```bash
bin/uedctl actor find | bin/uedctl actor preview - --annotate name --size 900 \
  --out <proj>/shots/schematic-<milestone>.png
```

- **`--annotate name` — NEVER face annotations.** The default includes face-index
  numbering; it is noise here. Names only.
- **`actor preview` needs an explicit name source.** Bare `actor preview` selects
  nothing and silently writes no file (exit 0). Always pipe `actor find |` into
  `actor preview -`.

**c. `level preview --native` — optional fast draft** (~1 s, textured, **no lighting**).
Handy for quick geometry spot-checks between milestones. Never judge lighting by it.

**Always `Read` the PNGs you generate.** Look at your own work and fix what looks wrong.
An unexamined render is worthless.

---

## 6. Milestones — report at each one

At each milestone: produce the pictures, **`Read` them yourself**, then report a short
progress note **with the absolute PNG paths** so they can be shown.

| # | Milestone | Deliverable |
|---|-----------|---|
**EVERY milestone produces BOTH kinds of picture — wireframe AND in-game. No exceptions.**

| # | Milestone | Deliverable |
|---|-----------|---|
| 1 | **Blockout** — the space exists, on-grid, correct scale, walkable | wireframe schematic + 2–3 `--game` shots |
| 2 | **Materials & lighting** — textured, lit to the photo's palette and mood | wireframe schematic + 3–4 `--game` shots |
| 3 | **Detail & props** — the geometry and decoration that make it specific | wireframe schematic + 3–4 `--game` shots |
| 4 | **Gameplay** — PlayerStart, PathNodes, DX interactivity, multiple routes | wireframe schematic + 4–5 `--game` shots |

Do not skip ahead. A wrong blockout is cheap to fix at milestone 1 and expensive at 4.

---

## 7. The quality bar

- **Kill the box.** No room is a bare cube. Break up every surface with recesses,
  columns, beams, level changes, trim.
- **Light with intent.** Light comes from things that plausibly emit it, in the photo's
  colours. Use coloured light (`LightHue`/`LightSaturation`), pools of light and real
  darkness. `Engine.Light` defaults to Radius 64 — usually far too small; reach is
  roughly `(Radius+1)×25` uu. Flat, evenly-lit rooms read as amateur.
- **Deus Ex means choice.** At least one obstacle with **more than one solution** —
  a locked door plus a vent, a guarded route plus a climb. This is the point of the
  design-philosophy doc.
- **Environmental storytelling.** The space should imply who uses it and what happened.
- **Human scale.** Doorways ~128×64. Ceilings ≥96. Stairs rise ≤25 (DX `MaxStepHeight`).
- **On-grid, always.**

---

## 8. Hard constraints

- **Work only inside your own `_scratch/levelbuild/<your-slug>/`.** `_scratch/` is
  gitignored — that is exactly why we build here.
- **Do NOT `git commit`, `git add`, `git push`, or change branches.** Nothing about this
  task touches version control. If you think you need to, you are wrong — stop and say so.
- **Do NOT modify uedctl's source, docs, tests, or board.** You are a *user* of the tool.
- **Do NOT run the repo's review-gate subagents.** That process governs changes to the
  tool; you are not changing the tool.
- **Do not spawn subagents.**
- If you hit a genuine uedctl **bug or missing capability**, do not patch the tool —
  note it in your report and work around it.

---

## 9. Reporting

Your final message is a report: what you built, the design decisions and why, the
absolute paths of your best `--game` shots, and anything that fought you. Keep the
level in place on disk — do not clean up.
