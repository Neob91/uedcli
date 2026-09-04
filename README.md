# uedcli

![pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![built with Claude](https://img.shields.io/badge/built%20with-Claude-8A5CF6)

**A text-only control layer for UnrealEd 2.2 (Unreal Engine 1).** Query, edit, build and
render classic UE1 levels — Deus Ex to start — through composable commands, no GUI. The T3D
level model (Unreal's text scene format) is the source of truth; the `.dx` map is a build
artifact; UnrealEd is the compiler and renderer.

> **Pre-alpha — expect breaking changes.** Published to get it out there, not because it's
> stable: verbs, flags and output change without notice. It's **mostly AI-built**, and some
> docs are still being cleaned up. No support.

![A room built from composable brush verbs, rendered by actor diagram](docs/images/readme/hero-room-wire.png)

*A subtracted room (gold) with additive pillars and a staircase (blue), built by piping
`brush build` generators into `actor diagram` and rendered offline — no editor open.*

## What it is

UnrealEd is a crash-prone, GUI-only, largely undocumented editor from 1998. uedcli wraps a
headless UnrealEd-2.2-under-wine and turns level design into scriptable text: small
single-purpose **verbs that pipe together** (`find` → `clip` → `replace`), the T3D files kept
in git as the model, and offline renderers. Because it's all text, an LLM can drive it end to
end.

## See it work

**Build geometry from stateless generators and render it — no game files, no editor:**

```bash
uedcli brush build cube --width 768 --breadth 512 --height 288 --csg subtract --base-name Room \
  | uedcli actor diagram --from-t3d - --view iso --out room.png
```

The `brush build` verbs — `cube`, `cylinder`, `cone`, `sheet`, `staircase`, `spiral`,
`extrude`, `revolve` — print T3D to stdout; `actor diagram` renders any T3D, as a labeled
wireframe or a textured, CSG-solved view (all offline):

![The same room, CSG-solved and textured offline](docs/images/readme/room-textured.png)

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

uedcli is host-native Python **3.12** with one dependency (`Pillow`). The `bin/uedcli` launcher
creates a dev venv on first run; the host just needs `python3.12` on `PATH`. Docker is only
needed for the editor/build containers uedcli drives.

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
- [`dev/docs/unrealed/`](dev/docs/unrealed/README.md) — the verified UnrealEd-2-under-wine
  knowledge base (exec verbs, quirks, rendering). Public docs on the engine are almost
  nonexistent.
- [`dev/docs/board/`](dev/docs/board/README.md) — the roadmap, as a stage-queue of work items.

## Project status

Targets one engine (UE1) and, so far, one game (Deus Ex). Coverage is uneven; use it to
explore, not to depend on. Issues and ideas welcome.
