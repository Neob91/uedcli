# uedcli docs

`uedcli` turns level design into plain text — no GUI. An LLM (or you) can query it, script it, and
audit it directly, issuing plain, named commands (`actor find`, `brush build`, `mover key move`, …)
against Deus Ex `.dx` and Unreal/UT `.unr` levels alike; the T3D text format is internal plumbing.
The git-tracked T3D trunk is the source of truth; the `.dx`/`.unr` map file is a build artifact;
`level materialize` compiles the trunk into a map file. Photo renders in-game (`--game`, the
default) or with the native offline rasterizer.

```
uedcli <verb> …                      # if installed on $PATH (pipx)
bin/uedcli <verb> …                  # from Tools/uedcli, host-native via the dev venv
```

These are the user-facing docs — how to drive uedcli and how to design good, buildable levels with
it. There are three:

- **[usage/](usage/README.md)** — task-oriented guides: how to accomplish a workflow, mixing
  commands the way a real task does (piping, movers & animation, building & shaping geometry, level
  lifecycle, discovery idioms, sharing & reuse). Read this for how to get something done.
- **[reference/](reference/actor/README.md)** — dry, one-command-family-per-page CLI reference:
  query/mutate verbs, the `diagram` viewer, `brush poly list`, brush clip, stash/prefab, the class
  and texture catalogs, sound/music. Read this for what a specific verb takes and how it behaves.
  See the table below for the full family list.
- **[leveldesign/](leveldesign/README.md)** — level-design craft: geometry/BSP, zoning, lighting,
  textures, movers, NPCs, human-scale numbers, and the Deus Ex immersive-sim design philosophy —
  mapped onto the verbs. Read this for how to build something worth looking at.

`uedcli docs list|show|search` serves this whole tree — usage/, reference/, and leveldesign/ — from
the CLI, so you can read all of this in the terminal, offline. Because the split multiplies
basename collisions within `reference/` (`build` exists under both `actor/` and `brush/`;
`list`/`show`/`search`/`classify` repeat across every catalog family), **topic keys are full
paths** — `reference/actor/diagram`, not `diagram` — and `docs show`/`docs search` take the full
path.

## Where to start

Skim **[reference/](reference/actor/README.md)** for the verb families (generators → `actor add -`,
per-surface `brush poly`, per-actor `actor prop set` / `mover key`) and **[usage/](usage/README.md)**
for worked task flows, then work through **[leveldesign/](leveldesign/README.md)** — start in
`general/` for engine-generic craft (geometry, zones, lighting) and drop into `deusex/` when you
need a Deus Ex class name, dimension, or the immersive-sim approach.

## The composing pattern

uedcli has no monolithic "make a room" command. Small verbs pipe together: a generator prints a T3D
snippet, `actor add -` writes it into the trunk, and per-surface / per-actor edits run model-side.
You never edit inside the editor by hand — the verbs write the trunk, `level materialize` builds it,
`level photo` shows it. The full pattern and the four verb families are in
**[leveldesign/README.md](leveldesign/README.md)**.

Verbs are small and pipe together instead of growing bespoke flags:

- Producer/query verbs print their result to stdout, one item per line (pipe-friendly); human
  summaries and counts go to stderr. Many add `--json` for structured output.
- Mutating verbs read their target set from stdin via `-` — `actor find … | actor delete -`.
  `-` is the sole names source (not mixable with names as CLI args); empty stdin is a clean
  no-op (exit 0), not an error.
- Two stdin conventions, disambiguated by verb: a name list (`find → mutate -`) versus a
  T3D snippet (`build → add -`). Keep them distinct.
- A verb over a set takes the set, and that is the operation — e.g. `actor bbox <names…>`
  returns the box enclosing all of them, so there is no `--union` flag.
- Prefer a stateless `find`/query verb feeding another verb over per-command filter flags.

Errors never leak a Python traceback: a bad actor/class/value raises a clear message naming the
offending value and exits non-zero (typically exit 2).

Set-mutating verbs are producers — they print their touched/allocated actor names to stdout
(one per line) plus a summary to stderr, so they chain via `-`
(`actor find | actor rotate - | brush scale -`): `actor add` (allocated names), `actor duplicate`,
`actor rotate` / `order` / `move` / `delete` / `prop set|unset` / `folder set|unset|rename` /
`label add|remove|clear`, `brush scale` / `brush apply-transform` / `brush poly align`
(touched brush names), and `stash apply` / `prefab apply`. For `delete` the stdout is the removed
names — a log, since they no longer exist to pipe into an edit.

## Projects: `uedcli.toml`

A **project** is any repo with a free-standing **`uedcli.toml`** at its root (found by walking up
from cwd; nearest wins — or point `--project` / `$UEDCLI_PROJECT` at the root dir or the file). The
file is hand-written (no `project init`):

```toml
game = "deusex"                 # required: selects [games.deusex] in ~/.uedcli/config.toml
paths = "Textures:System"       # optional overlay package dirs, colon-separated, relative to root
maps = "uedcli/maps"            # optional maps dir (T3D trunks), default "maps"
prefabs = "Prefabs"             # optional prefab library dir, default "prefabs"
catalog = "texture-catalog"     # optional texture-catalog dir, default "texture-catalog"
```

All dir keys are relative to the project root (absolute allowed), so uedcli can point at a repo's
**existing** dirs rather than force a parallel tree.

- **Machine-local throwaway state** (stash register, locks, staging temps, delivered preview maps)
  lives in a gitignored, **self-ignoring** `.uedcli/` beside the file — uedcli creates it (writing
  its own `.gitignore` of `*`) on first use; safe to delete.
- **The per-user `~/.uedcli/`** holds only `config.toml` (the `[games.*]` blocks — where each game's
  base asset packages live) and the derivable, content-addressed `cache/{textures,stubs,schema}`
  shared across projects. There is no central per-project bucket and no project `id`.

**Package layering.** The effective package search path is the project's overlay `paths` first, then
the selected game's base dirs. Duplicates are removed, keeping the project's copy over the game's.
`paths` are **bare directories**,
colon-separated — uedcli owns the five package extensions (`.u .dx .utx .uax .umx`) and scans the
dirs itself. Because `:` is the list separator, a pasted **Windows path** (`C:\DX\System`) cannot be
a dir: uedcli names it and exits 2, in both the project and the `[games.*]` config. Use the POSIX
path the dirs are actually at.

**Mover detection reads the class hierarchy, so it needs the packages.** Whether an actor is a
**mover** (an animated brush — see [`mover`](reference/mover.md)) is
decided by resolving its class against `Engine.Mover` in the game's code packages, *not* by guessing
from the class name. So every verb that has to know — `mover key *`, `level doctor`, `event graph`,
`brush scale`, `brush apply-transform`, `brush intersect`/`deintersect`, `stash capture`,
`level photo --native` — needs a resolvable package search path: a project **and**
`~/.uedcli/config.toml`. Without one the verb exits 2 naming itself and what is missing; it never
falls back to a name guess, since that would silently report a real mover as a static brush.
(`level materialize` and `level photo --game` need the same config to load the game's packages to
build and render, so in practice every verb on this page that touches packages wants it configured.)

The same rule applies **per actor**: if an actor's class — or any class on its ancestor chain — is
not on the composed search path, the verbs above exit 2 naming that class instead of quietly
deciding it is not a mover. The package holding the class is then missing from your project `paths`
or the game's base dirs ([`project show`](reference/project.md) prints the resolved path).

## Choosing a level

Most verbs operate on the **current level**, named by the **`UEDCLI_LEVEL` environment variable** (a
bare level name; a level's identity is its `maps/<name>/` directory). Set once per shell:

```
export UEDCLI_LEVEL=20_AireGardens
uedcli actor find --folder castle.**        # operates on 20_AireGardens
```

A verb with no `UEDCLI_LEVEL` and no explicit `--tree` exits 2 with `no level: set the environment
variable (export UEDCLI_LEVEL=<name>) or pass a level explicitly (--tree level/<name>)`. There is no
`level select` verb — the level is the env var (a child process can't set the parent shell's env).
When a **mutating** verb resolves the level from `UEDCLI_LEVEL` (not an explicit `--tree`), it echoes
`editing level 'X' (from $UEDCLI_LEVEL)` to stderr, so a stale export can't silently edit the wrong level.

The full command set for creating, importing, listing, and inspecting a level is
[`reference/level/`](reference/level/README.md).

## `--tree KIND/NAME` — edit a stash, prefab, or another level in place

Every content mutating/query verb takes **`--tree KIND/NAME`** (KIND ∈ `level|stash|prefab`)
to operate on a named tree instead of `$UEDCLI_LEVEL`: `--tree level/<other>` another level,
`--tree stash/<id>` a captured stash, `--tree prefab/<name>` a library prefab **in place**
(the one-command prefab-template edit — no apply / re-capture / promote roundtrip). NAME may be
nested (`stash/hangar/arch`). Omit it for the default ambient `$UEDCLI_LEVEL`. It rides
`actor find/show/add/delete/move/prop/rotate/scale/order/bbox/folder/label`, `brush replace/vertex/poly`,
`mover key *`, the read verbs `actor show`/`level status`/`level doctor`/`event graph` and `stash
capture`'s SOURCE (`stash capture --tree level/<name>`; rejected together with `--from-t3d`),
**and — level-kind only — `level materialize`/`level photo`** (`--tree level/<name>`
builds/photographs that level; `--tree stash|prefab` is rejected there, since a captured set has no world
— use `stash`/`prefab diagram`). Passing `--tree` explicitly suppresses the `editing level '…' (from
$UEDCLI_LEVEL)` echo. For a stash/prefab box, `level status`/`level doctor` label it by kind and skip
the git hint. It is **not** on the generators (`brush build`/`actor build` — they read no box) or
`actor diagram` (use `stash`/`prefab diagram`).

## Generators — stateless T3D producers

These write a T3D snippet to **stdout** and never touch the trunk or stash. The caller decides what
to do with the output. **Name allocation and the write into the trunk happen at `actor add`, not at
generation time** — so `--base-name` is a *stem/prefix*, and `actor add` appends a unique `_<rand>`
suffix (the spiral writes a central column plus one wedge-tread actor per step, each with a per-brush
index; the staircase is one actor). Duplicate base names are safe.

```bash
uedcli brush build cube --width 256 --breadth 256 --height 128 | uedcli actor add -
uedcli brush build cube --width 256 --breadth 256 --height 128 > /tmp/cube.t3d
```

The generators are [`brush build`](reference/brush/build.md), [`actor build`](reference/actor/build.md),
and [`brush intersect`/`brush deintersect`](reference/brush/intersect.md).

## Mutating verbs

These transform the in-memory level and rewrite the T3D trunk. Committing is your own `git`. Each
also accepts `--tree KIND/NAME` (above) to edit a different box.

## Usage guides

| Guide | Covers |
|---|---|
| [Door mover flow](usage/door-mover-flow.md) | turn existing door actors into a working mover via CSG deintersect |
| [Mover keyframe workflow](usage/mover-keyframes.md) | build a mover and author its keyframe stops |
| [CSG combining a stash](usage/csg-combine-a-stash.md) | pipe a captured actor set through a CSG generator |

## Reference

| Family | Covers |
|---|---|
| [`reference/actor/`](reference/actor/README.md) | find/add/delete/move/rotate/prop/build, folders, labels |
| [`reference/actor/diagram.md`](reference/actor/diagram.md) | the brush/actor viewer |
| [`reference/brush/`](reference/brush/README.md) | poly/vertex/measure/core, clip/snap/replace, scale/apply-transform |
| [`reference/brush/build.md`](reference/brush/build.md) | parametric brush primitives (cube/cylinder/cone/sheet/staircase/spiral/extrude/revolve) |
| [`reference/level/`](reference/level/README.md) | create/import/reimport/list/status/doctor/materialize/photo |
| [`reference/class/`](reference/class/README.md) | actor-class discovery: list/show/preview/search/prewarm/classify |
| [`reference/mover.md`](reference/mover.md) | `mover key` — animated brush actors (doors/lifts/gears) |
| [`reference/sound/`](reference/sound/README.md) | sound catalog: list/show/search/classify |
| [`reference/music/`](reference/music/README.md) | music catalog: list/show/search/classify, title/format |
| [`reference/stash.md`](reference/stash.md) | private, machine-local captured actor sets |
| [`reference/prefab.md`](reference/prefab.md) | durable, git-tracked, shareable actor sets |
| [`reference/texture/`](reference/texture/README.md) | texture catalog: list/show/preview/search/classify |
| [`reference/docs.md`](reference/docs.md) | `uedcli docs list/show/search` |
| [`reference/event.md`](reference/event.md) | `event graph` — trigger wiring |
| [`reference/project.md`](reference/project.md) | `project show` |
| [`reference/cache.md`](reference/cache.md) | package-schema cache maintenance |
| [`reference/substrate.md`](reference/substrate.md) | `substrate stub` — v68→v69 code package conversion |
| [`reference/uscript.md`](reference/uscript.md) | `uscript compile` — compile UnrealScript to a .u package |
