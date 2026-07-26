# uedcli docs

`uedcli` makes level design a **queryable, scriptable, auditable** text surface an LLM can drive
entirely as text — no GUI. The **git-tracked T3D trunk is the source of truth**; the `.dx`/`.unr`
map file is a build artifact; `level materialize` compiles the trunk into a map file. Preview
renders **in-game** (`--game`, the default) or with the **native** offline rasterizer.

These are the **user-facing** docs — how to *drive* uedcli and how to *design good, buildable
levels* with it. There are two:

- **[usage.md](usage.md)** — the CLI: query/mutate verbs, the `preview` viewer, `brush poly list`,
  brush clip, stash/prefab, the texture catalog (`sync`/`list`/`search`/`tags`/`classify`). Read
  this for **what to type**. It also documents `uedcli docs list|show|search`, which serves these
  very pages from the CLI — so you can read all of this in the terminal, offline, without going
  looking for the files.
- **[leveldesign/](leveldesign/README.md)** — level-design craft for uedcli users: geometry/BSP,
  zoning, lighting, textures, movers, NPCs, human-scale numbers, and the Deus Ex immersive-sim
  design philosophy — mapped onto the verbs. Read this for **how to build something worth looking
  at**.

## Where to start

New here? Skim **[usage.md](usage.md)** for the verb families (generators → `actor add -`,
per-surface `brush poly`, per-actor `actor prop set` / `mover key`), then work through
**[leveldesign/](leveldesign/README.md)** — start in `general/` for engine-generic craft (geometry,
zones, lighting) and drop into `deusex/` when you need a Deus Ex class name, dimension, or the
immersive-sim approach.

## The composing pattern in one line

uedcli has no monolithic "make a room" command. Small verbs pipe together: a *generator* prints a
T3D snippet, `actor add -` writes it into the trunk, and per-surface / per-actor edits run
model-side. You never edit inside the editor by hand — the verbs write the trunk, `level
materialize` builds it, `level preview` shows it. The full pattern and the four verb families are in
**[leveldesign/README.md](leveldesign/README.md)**.
