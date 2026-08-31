# uedcli — usage

`uedcli` is the LLM-facing CLI for authoring UnrealEngine-1 levels (Deus Ex `.dx`,
Unreal/UT `.unr`) without opening the editor. You issue semantic, by-name commands
(`actor find`, `brush build`, `mover key move`, …); the T3D text format is internal plumbing.

The source of truth is a git-tracked T3D tree on disk (one directory per actor under
`maps/<level>/`), not a live editor or session store — work-in-progress is uncommitted /
feature-branch state in your own repo, and `git` is the history and merge engine. Reads and
edits are model-side compute against that tree (instant, no container). The editor / headless
game is reached only for commands that must build or render: `level materialize` and
`level preview --game`. Each spins up its own container as needed — no persistent session, no
`--container` flag.

```
uedcli <verb> …                      # if installed on $PATH (pipx)
bin/uedcli <verb> …                  # from Tools/uedcli, host-native via the dev venv
```

`uedcli docs list|show|search` prints this file and the level-design guides to your terminal — see
[Documentation](#documentation--read-the-docs-from-the-cli) below.

## Composability

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

⚠ The per-face verbs print faces, not actor names. `brush poly set` / `pan` / `rotate` / `scale`
print `BRUSH:idx` selectors — one per touched face — because a bare brush name means all of
that brush's faces, so printing one would hand the next verb a wider set than it edited. The names
are canonical and `all` is expanded, so `brush poly pan wall:all …` prints `WALL:0 … WALL:5`,
ready to feed the next verb's `-`.

⚠ `brush poly align` has not been converted and still prints brush names, so its output cannot be
piped into a per-face verb. It does not quietly widen the set — the per-face verbs take
`BRUSH:SELECTOR` only (see below), so a bare name is rejected and
`brush poly align … | brush poly rotate -` exits 2 with
`surface selector must be BRUSH:SELECTOR, got 'WALL'`. Re-select the faces with `brush poly find`
between the two verbs.

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
the selected game's base dirs, deduped project-shadows-base. `paths` are **bare directories**,
colon-separated — uedcli owns the five package extensions (`.u .dx .utx .uax .umx`) and scans the
dirs itself. Because `:` is the list separator, a pasted **Windows path** (`C:\DX\System`) cannot be
a dir: uedcli names it and exits 2, in both the project and the `[games.*]` config. Use the POSIX
path the dirs are actually at.

**Mover detection reads the class hierarchy, so it needs the packages.** Whether an actor is a
**mover** (an animated brush — see [Movers](#movers--animated-brush-actors-doors--lifts--gears)) is
decided by resolving its class against `Engine.Mover` in the game's code packages, *not* by guessing
from the class name. So every verb that has to know — `mover key *`, `level doctor`, `event graph`,
`brush scale`, `brush apply-transform`, `brush intersect`/`deintersect`, `stash capture`,
`level preview --native` — needs a resolvable package search path: a project **and**
`~/.uedcli/config.toml`. Without one the verb exits 2 naming itself and what is missing; it never
falls back to a name guess, since that would silently report a real mover as a static brush.
(`level materialize` and `level preview --game` need the same config to load the game's packages to
build and render, so in practice every verb on this page that touches packages wants it configured.)

The same rule applies **per actor**: if an actor's class — or any class on its ancestor chain — is
not on the composed search path, the verbs above exit 2 naming that class instead of quietly
deciding it is not a mover. The package holding the class is then missing from your project `paths`
or the game's base dirs (`uedcli project show` prints the resolved path).

**`project show [--json]`** prints the resolved root, game, managed dirs, and composed package search
path (each entry tagged `project`/`base`); `--json` emits
`{root, game, maps, prefabs, catalog, search_path:[{path, provenance}]}`.

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

| Command | What it does |
|---|---|
| `level create <name>` | scaffold a NEW level directory `maps/<name>/` with a `LevelInfo` actor (required by `materialize`); prints `to edit it: export UEDCLI_LEVEL=<name>` |
| `level import MAPFILE --tree KIND/NAME [--overwrite]` | decode an existing COMPILED map file (`.dx`/`.unr`) into a NEW level or stash — the inverse of `materialize`, and no editor is involved. See [`level import`](#level-import--read-an-existing-map-file) |
| `level reimport MAPFILE --tree level/NAME [--force]` | fold a hand-edited COMPILED map back into the level trunk that produced it, matching actors by NAME. See [`level reimport`](#level-reimport--fold-editor-changes-back-into-the-trunk) |
| `level list [--json]` | list the project's levels (trunk dirs under `<maps>`), one name per line to stdout (pipe-friendly); a count + the active `$UEDCLI_LEVEL` go to stderr. `--json` emits `[{name, active}, …]` |
| `level status [--tree KIND/NAME] [--json]` | thin read-only dashboard for the current level (or a `--tree` box): actor counts, duplicate `order_value`s, git state. `--json` emits a `{kind, name, actors, duplicate_order_values, git, texture_packages}` object (`{"selected": null}` when no level is set) |

---

# Query verbs — model-side, instant, no editor

## Actors

| Command | What it does |
|---|---|
| `actor find [filters…] [--json] [--exclude] [-]` | print names of matching actors, one per line, for piping; with no filters, prints **every** actor; a trailing `-` restricts the search to a piped name-set (boolean queries — see below) |
| `actor show <name\|->` | print named actors' full canonical T3D blocks |
| `actor bbox <names…\|-> [--field F \| --json]` | the world axis-aligned bounding box enclosing the given actors as ONE box |
| `actor prop get <name\|-> [KEY…] [--kv \| --json]` | print EFFECTIVE property values (see below) |
| `actor folder get <names…\|->` | print each actor's uedcli-side folder path (`(none)` if unfoldered) |
| `actor label get <names…\|-> [--json]` | print each actor's uedcli-side labels as `Name<TAB>l1,l2` (sorted, comma-joined; `(none)` if unlabelled); `--json` emits `{name: [labels…]}` |

**`actor find` filters** (repeat any flag; within a flag the patterns OR, across flags they AND):
- `--exact-class C` — match the class EXACTLY (bare or `Package.Name`, case-insensitive). Does NOT
  include subclasses — `--exact-class Light` skips `Spotlight`. (This replaced a plain `--class`,
  which was ambiguous about whether subclasses counted; bare `--class` is not a flag at all.)
- `--subclass-of C` — match `C` OR any class that descends from it (`--subclass-of Engine.Light`
  also matches `Spotlight`, `TriggerLight`, …). Descendant-aware; needs the class schema (the game
  `.u` install). ORs with `--exact-class` within the class dimension.
- `--group G` — membership in the T3D `Group=` prop (comma-joined groups are split).
- `--name GLOB` — fnmatch glob over the actor Name (case-insensitive, whole-name anchored).
- `--prop KEY[.PATH]=VALUE` — match the **EFFECTIVE** value (stored, else the class default decoded
  from the game `.u`, else zero) with a **type-aware** compare (`True`≡`1`, `4`≡`4.0`, enum
  name≡ordinal). Dot-paths reach into arrays/structs (`Location.X=512`). An actor whose class
  doesn't declare KEY simply doesn't match; a KEY *no* considered class declares errors (exit 2).
  Needs the class schema (the game `.u` install).
- `--kind point|brush` — the brush-vs-point split. `brush` = actors carrying a PolyList (CSG
  brushes, builders, movers — the ones `brush`/`poly`/`vertex` verbs accept); `point` =
  location-only actors (Light, LevelInfo, nav points, **and mesh decorations** — a mesh deco has
  visible geometry but is still a point actor).
- `--within-bbox X0,Y0,Z0,X1,Y1,Z1` — match actors whose **world bounding box is fully inside** the
  given axis-aligned box (two opposite corners in any order, unreal units — same space as `--at` —
  **edge-inclusive**). Honours each actor's full transform (a scaled/rotated brush's TRUE world box
  is tested); a point actor is its `Location` point. **Single-valued** (not repeatable). Matches
  **every** contained actor (lights, nav points, decorations too), so add `--kind brush` for geometry
  only. Being full **containment**, a brush straddling the box edge (a room shell poking past a tight
  box) is **not** matched — size the box to enclose the whole feature, or use `--overlapping-bbox`.
- `--overlapping-bbox X0,Y0,Z0,X1,Y1,Z1` — the looser companion: match actors whose **world bounding
  box overlaps** the given box (same arguments, transform-honoured, **edge-inclusive**). Contained vs
  straddling: `--within-bbox` drops a room shell / wall poking past the box edge, `--overlapping-bbox`
  grabs it — better for "everything in this area." **Single-valued**; ANDs with the other filters
  (passing both degenerates to `--within-bbox`, since contained ⊆ overlapping). Caveat: it tests the
  **world AABB**, so a diagonal or L-shaped brush can match on its bounding box with no solid geometry
  actually inside the box.
- `--folder PATTERN` / `--no-folder` — see **Folders** below.
- `--label GLOB` / `--no-label` — see **Labels** below.
- `--json` — emit the names as a JSON array.

```bash
uedcli actor find --group cells | uedcli actor delete -
uedcli actor find --folder castle.tower.** | uedcli actor bbox -   # enclosing box of a subtree
uedcli actor find --within-bbox -512,0,-256,512,768,256 --kind brush | uedcli actor preview -   # render a region
```

**Discover brushes by CSG type** (additive vs subtractive) uses the existing `--prop` — there is no
`brush find`/`brush list` verb and no `--csg` filter:

```bash
uedcli actor find --kind brush --prop CsgOper=CSG_Subtract   # every carve
uedcli actor find --kind brush --prop CsgOper=CSG_Add         # every additive
```

`CsgOper` is a declared enum, matched type-aware. Keep `--kind brush`: an unset `CsgOper` reads the
class default `CSG_Active`, not `CSG_Add` — only the transient builder brush omits it, so every placed
world brush carries an explicit `CSG_Add`/`CSG_Subtract`; and `--prop CsgOper=` over a set with no
brush exits 2. To author CSG sets use `brush intersect`/`brush deintersect`; to change CSG precedence
use `actor order`.

**Boolean queries — `find <filters> -`:** with a trailing `-`, `find` reads a newline actor-name list
from stdin and searches ONLY that set; the filters are the predicate. `--exclude` keeps the
non-matches instead. This composes into full boolean logic:

    actor find --group A | actor find --group B -            # A AND B
    actor find --group A | actor find --group B --exclude -  # A but NOT B
    { actor find --group A; actor find --group B; } | sort -u | actor find -   # A OR B (re-normalized)

Unknown piped names are a hard error (exit 2). `find -` with no filters echoes the piped set (a strict
validator).

`actor show <name>` takes ONE actor name (case-insensitive) — **not a glob**: patterns belong to
`actor find`, and `actor find 'Light*' | actor show -` prints the whole matched set. A name that
matches no actor errors (exit 2). Reads a stdin name list with `-` (empty stdin is a clean no-op,
exit 0). By default each block carries the uedcli-side sidecars as comments — a `// uedcli-folder:`
line for a foldered actor and a `// uedcli-labels:` line for a labelled one — so
`actor show A | actor add -` round-trips both; `--t3d-only` suppresses them for a byte-exact editor
export.

The T3D that `actor show` prints — and the trunk stores — is faithful, not abbreviated: it states
every authored property explicitly, including ones equal to the class default
(`Location=(X=0.000000,Y=0.000000,Z=0.000000)`, `Rotation=(Pitch=0,Yaw=0,Roll=0)`, a `Tag` the
editor stamped). UnrealEd's own export omits those, so its export is shorter than the trunk — the
build's post-verify compares the two by value, not text: each property resolves to what it would
import as (the stored value, or the class default when the line is absent), so the two spellings are
the same level. Never hand-delete such a line to "clean up" the trunk: an omitted property means the
class default, which is non-zero for some classes.

**`actor prop get`** prints EFFECTIVE property values — the stored value if present, else the class
default decoded offline from the game packages, else the type's zero — one line per KEY in argument
order (a whole static array prints as one `(0=V,1=W,…)` line; a whole struct prints every member).
With **no KEYs**, dumps the actor's STORED props (plus `Location`). `--kv` prints round-trippable
`KEY=VALUE` lines (feeds back into `actor prop set`); `--json` emits a `{key: value}` object (values
as strings). The name may be `-` to read a stdin name list and dump every piped actor (output is then
`<name>\t<key>=<value>`).

**`actor bbox`** honours each actor's rotation/scale/location; a point actor contributes a zero-size
box at its Location. Default prints four labeled `min`/`max`/`size`/`center` lines; `--field
min|max|size|center` prints just that one bare `x,y,z` vector; `--json` emits `{min,max,size,center}`
each `{x,y,z}`. The count summary goes to stderr.

The reported numbers are **tolerance-snapped** to within 0.001 uu of a whole number: UE1's rotator
table is not exact — a 180° yaw carries `sin = -8.742278e-08`, so a ±64 vertex offset leaks ~6e-06
into the cross axis and a brush exactly on `Y=228` would otherwise report `227.999994`, reading as
"off-grid" for geometry whose trunk is exact. A **genuine** fraction (a 2.5-uu semisolid, an
odd-span center) is preserved — the snap only fires inside that band. `brush vertex list` and the
stash summary snap the same way, so every report of a world coordinate agrees. The snap is confined
to reporting: `doctor`, the CSG core and the preview cameras see raw values, because a cleaned
coordinate feeding a geometric *decision* would mask the faults those tolerances exist to catch.
`actor find --within-bbox` compares within the same tolerance, so a box piped from
`actor bbox --field min/max` contains the actor it came from.

## Brush surfaces & geometry

| Command | What it does |
|---|---|
| `brush poly list <name> [--json]` | per-poly table for a brush (see below) |
| `brush poly find <name> [filters] [--json]` | matching faces as `BRUSH:idx` selectors, for piping |
| `brush vertex list <name> [--json]` | welded brush corners: world coord + the polys sharing each |
| `brush measure relation <names…> [--top N\|all]` | exact geometric facts between every pair of faces across 2+ brushes (see below) |

**`brush measure relation`** replaces eyeballing a render with exact computed facts: for every pair
of faces across the named brushes (2+ names, or `-` for a stdin name list), it reports whether the
planes are coplanar or parallel, both normals, the signed distance between them, the 2-D footprint
relationship (`none`/`vertex`/`edge`/`partial`/`contains`/`coincident`), and the centroid/edge-min
deltas in the shared plane's own U/V axes. `--top N` caps how many ranked candidate face-pairs are
shown per brush pair (default 1, closest first); `--top all` shows every qualifying pair. Brushes
sharing no plane and no parallel-facing relationship with anything else named are reported as
`disjoint` rather than silently omitted.

```
$ uedcli brush measure relation Wall_North Floor
Wall_North <-> Floor  (1 of 12 candidates shown)
  Wall_North:5 <-> Floor:4
    plane: coplanar
    normals:
      Wall_North:5: (0.000, 0.000, -1.000)
      Floor:4: (0.000, 0.000, 1.000)
    distance: 0.000uu
    footprint_2d: contains (Wall_North:5 in Floor:4)
    deltas:
      centroid: U=120.000uu V=0.000uu
      edge: U-min=0.000uu V-min=0.000uu

checked: 2 brushes, 1 pairs, every face
```

**`brush poly list`** is the precise surface reference. Columns: `idx | facing (±X/±Y/±Z or slant) |
texture | flags (decoded to NAMES) | pan | centroid | area | nverts`. Flags decode to names
(`masked`/`translucent`/`fakebackdrop`/`unlit`/…, plus a hex tail for unknown bits). `--json`
emits `{actor, polys:[…]}`.

**`brush poly find`** is a stateless producer: it prints the brush's matching faces as `BRUSH:idx`
selectors, one per line (a match count → stderr). Filters AND together:
- `--item NAME` — the builder ItemName (`Side`/`Cap`/`Step`/…, case-insensitive).
- `--facing DIR` — snapped outward facing (`+X`/`-X`/`+Y`/`-Y`/`+Z`/`-Z`/`slant`).
- `--texture REF` — the texture ref (exact or last dot-component, case-insensitive).
- `--json` — an array of `{brush,poly,item,facing,texture}`.

Its output feeds `brush poly set|pan|rotate|scale -` and `brush poly align -` — and those four
per-face verbs print the same `BRUSH:idx` form, so they chain into each other directly.

## Level lint & trigger wiring

**`level doctor [--json] [--severity {info,warn,error}] [--category NAME]…`** statically checks the
level for the BSP/geometry problems that cause holes, HOMs, and invisible walls — **fully offline,
no editor.** It flags: degenerate faces UnrealEd will silently drop (too few vertices, zero area,
non-convex, non-planar); brushes that aren't watertight (open/duplicated/back-wound edges); solidity
mistakes (a portal marked semisolid); gross CSG-order errors (an additive brush buried inside a later
subtract, a subtract that carves nothing); and scale issues. Each finding names the brush, poly,
world coordinate, engine symptom, and fix.

**What `level doctor` will and will not find.**

`doctor` checks whether the level is mechanically well-formed: things objectively broken and
decidable from the trunk alone. "Broken" means the engine or data cannot work as authored, not that
a human would judge the result poor.

The dividing line is intent: `doctor` reports only what is wrong no matter what the author meant. A
dangling `Event` fires into the void; a light inside a solid lights nothing. But `doctor` cannot
know what a space is meant to be, so it does not judge passages: it can measure the free gap between
two brushes, but cannot tell a deliberately sealed wall from an accidentally blocked doorway — both
are the same geometry. Any check that needs to guess the author's intent is out of scope
permanently. *(Owner ruling and rationale, 2026-07-26.)*

In scope:

- **Math and geometry** that breaks or burdens the BSP — degenerate/non-planar/non-convex faces,
  brushes that aren't watertight, solidity mistakes, CSG-order errors, scale problems.
- **Zoning** problems of the same kind.
- **Obvious footguns with an objectively wrong answer** — e.g. an `Event` matching no actor's `Tag`
  (it fires into the void), or a light buried inside solid geometry (it lights nothing).

It will not find gameplay or style problems, and a clean report says nothing about them. Out of
scope by design:

- whether a corridor or doorway is comfortable to move through, or geometry protrudes into an
  entrance;
- whether a decoration is well placed, correctly oriented, or seated on its surface;
- whether the level has the trim, edge detail, or finish a real space would have;
- whether it is well lit, legible, or fun.

These are level-design quality; they need a human or an independent reviewing agent looking at
renders. A level can be `no issues found` and still be cramped, ugly and half-finished. *(Owner ruling, 2026-07-26.)*

- Categories: `degenerate, watertight, convex, planar, solidity, csg_order, scale`. `--category`
  takes one; repeat it to OR several (`--category watertight --category convex`). Exact,
  case-insensitive; an unknown category exits 2 listing the valid ones.
- `--severity` / `--category` filter what's **shown**; the **exit code always reflects ALL findings**
  (non-zero if any ERROR exists, regardless of the filter), so it works as a CI gate.
- It is a **high-recall per-brush predictor**, not a completeness guarantee: holes that only emerge
  from how brushes split each other during the build (slivers, T-junction cracks) need the build
  itself.
- **It needs the game's code packages on the search path** (a project + `~/.uedcli/config.toml`):
  the watertight check applies to closed solids — world brushes *and movers* — and mover-ness is a
  class-hierarchy question (see [Projects](#projects-uedclitoml)). With no resolver it exits 2
  naming the verb and what is missing, rather than reporting a partly-checked level as clean.

**`event graph [--dot | --json]`** reports how the level's actors are wired to trigger each other —
**offline, model-side** (no editor; it does read the game's `.u` packages, because a Mover is a node
even with no eventing props — see [Projects](#projects-uedclitoml)). An actor's **`Event`** property
is the event it *fires*; another's **`Tag`** property is its *receiver* identity. A directed edge
**A → B** means `A.Event == B.Tag`.

- **Default (text):** one wiring per line to **stdout** —
  `Trig (Engine.Trigger) --OpenDoor--> Door (Engine.Mover)`; the summary + lint go to **stderr**.
- **`--dot`:** Graphviz DOT to stdout (`uedcli event graph --dot | dot -Tpng -o wiring.png`).
- **`--json`:** a `{nodes, edges, lint}` object.

The **lint** reports `dangling_event`, `unreachable_tag`, `unreachable_mover`, and `cycle`. It
**exits 0 even with findings** (a query verb — lint is advisory; grep the output for CI). Only an
explicitly-set, non-empty `Tag` counts as a receiver.

## Folders — hierarchical actor organization

Actors are organized into a **tree of folders** — a per-actor dotted **path** (`castle.tower.roof`),
so logical subsets are addressable. A folder is **uedcli-side only**: it lives in a trunk sidecar
beside the actor, is **never emitted to the built map**, and is a **separate dimension** from the T3D
`Group=` property (retained unchanged). One folder per actor.

- **Set at creation:** on the **generator** — `brush build … --folder <path>` / `actor build … --folder
  <path>` — which emits a `// uedcli-folder:` carrier in the T3D; `actor add` persists it (it has no
  `--folder` of its own). `actor show` emits the same carrier, so `actor show A | actor add -` round-trips.
- **Manage:** `actor folder set --to <path> <names…|->`, `actor folder unset <names…|->`,
  `actor folder get <names…|->`, `actor folder rename <old-path> <new-path>` (re-parent/rename a whole
  subtree: rewrites the `old` prefix to `new` on every actor filed at `old` or under it; `old`
  matching no actor is an error). `set`/`unset`/`rename` are PRODUCERS (touched Names → stdout, a summary →
  stderr), so they chain: `uedcli actor find --subclass-of Engine.Light | uedcli actor folder set
  --to castle.lights - | uedcli actor prop set - LightBrightness=200`.
- **Query:** `actor find --folder <pattern>`.

Pattern matching is **globstar** with one asymmetry:
- A **wildcard-free** pattern (`castle`) selects that folder **and its whole subtree**.
- `*` matches exactly one segment; `**` matches any depth.
- A **wildcarded** pattern is a *pure glob with NO subtree extension* — `**.roof` matches roof NODES
  only, not their contents (use `--folder '**.roof' --folder '**.roof.**'` for "every roof and
  everything inside").
- `--no-folder` matches only unfoldered actors (the only way to query them).

## Labels — flat, multi-valued actor classification

Alongside the single-path folder, each actor carries a **set of labels** — flat tokens
(`lighting`, `flammable`, `hero`) that answer "what is this about", the cross-cutting axis one
hierarchy can't express (a torch is at `castle.tower` AND is `lighting` AND `interactive`). Like
folders, labels are **uedcli-side only**: they live in a per-actor trunk sidecar, are **never emitted
to the built map**, and are **orthogonal** to the folder, the T3D `Group=` prop, and the T3D `Tag=`
prop (named `label`, not `tag`, to avoid colliding with `Engine.Actor.Tag`). An actor may carry any
number of labels. A label token is `[A-Za-z0-9_+-]`, no `.`, no leading `-`; stored as authored
(case preserved) and matched case-insensitively.

- **Set at creation:** on the **generator** — `brush build … --label L` / `actor build … --label L`
  (repeatable) — which emits a `// uedcli-labels:` carrier; `actor add` persists it (no `--label` of its
  own). `actor show` emits the same carrier, so a show → add round-trips.
- **Manage:** `actor label add --label L <names…|->` (set union), `actor label remove --label L
  <names…|->` (set difference), `actor label clear <names…|->` (drop all), `actor label get
  <names…|->`. There is **no `set`** — compose `clear` then `add`. `add`/`remove`/`clear` are
  PRODUCERS (touched Names → stdout, a summary → stderr) and **validate-all-then-apply**: a bad
  `--label` or an unknown name leaves every actor untouched (exit 2 naming the offender).
- **Query:** `actor find --label <glob>` (repeatable = OR) / `--no-label`.

Matching is a **flat `*`-glob** (no path structure): an actor matches if ANY of its labels matches
the pattern; `*` is the ONLY wildcard (`dup-*` finds a duplicate batch, `lighting` matches that exact
label), and `?`/`[`/`]` are rejected. Repeat `--label` to OR patterns; it ANDs across the other
`find` dimensions. `--no-label` (mutually exclusive with `--label`) matches only unlabelled actors —
the only way to query them.

```bash
uedcli actor find --subclass-of Engine.Light | uedcli actor label add --label lighting -
uedcli actor find --label 'dup-*' | uedcli actor move -   # re-address a duplicated batch
```

Labels are **trunk-only** this release: every label surface (`actor label …`, `actor find
--label`/`--no-label`, the generators' `--label`, and `actor duplicate`) rejects `--tree stash|prefab`
(exit 2). `actor duplicate` inherits the source's labels plus a fresh `dup-<rand>` batch label — see
below.

---

# Mutating verbs — model-side, rewrite the trunk

These transform the in-memory level and rewrite the T3D trunk. Committing is your own `git`. Each
also accepts `--tree KIND/NAME` (see below) to edit a different box.

## Actors

| Command | What it does |
|---|---|
| `actor add <file\|-> [--order POS]` | add the actor(s) in a T3D snippet (point → IMPORTADD, brush → PASTE); a pure carrier-consumer — persists any `// uedcli-folder:`/`// uedcli-labels:` carrier in the T3D (folder/label are set on the generator or later via `actor folder set`/`actor label`); prints allocated names to stdout |
| `actor duplicate <names…\|-> (--by DX,DY,DZ \| --at X,Y,Z) [--label L…] [--folder PATH]` | copy actors with fresh names, offset by `--by` or anchored by `--at` (one is REQUIRED); copies inherit the source's labels plus a fresh `dup-<rand>` batch label. Always appends (no `--order`). Prints allocated names to stdout |
| `actor delete <names…\|->` | delete one or more actors, restoring swept neighbours |
| `actor move <name> (--to X,Y,Z \| --by DX,DY,DZ)` | move a single actor |
| `actor rotate <names…\|-> (--by \| --to) PITCH,YAW,ROLL [--pivot … \| --pivot-actor …]` | rotate a group around a pivot |
| `brush scale <names…\|-> (--by \| --to) SX,SY,SZ [--pivot … \| --pivot-actor …]` | scale BRUSH actors via MainScale (negative axis mirrors); a point actor is rejected |
| `brush apply-transform <names…\|-> [--lock-textures \| --no-lock-textures]` | bake MainScale+Rotation+PostScale into brush vertices, reset the fields; rejects movers/point actors |
| `actor order <names…\|-> (--first \| --last \| --before NAME \| --after NAME)` | reorder EXISTING actors' CSG precedence (no geometry change) |
| `actor prop set <name> KEY[.PATH]=VALUE…` | set properties in one atomic, schema-validated edit |
| `actor prop unset <name> KEY[.PATH]…` | clear properties (revert to class default) |
| `actor folder set/unset/rename` | manage the uedcli-side folder (see Folders); prints the touched names |
| `actor label add/remove/clear` | manage the uedcli-side labels (see Labels) |

**`actor add`** — a point actor enters via `MAP IMPORTADD`, a brush via `EDIT PASTE` (only
paste/ADD brushes are later selectable — uedcli handles this and compensates the +32uu paste drift).
`--folder PATH` stamps every added actor's folder (overrides any `// uedcli-folder:` carrier).
`--label L` (repeatable) stamps labels on every added actor, likewise overriding any
`// uedcli-labels:` carrier; absent, the carrier (from `actor show`) sets the labels, else the actor
is unlabelled. `--order first|last|before=NAME|after=NAME` (default `last`) places the added actor(s)
in CSG order; multiple actors land as a block preserving input order (level target only — rejected on
`--tree stash|prefab`).

**`actor duplicate`** copies actors under fresh names, requiring **exactly one** of `--by DX,DY,DZ`
(a relative per-actor offset) or `--at X,Y,Z` (anchor the copied set's bounding-box minimum corner);
neither is an error (exit 2), and `--by 0,0,0` overlaps the originals in place. Copies **inherit
their source's labels** plus **one fresh `dup-<rand>` batch label**, so `actor find --label
dup-<rand>` re-addresses the whole batch after the pipeline ends (the token is echoed to stderr).
`--label L` (repeatable) is **additive** — stamped on top of the inherited labels and the
`dup-<rand>` token. `--folder PATH` overrides each original's folder. Trunk-only (rejects
`--tree stash|prefab`).

**`actor order`** re-mints `order_value`s to change CSG precedence without touching geometry (CSG
order is the `(order_value, name)` sort). `--first` makes an actor carve/add before everything else.
Multiple actors move as a block preserving their relative order.

**`actor prop set`** — `KEY=VALUE` replaces the whole value (static array: tuple form
`KEY=(0=V,3=W)`, clearing unmentioned elements; Vector/Rotator: comma sugar `KEY=X,Y,Z`); `KEY.N=V`
edits one array element; `KEY.Member=V` edits one struct member (siblings preserved; an unset prop
bases on the class default). Unknown name / bad enum / out-of-bounds index / overlapping tokens are
rejected; `Name`/`Brush` and the mover-key geometry (`KeyPos`/`KeyRot`/`KeyNum`) are refused, but
`NumKeys` is settable (2..8, == `mover key count`); `Location` routes to the typed field (a partial
struct zero-fills). **`actor prop unset`** clears the whole prop, one array element (`KEY.N`), or one
struct member (`KEY.Member`); clearing something not stored succeeds silently; `unset Location`
resets to the origin.

**`actor rotate`** rotates N actors (point actors + brushes) together — it orbits each Location about
the pivot and composes each orientation into the actor `Rotation` field, **the way UnrealEd stores a
rotated brush** (the PolyList stays local; the engine applies `Rotation` at CSG build). `--by` is a
**relative** rotation in **unreal rotation units** (16384 = 90°) `PITCH,YAW,ROLL` (negatives allowed);
`--to` sets the field **absolutely in place** (Location never moves; excludes `--pivot`). The pivot
is `--pivot X,Y,Z`, or `--pivot-actor NAME`'s Location, or (default) **the `Location` of the set
member nearest the selection's bbox center**. A brush's `Location` is the point that stays fixed when
it turns about itself, and it is an **authored** coordinate — so the pivot inherits whatever grid you
built on rather than being computed and rounded onto a different one. A lone brush turns in place.

Details that follow from that:

- **Brushes supply the pivot** when the selection has any; otherwise point actors' Locations do. So a
  lone decoration — or several sharing one Location — turns about **exactly** its own Location, and an
  off-grid prop is never dragged onto the grid by turning it.
- **Equidistant members take the alphabetically first Name** — the pivot is always a Location that
  exists in the trunk, never an average of several (which would land off-grid). It does not depend on
  the order names arrive in the pipe. Use `--pivot X,Y,Z` or `--pivot-actor` to pick a different one.
- **Locations are used as authored**, with no filtering. A brush in the raw CSG form
  (`Location=(0,0,0)` with world-space vertices) contributes the world origin, and a set of only
  those turns about the origin — `--pivot`/`--pivot-actor` overrides it.
- **There is no fallback rule**: every actor has an *effective* Location — an unauthored property
  takes its **class default** — so a non-empty selection always has a pivot. The default is resolved
  from the class, not assumed zero: `Engine.Camera` defaults `Location=(X=-500,Y=-300,Z=300)`. The
  class schema is consulted only for an actor that states no Location, so an ordinary rotate stays offline.

> The two reference points differ on purpose. Rotation and scale pivot near the center (you turn a
> thing about its middle). Placement anchors the bbox-min corner — `stash`/`prefab apply --at`,
> `actor duplicate --at`, and stash capture's normalization all land the set's minimum corner on the
> target, because you place a prefab by dropping a corner on a grid point you can read off and type.

A zero result is **written out** (`Rotation=(Pitch=0,Yaw=0,Roll=0)`), not omitted: an actor with no
`Rotation` property takes its *class* default, which is not zero for every class, so `--to 0,0,0`
means "unrotated" only when the rotator is there to say so.

**`brush scale`** (renamed from `actor scale` 2026-07-20 — MainScale is a brush-family property; a
mesh uses `DrawScale`) sets MainScale on BRUSH actors — `--to` absolute in place, `--by` a per-axis
factor that also orbits each Location about the pivot (`Loc' = P + S·(Loc−P)`). A negative axis
mirrors; there is no separate `mirror` verb (`mirror` = `brush scale --by -1,1,1`). It shares
`actor rotate`'s default pivot, so a lone brush mirrors **about its own `Location`** — in place. A
point actor is rejected.

**`brush apply-transform`** (renamed from `actor apply-transform`) bakes MainScale + Rotation +
PostScale permanently into the brush vertices and resets those fields (the offline
`ACTOR APPLYTRANSFORM`): reverses winding on a mirror/negative determinant, rewrites PrePivot, leaves
Location, rejects movers. `--lock-textures` (the DEFAULT) transforms the texture axes with the
geometry; `--no-lock-textures` leaves the mapping fixed.

## Brush shape & surfaces

| Command | What it does |
|---|---|
| `<generator> \| brush clip - (--axis A --offset N \| --plane PX,PY,PZ NX,NY,NZ) [--keep below\|above]` | clip every brush in a piped T3D set by one world plane; T3D to stdout |
| `<generator> \| brush snap - --grid N --tolerance T` | round every brush's near-grid local vertices to a grid; T3D to stdout |
| `<generator> \| brush replace <name> -` | in-place shape swap, keeping the target's identity |
| `brush vertex move <name> --at X,Y,Z (--to X,Y,Z \| --by DX,DY,DZ)` | move welded corners (selected by coordinate; repeat `--at`) |
| `brush poly move BRUSH:SELECTOR… \| - --by DX,DY,DZ` | translate whole faces: move every vertex of each face by a world delta |
| `brush poly set BRUSH:SELECTOR… \| -` | set the texture / surface flags on one or more faces |
| `brush poly pan BRUSH:SELECTOR… \| - (--to\|--by) U,V` | shift a face's texture by whole texels |
| `brush poly rotate BRUSH:SELECTOR… \| - --by UU` | turn a face's texture within its own plane |
| `brush poly scale BRUSH:SELECTOR… \| - --by FU,FV` | resize a face's texture in place |
| `brush poly align (--wall\|--floor\|--ring) targets…\|-` | flow one texture continuously across faces |

**`brush clip -|FILE`** is a stateless T3D **filter**: it reads a brush set as a T3D snippet on stdin
(`-`) or from a saved FILE, clips **every** brush in it by one world plane, and writes the clipped
brushes to stdout — so a chamfered box is one pipe:
`brush build cube … | brush clip - --plane 96,0,0 1,0,1 --keep below | actor add -`. The plane is
world-space (`--axis` + `--offset`, or point+normal) and is mapped into each brush's own local frame,
so a rotated/scaled brush clips correctly and keeps its `Rotation`. `--keep below` (default) keeps the
side opposite the normal. Empty stdin is a clean no-op (exit 0); a non-brush (point) actor in the set,
or a plane that would discard a whole brush, is a clean error (exit 2 naming it). A plane that misses a
brush's interior passes that brush through unchanged with a `did not intersect brush <name>` note on
stderr. To clip a **placed** actor, compose with `replace`:
`actor show WALL | brush clip - --plane … | brush replace WALL -`.

**`brush snap -|FILE --grid N --tolerance T`** is a stateless T3D **filter** that cleans off-grid
float noise: it reads a brush set on stdin (`-`) or a FILE, and for every brush rounds each **local**
vertex component to the nearest multiple of `--grid` **when it is within `--tolerance`** of it,
leaving a component farther than the tolerance in place. So a corner that drifted to `x=15.997`
snaps to `16`, while a genuinely off-grid `x=8.5` (nowhere near a 16-grid line) is preserved —
intentional angles survive, only slop is corrected. Snapping is per-axis and per-vertex, so a slant
vertex keeps its off-grid axis and cleans the others. Off-grid coordinates are the main cause of BSP
holes, so this is the tool for cleaning imported or drifted geometry before a build. Both flags are
**required** (no default grid/tolerance would be a silent guess); rounding is half toward +∞. A
`--tolerance` at or above half the grid snaps every component to a grid line — allowed, with a note on
stderr that it will destroy angles. Empty stdin is a clean no-op (exit 0); a non-brush (point) actor,
a non-positive grid, a negative tolerance, or a snap that would push a face non-planar is a clean
error (exit 2 naming it). To snap a **placed** actor, compose with `replace`:
`actor show WALL | brush snap - --grid 16 --tolerance 0.05 | brush replace WALL -`.

**`brush replace <name> -`** swaps a brush's **shape in place** from a piped generator T3D on stdin
(`-` is the sole shape source — the `build → replace -` convention, not a name list), **keeping** the
target's Name, `order_value`, Group, CsgOper, actor-level solidity PolyFlags, and old
Location/PrePivot. Only the incoming **PolyList** is taken (its own Location/PrePivot/Name ignored),
but its **per-surface attributes come with it** — reapply any `brush poly set` edits afterward. Empty
stdin is a clean no-op; input with no brush geometry, or more than one brush, is a clean error
(exit 2). E.g. `brush build cube --width 512 … | brush replace WALL -`.


**`brush vertex move`** moves one or more welded corners selected by their current world coordinate
(`--at`, repeatable). `--to` needs exactly one `--at`; `--by` applies a delta to every `--at` corner.
`brush vertex move` is **rotation-aware** — a world coord is mapped into the brush's local frame, so
it edits a rotated brush correctly and preserves `Rotation` (as does the `brush clip` filter above).

**`brush poly move --by DX,DY,DZ`** is the whole-face counterpart: it translates every vertex of each
selected face by a world delta, model-side and rotation-aware like `brush vertex move`. It takes the
same `BRUSH:SELECTOR` targets as the poly texture verbs below (`-` for stdin). Because a brush stores
welded corners, a corner shared with an unselected face moves too and that neighbour deforms — the
solid stays watertight. Most non-axis-aligned moves push a neighbour off its plane and are rejected
(exit 2 naming the face); moving a face along its own normal is the safe case.

Two different jobs, two verbs. **`brush poly set`** assigns a face's stored **attributes** — which
texture is on it, which surface flags it carries. **`brush poly pan` / `rotate` / `scale`** transform
the face's **texture frame** — where the texture sits, which way up it runs, how big it is.
**`brush poly align`** (next section) derives a whole frame from geometry.

**Targets, for all four.** `BRUSH:SELECTOR` positionals (SELECTOR = `all` or comma-separated poly
indices; repeatable, e.g. `Wall1:3,5 Wall2:all`), **or `-`** to read `BRUSH:idx` lines from stdin
(empty stdin = clean no-op, exit 0; `-` is the sole source and cannot be mixed with positionals).
A face named twice is edited **once**. Unlike `align`, which *also* accepts a bare brush name meaning
all its faces, **`set`/`pan`/`rotate`/`scale` do not** — say `Tower:all`. A whole brush is a
meaningful unit for an alignment mode ("wrap this cylinder"), but a whole-brush pan or rotate is a
blanket nudge of every face including ones you never looked at, and the relative forms compound it
silently, so "yes, all of them" has to be typed out.

**`brush poly set`** takes `--texture REF` (qualified `Package[.Group].Name`) and
`--add-flag`/`--remove-flag` (flag by **name**, case-insensitive — `Unlit`, `unlit`, `MASKED` all
work; repeatable). At least one of the three is required.

```bash
uedcli brush poly find WALL --facing +Z | uedcli brush poly set - --texture DeusExDeco.Wood
```

**`brush poly pan (--to | --by) U,V`** shifts the texture across the face by whole **texels**.
Exactly one of `--to` (absolute) / `--by` (relative to the current pan, which counts as `0,0` when
unset) is required; both take negatives. A pan of `0,0` **is** the unpanned state, so `--to 0,0`
clears the pan and `brush poly list` then shows `-` in the `pan` column — there is no separate
"explicitly zero" pan.

**`brush poly rotate --by UU`** turns the texture within the face's own plane. `UU` is in **unreal
rotation units** — 16384 = 90°, 65536 = a full turn — the same units as `brush build --rotate` and
`mover key rotate`; negative turns the other way (`--by -16384` ≡ `--by 49152`). The face's own
centre keeps its texture coordinate, so the texture **spins in place** instead of sliding. There is
**no `--to`**: an absolute angle could only be measured against an internal canonical frame whose
in-plane direction you cannot see or predict, so it would mean something different on every face
normal. A *known* orientation is `brush poly align`'s job.

**`brush poly scale --by FU,FV`** resizes the texture. It names what you **see**: `--by 2,2` makes
the texture look twice as big, `--by 0.5,1` halves its width only. U and V are independent, and both
factors must be positive. The face's own centre again keeps its texture coordinate, so the texture
grows in place rather than sliding off.

⚠ Ordering rules:

- Pan comes after align, never before. Every `brush poly align` mode stamps `Pan` on each face
  it touches, so a dialled-in pan applied first is discarded.
- Scale comes before `align --ring`, never after. A ring wrap computes each face's phase offset
  for the density it saw; rescaling afterwards leaves those offsets describing the old size and the
  seams no longer meet.
- Panning a subset of an aligned run breaks its continuity, since those faces shift relative to
  their neighbours while the rest stay put. Easy to do by accident — the natural idiom is
  `brush poly find … | brush poly pan -`, and `find` filters. Pan the whole run or none of it.
- `rotate` and `scale` give no continuity guarantee: each face pivots or grows about its own centre,
  so applying either across an aligned set breaks the seams `align` matched — and a shared wall/floor
  grid. They are for a one-off face (a sign, a monitor, a soffit). The run-aware turn is a flag on the
  alignment itself, not this verb.

`rotate` turns the texture the way you see it turn: the direction follows the face's visible surface
normal, so the same `--by 16384` looks the same whether you stand outside an additive pillar or
inside a subtractive room — uedcli flips the sign on a subtract. So `rotate` requires the brush's
`CsgOper` to be `CSG_Add` or `CSG_Subtract` (an absent one counts as `CSG_Add`) and exits 2 naming
any other value — `CSG_Intersect`, `CSG_Deintersect`, `CSG_Active` or anything unrecognised — because
a brush with no inside and outside gives the turn no direction to follow.

⚠ One case is still backwards: a **mirrored** brush — one whose scale has an **odd** number of
negative components, e.g. `MainScale=(-1,1,1)` — has its faces' winding reversed as the engine draws
them, so the visible normal is opposite the one uedcli computes and the turn inverts again. Negate
the angle there. An **even** number of negative components (`(-1,-1,1)`) is a 180° rotation, not a
mirror, and is **not** affected. (A geometric argument from the sign of the scale matrix's
determinant — uedcli's own frame math ignores scale entirely — not checked against the running editor.)

**Identifying a surface to edit:** `brush poly list <brush>` for the exact index/facing/texture,
then `actor preview <brush> --highlight <brush>:N` (below) to see it emphasised (or
`--frame <brush>:N` to frame it).

### Continuous texture alignment (`brush poly align`)

**`brush poly align (--wall | --floor | --ring) [--fresh-frame] [--fit-perimeter] (targets…|-)`** makes
one texture flow **continuously** across a set of faces instead of restarting the pattern at every
brush edge (offline texture-vector math — no editor involved).
Exactly one geometry mode is required. The face set is `BRUSH:SELECTOR` positionals (or a bare brush
Name = all its polys) **or** `-` reading the set from stdin (bare names, or the `BRUSH:idx` lines
`poly find` prints); empty stdin is a clean no-op. The **first face is the seam/seed**. Touched brush
names → stdout, a summary → stderr.

- **`--wall`** / **`--floor`** — a set of strictly **coplanar** faces gets ONE shared world texture
  frame (a seam vertex maps to the same coordinate from either face). `--wall` requires the faces
  **vertical** (normal ≈ ±X/±Y), `--floor` requires them **horizontal** (±Z) — an orientation guard.
- **`--ring`** — wrap a texture around a **cylinder's side faces**: U advances by each facet's true
  chord (`2·r·sin(π/N)`) around the ring, V runs along the axis. Exclude the two caps.
- **Frame source:** default **adopt-seed** (continue the seed face's already-dialled-in
  `TextureU/V` + `Pan`); `--fresh-frame` synthesizes a canonical frame from the face normal instead.
  ⚠ That canonical frame is **uedcli's own convention, not a reproduction of UnrealEd's
  "align to floor / wall direction"** — measured against the editor 2026-07-26, the two pick
  different in-plane axis directions (a mirror, a 180° turn, or on a non-axis-aligned wall a full 90°)
  and pin the texture's phase to a different point (uedcli to the seed face's centre, the editor to a
  world axis). A face aligned here and in the editor's GUI will not look the same; pick one tool per
  surface.
- **`--fit-perimeter`** (`--ring` only) snaps the scale so an integer number of texels fits the
  perimeter (an exact meet at the closing seam).

```bash
uedcli brush poly find Tower --item Side | uedcli brush poly align --ring -
uedcli actor find --folder castle.hall.northwall | uedcli brush poly align --wall -
```

## `--tree KIND/NAME` — edit a stash, prefab, or another level in place

Every content mutating/query verb above takes **`--tree KIND/NAME`** (KIND ∈ `level|stash|prefab`)
to operate on a named tree instead of `$UEDCLI_LEVEL`: `--tree level/<other>` another level,
`--tree stash/<id>` a captured stash, `--tree prefab/<name>` a library prefab **in place**
(the one-command prefab-template edit — no apply / re-capture / promote roundtrip). NAME may be
nested (`stash/hangar/arch`). Omit it for the default ambient `$UEDCLI_LEVEL`. It rides
`actor find/show/add/delete/move/prop/rotate/scale/order/bbox/folder/label`, `brush replace/vertex/poly`,
`mover key *`, the read verbs `actor show`/`level status`/`level doctor`/`event graph` and `stash
capture`'s SOURCE (`stash capture --tree level/<name>`; rejected together with `--from-t3d`),
**and — level-kind only — `level materialize`/`level preview`** (`--tree level/<name>`
builds/previews that level; `--tree stash|prefab` is rejected there, since a captured set has no world
— use `stash`/`prefab preview`). Passing `--tree` explicitly suppresses the `editing level '…' (from
$UEDCLI_LEVEL)` echo. For a stash/prefab box, `level status`/`level doctor` label it by kind and skip
the git hint. It is **not** on the generators (`brush build`/`actor build` — they read no box) or
`actor preview` (use `stash`/`prefab preview`).

---

# Generators — stateless T3D producers

These write a T3D snippet to **stdout** and never touch the trunk or stash. The caller decides what
to do with the output. **Name allocation and the write into the trunk happen at `actor add`, not at
generation time** — so `--base-name` is a *stem/prefix*, and `actor add` appends a unique `_<rand>`
suffix (the spiral writes a central column plus one wedge-tread actor per step, each with a per-brush
index; the staircase is one actor). Duplicate base names are safe.

```bash
uedcli brush build cube --width 256 --breadth 256 --height 128 | uedcli actor add -
uedcli brush build cube --width 256 --breadth 256 --height 128 > /tmp/cube.t3d
```

## `brush build <shape>`

Parametric brush primitives (UnrealEd's GUI BrushBuilders, replicated model-side). Writes one actor
T3D (the **spiral** writes a central column plus one wedge-tread actor per step — `N+1` actors,
ascending monotonically around the column; the **staircase** is a single non-convex brush actor).

```
brush build cube      --width W --breadth B --height H
brush build cylinder  --height H --radius R [--sides 8] [--align-to-side] [--axis x|y|z]
brush build cone      --height H --radius R [--sides 8] [--align-to-side] [--axis x|y|z]
brush build sheet     --width W --height H [--plane xy|xz|yz] [--flag NAME …]
brush build staircase --steps N --depth D --rise R --breadth B
brush build spiral    --steps N --inner-radius R --step-width W --rise H [--angle-per-step 8192]
brush build extrude   --point U,V --point U,V --point U,V […] --depth D [--axis x|y|z]
brush build revolve   --point U,V --point U,V --point U,V […] --angle UU [--segments N] [--axis x|y|z]
```

Common options on **every** shape: `--at X,Y,Z` (world Location; see Pivots), `--base-name`,
`--csg add|subtract`, `--solidity solid|semisolid|nonsolid`, `--folder`, `--label`, `--texture`,
`--rotate PITCH,YAW,ROLL`, `--prop KEY[.PATH]=VALUE`, `--mover-class Package.Name`. (There is no
`--group` flag — the engine `Group` property is set with `--prop Group=<name>`.)

**Every dimension must be greater than zero.** A width, breadth, height, radius, depth, rise, inner
radius or step width that is negative or zero is rejected up front — exit 2, naming the flag and
value (`brush build staircase: --depth must be greater than 0, got -32.0`). A negative length would
otherwise build a self-overlapping, inside-out brush that looks fine until the map build fails with
an unrelated-looking BSP error. Counts and angles keep tighter rules: `--steps` needs at least 1,
`--sides` at least 3, `--angle-per-step` between 0 and 32768 unreal rotation units (a half turn), and
`--angle` between 0 and 65536.

**Builder angles are unreal rotation units, like `--rotate`** — `16384` = 90°, `65536` = a full
turn — never degrees. `spiral --angle-per-step` defaults to `8192` (45°). Thirds are not exactly
representable (`65536` is a power of two), so a 60° sweep is `10923` uu = 60.002°. `cylinder`/`cone`
take no angle at all: the useful control there is the **`--align-to-side`** flag, which offsets the
cross-section by half a segment (`180/--sides` degrees) so a flat FACE, rather than a vertex, meets
an axis-aligned wall — the same as UnrealEd's own `AlignToSide` checkbox. For any other cross-section
angle use `--rotate`, whole-actor placement. `--sides` has no upper bound: above 16 a round cap is
split into several convex `Cap`/`Base` faces (an engine face holds at most 16 vertices), so the brush
stays one solid built from valid faces.

**`cylinder`/`cone --axis x|y|z` (default `z`)** orients the prism's long axis along that world axis
directly — the vertices are built rotated, so **no `Rotation` field is emitted** and a horizontal
pipe or beam needs no `--rotate`. It is the axis the n-gon cross-section is normal to; the `(U,V)`
map onto the other two world axes in right-handed cyclic order, the same meaning as
`extrude`/`revolve --axis`: `z` → cross-section in X,Y; `x` → Y,Z; `y` → Z,X. For any other
orientation use `--rotate`, which stacks on top. `sheet` keeps `--plane` (the plane it lies in),
`cube` takes neither.

- **`--rotate PITCH,YAW,ROLL`** (unreal rotation units — 16384 = 90°, 65536 = a full turn) **SETS** the emitted actor's `Rotation` field absolutely (a
  fresh actor is at identity, so no add-vs-override ambiguity). The rotation is **stored on the
  actor, not baked into the vertices** (matching UnrealEd); a warning goes to stderr if it carries
  any vertex off the integer grid (the editor snaps them on import). It lives on the generators, not
  on `actor add`. Passing `--rotate 0,0,0` **writes** `Rotation=(Pitch=0,Yaw=0,Roll=0)` (an omitted
  `Rotation` means "the class default", which is not zero for every class); leave the flag off
  entirely to emit no `Rotation` at all.
- **`--prop KEY[.PATH]=VALUE`** (repeatable) bakes a property into the T3D, **schema-validated against
  the emitted actor's class** (`Engine.Brush`, or `--mover-class`) before emit — same grammar as
  `actor prop set`. Overrides compose over the generator's own fields (incl.
  `CsgOper`/`PolyFlags`/`Group`/`Rotation`), so a `--prop` can override a dedicated flag.
- **Pivots:** cube/cylinder/cone/**sheet** are **centered on the origin** (`--at` sets the geometric
  center on every axis, including Z); the **staircase uses a front-bottom-corner pivot** — its
  geometry spans `0..steps·depth` in X, `0..breadth` in Y, `0..steps·rise` in Z (entirely at/above the
  floor), so `--at` places that min corner; the **spiral anchors at the base of its column axis**
  (centred in XY, *bottom* in Z); **`extrude`/`revolve` anchor on profile coordinate `(0,0)`** —
  for a revolve that is the bend centre (see below).
- **Item labels:** every built face carries UED's `Item` (ItemName) tag (`Base`/`back`/`Step`/`Rise`/
  `Side` on the staircase, `OUTSIDE` on the cube, `Cap`/`Side<k>` on `extrude` and `revolve`,
  `Side`/`Cap`/`Base`/`Sheet` on the others) — a semantic selection handle for `brush poly find
  --item …`. Address a specific staircase face (a tread, a riser, one side strip) via its `Item`,
  since the whole staircase is one actor.
- **`sheet`** defaults to TwoSided + NotSolid (a fence / masked panel). **`--flag NAME`**
  (repeatable) ORs extra surface/poly flags onto the sheet's face AT BUILD TIME on top of that
  default — `--flag portal --flag translucent` bakes a zone portal in one step instead of a follow-up
  `brush poly set --add-flag`.
- **`staircase` = ONE non-convex brush** named `Staircase` (or `--base-name`): the UED
  `LinearStairBuilder` stepped wedge — `Base` + `back` + per-step `Step`/`Rise` + tiled convex `Side`
  strips, `2 + 4·steps` faces. Its per-step boundaries are watertight T-junctions that `level doctor`
  accepts. **Native caveat:** UnrealEd (the default `level materialize`) and the real engine (the
  default `level preview --game`) build this non-convex brush correctly, but the experimental native
  CSG core assumes convex brushes, so `level preview --native` mis-builds its concave notches — use
  `--game`/UnrealEd for staircases. **Spiral is currently rough** (rectangular slabs, gaps) — prefer
  a cylinder column + per-step wedges until it's redone.

### `extrude` — sweep a profile you draw

Every other shape is *fixed parametric*: you choose sizes, never a silhouette. `extrude` takes a
**profile** — a closed 2D polygon you draw point by point — and sweeps it in a straight line, so an
L-shaped ledge, an arch voussoir, a moulded cornice or a chamfered pillar is one command instead of
hand-written T3D or a chain of `brush clip` planes.

```bash
# an L-shaped ledge, 16 uu deep, swept along Y
uedcli brush build extrude --axis y --depth 16 --at 0,0,0 \
  --point 0,0 --point 96,0 --point 96,32 --point 32,32 --point 32,96 --point 0,96 \
  --folder castle.hall --texture CoreTexBrick.Brick.DrtyGrayWalks_A | uedcli actor add -
```

- **`--point U,V` (repeatable, ≥3)** is one profile vertex in the profile's own 2D coordinates;
  **argument order is ring order**. The ring is **closed implicitly** — do not repeat the first
  point as the last (harmless if you do: it is welded away). Either winding is accepted.
- **`--axis x|y|z` (default `z`)** names the world axis the profile plane is **normal to** —
  equivalently, the direction the sweep grows. `(U,V)` map onto the other two world axes in
  right-handed cyclic order:

  | `--axis`        | `U` | `V` | the sweep grows along |
  |-----------------|-----|-----|---|
  | `z` *(default)* | X   | Y   | +Z |
  | `x`             | Y   | Z   | +X |
  | `y`             | Z   | X   | +Y |

- **`--depth D`** is the sweep length in world units, and must be greater than 0.
- **`--at` is the world point profile coordinate `(0,0)` lands on.** The local vertices are the
  coordinates you drew, verbatim — nothing is re-centred — and the sweep runs `0..depth` from there.
  So a ring of voussoirs drawn at known offsets stays laid out as drawn. **Consequence:** `--rotate`
  turns an actor about its local origin, here profile `(0,0)`, not the brush's centre — a profile
  drawn away from `(0,0)` *swings through an arc* instead of turning in place.
- **The profile must be a simple ring.** Duplicate and collinear points are cleaned away silently
  (the engine drops them at build time anyway); a ring that crosses itself, touches itself, revisits
  a vertex, or encloses zero area is rejected with exit 2 naming the offending points — such a
  profile has no consistent inside, and the brush would be a self-intersecting solid (a guaranteed
  BSP defect).
- **Faces:** `Cap` at each end plus one `Side<k>` per profile edge, numbered in ring order — so
  `brush poly find --item Side0` selects "the face swept by my first profile edge". The numbering
  follows the *cleaned, counter-clockwise* ring: the same shape starting at a different vertex
  renumbers the sides.
- **Concave profiles are fully supported, as ONE brush.** The engine's polygon must be convex and
  holds at most 16 vertices, so a concave profile (an L, a notched cornice) or one longer than 16
  points has each of its two **caps tiled into several convex faces** — the brush itself stays
  single and non-convex, like `brush build staircase`. The tiling only adds *diagonals* of your
  profile, never a new point on its outline, so the solid stays watertight. Face count is
  therefore `points + 2 × cap-pieces`. **Native caveat:** UnrealEd (the default `level
  materialize`) and the real engine (the default `level preview --game`) build a concave brush
  correctly, but the offline draft renderer `level preview --native` assumes convex solids, so it
  draws a concave notch *filled in* — that is a preview artefact, not a geometry bug.

### `revolve` — sweep a profile around an axis

Same profile, same `--axis`, same `--at`; instead of a straight `--depth` it sweeps the profile
**around the profile plane's own `V` axis** — the line `U = 0`, through profile coordinate `(0,0)`.
So `--at` is the world position of the **bend centre**, and how far the shape sits from it is written
in the profile: a profile drawn at `U ∈ [64, 192]` revolves at radii 64 to 192. (Hence no `--pivot`
flag — moving the profile and moving the axis are the same operation.)

```bash
# a 90° curved corridor, 128 uu wide and tall, bending around the world origin
uedcli brush build revolve --axis x --angle 16384 --csg subtract --solidity semisolid \
  --point 64,0 --point 192,0 --point 192,128 --point 64,128 \
  --at 0,0,0 --folder castle.corridor | uedcli actor add -
```

- **`--angle UU`** is the total sweep in **unreal rotation units**, the same units as `--rotate`:
  `16384` = 90°, `65536` = a full turn. It must satisfy `0 < angle <= 65536`. Thirds are not
  exactly representable (`65536` is a power of two), so a 60° bend is `--angle 10923` = 60.002°.
- **`--segments N`** is how many flat facets the sweep is cut into. Default is **one facet per
  22.5°** — 4 for a 90° bend, 16 for a full turn, matching UnrealEd's density. A facet of 180° or
  more is flat (zero volume) and is rejected.
- **`--angle 65536` is a CLOSED turn:** the two caps would coincide, so both are omitted and the
  last facet's far ring is the first facet's near ring. It needs at least 3 segments.
- **The profile must sit strictly on the positive-`U` side of the axis** — every point's `U` > 0.
  A profile straddling the axis would sweep into a self-intersecting solid; one merely touching it
  would collapse the faces along the axis to zero width. To bulge the other way, mirror the
  profile's `U` values. (Solids of revolution, which need the touching case, are not supported.)
- **Faces:** a tiled `Cap` at each end (absent on a full turn) plus `points × segments` swept
  quads. Every quad of profile edge `k` is `Side<k>` **in every segment**, so
  `brush poly find --item Side0` selects the whole strip swept by your first profile edge ("the inner
  wall of the corridor").
- **A revolve is off the integer grid by construction** (every vertex away from `θ=0` lands on
  `radius · cos/sin θ`), and uedcli never snaps coordinates. An off-grid **solid** brush throws its
  BSP partition planes off-grid too, the primary cause of slivers, T-junctions and holes in the built
  map. Prefer **`--solidity semisolid`** where the swept shape is detail rather than structure: a
  semisolid receives cuts but emits no world-splitting planes.

**Two stderr advisories** fire on `extrude`/`revolve` (never on stdout, never changing exit status —
the brush is emitted either way):

- when the emitted brush has **off-grid vertices AND is solid** (the case above; not on a
  semisolid/nonsolid brush, where it is already handled, nor a `--mover-class` brush, which never
  partitions the world);
- when it has **more than 64 faces** — `points × segments` grows fast, and every face is BSP nodes
  and rendering cost. Use a simpler profile, fewer `--segments`, or `--solidity semisolid`.

## `actor build <Package.ClassName>`

Writes a point-actor T3D for the given class. The class must be fully qualified; a bare name (no `.`)
is rejected.

```
actor build <Package.Class> [--at X,Y,Z] [--base-name NAME] [--prop KEY[.PATH]=VALUE …] [--rotate PITCH,YAW,ROLL]
```

- `--at` sets `Location` (default origin).
- `--base-name` is the stem for the emitted Name (default: the bare class name, e.g. `Light`).
- `--prop KEY[.PATH]=VALUE` (repeatable) bakes a property, **schema-validated against the class**
  (unknown key / bad enum / out-of-bounds index → exit 2; needs the game `.u`). A `Location` token
  routes to the typed field, overriding `--at`.
- `--rotate PITCH,YAW,ROLL` (unreal rotation units — 16384 = 90°) SETS `Rotation` absolutely — shorthand for
  `--prop Rotation=PITCH,YAW,ROLL`. `--rotate 0,0,0` **writes** `Rotation=(Pitch=0,Yaw=0,Roll=0)`
  (an omitted `Rotation` means "the class default", which is not zero for every class); omit the
  flag entirely to emit no `Rotation` line.

```bash
uedcli actor build Engine.Light --at 1000,2000,128 --prop LightBrightness=80 | uedcli actor add -
```

---

# Movers — animated brush actors (doors / lifts / gears)

A **mover** is a brush actor that animates between **keyframes** (poses). uedcli authors them
model-side: a generator builds the base mover, then `mover key` verbs author its keyframes. Key 0 is
the **base pose** (the ordinary `Location`/`Rotation`); keys 1..`NumKeys`-1 are stored as offsets
from base. A mover has **2..8 keys** (`NumKeys` — the KeyPos/KeyRot arrays are a fixed `[8]`).

The workflow is **raise the count, then edit the keys** (mirroring the editor): `mover key count`
sets how many keys exist; `mover key move`/`rotate` edit an existing key by index (never growing the
count).

```bash
# 1. build the base mover (no CsgOper — a mover is out of world CSG) and add it
uedcli brush build cube --width 128 --breadth 16 --height 256 \
    --mover-class DeusEx.ElevatorMover --at 512,0,0 | uedcli actor add -

# 2. raise the waypoint count, then author each key's pose
uedcli mover key count  ElevatorMover0                      # print the current NumKeys
uedcli mover key count  ElevatorMover0 4                    # a 4-stop elevator (2..8)
uedcli mover key move   ElevatorMover0 1 --from-base --to 0,0,256   # key 1: 256uu above base
uedcli mover key move   ElevatorMover0 2 --from-world --to 512,0,512  # key 2: an absolute world pose
uedcli mover key rotate ElevatorMover0 3 --from-base --to 0,16384,0  # key 3: yaw 90° off base

# 3. inspect / nudge / remove keys
uedcli mover key list   ElevatorMover0 [--json]             # world pose + offset per key
uedcli mover key move   ElevatorMover0 1 --by 0,0,-16       # nudge the current offset (no frame)
uedcli mover key rotate ElevatorMover0 3 --by 0,8192,0
uedcli mover key remove ElevatorMover0 1                    # delete + compact indices (NumKeys--)
```

- **What counts as a mover is the CLASS HIERARCHY, not the class name.** `mover key` accepts any
  actor whose class is `Engine.Mover` or descends from it — including subclasses whose name does not
  end in `Mover` (`CaroneElevatorSet.CaroneElevator`, `CaroneElevatorSet.CEDoor`,
  `DeusEx.BreakableGlass`, `DeusEx.BreakableWall`) — and, symmetrically, a class that merely ends in
  `Mover` without descending from it is not one. A rejection says which class failed and against
  what: `mover key count: Wall0 is not a Mover (class Engine.Brush does not descend from
  Engine.Mover)`. Resolving the hierarchy reads the game's `.u` packages, so `mover key` needs a
  project + `~/.uedcli/config.toml` (see [Projects](#projects-uedclitoml)).
- **`--mover-class <Package.Name>`** (on `brush build`) must be fully qualified. It **rejects
  `--csg`/`--solidity`** (a mover carries neither); `--at`/`--texture`/`--group`/`--base-name` apply
  normally.
- **`mover key count <name> [<n>]`** gets (no `n`) or sets (`n` in 2..8) `NumKeys`. Setting is
  **non-destructive** — it only changes the count; lowering it leaves the now-inactive keys' offsets
  dormant, so raising it again restores them. Out of range is a clean error naming the value. It is
  **exactly equivalent to `actor prop set <name> NumKeys=<n>`** (`NumKeys` is a first-class settable
  prop; `KeyPos`/`KeyRot`/`KeyNum` remain `mover key`-only).
- **`mover key move`/`rotate <index>` are edit-only** (`1 <= index < NumKeys`); they do NOT grow
  `NumKeys` — raise it first with `mover key count`. Index 0 is the base pose (edit it with `actor
  move`/`actor rotate`, which rigidly shift/rotate the whole animation).
  - **`--to` requires a coordinate frame:** `--from-base` (the coords are the offset from the base
    pose, written straight in) or `--from-world` (absolute world; uedcli subtracts the base). Passing
    `--to` with no frame is an error — there is no silent default.
  - **`--by DX,DY,DZ`** nudges the *current* offset and is frame-agnostic (it rejects
    `--from-base`/`--from-world`).
  - *Tilted-base caveat:* the rotation math is per-component FRotator arithmetic, geometrically naive
    for a non-cardinal base `Rotation` — for a tilted base, `--from-world` and `--from-base` are not a
    simple additive re-basing.
- **`mover key list --json`** emits `{idx, world_pos, world_rot, off_pos, off_rot, base}` per key.
- Mover config props (`MoveTime`/`DelayTime`/`StayOpenTime`/`OtherTime` timing, the
  `MoverGlideType`/`MoverEncroachType`/`BumpType` behavior enums, `Tag`/`Event`, return-group leader)
  are plain scalars — set them with `actor prop` or the generator's `--prop`, not the `mover key`
  family.

---

# `brush intersect` / `brush deintersect` — CSG-merge a brush SET into one brush

Two **generators** that take their shape from a piped brush set instead of parameters: they read a
T3D brush set on **stdin** (`-`) and write **one** brush (or Mover) actor T3D to stdout. Model-side
and instant — no editor, no container. (They need the game's `.u` packages: a Mover in the piped set
is refused, a class-hierarchy question — see [Projects](#projects-uedclitoml).)

```
brush intersect   - [<brush build output flags>] [--origin …] [--pivot …]
brush deintersect - [<brush build output flags>] [--origin …] [--pivot …]
```

They differ only in the background the set is merged against:

| verb | background | the set's role | result | needs |
|---------------|--------------|---------------------------------------------|-------------------------------------------|-------------------|
| `intersect`   | **empty**    | additives make solid, subtractives carve it  | the resulting **solid**, welded into one brush | ≥1 additive brush |
| `deintersect` | **solid**    | subtractives carve **voids** out of solid    | the **void** as a solid — the "negative"/plug  | ≥1 subtractive brush |

So `intersect` welds a cluster: an additive block with a subtractive notch becomes one brush shaped
like block-minus-notch. `deintersect` gives the solid that exactly fills what the set carves — the
door **plug** that fits a subtracted doorway, which is why it pairs with `--mover-class`.

```bash
uedcli actor find --folder castle.door | uedcli actor show - | uedcli brush intersect - | uedcli actor add -
uedcli stash show arch                 | uedcli brush deintersect -                     > plug.t3d
uedcli prefab show archway             | uedcli brush intersect -                       | uedcli actor add -
```

Every tier feeds them through its own `show` verb — which is why there are no `stash`/`prefab`
intersect verbs.

## Input rules

- **Stdin order IS the CSG order**, never re-sorted. A mixed add/subtract set is order-dependent
  (the last operation on a region wins): `add block, subtract notch` carves the block, the reverse
  order subtracts into empty space and leaves the block whole. You control order through the pipe.
- **Empty stdin is a clean no-op** (exit 0), like every generator.
- **Non-brush actors and Movers are refused** (exit 2, naming them) rather than skipped — a merge
  quietly missing a piece reads as a complete answer. Narrow the pipe (`actor find --kind brush …`).
- **Scaled, mirrored, and sheared source brushes build** — the transform is baked into the CSG
  input. Only a **non-invertible (degenerate) scale** (a zero or sub-epsilon axis) is refused, exit 2
  naming the brush.

## Output flags

They accept the same output-shaping flags as `brush build` — `--csg`, `--solidity`, `--texture`,
`--mover-class`, `--prop`, `--rotate`, `--base-name`, `--folder`, `--label` — with **two
verb-specific defaults**:

- **`--at` defaults to *keep the carved position*** (not the origin): omitted, the result stays
  where the set carved it.
- **`--solidity` defaults to the *faithful per-face rule***: a result face **keeps the solidity of
  the additive it came from**, and a face from a subtractive is forced solid. A **semisolid**
  additive yields semisolid faces — which **still block** (a semisolid face has the same collision as
  solid; only *nonsolid* is walk-through), so a semisolid-paned door is fine. The gotcha is a
  **nonsolid** additive: its faces come out walk-through — pass **`--solidity solid`** to scrub the
  per-face bits to plain solid. **`--solidity` is INVALID with `--mover-class`** (every value,
  `solid` included): a mover always keeps the source per-face solidity, so there is nothing to override.

## Placement — `--origin` and `--pivot`

A brush's world geometry is `world = Location + R·(vertex − PrePivot)`, so it is moved by `Location`
and rotates about `PrePivot`. The raw CSG output has `Location=(0,0,0)` and world-space vertices,
which would make a mover rotate about the *world origin*. So the result is **re-centred**:

- **`--origin center|min|max|X,Y,Z|keep`** — where the result's local origin sits. Default
  `center`. `keep` emits the raw faithful form (`Location=0`, world vertices) for diffing against
  an editor export; it rejects `--at` and `--pivot`.
- **`--pivot center|min|max|X,Y,Z`** — the world point the result rotates about, written as
  `PrePivot`. Defaults to the `--origin` anchor.
- **`--at X,Y,Z`** places the result so its **pivot** lands there.

World position is preserved by construction in every combination.

## What it refuses

The merge is faithful or it fails — it never returns a partial weld:

- a **non-brush actor or a Mover** in the piped set (exit 2, naming it) — narrow the pipe with
  `actor find --kind brush`;
- a **non-invertible (degenerate) source brush** — a zero or sub-epsilon scale axis (exit 2, naming it);
- a set with **no additive** (`intersect`) or **no subtractive** (`deintersect`), pointing you at
  the other verb;
- a **name list** on stdin instead of a T3D snippet (the two stdin conventions are easy to mix up).

Empty stdin is the one silent case: a clean no-op, exit 0, like every generator.

## Disjoint results

A set can merge into several disconnected solids (two far-apart clusters). They stay **one actor**
(as in UnrealEd) and the verb says so on stderr with the component count. There is no `--split`: run
the verb per subset for independently movable pieces — the input is a set, so that is already a
natural pipe.

## The door-mover flow

```bash
uedcli actor find --folder castle.door | uedcli actor show - \
  | uedcli brush deintersect - --mover-class Engine.Mover \
        --pivot min --at 4096,2048,128 \
  | uedcli actor add -
uedcli mover key count Mover0 2
uedcli mover key rotate Mover0 1 --by 0,16384,0        # swings about the hinge, not the centre
```

---

# `actor preview` — the brush viewer

A self-rendered **colour** image (no editor) so you can see geometry and map **poly index ↔
face**. Reads named actors from the current level, model-side. **`--faces`** picks how faces are drawn:
`wire` (the default) is a content-free schematic of outlines; `textured` is the **CSG-solved textured
world**, as UnrealEd's 3D viewport draws it. (Renamed from `brush preview`; `stash preview`/`prefab
preview` keep their names.)

```
actor preview [<names…> | --from-t3d <FILE…|->]
              [--layout quad|single|breakdown] [--view top|front|side|iso]
              [--faces wire|textured]
              [--brush-colors csg|legend] [--annotate SELECTORS]
              [--frame BRUSH[:IDX] | X0,Y0,Z0,X1,Y1,Z1] [--frame-tightness N]
              [--highlight POLY|NAME ...] [--focus BRUSH]
              [--show collision,light-range,sound-range]
              [--iso-angle 30] [--size 1024] [--locator-cells 12 | --no-locator-cells] [--grid-size N]
              [--json] [--out PATH]
```

- **Target set** — actor names, or `-` to read a newline name list from stdin (`actor find … | actor
  preview -`), or **`--from-t3d <FILE…|->`** to render the actors in one-or-more T3D files (or a `-`
  stdin snippet: `brush build spiral | actor preview --from-t3d -`). Multiple files concatenate in
  order; `-` is the sole value. `--from-t3d` is mutually exclusive with names. Giving no target set
  at all (no names, no `-`, no `--from-t3d`) is an error (exit 2); an empty `-` stdin stays a clean
  no-op (exit 0).
- **`--layout {quad,single,breakdown}`** (default `quad`) picks the pane layout. **`quad`** is the
  UED-style 2×2 grid (Top / Front / Iso / Side). **`single`** renders one `--view`. **`breakdown`** is
  described next.
- **`--layout breakdown`** renders a near-square **grid** of panes that walks the scene **actor by
  actor**. Pane 0 is the whole scene in CSG colour — a plain spatial **map** with **no labels** (no
  legend, no names, no on-face numbers); you identify each actor from its own captioned pane below. Each
  following pane is **one actor**: a **brush** is `--focus`ed and zoomed to its own AABB with all its
  faces numbered; a **point actor** is zoomed to a box around its Location with its marker/sprite drawn
  (no face numbers — a point has none). Every pane is captioned with the actor name. Panes follow the
  actor-set order (brushes and point actors intermixed) and are square cells laid out in
  `ceil(sqrt(N))` columns (near-square, slightly wider than tall). One view (uses `--view`); composes
  with `--annotate` (the per-brush number set), `--brush-colors`, `--highlight` (a highlighted poly
  re-lights in every pane), `--show`, `--size`. It sets its own focus and zoom per pane, so
  **`--focus`/`--frame` are ignored** under it. Brush + point-actor counts are reported on stderr;
  breakdown is a small-selection inspector (it warns past ~16 panes — a whole level makes an unusably
  large grid, and point actors add panes too, so subset first).
- **`--faces {wire,textured}`** picks how faces are drawn.
  - **`wire`** (default) draws outlines only — the schematic, CSG-coloured (added blue, subtracted gold,
    …). It needs no game content at all and works on `--from-t3d` from anywhere.
  - **`textured`** is the **CSG-solved textured world**, exactly what UnrealEd's 3D viewport shows: the
    set is run through the native CSG **solve** and only the surfaces that **survive** are drawn, each
    filled by **sampling its own texture** through the face's authored UV frame
    (`Origin`/`TextureU`/`TextureV`/`Pan`), with **no wireframe**. Because it is a real solve, an
    additive brush that is **not inside subtracted (empty) space is invisible** — visibility is spatial
    containment, not a per-brush rule — and a subtracted **room shows its interior** (its camera-facing
    near walls are dropped, so you see in) instead of a solid box. Texture **alignment, panning and
    tiling** stay correct **across CSG splits**, so a wall cut by a doorway keeps one continuous texture.
  - It shades each face by a fixed key light (no scene lighting), picks a mip level per face from how
    densely the texture lands on screen, and honours a **masked** texture's cut-out holes. A surviving
    surface with no `Texture` fills a neutral grey; that is normal, not an error.
  - **Movers** are excluded from the world solve (a mover carries no world `CsgOper`) and draw as a
    **magenta overlay** against the same depth buffer, so a mover behind a wall is hidden and one in
    front occludes. **Point actors** keep their sprite/marker overlay.
  - **`textured` reads the game's class hierarchy** (to tell a mover from a world brush), so unlike
    `wire` it needs **both a resolved project and the per-user games config**, plus **every texture a
    surviving surface references to be readable** — miss one and it exits 2 naming the ref (a bare
    `Texture=Name` is rejected; qualify it as `Package.Name`). A scene that references no texture needs
    no texture source. It also **rejects `--brush-colors`** (it samples real textures) and any **scaled
    or sheared brush** (its UV frame is rotation-only) — both a clean exit 2; use `wire` for those.
  - A solve that leaves **no surface** (e.g. adds with nothing to carve empty space around them) is a
    clean exit 2 naming the cause; a set of only point actors and/or movers (no world brushes) draws its
    overlays over the dark background at exit 0. `textured` composes with every other option here — `--focus`,
    `--highlight` (its vivid outline is the only line art it keeps) and `--layout breakdown` included.
- **Brushes are coloured by CSG op** (UnrealEd's legend): added-solid **blue**, subtracted
  **gold/yellow**, semi-solid **pink**, non-solid **green**, mover **magenta**; front and
  obscured/back faces draw in the same shade (facing-blind). This says what each brush *does*.
- **`--brush-colors {csg,legend}`** picks the colour source for the `--faces wire` wireframe.
  `csg` (default) is the CSG-op colouring above. **`legend`** instead draws each brush in *its own
  per-actor tint* — every brush a distinct colour (you trade the CSG cue for telling same-op brushes
  apart at a glance). It has no meaning under `--faces textured`, which colours nothing from it, so
  passing it there is a clean exit 2.
- **Labels use a HYBRID per-actor TINT.** The CSG palette has only ~5 hues, so two brushes with the
  SAME CSG op share ONE wireframe colour; to tell them apart, each **actor** is assigned a distinct
  **tint** from a categorical palette (~10 hues, cycled). A brush's **on-face poly-index decal** (the
  painted digits and their 6/9 baseline underline) carries that tint; a point actor's **marker** is
  drawn in it — so a number shared across brushes (every brush has a face `1`) is disambiguated by its
  tint. **Actor names are not drawn on the preview**; identify each actor from its locator cell
  reported on stderr (below).
- **Poly face indices are painted ON the face (on-face numbers).** Each face's index is a **number
  texture lying flat in the face's own 3-D plane** — it foreshortens with the surface under the
  projection, so it reads as decaled onto the geometry. It is placed at the **roomiest spot on the
  face** (the largest spot where it fits *inside* the face polygon — off to a side on a triangle/arch,
  not centred over a narrow point) and sized to **75% of the largest number that would fit there**.
  Sizing always assumes a **2-digit width** and centres the actual number in that slot, so a single
  digit (`5`) renders at the same scale as a two-digit one (`12`) rather than ballooning. Numbers
  **hang by gravity** on walls and slopes (strokes run straight up the surface) and align to the
  **world Y axis** on floors/ceilings/caps, with a short underline as a `6`/`9` cue. This is the only
  way poly faces are labelled — there is no leader-box mode.
- **Overlapping numbers: a tiny nudge, then a white outline.** Two faces can project close together on
  screen — including two faces of the **same brush** — so numbers can overlap. First, a **tiny
  reshuffle**: a number overlapping another (or a point-actor marker) may **shrink by at most 10%**
  and **move by at most 10% of its own diagonal**; it never makes a big jump or shrinks to a speck. A
  number with no overlap doesn't move. Second, wherever two numbers still overlap, a thin **white
  outline (1 screen pixel, constant width at any zoom)** is drawn just outside the strokes in the
  overlap, so you can trace each number apart. Numbering is **facing-blind**: front AND back faces get
  a number (the front/back distinction is carried by opacity, below, not by hiding back faces), and
  `--annotate`'s `poly` selectors still choose *whether* poly numbers draw at all (e.g. `none`,
  `poly:hi`). (Under `--layout breakdown` each brush is alone in its pane, so cross-brush overlap
  disappears and the outline only marks the occasional same-brush overlap.)
- **On-face numbers are graded translucent by depth.** A visible face is drawn at 56% opacity, and each
  face in front of it keeps 60% of that (near faces clear, buried faces faint), so the nearer faces'
  numbers stand out. A face counts as "in front" under the **self-or-solid** rule: a nearer front face
  that covers it dims it **iff** that occluder is a **solid** CSG op (added/semi-solid/mover) **or**
  belongs to the **same brush**. So a hollow room's near walls dim its own far walls, while a solid
  brush sitting **inside** a room is **not** dimmed by the room's walls; solid brushes still dim across
  brushes. A number **unreadable on screen** is omitted — a **view-dependent** verdict: a face too
  small, too edge-on, or too zoomed-out gets no number, and the same face is numbered once it's big
  enough (zoomed in, or in its `--layout breakdown` pane). There is no fallback for an omitted face.
  Under **`--faces textured`** the fills are opaque but the numbers are not hidden by them: a face you
  cannot see still shows its index, at 60% of a visible face's opacity, so a number can sit on a wall
  in front of the face it belongs to. Read indices off `--faces wire`, or pass `--annotate none` for a
  clean filled picture.
- **`--annotate`** takes a **comma-set of `poly` selectors** (the drawn numbers are their **union**).
  Bare **`poly`** means every face index; each colon **filter** narrows; multiple filters on one
  selector intersect; commas union. Tokens are case/whitespace-insensitive. **Actor names are never
  drawn** — locate a brush by its locator cell (printed on stderr, below).
  - `poly` filters: **`vis`** (retained as an inert alias of bare `poly` — see the note below),
    **`hi`** (highlighted faces only). (`highlighted` is accepted as a synonym for `hi`.)
  - Examples: `poly:vis` = every face (same as bare `poly`); `poly:hi` = highlighted faces only.
  - Whole-value keywords (stand alone): **`none`** = nothing; **`all`** = `poly`;
    **`highlighted`** = `poly:hi`.
  - **Default:** `poly:vis,poly:hi` — face indices (painted on-face). (On-face
    numbering is facing-blind, so `poly:vis` — now an inert alias of bare `poly` — numbers every face;
    opacity, not presence, is the front/back cue. `vis` is kept only so pre-facing-blind specs still
    parse.)
  - An invalid token is a clean named error (e.g. `--annotate: unknown filter 'foo' for kind 'poly'`).
- **Point actors** render as their **DT_Sprite** billboard (footprint `DrawScale·USize × DrawScale·
  VSize`) or, for DT_Mesh/DT_None (or a sprite that does not decode), a small **marker** (a filled
  diamond in the actor's tint, with a white halo) at Location. A sprite that does not decode prints a
  stderr note **naming why** — `unknown-texture` (nothing of that name on the search path),
  `unqualified-ref` (write it as `Package.Name`), `unverified-format` (a real texture in a pixel
  layout uedcli cannot read yet), and so on. With **no texture search path configured**, the note says
  so instead of naming a case — run `project show` to see what is on the path. Its **name is not
  drawn**; find it by the locator cell reported on stderr.
- **`--frame TARGET`** frames a target to fill the view (frames only — never highlights), in one of two
  forms. A **selector** — a bare **`BRUSH`** name frames that actor's whole AABB, or **`BRUSH:IDX`**
  frames ONE poly (a multi-index / `:all` value is an error). OR an **explicit world AABB** — six
  comma-separated numbers **`X0,Y0,Z0,X1,Y1,Z1`**, framed **exactly** (+ a small margin). **`--frame-
  tightness N`** (default `0.8`, must be in `[0, 1]`) sets framing tightness toward a **selector**
  target only: `0` = whole-set frame, `1` = tightest (target + margin); no `--frame` ⇒ no-op. An
  explicit-AABB `--frame` is always framed exactly — `--frame-tightness` does NOT modulate it.
- **`--highlight POLY|NAME`** emphasises a poly or actor; repeatable, no effect on framing. A token
  **with a colon** is a poly selector `BRUSH:IDX` (set form `BRUSH:1,2` / `BRUSH:all` too) — those
  polys draw with a **bolder line** in their brush's vivid CSG hue. Under `--faces textured` a
  highlighted face keeps its texture and takes only that vivid outline. A token **without a colon** is an
  **actor name**: a brush actor highlights **all** its polys; a point actor gets **corner brackets**
  (a selection reticle) framing its sprite/marker. An unknown name / a selector on a non-brush → clean
  exit 2. Under a filled mode a highlight re-colours **what is visible** and never x-rays: a
  highlighted face that something in front of it hides shows nothing, and a **stderr note** names any
  selector that landed on nothing visible for any reason (hidden, culled, invisible, or off-frame) —
  under `--layout quad` that means no pane showed it.
- **`--focus BRUSH`** spotlights ONE brush: only it shows face indices (in its tint), and every OTHER
  brush recedes — for reading one brush's faces in a busy scene. Under `--faces wire` those brushes
  recede to a **faint (dimmed)** wireframe; under `--faces textured` their solved **fills** fade too, to
  a faint wash of their own colour. **`--focus` changes brightness only — never what is visible or what
  hides what**, so the picture stays physically honest either way: a crate inside a subtracted room stands in
  front of the room's far wall, a brush between the camera and the focused one still covers it, and a
  brush sealed inside a solid *added* brush stays hidden.
  **`--highlight` overrides `--focus`'s dimming**: a highlighted poly/actor draws at full strength and
  keeps its index even when its brush is not the focus. It does **not** override depth — a highlighted
  face something hides is still hidden (focus dims; highlight re-lights what is visible).
  An unknown name / a point actor → clean exit 2.
- **`--show SET`** is a **comma-set (union)** of range overlays for **POINT** actors (default: none).
  Members: **`collision`** — a faint light-red collision cylinder for every colliding point actor
  (`bCollideActors`): a circle in TOP, a `2·CollisionRadius × 2·CollisionHeight` rect in FRONT/SIDE, an
  8-sided wire cylinder in ISO (`CollisionHeight` is a HALF-height); **`light-range`** — a faint orange
  sphere of a light's reach (`25·(LightRadius+1)` UU); **`sound-range`** — a faint blue sphere of an
  AmbientSound's reach (`25·(SoundRadius+1)` UU). Brush actors (including movers) are excluded, so a
  brush preview needs no class schema. An unknown member is a clean named error.
- **Locator cells are drawn on every preview by default** — a **label gutter** with columns `A,B,C…`
  across the top and rows `1,2,3…` down both sides (no gridlines), so every region of the image has a
  text address like `D4` (a letter is always a column, a number always a row). It is **on by default**
  and orthogonal to `--annotate`, so `--annotate none` still carries the gutter. Each actor's cell is
  reported as a **legend on stderr**: a density header, then one line per actor — `Pillar  D4  (C3–E5)`
  (the centroid cell, plus the covered range in parens) under `single`/`breakdown`, or pane-qualified
  `Pillar  Top:D4 Front:B7 Side:C7 Iso:E5` under `quad`. An actor that draws no pixel (e.g. one hidden
  behind solid geometry under `--faces textured`) still gets a cell, flagged `(hidden)`. Two actors in
  the same cell each keep their own line. **The address is a region of the image/projection, never a
  world coordinate** — carry a cell back into a name set with `actor find`.
- **`--locator-cells N`** (default `12`) sets the density: `N` columns × `N` rows. Must be in `[1, 52]`
  (else a clean exit 2 naming the value). Under `breakdown` the locator + legend ride pane 0 (the
  whole-scene pane) only. **`--no-locator-cells`** turns the whole feature off — gutter, stderr legend
  and the `--json` cell data together — and gives the geometry the wider drawable rect back. The two
  flags are mutually exclusive (a clean exit 2 naming both if given together).
- **Every orthographic pane** (`top`/`front`/`side`) **carries a world-space gridline overlay** —
  a ruler for scale and position, ported from UnrealEd's own 2D-viewport grid — **whether or not
  `--grid-size` is given**; the flag only overrides the spacing it picks automatically. **`iso` never
  gets one** (its screen axes mix world axes, so a world lattice would not be a ruler there); giving
  `--grid-size` together with `--view iso` under `single`/`breakdown` is a clean exit 2 (`quad` always
  renders the ortho panes regardless of `--view`, so it is unaffected). Two tiers: a **minor** line
  every step and a **major** line every 8th, both drawn as neutral greys never confused with the CSG
  palette. **`--grid-size N`** sets the minor spacing in world units and must be a **power of two >= 1**
  (else a clean exit 2 naming the value); without it, each pane picks its own step — the largest power
  of two `<= span/16` of that pane's own framed world extent, landing 16-32 minor divisions across the
  pane at any zoom, so the grid reads as a ruler rather than a lone crosshair. A spacing too fine for
  the pane **escalates** to a coarser one instead of erroring (matching the editor; the auto step never
  needs this — it already clears the density threshold); one too coarse to show any line at all draws
  nothing (exit 0) — the stderr report (below) always names the step, so neither substitution is
  silent. **Nothing about the grid is drawn into the image beyond the lattice itself** — no caption, no
  legend; every gridded pane instead gets **one line printed to stderr**: the framed world extent in
  the pane's own two axes, plus `set` (the step asked for — explicit `--grid-size` or the auto default)
  and `visible` (`set` after escalation, what is actually on screen — equal to `set` on every default
  render, differing only when an explicit `--grid-size` escalated), e.g. `X -1024..2048  Y -512..1536
  grid set 32, visible 64`. Pane-qualified under `quad`/`breakdown` (`Top: X -1024..2048  Y -512..1536
  grid set 32, visible 64`), unqualified under `single`; printed unconditionally, independent of
  `--locator-cells`/`--json`. (Major-tier spacing is deliberately not reported — the tier test is on the
  pre-escalation step, so it is pinned to `8 * set` world units, not `8 * visible`, and a caption
  printing the latter reads wrong once escalated.) Under `quad`/`breakdown`, each pane frames (and so
  may escalate) independently, so panes can report different steps. The grid is a backdrop: it never
  covers geometry, is never dimmed by `--focus`, and is unaffected by `--faces`.
- **`--json`** prints a JSON object to stdout **instead of** the bare image path. With locator cells on
  (the default), it is the machine form of the legend:
  `{image, locator:{cols,rows}, actors:{<name>:{panes:{<Pane>:{cell,span}}, hidden}}}`, pane-keyed for
  every layout (a `single` render has one pane keyed by its `--view`). With `--no-locator-cells`, the
  addressing drops out but `hidden` stays a real answer: `{image, actors:{<name>:{hidden}}}` — no
  `locator` key, no `panes`/`cell`/`span`. The stderr legend is unchanged (and likewise absent with
  `--no-locator-cells`).
- `--out PATH` is the host image path. **A preview is always a PNG** (written via **Pillow**, the
  LLM-viewable form — no flag and no other way to get raw PPM out). Whatever extension you pass is
  **replaced** by `.png`, so `--out shot.jpg` writes `shot.png` and `--out shot` writes `shot.png`.
  `--out` is **optional**: with no `--out`, a unique temp file is minted (`uedcli-preview-*.png`).
  Either way, unless `--json` is given, the **absolute path actually written is printed to stdout**.

---

# `stash` / `prefab` — capture, place, and share actor sets

A **stash** is a private, machine-local register entry (a named, captured actor set living in
`.uedcli/stash/<id>/`). A **prefab** is the durable, git-tracked, shareable form under the library
root (`<prefabs-dir>/<name>/`). A stash, a prefab, and a level trunk are the **SAME on-disk format** —
the per-actor T3D tree `actors/<name>/{actor.t3d, order_value[, folder]}` — read/written through one
shared code path, with any per-box extras (`meta.json` capture anchor, `packages` deps) beside
`actors/`. Both carry the set's texture-package deps and each member's folder.

## Stash

```
stash capture [- [<names…>] | <names…>] [--id ID] [--force] [--from-t3d <FILE…>]
stash show    <id> [<names…>] [--summary]        # T3D dump (default), or a bbox/class/poly summary
stash list                                        # register ids
stash preview <id> [<names…>] <preview opts>      # composite render (like actor preview)
stash drop    <id>
stash apply   <id> [--at X,Y,Z] [--group NAME | --no-group] [--folder PATH]
stash promote <id> --as <name> [--force] [--prefab-dir DIR]
```

- **`stash capture`** takes actors from the current level (empty names = all), from one-or-more T3D
  files via **`--from-t3d <FILE…>`** (multiple concatenate), or from a **`-` stdin T3D snippet**
  (`brush build cube | stash capture -`). A leading `-` reads the T3D from stdin as the source; any
  remaining names still select a subset. `-` is mutually exclusive with `--from-t3d` and `--tree`
  (each names a source); empty/whitespace-only stdin exits 2. `--id` defaults to an
  auto-slug from the first actor name; `--force` overwrites an existing id. Capture normalizes the set
  to its bbox-min corner and records the original world anchor. It reads the game's `.u` packages
  (an ingested Mover is folded to its base pose, needing the class hierarchy — see
  [Projects](#projects-uedclitoml)).
- **`stash apply`** is a **model-side merge into the current level** (no editor): it translates to
  the placement anchor, auto-allocates fresh names, sets Group, appends order, and unions the set's
  packages. **Without `--at`, it applies at the captured world anchor.** `--group` defaults to the id;
  `--no-group` strips it; `--folder PATH` also stamps a uedcli-side folder (independent of `--group`).
- **`stash promote`** copies a register entry into the durable prefab library (the sharing step).
- **CSG-combining a stash** is not a stash verb: pipe it into the generator —
  `uedcli stash show arch | uedcli brush intersect - | uedcli actor add -` (see
  [`brush intersect` / `brush deintersect`](#brush-intersect--brush-deintersect--csg-merge-a-brush-set-into-one-brush)).

## Prefab

The durable library. Its **reads are project-only** (they touch just the tracked dir); `apply`
mutates the current level. The library root is the resolved project's prefabs dir (the `uedcli.toml`
`prefabs` key, default `<root>/prefabs/`); override per-invocation with **`--prefab-dir DIR`**, placed
**before** the sub-verb (with the flag, no project is needed).

```
prefab [--prefab-dir DIR] list
prefab [--prefab-dir DIR] show  <name> [<names…>] [--summary]
prefab [--prefab-dir DIR] preview <name> [<names…>] <preview opts>
prefab [--prefab-dir DIR] apply <name> [--at X,Y,Z] [--group NAME | --no-group] [--folder PATH]
prefab [--prefab-dir DIR] drop  <name>
```

- **Unlike `stash apply`, `prefab apply` also defaults to the captured anchor** with no `--at`
  (`--at` overrides). `--group`/`--no-group`/`--folder` behave as in `stash apply`.

---

# `level import` — read an existing map file

**`level import`** goes the opposite way from `materialize`: it takes an already-compiled map file
(`.dx`/`.unr`) and turns it back into a T3D tree you can query, diff and edit with every ordinary
verb. Use it to study how an existing map is built, to lift a room or a prop out of one, or to
compare a map against your own.

It reads the map file's bytes **directly**. No UnrealEd, no container, no game — fast and works
anywhere, unlike `materialize`.

```
level import MAPFILE --tree KIND/NAME [--overwrite]
```

- **`MAPFILE`** is the compiled map to read, relative to the current directory. A file that is
  missing, unreadable, or not an Unreal package **exits 2** naming it.
- **`--tree KIND/NAME`** is the **destination, which import creates** — `level/NAME` writes a new
  level trunk at `maps/NAME/`, `stash/NAME` writes a new stash entry. `prefab/…` is refused: a
  prefab is a small reusable fragment, not a home for a whole level.
- **`--overwrite`** permits replacing an existing destination (default: refuse, exit 2). The check
  runs **before the map file is read**, so a refusal touches nothing. An existing but *empty* level
  directory does not count as existing, so retrying a failed import needs no flag.
- **Output:** the imported actor names go to **stdout**, one per line, so you can pipe them onward;
  the summary (how many actors, what was dropped) goes to **stderr**.

```
level import ~/DeusEx/Maps/02_NYC_Street.dx --tree level/nyc-study
export UEDCLI_LEVEL=nyc-study
actor find --subclass-of Engine.Light      # now query it like any other level
```

## What import leaves out

A saved map is the editor's workspace, not a clean inventory of level content — it also contains the
tools the designer happened to be holding. Import drops two kinds as apparatus rather than content:

- the **builder brush** — the red scratch shape used to sculpt geometry before committing it. Every
  saved map has exactly one. If kept, rebuilding the map later would place it alongside the fresh one
  the editor makes for itself, and the two would collide over a name.
- the **viewport cameras** — one `Camera` actor per editor viewport open at save time (four to eight
  in a typical map).

Everything else is imported as it stands, with its properties and brush geometry.

## Requirements and caveats

- **A project is required**, and its configured package paths must contain the classes the map uses.
  Import reads each class's definition to know what its stored properties mean, and each class's
  defaults to know which values were changed from them.
- **Import is strict.** Every class and every polygon texture the map references must exist on the
  package path; if one does not, the whole import **exits 2 naming it** rather than writing a tree
  with references that cannot be rebuilt. Importing a map that needs mod packages means installing
  those packages first.
- **Folders and labels start empty** — a compiled map has no equivalent to recover.
- **References between actors keep the source map's name.** A property pointing at another actor
  reads `Class'<sourcemap>.Other'` — a faithful record of the original, but pinned to the old map's
  name rather than rebinding to your new level's.
- **Resources embedded inside the map file itself are a rough edge.** Some maps store a texture or a
  sound *inside* the map file rather than referencing a shared package (the `myLevel` pseudo-package).
  Such a reference resolves to nothing on your package path: on a **brush face** it is caught by the
  validation above and the import **exits 2 naming it**; anywhere else — an actor property such as a
  decoration's `Skin` — it is **imported as written** and left dangling, since validation covers
  classes and face textures, not every object reference. A dangling reference does no harm until you
  rebuild the map, which will not find it. Extracting embedded resources into a real package first is
  the way round it, and is not yet built.
- **Maps built by uedcli's own native builder import without brush geometry**, because that builder
  keeps each shape only in the compiled world and leaves the per-brush copy empty. Editor-built maps
  (all retail content) carry both and import fully.

---

# `level reimport` — fold editor changes back into the trunk

**`level reimport`** is `level import`'s sibling for a level you already have in trunk: it decodes
a compiled map file the same way, but instead of creating a fresh tree it MATCHES actors by name
against the trunk you point it at, so actors it doesn't mention are left completely alone —
their body, their folder/label, and their CSG order.

Use it when you (or someone else) opened the level's materialized `.dx`/`.unr` directly in
UnrealEd — to do something uedcli can't yet express — and want those changes back in trunk without
losing history or metadata for everything you didn't touch. `level import --overwrite` also
replaces an existing level, but wholesale: every actor is rewritten fresh, folders/labels are lost,
and the diff touches the entire level regardless of how small the real edit was. `level reimport`
is the targeted alternative.

```
level reimport MAPFILE --tree level/NAME [--force]
```

- **`MAPFILE`** is the compiled map to read — same rules as `level import`.
- **`--tree level/NAME`** names the level to reimport INTO, and it must already exist (the
  opposite of `level import`'s create-only destination) — use `level import` first if it doesn't.
  Defaults to the level named by `$UEDCLI_LEVEL`, like an ordinary content verb.
- **Matching is by actor name.** An actor present in both the trunk and the map is updated in
  place; one only in the map is added; one only in the trunk is deleted — including an actor added
  to the trunk after the materialize that produced MAPFILE (by another session, or by hand):
  reimport only knows "in the map, or not", the same as `level import --overwrite`. A matched
  actor's folder/labels are carried over from the trunk unchanged, whether or not its body changed
  — the compiled map format carries neither. Every added actor gets one shared `reimport-<hex>`
  label, freshly minted per invocation, so `actor find --label reimport-<hex>` finds them for
  review afterward.
- **CSG order (`order_value`) is recomputed for brushes only** — point actors don't participate in
  CSG, so their order is never touched. A brush whose relative position among brushes didn't
  change keeps its exact `order_value` (no diff); a moved or newly added brush gets a freshly
  computed one.
- **`--force`** is required if the reimport would modify or delete more than 20% of the trunk's
  actors — a guard against reimporting the wrong file. Ordinary repositioning (`Location`/
  `Rotation` only) and pure additions never count toward that percentage.
- **Output:** the reimported level's actor names go to stdout, one per line; the summary (added/
  deleted/changed counts) goes to stderr.

```
export UEDCLI_LEVEL=nyc-study
level materialize --out /tmp/nyc-study.dx
# ... open /tmp/nyc-study.dx in UnrealEd, tweak something, save ...
level reimport /tmp/nyc-study.dx --tree level/nyc-study
```

Everything `level import`'s "What import leaves out" and "Requirements and caveats" sections say
about the decode itself — the dropped builder brush and viewport cameras, the strict class/texture
validation, folders and labels having no equivalent in a compiled map — applies here too.

---

# `level materialize` — build the map file

**`level materialize`** is the pure build step: it drives **UnrealEd** to compile the selected
level's T3D trunk into the `.dx`/`.unr` **build artifact** — map-file output only (the T3D tree is the
source, reached via git, not a build target).

```
level materialize [--out OUT] [--overwrite] [--no-verify] [--keep-build] [--no-bsp-check]
```

- **`--out OUT`** names the destination map file (`.dx` or `.unr`). It **refuses to overwrite an
  existing file** (exit 2) unless **`--overwrite`** is given.
- A **post-build verify** (H3) confirms the rebuilt map matches the intended trunk; **`--no-verify`**
  skips it (debugging / known-buggy verify), and **`--keep-build`** copies the built map to the
  project's `.uedcli/tmp/` on a verify FAILURE instead of discarding it.
- Before any editor work, materialize checks that every package the level **references** (via a
  qualified `Class=` or a face's `Texture=`) is present on the configured package path. If any is
  missing it **exits 2 naming the complete set** and writes nothing, rather than silently dropping
  those references. This gate runs even under `--no-verify`. A composed package path that resolves to
  **0 packages** prints one advisory line but does not block a level that references nothing.
- The verify compares the built map against the trunk in UnrealEd's own terms, so it needs each actor
  class's **defaults** out of the game's `.u` packages. They are resolved *before* the editor starts,
  so an actor whose `Class=` is not fully qualified (`Package.Class`) — or whose package is missing
  from the configured paths — **exits 2 in about a second**, naming the actor and class, instead of
  failing after a full build. `--no-verify` does not need them.
- After a successful build+save, materialize runs two **advisory BSP health checks** and prints any
  findings to **stderr** — the exit code stays **0** (these report on an already-good build; they
  never fail it). The **build-output** check parses UnrealEd's own rebuild warnings (dropped faces,
  unlinked T-junction sides, sliver nodes) into counts; the **built-model** check reads the saved map
  and locates a defect the static `level doctor` cannot: **invisible walls** (near-zero-area BSP
  nodes). A check that cannot run (editor wedged, unreadable map) prints one "skipped" line and
  the build still succeeds. **`--no-bsp-check`** turns both off.
- Committing is your own `git`. Lightmaps and rebuilt BSP are **regenerable build output**, never
  part of the level's identity.

*(A native, in-process Rust build is under development, targeting byte-identity with UnrealEd's build
of the same trunk; the editor path above remains the current one.)*

---

# `level preview` — freely-posed still shots

**`level preview`** renders **still first-person shots** of the current level from arbitrary camera
poses. A **two-tier** command behind one verb, sharing one batched **pose grammar**. Read-only — it
never writes the trunk or a committed map.

```
level preview SHOT… --out-dir DIR [--game | --native] [--size WxH] [--fov DEG]
              [--map PATH] [--rebuild] [--keep-alive]
level preview --list-actors Package.Class [--sample N] [--game --map PATH]   # discovery mode
```

## The pose grammar (SHOT tokens)

One shot per positional token, fields `;`-separated (angles in **unreal rotation units**: 16384 =
90°, 65536 = a full turn; append `;name:STEM` to name the output PNG, default `shot-01`, `shot-02`,
…):

- `at:X,Y,Z;rot:PITCH,YAW` — camera eye at a world point, aimed by angles (positive pitch looks up).
  **All angles (`rot`, `azimuth`, `elev`) are unreal rotation units: 16384 = 90°, 65536 = a full turn.**
- `at:X,Y,Z;look:X,Y,Z` — camera eye at a point, aimed AT another point.
- `at:@Actor;…` / `…;look:@Actor` / `orbit:@Actor;radius:R;azimuth:A[;elev:B]` — pose relative to a
  named actor (resolved against the trunk, or with `--game --map` against the **running game**).
  `orbit` places the camera on a ring of R uu around the actor, aimed inward.

## Backends

- **`--game` (the DEFAULT)** — the faithful lit tier. Delivers the map into a **warm per-user
  headless game container** (booted once ~90s, then REUSED across previews; self-terminates after
  10 min idle) and captures **truly-lit first-person frames** (real lighting/sky/textures). Pitch is
  clamped host-side to ±89.9°; movers render at rest pose. First batch ~1–3 min (boot + travel);
  later batches skip the boot. It is the default because it shows lighting/meshes/sky and the offline
  draft mis-renders overlapping-subtract geometry silently.
  - **Prerequisites.** Docker, and the game's own files on the composed package search path (its
    `System/` and content), configured under `~/.uedcli/config.toml` `[games.*].paths`. On a fresh
    machine, `dev/scripts/setup-game-preview.sh /path/to/DeusEx` (or `--url <installer>`, or no
    argument at all to use its built-in checksum-pinned default download) provisions the whole path
    in one command — the base image, the game files, the config, and a verify render; run it with
    `--help`. The image is built and the preview package compiled automatically on first use — **no
    UnrealEd/UCC toolchain to install** (the generic preview compiles its engine-only helper with
    the container's own UCC).
  - **`--map PATH`** previews a **prebuilt** map file instead of the selected trunk (skips the
    materialize cache); actor-relative shots resolve against the running game.
  - **`--rebuild`** forces a fresh materialize under a new unique name (guarantees the game reloads it).
  - **`--keep-alive`** PINs the warm container (disables idle death) and prints its **noVNC URL** for
    live inspection (dev-debug; release the pin with `docker rm -f`).
  - Without `--map`, this tier **materializes the trunk internally** — post-verify included, with no
    `--no-verify` escape — so it inherits `level materialize`'s requirement that every actor class be
    fully qualified and its package present on the search paths. An unresolvable class exits 2 naming
    the actor, before anything is built.
- **`--native`** — the opt-in offline draft. **No container at all**: the native CSG core carves the
  trunk in-process and a software rasterizer renders **textured, flat-shaded** perspective stills in
  seconds. Movers render at base pose; point actors, meshes, sky, lighting, and translucency do NOT
  render (translucent/masked faces render opaque). Scaled, mirrored, and sheared brushes render (the
  transform is baked into the geometry), but the texture frame is rotation-only, so textures slide on
  scaled faces. `--fov DEG` (default 75) applies here; `--map` /
  `--rebuild` / `--keep-alive` are rejected with `--native`.

**Shared:** `--out-dir DIR` (required unless `--list-actors`; created if absent), `--size WxH`
(default 1280×960).

## Discovery mode

**`--list-actors Package.Class`** (with `--game --map`) prints the running map's actors of that class
as `Name x y z` instead of shooting (e.g. `Engine.PathNode` blankets every walkable spot) — to
discover `@Actor` refs for shots. `--sample N` prints N evenly-spread; no screenshots, `--out-dir`
not needed.

---

# Texture catalog (offline, reads the game `.utx`/`.u`)

The `texture` verbs carry the same family as `class` — `list`, `show`, `preview`, `search`,
`classify`, `prewarm` — over every texture on the composed package path (`Engine.Texture` and its
descendants: `FireTexture`, sprites, and the rest). The tool enumerates, reports the file facts,
produces the picture, and stores the classification it is handed; it never infers meaning — the one
exception is colours, pre-filled from the texture's own pixels. Every verb takes `--catalog-dir DIR`
(default: the resolved project's catalog dir — the `uedcli.toml` `catalog` key, or
`<root>/texture-catalog/`).

```bash
# enumerate every texture, one ref per line (sorted); filter and shape as needed
uedcli texture list [--package P] [--group G] [--masked]
                    [--classified | --unclassified] [--json]

# a texture's facts (size, format, group, masked) + content identity + stored classification
uedcli texture show <Package[.Group].Name>… | -  [--json]

# write a texture's mip-0 bitmap as a PNG (native P8/BC1/BC2/BC3 decode, mask NOT applied)
uedcli texture preview <Package[.Group].Name>… | -  [--out FILE] [--skeleton]

# RANKED discovery: textures whose name / stored tags / description match the terms, best first
uedcli texture search <term>… [--tag T] [--color C] [--package P] [--group G] [--masked]
                      [--classified | --unclassified] [--json]

# record / inspect what a texture IS — one git-tracked shard per content identity
uedcli texture classify set <Package[.Group].Name> --tags metal,wall \
    --description "riveted metal wall panel" [--colors grey] [--force]
uedcli texture classify set -             # read JSONL rows {ref, tags?, description?, colors?} from stdin
uedcli texture classify unset <ref>… | - (--tags[=A,B] | --description | --colors | --all)
uedcli texture classify status [--json]   # how many textures on the path are classified, of the total
uedcli texture classify tags [--json]     # the tag vocabulary in use, with counts

# decode every texture ahead of an offline session
uedcli texture prewarm [--package P]
```

- **Identity is the content, not the ref.** A texture's classification is keyed by
  `sha256(width, height, RGB)` over its mip-0 pixels — so two identically-pixelled textures (even in
  different packages, or one masked and one not) are one classifiable thing, sharing one shard. A
  procedural texture (`FireTexture` and friends) has no pixels, so it is keyed by its casefolded
  `Package.Name` instead. `show` and `list --json` print the identity.
- **`group` and `masked` are per-ref facts**, read live from the package, not part of identity:
  `group` is the texture's Outer (e.g. `Ladder`), `masked` its effective `bMasked` flag. Filter on
  them with `--group`/`--masked`.
- **`set` refuses over an existing classification** (exit 2); `--force` replaces it wholesale (no tag
  union, an omitted description is wiped). The stored `ref` is write-once — the first classifier's
  spelling.
- **Colours are pre-filled** from a fixed palette by descending share, so `search --color brown`
  works on a fresh clone before anything is classified; an LLM-supplied `--colors` overrides them.
- **`preview --skeleton`** emits a ready-to-fill JSONL row per ref (the preview path + pre-filled
  colours) — pipe it straight into `classify set -`. `list` and `search --json` never render; they
  report only an already-cached preview (null until the preview cache lands).

The classification shards live under the tracked `catalog` dir (`classified/texture/`).

---

# Class discovery (offline, reads the game `.u`)

```bash
# browse actor classes as an indented inheritance TREE (rooted at Engine.Actor)
uedcli class list [--depth N|all] [--subclass-of Package.Class] [--package P]
                  [--flat] [--include-non-actor] [--include-abstract]
                  [--classified | --unclassified] [--json]

# a class's OWN editable props grouped by editor category + super chain + placeable/abstract flags,
# then a Facts block (DrawType, default Mesh, mesh extents, collision, PrePivot, parent), then any
# stored classification
uedcli class show <Package.Class> [--depth N|all] [--category NAME] [--json]

# render the class's default Mesh as an orthographic PNG thumbnail (no editor, no game)
uedcli class preview <Package.Class> [--rotate PITCH,YAW,ROLL] [--out FILE] [--size PX] [--json]

# RANKED discovery: classes whose name / stored tags / description match the terms, best first
uedcli class search <term>… [--tag T] [--subclass-of Package.Class] [--drawtype DT]
                    [--include-abstract] [--json]

# eagerly warm the package schema cache so a later offline list/search/show starts warm
uedcli class prewarm [--package P] [--force]

# record / inspect what a class IS — one git-tracked shard per class (tags + description)
uedcli class classify set <Package.Class> --tags chair,mount:floor --description "a bar stool"
uedcli class classify set -           # read JSONL rows {ref, tags, description} from stdin
uedcli class classify unset <Package.Class> [--tags[=A,B] | --description | --all]
uedcli class classify status [--json]     # how many classes on the path are classified, of the total
uedcli class classify tags [--json]       # the tag vocabulary in use, with counts
```

- **`class list`** auto-fits ~60 lines; abstract classes are marked `*`, a collapsed node shows its
  hidden direct-subclass count as `(N)`. `--flat` gives a pipeable one-`Package.Class`-per-line list;
  `--subclass-of` reroots (e.g. `--subclass-of Engine.Mover`); `--depth all` for the whole tree.
  `--classified` / `--unclassified` filter the `--flat` list to classes that do / don't have a stored
  classification shard (they **require** `--flat` — a tree can't be per-node filtered — else exit 2).
  `--json` emits one object per class (`{ref, classified, preview}`); `preview` is an already-cached
  thumbnail path or `null` (`list` never renders — only `class preview` does).
- **`class show`** is the UnrealEd property-browser view (Movement/Display/Lighting/…): own editable
  props by category, non-editable internals hidden, inherited props collapsed to per-category counts.
  `--depth N|all` expands inherited props (tagged with their source class); `--category NAME`
  (repeatable) shows only that category, expanded over the whole chain.
- After the property schema, `class show` prints a **Facts** block read from the class's package —
  the file-facts an agent needs to place a prop, nothing inferred:

  ```
  Facts:
    drawtype:  DT_Mesh
    mesh:      DeusExDeco.CrateUnbreakableLarge
    extents:   x -40..40  y -40..40  z -56..56   (mesh-local uu; Scale applied, pre-Origin/RotOrigin, DrawScale not)
    collision: radius 56.5  height 56
    prepivot:  0,0,0
    parent:    DeusEx.Containers
  ```

  - **`extents`** is the default `Mesh`'s bounding box as **signed lo..hi per axis** in integer
    Unreal units, in the mesh's own frame: the mesh's `Scale` is applied per-axis (each axis then
    re-sorted so `lo <= hi`), while `Origin`, `RotOrigin` and per-placement `DrawScale` are **not**.
    These are **seating/footprint** facts — the height and whether the mesh sits at `z=0`. They do
    **not** state which way the mesh faces in the world.
  - **`collision`** is the upright collision cylinder (`CollisionRadius`/`CollisionHeight`), which
    carries no facing; **`prepivot`** is `PrePivot`; **`parent`** is the direct super class.
  - A **non-mesh** class (`DrawType` `DT_Sprite`/`DT_Brush`/`DT_None`) has no mesh, so `mesh` and
    `extents` are `none` (`null` in `--json`) — not an error. A `DT_Mesh` class whose `Mesh` is
    missing or fails to decode **exits 2** naming the class and mesh.
- After the Facts block, `class show` prints the stored **Classification** (the `tags` and
  `description` an LLM recorded via `class classify`), or `(unclassified)` when there is none.
- **`--json`** prints only the facts as one JSON object — `{"ref", "drawtype", "mesh", "extents":
  {"x":[lo,hi],…}|null, "collision":{"radius","height"}, "prepivot":[x,y,z], "parent", "abstract",
  "placeable", "classification": {"tags":[…], "description":…}|null}` — instead of the property
  schema.
- Reading a class means reading its whole **super chain**, so if an ANCESTOR's package is missing
  from the search path (or unreadable), `class show` **fails with exit 2 naming that package** —
  `cannot read schema for DeusEx.Flare: package 'Engine' (needed for Engine.Actor) not found on the
  schema search path …` — instead of printing the class's own properties as if that were the full
  list. (A missing package for the class you NAMED is caught earlier, as `unknown class: …`.)

### `class preview` — see the mesh

`class preview <Package.Class>` renders the class's default `Mesh` as an orthographic PNG thumbnail,
natively — it decodes the mesh and its skins from the game's own `.u` packages and software-renders
them, with no editor, container or game. It writes one PNG and prints `<ref><TAB><path>` to stdout
(a human azimuth summary goes to stderr):

```bash
uedcli class preview DeusEx.CrateUnbreakableLarge --out crate.png
# DeusEx.CrateUnbreakableLarge	/abs/path/crate.png   (stdout)
# azimuth 8192 uu (mesh-local yaw, 65536=360deg; not world facing)   (stderr)
```

- The shot is the same **mesh-local frame** as `class show`'s `extents`: the mesh's `Scale` is
  applied, `Origin`/`RotOrigin` are not, and the framing auto-centres — so the picture and the
  extents agree. The default view is **iso** (front-three-quarter).
- **`--rotate PITCH,YAW,ROLL`** poses the mesh at that mesh-local rotator (unreal rotation units,
  16384 = 90°, 65536 = a full turn) **before** the camera shoots it — the **pose oracle**: preview a
  *candidate placement rotation* before you commit it, instead of round-tripping through the game.
- **azimuth** is the camera's mesh-local yaw in unreal rotation units (65536 = 360°) — which yaw in
  the image faces you. `--rotate`'s yaw shifts it. It is a **mesh-local** reading and does **not**
  claim world facing: a non-identity `RotOrigin` re-aims the mesh in the world and is unreconciled
  here (same scope limit as `class show`'s extents). It appears on the stderr summary, and in `--json`.
- **`--out FILE`** names the PNG (relative paths join the cwd; the extension is always replaced by
  `.png`); with no `--out` a unique temp file is written. **`--size PX`** sets the edge length
  (default 512). **`--json`** prints one object `{"ref", "path", "azimuth", "rotate"}` instead of the
  text row (`rotate` is the applied `[pitch, yaw, roll]` or `null`).
- A **non-mesh** class (`DrawType` `DT_Sprite`/`DT_Brush`/`DT_None`) has no mesh to render — a stderr
  note, **exit 0**, no image (matching `class show`'s null extents; not an error). A `DT_Mesh` class
  whose `Mesh` default is unresolvable, or a skin that fails to decode, **exits 2** naming it — never
  a wrong picture. With no composed package path, `class preview` **exits 2** (`no package search
  path`).

### `class classify` — record what a class is

The tool stores the classification an LLM hands it; it never infers meaning. Each class gets one
git-tracked shard under the catalog dir (`classified/class/<package>/<class>.json`, path casefolded),
holding exactly `{kind, ref, tags, description}`. Concurrent agents classifying different classes
never touch the same file.

```bash
# record tags + a description (the class must be on the composed package path)
uedcli class classify set DeusEx.BarStool --tags chair,mount:floor,faces:+z \
    --description "bar stool; DX places these along the DiveBar counter"

# batch: one JSON object per line on stdin, one shard write per row
printf '%s\n' '{"ref":"DeusEx.BarStool","tags":["chair"],"description":"a stool"}' \
    | uedcli class classify set -
```

- **`set`** merges: on re-set, `--tags` **union** onto the stored tags through a strip / lowercase /
  de-dupe normalizer, so re-running never loses a tag. A **different non-empty** `--description`
  **exits 2** printing the stored text; pass `--replace` to overwrite; identical text is a no-op. An
  unknown class, or a ref that is not `Package.Class`, **exits 2** naming it.
- **`mount:` and `faces:` are reserved tag namespaces.** A `faces:` tag needs an axis token —
  `+x -x +y -y +z -z` (case-normalized, so `faces:+X` is fine); any other value **exits 2** naming
  it. A `mount:` tag needs a non-empty value (free text, e.g. `mount:wall`). Only the **shape** is
  checked — what the value *means* is authored, never computed. They are ordinary tags otherwise
  (they show up in `classify tags` and filter via search).
- **`set -`** reads JSONL rows `{ref, tags, description}` from stdin, one shard write per row. It is
  **all-or-nothing**: every row is validated first, and a single bad row **exits 2** naming it with
  nothing written. Empty stdin is a clean no-op (exit 0).
- **`unset <Package.Class>… | -`** undoes classification: `--tags A,B` removes those tags, bare
  `--tags` clears the whole tags field, `--description` clears the description, and `--all` deletes
  the shard. `-` reads a newline ref list from stdin (empty stdin is a clean no-op). A ref with no
  shard **exits 2** naming it.
- **`status [--json]`** reports how many classes on the path have a shard, of the total.
  **`tags [--json]`** lists the tag vocabulary in use with occurrence counts, to curb drift.
- Every `classify` verb needs the composed package path (to know the class exists); with none it
  **exits 2** (`no package search path`).

### `class search` — ranked discovery

`class list` **enumerates** the class tree deterministically; `class search` **ranks** it by
relevance. Give it one or more terms and it prints the matching classes best-first, matching each
term against the class's leaf name, its stored classification tags, and its description.

```bash
uedcli class search chair                              # anything named/tagged/described "chair"
uedcli class search crate --tag storage --drawtype DT_Mesh
uedcli class search lamp --subclass-of Engine.Light --json
```

- **Terms are required.** A term-less `class search` **exits 2** pointing at `class list` (the
  enumerator). A class must match **every** term (AND); a term matching nothing drops the class.
- **Ranking** is a fixed tier order per term, summed across terms: exact leaf class name (5) > exact
  tag (4) > substring of the `Package.Class` ref (3) > substring of a tag (2) > substring of the
  description (1). Ties break by ref ascending, so output is deterministic.
- **Corpus** is every placeable Actor subclass. `--subclass-of Package.Class` restricts it to that
  base's descendants (an unknown base **exits 2** naming it); `--include-abstract` also searches
  abstract / non-placeable classes.
- **`--tag T`** (repeatable) keeps only classes carrying that exact stored tag — reserved
  `mount:`/`faces:` tags filter here like any other (`--tag faces:+x`). **`--drawtype DT`** keeps
  only classes whose resolved `DrawType` default equals `DT` (case-insensitive; an unknown token
  **exits 2** listing the valid ones). `--drawtype` reads each surviving class's defaults, so it
  costs more than a name/tag match.
- Plain output is one `Package.Class` per line to stdout (the match count on stderr); **no match** is
  a clean exit 0 with empty stdout. **`--json`** emits one object per match:
  `{ref, score, classified, tags, description}`. With no composed package path, `search` **exits 2**
  (`no package search path`).

### `class prewarm` — warm the cache before an offline session

Building the class index and resolving property schemas decodes every `.u` on the path the first
time. `class prewarm` does that decode ahead of time and persists it, so a later **offline**
`class list` / `search` / `show` starts warm instead of cold.

```bash
uedcli class prewarm                    # warm every package on the path
uedcli class prewarm --package DeusEx    # just one package
uedcli class prewarm --force             # re-decode even entries that are already warm
```

- It warms the **package schema cache** (class discovery + property schemas). It does **not** render
  previews or resolve mesh facts — those have no persistent cache yet, so a cold `class preview` or
  `class show`'s extents still pay their own cost.
- Prints each warmed package stem to stdout, one per line, with a count on stderr. `--package P`
  warms only `P` (an unknown package **exits 2** naming it); `--force` re-decodes and rewrites each
  entry even when a valid one exists (the default fills only misses). With no composed package path
  it **exits 2** (`no package search path`).

---

# Sound & music catalog (offline, reads the game packages)

Two nouns, `sound` and `music`, catalog the substrate's audio the way `class` catalogs its actor
classes — enumerate, inspect, search, and record a classification — offline, reading the game's own
packages (`.uax`/`.u` for `Sound`, `.umx` for `Music`), no editor or level. `music` additionally
reports each module's **embedded title**. Both are **phase (a)**: no sample decoding yet, so there is
no `sound preview` (spectrogram), duration, or export.

```bash
# enumerate every object, one full dotted ref per line (count to stderr); NO default filter
uedcli sound list [--package NAME]… [--classified | --unclassified] [--json]
uedcli music list [--package NAME]… [--classified | --unclassified] [--json]

# facts (package, group, identity) + stored classification; music also prints title + format
uedcli sound show <ref>… | -   [--json]
uedcli music show <ref>… | -   [--json]

# RANKED discovery: objects whose name / stored tags / description match the terms, best first
uedcli sound search <term>… [--tag T] [--json]
uedcli music search <term>… [--tag T] [--json]

# record / inspect what an object IS — one git-tracked shard per object (tags + description)
uedcli sound classify set <ref> --tags a,b --description "…"   # refuses if already set; --force replaces
uedcli sound classify set -            # read JSONL rows {ref, tags, description} from stdin
uedcli sound classify unset <ref>… | -  [--tags[=A,B] | --description | --all]
uedcli sound classify status [--json]   # how many objects on the path are classified, of the total
uedcli sound classify tags [--json]     # the tag vocabulary in use, with counts
```

- **Ref and identity.** `list` prints each object's full dotted ref (`Package.Group.Name`, or
  `Package.Name` for a root object). An object's **identity** — the shard key — is `Package.Name` when
  that bare name is unique in its package, else the full dotted `Package.Group.Name` (one package can
  hold the same bare name in two groups). `show`/`classify` accept **either** spelling; both resolve to
  the same object. A ref that is unknown, or a 2-part name that is ambiguous because it collides across
  groups, **exits 2** naming it (use the full dotted ref).
- **`list` prints its whole set** — one ref per line, count to stderr — with **no default filter**.
  Narrow with a pipe (`sound list | grep -v '^DeusExConAudio'`) or **`--package NAME`**, which takes an
  **exact** package stem (not a glob) and is **repeatable** (`--package A --package B` = the union); an
  unknown package **exits 2** naming it. `--classified` / `--unclassified` keep only objects that do /
  don't have a shard. `--json` emits one object per line: `{ref, identity, group, classified}` (music
  also carries `title`, `format`).
- **`music show` / `music list --json`** carry the module's **embedded title** and **format**, read
  live from the `.umx`. The format is `IT`, `S3M`, `XM`, or `unknown`; a module with no readable title
  reports `title: null` with the format still named, never a blank that reads as "no module".
- **`classify set` refuses to overwrite.** A `set` over an already-classified object **exits 2** naming
  the ref and printing the stored payload; **`--force`** replaces the shard **wholesale** — it does not
  merge, so a `--force` that omits `--tags`/`--description` drops the stored value. `set -` reads JSONL
  rows `{ref, tags?, description?}` from stdin, all-or-nothing (one bad row writes nothing; `--force`
  governs every row); empty stdin is a clean no-op. Shards live under `classified/<sound|music>/…`,
  holding exactly `{kind, ref, tags, description}`.
- **`unset`**, **`status`**, **`tags`**, and **`search`** mirror `class classify` / `class search`:
  `search` requires at least one term (term-less **exits 2** pointing at `list`) and ranks by exact
  leaf name > exact tag > ref substring > tag substring > description substring. With no composed
  package path, every verb **exits 2** (`no package search path`).

---

# Documentation — read the docs from the CLI

uedcli carries its own user documentation, queryable from the tool itself — no network, no repo
checkout, always the version matching the binary you are running. `uedcli docs show usage` prints
this file.

```bash
# every page's topic key, one per line
uedcli docs list [--json]

# print one page's markdown, verbatim
uedcli docs show leveldesign/general/lighting

# rank pages matching a text query, printing the keys `docs show` takes
uedcli docs search "mover" [--json]

# search feeds show directly
uedcli docs search voussoir | uedcli docs show -
```

**A topic key** is how a page is addressed: its path with the `.md` dropped, so
`leveldesign/general/lighting` (a trailing `.md` is accepted too, and matching is
case-insensitive). A directory's overview page is addressed by the **directory's own name** —
`uedcli docs show leveldesign/deusex` gives that section's overview — and this usage reference is
`usage`, with the docs landing page at `index`.

- **`docs list`** prints every topic key to stdout, sorted, with the count on stderr. `--json`
  gives `[{"path": <topic key>, "title": …}]` — `path` holds the topic key, not a filesystem path.
- **`docs show <topic>`** writes the page's markdown to stdout byte-for-byte and nothing to
  stderr. `docs show -` instead reads topic keys from stdin, one per line, and prints them all,
  each preceded by a `<!-- topic: <key> -->` marker line. That form is **all-or-nothing**: if any
  key is unknown, nothing is printed and it exits 2 naming the offending keys. Empty stdin is a clean
  no-op (exit 0).
- **`docs search <query>`** matches a literal, case-insensitive substring against every page's title
  and body lines, and prints the matching topic keys best-first. The ranking is simple: **a title
  match is worth ten matching body lines**, matching body lines one each. So a page *about* your
  query usually leads — but a long page that mentions it eleven times outranks a short page with it
  in the title, working as intended. No matches is a normal empty success (exit 0); an empty query is
  refused (exit 2), since a blank substring would "match" every page. `--json` adds a `snippet` — the
  first matching **body** line, up to 120 characters. The page's heading is its `title`, not a body
  line, so a snippet never just repeats it.

An unknown topic exits 2 with `Doc not found: <topic>` and, where there is an obvious near miss, a
`did you mean:` hint. A bare page name that exists in two places (`human-scale`) does *not* resolve —
the hint lists both candidates.

There are no partial answers. If any part of the docs tree cannot be read — a permission problem on
a directory, say — every `docs` verb exits 2 naming that directory, rather than quietly serving the
pages it *could* read.

Every `docs` verb is read-only and fully offline: no project, no selected level, no game install, so
it works in a bare checkout or install.

---

# Substrate & cache utilities

- **`substrate stub [package] [--force] [--list]`** — convert a Deus Ex v68 code package (`.u`) into
  a UED22-loadable v69 "stub" (mesh-preserving; the editor is v69-authoritative). `--list` prints the
  stub cache manifest without building.
- **`cache clear`** — delete the persistent package-schema cache (`~/.uedcli/cache/schema`); it is
  pure derivable throwaway and rebuilds on the next command (escape-hatch / reclaim old
  decoder-version dirs).
- **`cache gc [--max-bytes N] [--max-entries N]`** — *shrink* that cache instead of emptying it:
  delete orphaned old decoder-version (`v<N>/`) dirs, then evict least-recently-used entries until
  the cache fits its cap (default 256 MiB, no count cap; `N=0` evicts everything). Evicted entries
  just re-decode when next needed. A GC runs automatically after a cache write — reach for this verb
  only to reclaim disk on demand. Prints a one-line summary; a negative cap exits 2.
