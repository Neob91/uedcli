# uedcli

![pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![license MIT](https://img.shields.io/badge/license-MIT-green)
![built with Claude](https://img.shields.io/badge/built%20with-Claude-8A5CF6)

**Build, edit and render Unreal Engine 1 game levels from the command line — no GUI, so an AI
agent can do it end to end.** uedcli reimplements UnrealEd (the Unreal 1 editor) as text: brush
geometry, CSG, and rendering run natively, in-process, no editor in the loop. The git-tracked T3D
model (Unreal's text scene format) is the source of truth; the compiled `.dx`/`.unr` map is a
build artifact. Deus Ex is the first supported game.

> **Pre-alpha — expect breaking changes.** Published to get it out there, not because it's
> stable: verbs, flags and output change without notice. It's **mostly AI-built**, and some
> docs are still being cleaned up. No support.

![Composing a colonnade hall from text verbs and rendering it — no editor](docs/images/readme/hall-cast.svg)

The pipeline above builds a colonnade hall from `brush build` generators and renders it offline —
no editor, no GUI. It produces:

![hall.png — the rendered wireframe](docs/images/readme/hall-iso.png)

*`hall.png`: gold = the subtracted room volume, blue = the additive columns and staircase.*

- **Author geometry as text** — parametric `brush build` generators (`cube`, `staircase`, `spiral`, `revolve`, …) emit T3D you can pipe anywhere.
- **Query & edit by name** — `find` / `show` / `clip` / `replace` compose over stdin; no GUI selection.
- **Decode retail maps** — `level import` turns a compiled `.dx`/`.unr` into a queryable, diffable T3D tree, natively.
- **Render offline** — labeled wireframes and CSG-solved textured views, no editor.
- **Faithful build** — unbuilt T3D output already matches UnrealEd byte-for-byte; the full `level materialize` build (BSP + lighting) is being driven to the same parity, verified incrementally.
- **Git-native** — levels are per-actor T3D files that diff and merge like code.

## What it is

UnrealEd is a GUI editor — point-and-click, with no interface an agent can drive. uedcli exposes
that same level-editing power as text an agent can drive: every read and edit is native compute
against per-actor T3D files in git, no editor involved. The one step still delegated to the
editor is the final `level materialize` build (BSP + lighting) — being brought native too.

## See it work

**Build geometry from stateless generators and render it — no game files, no editor:**

```bash
uedcli brush build cube --width 768 --breadth 512 --height 288 --csg subtract --base-name Room \
  | uedcli actor diagram --from-t3d - --view iso --out room.png
```

The `brush build` verbs — `cube`, `cylinder`, `cone`, `sheet`, `staircase`, `spiral`,
`extrude`, `revolve` — print T3D to stdout; `actor diagram` renders any T3D, as a labeled
wireframe or a CSG-solved view textured from your project's textures — both offline:

![The hall, CSG-solved and textured offline](docs/images/readme/hall-textured.png)

**Verbs compose over stdin.** Query verbs print one name per line; mutating verbs read that set
from `-`. Clip a placed brush in place with show → clip → replace:

```bash
uedcli actor find --exact-class Brush \
  | uedcli actor diagram -                       # render the set

uedcli actor show Brush41 \
  | uedcli brush clip - --axis z --offset 128 --keep below \
  | uedcli brush replace Brush41 -               # cut it, put it back
```

**Render lit, in-game frames** by booting the real engine headless (`level photo --game`), or a
fast offline draft (`level photo --native`). See
[`docs/reference/level/photo.md`](docs/reference/level/photo.md).

## Quickstart

uedcli is a Python **3.12** CLI plus a small Rust core (the CSG/geometry engine), with one
Python dependency (`Pillow`). The `bin/uedcli` launcher builds both into a local venv on first
run (the Rust build uses Docker; `UEDCLI_SKIP_NATIVE=1` skips it, disabling the native
render/import paths). Releases will ship as standalone binaries.

```bash
export PATH="$PWD/bin:$PATH"     # or symlink bin/uedcli into ~/.local/bin/

uedcli --help
bin/test                         # offline unit tests (committed fixtures, no editor)
```

The `brush`/`actor`/`level` verbs above run inside a uedcli project. To create one — plus a
level to edit and lit `--game` renders — you supply your own Deus Ex copy;
`dev/scripts/setup-game-preview.sh` provisions everything (see
[`dev/docs/deusex-assets-setup.md`](dev/docs/deusex-assets-setup.md)).

## Documentation

- [`docs/`](docs/README.md) — user-facing: the CLI reference (`docs/reference/`) and
  task-oriented guides (`docs/usage/`).
- [`dev/docs/architecture.md`](dev/docs/architecture.md) — layers, the write pattern,
  invariants, the T3D trunk, how to add a verb.
- [`dev/docs/unrealed/`](dev/docs/unrealed/README.md) — the verified UnrealEd knowledge base
  (exec verbs, quirks, rendering). Public docs on the engine are almost nonexistent.
- [`dev/docs/board/`](dev/docs/board/README.md) — the roadmap, as a stage-queue of work items.

## Project status

Targets one engine (UE1) and, so far, one game (Deus Ex). Coverage is uneven; use it to
explore, not to depend on. Issues and ideas welcome.

## License

MIT — see [LICENSE](LICENSE).
