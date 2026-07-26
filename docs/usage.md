# uedcli — usage

`uedcli` is the LLM-facing CLI for authoring **UnrealEngine-1 levels** (Deus Ex `.dx`,
Unreal/UT `.unr`) without opening the editor by hand. You issue **semantic, by-name commands**
(`actor find`, `brush build`, `mover key move`, …); the T3D text format is internal plumbing.

The durable source of truth is a **git-tracked T3D tree** on disk (one directory per actor under
`maps/<level>/`), NOT a live editor and NOT a bespoke session store — work-in-progress is simply
an uncommitted / feature-branch state in your own repo, and `git` is the history and the merge
engine. Reads and edits are **pure model-side compute** against that tree (instant, no container).
The real editor / headless game is reached **only** for the few commands that must build or render:
`level materialize` and `level preview --game`. Each such command spins up its own container as needed — there is no persistent session
and no `--container` flag.

```
uedcli <verb> …                      # if installed on $PATH (pipx)
bin/uedcli <verb> …                  # from Tools/uedcli, host-native via the dev venv
```

## Composability — the core philosophy

Verbs are small and pipe together instead of growing bespoke flags:

- **Producer / query verbs print their result to stdout, one item per line** (pipe-friendly);
  human summaries and counts go to **stderr** so they never pollute the pipe. Many add **`--json`**
  for structured output.
- **Mutating verbs read their target set from stdin via `-`** — `actor find … | actor delete -`.
  `-` is the *sole* names source (not mixable with names as CLI args); **empty stdin is a clean
  no-op (exit 0)**, not an error.
- **Two stdin conventions, disambiguated by verb:** a **name list** (`find → mutate -`) versus a
  **T3D snippet** (`build → add -`). Keep them distinct.
- **A verb over a SET takes the set, and that IS the operation** — e.g. `actor bbox <names…>`
  returns the box enclosing ALL of them, so there is no `--union` flag.
- Prefer a stateless **`find` / query** verb whose output feeds another verb over per-command
  filter flags.

**Errors never leak a Python traceback.** A bad actor/class/value raises a clear message that names
the offending value and exits non-zero (typically exit 2).

**Output streams for mutators.** Set-mutating verbs are PRODUCERS — they print their touched/allocated
actor names to **stdout** (one per line) plus a summary to **stderr**, so they chain via `-`
(`actor find | actor rotate - | brush scale -`): `actor add` (allocated names), `actor duplicate`,
`actor rotate` / `order` / `move` / `delete` / `prop set|unset` / `folder set|unset` /
`label add|remove|clear`, `brush
scale` / `apply-transform` / `poly set` / `align` (touched brush names), and `stash apply` /
`prefab apply`. (For `delete`
the stdout is the removed names — a log/count, since they no longer exist to pipe into an edit.)

## Projects: `uedcli.toml`

A **project** is any repo with a free-standing **`uedcli.toml`** at its root (found by walking up
from cwd; nearest wins — or point `--project` / `$UEDCLI_PROJECT` at the root dir or the file). The
file is hand-written (there is no `project init`):

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
  lives in a gitignored, **self-ignoring** `.uedcli/` beside the file —
  uedcli creates it (writing its own `.gitignore` of `*`) on first use; safe to delete.
- **The per-user `~/.uedcli/`** holds only `config.toml` (the `[games.*]` blocks — where each game's
  base asset packages live) and the derivable, content-addressed `cache/{textures,stubs,schema}`
  shared across projects. There is no central per-project bucket and no project `id`.

**Package layering.** The effective package search path is the project's overlay `paths` first, then
the selected game's base dirs, deduped project-shadows-base. `paths` are **bare directories**,
colon-separated — uedcli owns the five package extensions (`.u .dx .utx .uax .umx`) and scans the
dirs itself.

**Mover detection reads the class hierarchy, so it needs the packages.** Whether an actor is a
**mover** (an animated brush — see [Movers](#movers--animated-brush-actors-doors--lifts--gears)) is
decided by resolving its class against `Engine.Mover` in the game's own code packages, *not* by
guessing from the class name. So every verb that has to know — `mover key *`, `level doctor`,
`event graph`, `brush scale`, `brush apply-transform`, `brush intersect`/`deintersect`,
`stash capture`, `level preview --native` — needs a resolvable package search path: a project
**and** `~/.uedcli/config.toml`. Without one the verb exits 2 naming itself and what is missing; it
never falls back to a name guess, because that would silently report a real mover as a static brush.
(`level materialize` and `level preview --game` need the same config for an unrelated reason — they
load the game's packages to build and to render — so in practice every verb on this page that
touches packages at all wants it configured.)

The same rule applies **per actor**: if an actor's class — or any class on its ancestor chain — is
not on the composed search path, the verbs listed above exit 2 naming that class instead of quietly
deciding it is not a mover. If you hit that, the package holding the class is missing from your
project `paths` or the game's base dirs (`uedcli project show` prints the resolved path).

**`project show [--json]`** prints the resolved root, game, managed dirs, and composed package search
path (each entry tagged `project`/`base`); `--json` emits
`{root, game, maps, prefabs, catalog, search_path:[{path, provenance}]}`.

## Choosing a level

Most verbs operate on the **current level**, named by the **`UEDCLI_LEVEL` environment variable** (a
bare level name; a level's identity is its `maps/<name>/` directory). Set it once per shell:

```
export UEDCLI_LEVEL=20_AireGardens
uedcli actor find --folder castle.**        # operates on 20_AireGardens
```

A verb with no `UEDCLI_LEVEL` and no explicit `--tree` exits 2 with `no level: set the environment
variable (export UEDCLI_LEVEL=<name>) or pass a level explicitly (--tree level/<name>)`. There is no
`level select` verb — the level is the env var (a child process can't set the parent shell's env).
When a **mutating** verb resolves the level from `UEDCLI_LEVEL` (not an explicit `--tree`), it echoes
`editing level 'X' (from $UEDCLI_LEVEL)` to stderr, so a stale export can't silently edit the wrong
level.

| Command | What it does |
|---|---|
| `level create <name>` | scaffold a NEW level directory `maps/<name>/` with a `LevelInfo` actor (required by `materialize`); prints `to edit it: export UEDCLI_LEVEL=<name>` |
| `level list [--json]` | list the project's levels (trunk dirs under `<maps>`), one name per line to stdout (pipe-friendly); a count + the active `$UEDCLI_LEVEL` go to stderr. `--json` emits `[{name, active}, …]` |
| `level status [--tree KIND/NAME] [--json]` | thin read-only dashboard for the current level (or a `--tree` box): actor counts, duplicate `order_value`s, git state. `--json` emits a `{kind, name, actors, duplicate_order_values, git, texture_packages}` object (`{"selected": null}` when no level is set) |

---

# Query verbs — model-side, instant, no editor

## Actors

| Command | What it does |
|---|---|
| `actor find [filters…] [--json] [--exclude] [-]` | print names of matching actors, one per line, for piping; with no filters, prints **every** actor; a trailing `-` restricts the search to a piped name-set (boolean queries — see below) |
| `actor show <name\|glob\|->` | print matching actors' full canonical T3D blocks |
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
  is tested); a point actor is its `Location` point. **Single-valued** (not repeatable). Selects a
  region's actors — it matches **every** contained actor (lights, nav points, decorations too), so
  add `--kind brush` when you want geometry only. Because it's full **containment**, a brush that
  straddles the box edge (a room shell poking past a tight box) is **not** matched — size the box to
  enclose the whole feature. (A looser "also catch straddling brushes" variant, `--overlapping-bbox`,
  is not yet implemented.)
- `--folder PATTERN` / `--no-folder` — see **Folders** below.
- `--label GLOB` / `--no-label` — see **Labels** below.
- `--json` — emit the names as a JSON array.

```bash
uedcli actor find --group cells | uedcli actor delete -
uedcli actor find --folder castle.tower.** | uedcli actor bbox -   # enclosing box of a subtree
uedcli actor find --within-bbox -512,0,-256,512,768,256 --kind brush | uedcli actor preview -   # wireframe a region
```

**Boolean queries — `find <filters> -`:** with a trailing `-`, `find` reads a newline actor-name list
from stdin and searches ONLY that set (the "universe"); the filters are the predicate. `--exclude`
keeps the non-matches instead. This composes into full boolean logic:

    actor find --group A | actor find --group B -            # A AND B
    actor find --group A | actor find --group B --exclude -  # A but NOT B
    { actor find --group A; actor find --group B; } | sort -u | actor find -   # A OR B (re-normalized)

Unknown piped names are a hard error (exit 2). `find -` with no filters echoes the piped set (a strict
validator).

`actor show <name>` — an exact name that matches nothing errors (exit 2); a glob with zero matches
prints nothing (exit 0, grep-like). Reads a stdin name list with `-`. By default each block also
carries the uedcli-side sidecars as comments — a `// uedcli-folder:` line for a foldered actor and a
`// uedcli-labels:` line for a labelled one — so `actor show A | actor add -` round-trips both;
`--t3d-only` suppresses them for a byte-exact editor export.

The T3D that `actor show` prints — and that the trunk stores — is **faithful, not abbreviated**: it
states every authored property explicitly, including ones whose value happens to equal the class
default (`Location=(X=0.000000,Y=0.000000,Z=0.000000)`, `Rotation=(Pitch=0,Yaw=0,Roll=0)`, a `Tag`
the editor stamped). UnrealEd's own export omits those, so its export of the same level is shorter
than the trunk — that is expected, and the build's post-verify compares the two by **value, not by
text**: each property resolves to what it would import as (the stored value, or the class default
when the line is absent), so the two spellings simply are the same level. Never hand-delete such a
line to "clean up" the trunk: an omitted property does not mean zero, it means *the class default*,
which is non-zero for some classes.

**`actor prop get`** prints EFFECTIVE property values — the stored value if present, else the class
default decoded offline from the game packages, else the type's zero — one line per KEY in argument
order (a whole static array prints as one `(0=V,1=W,…)` line; a whole struct prints every member).
With **no KEYs**, dumps the actor's STORED props (plus `Location`). `--kv` prints round-trippable
`KEY=VALUE` lines (feeds back into `actor prop set`); `--json` emits a `{key: value}` object (values
as strings). The name may be `-` to read a stdin name list and dump every piped actor (output is then
`<name>\t<key>=<value>` so a multi-actor dump stays parseable).

**`actor bbox`** honours each actor's rotation/scale/location; a point actor contributes a zero-size
box at its Location. Default prints four labeled `min`/`max`/`size`/`center` lines; `--field
min|max|size|center` prints just that one bare `x,y,z` vector; `--json` emits `{min,max,size,center}`
each `{x,y,z}`. The count summary goes to stderr.

## Brush surfaces & geometry

| Command | What it does |
|---|---|
| `brush poly list <name> [--json]` | per-poly table for a brush (see below) |
| `brush poly find <name> [filters] [--json]` | matching faces as `BRUSH:idx` selectors, for piping |
| `brush vertex list <name> [--json]` | welded brush corners: world coord + the polys sharing each |

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

Its output feeds `brush poly set -` and `brush poly align -`.

## Level lint & trigger wiring

**`level doctor [--json] [--severity {info,warn,error}] [--category C,…]`** statically checks the
level for the BSP/geometry problems that cause holes, HOMs, and invisible walls — **fully offline,
no editor.** It flags: degenerate faces UnrealEd will silently drop (too few vertices, zero area,
non-convex, non-planar); brushes that aren't watertight (open/duplicated/back-wound edges); solidity
mistakes (a portal marked semisolid); gross CSG-order errors (an additive brush buried inside a later
subtract, a subtract that carves nothing); and scale issues. Each finding names the brush, poly,
world coordinate, engine symptom, and fix.

- Categories: `degenerate,watertight,convex,planar,solidity,csg_order,scale`.
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
even with no eventing props — see [Projects](#projects-uedclitoml)).
An actor's **`Event`** property is the event it *fires*; another actor's
**`Tag`** property is its *receiver* identity. A directed edge **A → B** means `A.Event == B.Tag`.

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
`Group=` property (which is retained unchanged). One folder per actor.

- **Set at creation:** on the **generator** — `brush build … --folder <path>` / `actor build … --folder
  <path>` — which emits a `// uedcli-folder:` carrier the T3D carries; `actor add` persists it (it has no
  `--folder` of its own). `actor show` emits the same carrier, so `actor show A | actor add -` round-trips.
- **Manage:** `actor folder set --to <path> <names…|->`, `actor folder unset <names…|->`,
  `actor folder get <names…|->`. `set`/`unset` are PRODUCERS (touched Names → stdout, a summary →
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
prop (named `label`, not `tag`, precisely to avoid colliding with `Engine.Actor.Tag`). An actor may
carry any number of labels. A label token is `[A-Za-z0-9_+-]`, no `.`, no leading `-`; stored as
authored (case preserved) and matched case-insensitively.

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
the only way to query them, since an unlabelled actor matches no `--label` pattern.

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

These transform the in-memory level and rewrite the T3D trunk. Committing is your own `git`. Every
one of them also accepts `--tree KIND/NAME` (see below) to edit a different box.

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
| `actor folder set/unset` | manage the uedcli-side folder (see Folders); prints the touched names |
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
a bare `duplicate` with neither is an error (exit 2), and `--by 0,0,0` is the explicit way to overlap
the originals in place. Copies **inherit their source's labels** and additionally all receive **one
fresh `dup-<rand>` batch label**, so `actor find --label dup-<rand>` re-addresses the whole batch
after the pipeline ends (the token is echoed to stderr). `--label L` (repeatable) is **additive** —
stamped on top of the inherited labels and the `dup-<rand>` token, not instead of them. `--folder
PATH` overrides each original's folder. Duplicate is trunk-only (rejects `--tree stash|prefab`).

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
`--to` sets the field **absolutely in
place** (Location never moves; excludes `--pivot`). The pivot is `--pivot X,Y,Z`, or
`--pivot-actor NAME`'s Location, or (default) the targets' grid-aligned center.
A zero result is **written out** (`Rotation=(Pitch=0,Yaw=0,Roll=0)`), not omitted: an actor with no
`Rotation` property takes its *class* default, which is not zero for every class, so
`--to 0,0,0` really does mean "unrotated" only when the rotator is there to say so.

**`brush scale`** (renamed from `actor scale` 2026-07-20 — MainScale is a brush-family property; a
mesh uses `DrawScale`) sets MainScale on BRUSH actors — `--to` absolute in place, `--by` a per-axis
factor that also orbits each Location about the pivot (`Loc' = P + S·(Loc−P)`). A negative axis
mirrors; there is no separate `mirror` verb (`mirror` = `brush scale --by -1,1,1`). A point actor is
rejected.

**`brush apply-transform`** (renamed from `actor apply-transform`) bakes MainScale + Rotation +
PostScale permanently into the brush
vertices and resets those fields (the offline `ACTOR APPLYTRANSFORM`): reverses winding on a
mirror/negative determinant, rewrites PrePivot, leaves Location, rejects movers. `--lock-textures`
(the DEFAULT) transforms the texture axes with the geometry; `--no-lock-textures` leaves the mapping
fixed.

## Brush shape & surfaces

| Command | What it does |
|---|---|
| `brush clip <name> (--axis A --coord N \| --plane PX,PY,PZ NX,NY,NZ) [--keep below\|above]` | model-side Sutherland-Hodgman halfspace clip |
| `<generator> \| brush replace <name> -` | in-place shape swap, keeping the target's identity |
| `brush vertex move <name> --at X,Y,Z (--to X,Y,Z \| --by DX,DY,DZ)` | move welded corners (selected by coordinate; repeat `--at`) |
| `brush poly set BRUSH:SELECTOR… \| -` | set flags/texture/pan on one or more surfaces |
| `brush poly align (--wall\|--floor\|--ring) targets…\|-` | flow one texture continuously across faces |

**`brush clip`** plane is world-space (axis+coord, or point+normal); `--keep below` keeps the side
opposite the normal. It clips the model, validates, then re-adds via paste so the clipped brush stays
selectable. If the plane misses the brush interior it is a no-op and prints
`clip plane did not intersect brush <name> — left unchanged`.

**`brush replace <name> -`** swaps a brush's **shape in place** from a piped generator T3D on stdin
(`-` is the sole shape source — the `build → replace -` convention, not a name list), **keeping** the
target's Name, `order_value`, Group, CsgOper, actor-level solidity PolyFlags, and old
Location/PrePivot. Only the incoming **PolyList** is taken (its own Location/PrePivot/Name ignored),
but its **per-surface attributes come with it** — reapply any `brush poly set` edits afterward. Empty
stdin is a clean no-op; input with no brush geometry, or more than one brush, is a clean error
(exit 2). E.g. `brush build cube --width 512 … | brush replace WALL -`.

**`brush vertex move`** moves one or more welded corners selected by their current world coordinate
(`--at`, repeatable). `--to` needs exactly one `--at`; `--by` applies a delta to every `--at` corner.
`brush clip` and `brush vertex move` are **rotation-aware** — a world plane/coord is mapped into the
brush's local frame, so they edit a rotated brush correctly and preserve its `Rotation`.

**`brush poly set`** edits surface attributes model-side. Targets are `BRUSH:SELECTOR` positionals
(SELECTOR = `all` or comma-separated poly indices; repeatable, e.g. `Wall1:3,5 Wall2:all`), **or `-`**
to read the `BRUSH:idx` lines `brush poly find` prints from stdin (empty stdin = clean no-op).
Options: `--texture REF` (qualified `Package[.Group].Name`), `--add-flag`/`--remove-flag` (flag by
**name**, case-insensitive — `Unlit`, `unlit`, `MASKED` all work; repeatable),
`--pan-to U,V` / `--pan-by U,V` (integer texel pan).

```bash
uedcli brush poly find WALL --facing +Z | uedcli brush poly set - --texture DeusExDeco.Wood
```

**Identifying a surface to edit:** `brush poly list <brush>` for the exact index/facing/texture,
then `actor preview <brush> --highlight <brush>:N` (below) to see it emphasised (or
`--frame <brush>:N` to frame it).

### Continuous texture alignment (`brush poly align`)

**`brush poly align (--wall | --floor | --ring) [--fresh-frame] [--fit-perimeter] (targets…|-)`** makes
one texture flow **continuously** across a set of faces instead of restarting the pattern at every
brush edge (offline texture-vector math — the model-side analogue of UnrealEd's `TEXTURE ALIGN`).
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
nested (`stash/hangar/arch`). Omit it for the ambient `$UEDCLI_LEVEL` (the default). It rides
`actor find/show/add/delete/move/prop/rotate/scale/order/bbox/folder/label`, `brush clip/replace/vertex/poly`,
`mover key *`, the read verbs `actor show`/`level status`/`level doctor`/`event graph` and `stash
capture`'s SOURCE (`stash capture --tree level/<name>`; rejected together with `--from-t3d`),
**and — level-kind only — `level materialize`/`level preview`** (`--tree level/<name>`
builds/previews that level; `--tree stash|prefab` is rejected there, since a captured set has no world
— use `stash`/`prefab preview`). Passing `--tree` explicitly suppresses the `editing level '…' (from
$UEDCLI_LEVEL)` echo (you named the target). For a stash/prefab box, `level status`/`level doctor`
label it by kind and skip the git hint. It is **not** on the generators (`brush build`/`actor build` —
they read no box) or `actor preview` (use `stash`/`prefab preview`).

---

# Generators — stateless T3D producers

These write a T3D snippet to **stdout** and never touch the trunk or the stash. The caller decides
what to do with the output. **Name allocation and the write into the trunk happen at `actor add`,
not at generation time** — so `--base-name` is a *stem/prefix*, and `actor add` appends a unique
`_<rand>` suffix (the spiral writes a central column plus one wedge-tread actor per step, each with a
per-brush index; the staircase is one actor). Duplicate base names are safe.

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
brush build cylinder  --height H --radius R [--sides 8] [--align-to-side]
brush build cone      --height H --radius R [--sides 8] [--align-to-side]
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
radius or step width that is negative or zero is rejected up front — exit 2, naming the flag and the
value (`brush build staircase: --depth must be greater than 0, got -32.0`). A negative length would
otherwise build a self-overlapping, inside-out brush that looks fine until the map build fails with
an unrelated-looking BSP error. Counts and angles keep their own, tighter rules instead: `--steps`
needs at least 1, `--sides` at least 3, `--angle-per-step` must be between 0 and 32768 unreal
rotation units (a half turn), and `--angle` between 0 and 65536.

**Builder angles are unreal rotation units, like `--rotate`** — `16384` = 90°, `65536` = a full
turn — never degrees. `spiral --angle-per-step` defaults to `8192` (45°). Note that thirds are not
exactly representable (`65536` is a power of two), so a 60° sweep is `10923` uu = 60.002°; degrees
divide by three exactly and UU does not. `cylinder`/`cone` take no angle at all: the one thing an
author ever wanted there is the **`--align-to-side`** flag, which offsets the cross-section by half
a segment (`180/--sides` degrees) so a flat FACE, rather than a vertex, meets an axis-aligned wall
— the same parameter as UnrealEd's own `AlignToSide` checkbox. For any other cross-section angle
use `--rotate`, which is whole-actor placement.

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
  `CsgOper`/`PolyFlags`/`Group`/`Rotation`), so a `--prop` can override a dedicated flag's value.
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
  CSG core assumes convex brushes, so `level preview --native` mis-builds its
  concave notches — use `--game`/UnrealEd for staircases. **Spiral is currently rough** (rectangular
  slabs, gaps) — prefer a cylinder column + per-step wedges until it's redone.

### `extrude` — sweep a profile you draw

Every other shape is *fixed parametric*: you choose sizes, never a silhouette. `extrude` takes the
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
  turns an actor about its local origin, which here is profile `(0,0)`, not the brush's centre — a
  profile drawn away from `(0,0)` therefore *swings through an arc* instead of turning in place.
- **The profile must be a simple ring.** Duplicate and collinear points are cleaned away silently
  (the engine drops them at build time anyway); a ring that crosses itself, touches itself, revisits
  a vertex, or encloses zero area is rejected with exit 2 naming the offending points — such a
  profile has no consistent inside, and the brush built from it would be a self-intersecting solid
  (a guaranteed BSP defect).
- **Faces:** `Cap` at each end plus one `Side<k>` per profile edge, numbered in ring order — so
  `brush poly find --item Side0` selects "the face swept by my first profile edge". Note the
  numbering follows the *cleaned, counter-clockwise* ring: giving the same shape starting at a
  different vertex renumbers the sides.
- **Concave profiles are fully supported, as ONE brush.** The engine's polygon must be convex and
  holds at most 16 vertices, so a concave profile (an L, a notched cornice) or one longer than 16
  points has each of its two **caps tiled into several convex faces** — the brush itself stays
  single and non-convex, exactly like `brush build staircase`. The tiling only adds *diagonals* of
  your profile, never a new point on its outline, so the solid stays watertight. Face count is
  therefore `points + 2 × cap-pieces`. **Native caveat:** UnrealEd (the default `level
  materialize`) and the real engine (the default `level preview --game`) build a concave brush
  correctly, but the offline draft renderer `level preview --native` assumes convex solids, so it
  draws a concave notch *filled in* — that is a preview artefact, not a geometry bug.

### `revolve` — sweep a profile around an axis

Same profile, same `--axis`, same `--at`; instead of a straight `--depth` it sweeps the profile
**around the profile plane's own `V` axis** — the line `U = 0`, which passes through profile
coordinate `(0,0)`. So `--at` is the world position of the **bend centre**, and how far the shape
sits from that centre is written in the profile itself: a profile drawn at `U ∈ [64, 192]` revolves
at radii 64 to 192. (That is why there is no `--pivot` flag — moving the profile and moving the
axis are the same operation.)

```bash
# a 90° curved corridor, 128 uu wide and tall, bending around the world origin
uedcli brush build revolve --axis x --angle 16384 --csg subtract --solidity semisolid \
  --point 64,0 --point 192,0 --point 192,128 --point 64,128 \
  --at 0,0,0 --folder castle.corridor | uedcli actor add -
```

- **`--angle UU`** is the total sweep in **unreal rotation units**, the same units as `--rotate`:
  `16384` = 90°, `65536` = a full turn. It must satisfy `0 < angle <= 65536`. Thirds are not
  exactly representable (`65536` is a power of two), so a 60° bend is `--angle 10923` = 60.002°.
- **`--segments N`** is how many flat facets the sweep is cut into. The default is **one facet per
  22.5°** — 4 for a 90° bend, 16 for a full turn, matching UnrealEd's own density. A facet of 180°
  or more is flat (zero volume) and is rejected.
- **`--angle 65536` is a CLOSED turn:** the two caps would coincide, so both are omitted and the
  last facet's far ring is the first facet's near ring. It needs at least 3 segments.
- **The profile must sit strictly on the positive-`U` side of the axis** — every point's `U` > 0.
  A profile straddling the axis would sweep into a self-intersecting solid; one merely touching it
  would collapse the faces along the axis to zero width. To bulge the other way, mirror the
  profile's `U` values. (Solids of revolution, which need the touching case, are not supported.)
- **Faces:** a tiled `Cap` at each end (absent on a full turn) plus `points × segments` swept
  quads. Every quad of profile edge `k` is `Side<k>` **in every segment**, so
  `brush poly find --item Side0` selects the whole strip swept by your first profile edge — the
  handle you actually think in ("the inner wall of the corridor").
- **A revolve is off the integer grid by construction** (every vertex away from `θ=0` lands on
  `radius · cos/sin θ`), and uedcli never snaps coordinates for you. An off-grid **solid** brush
  throws its BSP partition planes off-grid too, which is the primary cause of slivers, T-junctions
  and holes in the built map. Prefer **`--solidity semisolid`** wherever the swept shape is detail
  rather than structure: a semisolid receives cuts but emits no world-splitting planes.

**Two stderr advisories** fire on `extrude`/`revolve` (never on stdout, and they never change the
exit status — the brush is emitted either way):

- when the emitted brush has **off-grid vertices AND is solid** (the case above; not on a
  semisolid/nonsolid brush, where it is already handled, and not on a `--mover-class` brush, which
  never partitions the world);
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

The workflow is **raise the count, then edit the keys** (mirroring the editor's own authoring flow):
`mover key count` sets how many keys exist; `mover key move`/`rotate` then edit an existing key by
index (they never grow the count).

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
  **non-destructive** — it only changes the count, never the stored key values; lowering the count
  leaves the now-inactive keys' offsets dormant, so raising it again restores them. Out of range is a
  clean error naming the value. It is **exactly equivalent to `actor prop set <name> NumKeys=<n>`**
  (`NumKeys` is a first-class settable prop; `KeyPos`/`KeyRot`/`KeyNum` remain `mover key`-only).
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
and instant — no editor, no container. (They do need the game's `.u` packages: a Mover in the piped
set is refused, and that is a class-hierarchy question — see [Projects](#projects-uedclitoml).)

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
like block-minus-notch. `deintersect` gives you the solid that exactly fills what the set carves —
the door **plug** that fits a subtracted doorway, which is why it pairs with `--mover-class`.

```bash
uedcli actor find --folder castle.door | uedcli actor show - | uedcli brush intersect - | uedcli actor add -
uedcli stash show arch                 | uedcli brush deintersect -                     > plug.t3d
uedcli prefab show archway             | uedcli brush intersect -                       | uedcli actor add -
```

Every tier feeds them through its own `show` verb — which is why there are no `stash`/`prefab`
intersect verbs.

## Input rules

- **Stdin order IS the CSG order**, and is never re-sorted. A mixed add/subtract set is
  order-dependent (the last operation on a region wins): `add block, subtract notch` carves the
  block, the reverse order subtracts into empty space and leaves the block whole. You control the
  order through the pipe.
- **Empty stdin is a clean no-op** (exit 0), like every generator.
- **Non-brush actors and Movers are refused** (exit 2, naming them) rather than skipped — a merge
  quietly missing a piece reads as a complete answer. Narrow the pipe (`actor find --kind brush …`).
- **Scaled source brushes are refused**, naming the brush: bake the scale first with
  `brush apply-transform <name>`. (A gap in the CSG core, not in these verbs.)

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
  `solid` included): a mover always keeps the source per-face solidity, so there is nothing to
  override — allowing it would be a footgun.

## Placement — `--origin` and `--pivot`

A brush's world geometry is `world = Location + R·(vertex − PrePivot)`, so it is moved by
`Location` and rotates about `PrePivot`. The raw CSG output has `Location=(0,0,0)` and world-space
vertices, which would make a mover rotate about the *world origin*. So the result is **re-centred**:

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
- a **scaled source brush** (exit 2, naming it) — bake it first with `brush apply-transform <name>`;
- a set with **no additive** (`intersect`) or **no subtractive** (`deintersect`), pointing you at
  the other verb;
- a **name list** on stdin instead of a T3D snippet (the two stdin conventions are easy to mix up).

Empty stdin is the one silent case: a clean no-op, exit 0, like every generator.

## Disjoint results

A set can merge into several disconnected solids (two far-apart clusters). They stay **one actor**
(as in UnrealEd) and the verb says so on stderr with the component count. There is deliberately no
`--split`: run the verb per subset for independently movable pieces — the input is a set, so that
is already a natural pipe.

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

# `actor preview` — the wireframe viewer

A self-rendered **color wireframe** image (no editor) so you can see geometry and map **poly index ↔
face**. Reads named actors from the current level, model-side. (Renamed from `brush preview`; the
`stash preview`/`prefab preview` variants keep their names.)

```
actor preview [<names…> | --from-t3d <FILE…|->]
              [--layout quad|single|breakdown] [--view top|front|side|iso]
              [--brush-colors csg|legend] [--annotate SELECTORS]
              [--frame BRUSH[:IDX] | X0,Y0,Z0,X1,Y1,Z1] [--frame-tightness N]
              [--highlight POLY|NAME ...] [--focus BRUSH]
              [--show collision,light-range,sound-range]
              [--iso-angle 30] [--size 1024] [--out PATH]
```

- **Target set** — actor names, or `-` to read a newline name list from stdin (`actor find … | actor
  preview -`), or **`--from-t3d <FILE…|->`** to render the actors in one-or-more T3D files (or a `-`
  stdin snippet: `brush build spiral | actor preview --from-t3d -`). Multiple files concatenate in
  order; `-` is the sole value. `--from-t3d` is mutually exclusive with names.
- **`--layout {quad,single,breakdown}`** (default `quad`) picks the pane layout. **`quad`** is the
  UED-style 2×2 grid (Top / Front / Iso / Side). **`single`** renders one `--view`. **`breakdown`** is
  described next.
- **`--layout breakdown`** renders a near-square **grid** of panes that walks the scene **actor by
  actor**. Pane 0 is the whole scene in CSG colour — a plain spatial **map** with **no labels** (no
  legend, no names, no on-face numbers); you identify each actor from its own captioned pane below. Each
  following pane is **one actor**: a **brush** is `--focus`ed and zoomed to its own AABB with all its
  faces numbered; a **point actor** is zoomed to a box around its Location with its marker/sprite drawn
  (no face numbers — a point has none). Every pane is captioned with the actor name. Panes follow the
  actor-set order (brushes and point actors intermixed as they appear) and are square cells laid out in
  `ceil(sqrt(N))` columns (a near-square grid, slightly wider than tall). It is one view (uses `--view`);
  composes with `--annotate` (the per-brush number set), `--brush-colors`, `--highlight` (a highlighted
  poly re-lights in every pane), `--show`, `--size`. It sets its own focus and zoom per pane,
  so **`--focus`/`--frame` are ignored** under it. The brush + point-actor counts are reported on stderr;
  breakdown is a small-selection inspector (it warns past ~16 panes — a whole level makes an unusably
  large grid, and point actors now add panes too, so subset first).
- **The wireframe is coloured by CSG op** (UnrealEd's legend): added-solid **blue**, subtracted
  **gold/yellow**, semi-solid **pink**, non-solid **green**, mover **magenta**; front faces darker,
  obscured/back faces lighter. This is the CSG cue — it says what each brush *does*.
- **`--brush-colors {csg,legend}`** picks the wireframe's colour source. `csg` (default) is the CSG-op
  colouring above. **`legend`** instead draws each brush's wireframe in *its own per-actor legend tint*
  — so every brush is a distinct colour matching its legend swatch (you trade the CSG cue for telling
  same-op brushes apart at a glance without reading numbers).
- **The legend never overlaps the geometry.** A top band is reserved for the legend panel and the
  geometry is framed below it. This applies to `quad`/`single`; **`breakdown` draws no legend at all**
  (every pane, including the overview, is legend-free — actors are identified by their captioned panes).
- **Labels use a HYBRID per-actor TINT + a LEGEND.** The CSG palette has only ~5 hues, so two brushes
  with the SAME CSG op share ONE wireframe colour; to tell them apart, each **actor** is assigned a
  distinct **tint** from a categorical palette (~10 hues, cycled). A brush's **on-face poly-index
  decal** (both the painted digits and their 6/9 baseline underline) carries that tint; a point actor's
  **marker** is drawn in it. A **legend** in the top-left maps each tint → actor **NAME** (a filled
  square for a brush, a filled diamond for a point actor). **Actor names live in the legend, not on
  the geometry** (to declutter) — so a number shared across brushes (every brush has a face `1`) is
  disambiguated by its tint + the legend, and you read *which brush* from the legend rather than a
  label crowding the wireframe. If a scene has more labelled actors than fit the legend's height, the
  overflow collapses into a final `+N MORE` row rather than spilling off the frame.
- **Poly face indices are painted ON the face (on-face numbers).** Each face's index is a **number
  texture lying flat in the face's own 3-D plane** — it foreshortens with the surface under the
  projection, so it reads as decaled onto the geometry (not a callout off to the side). It is placed at
  the **roomiest spot on the face** (the largest spot where it fits *inside* the face polygon — off to
  a side on a triangle/arch, not centred over a narrow point) and sized to **75% of the largest number
  that would fit there**, so it's as big as the face comfortably allows. Sizing always assumes a
  **2-digit width** and centres the actual number in that slot, so a single digit (`5`) renders at the
  same scale as a two-digit one (`12`) — a consistent look across a scene rather than lone digits
  ballooning. Numbers **hang by gravity** on
  walls and slopes (the strokes run straight up the surface) and align to the **world Y axis** on
  floors/ceilings/caps (a consistent orientation, not an arbitrary roll), with a short underline as a
  `6`/`9` cue. This is the only way poly faces are labelled — there is no leader-box
  mode.
- **Overlapping numbers: a tiny nudge, then a white outline.** Because two faces can project close
  together on screen — including two faces of the **same brush** — numbers can overlap. Two things keep
  them legible. First, a **deliberately tiny reshuffle**: a number that overlaps another (or a
  point-actor marker) may **shrink by at most 10%** and **move by at most 10% of its own diagonal** to
  reduce the overlap; it never makes a big jump or shrinks to a speck, so numbers stay big and roughly
  where you'd expect. A number with no overlap doesn't move at all. Second, wherever two numbers still
  overlap, a thin **white outline (1 screen pixel, constant width at any zoom)** is drawn just outside
  the strokes in the overlap, so you can still trace each number's shape apart from the other. Numbering
  is **facing-blind**: front AND back faces get a number (so the front/back distinction is carried by
  opacity, below, not by hiding back faces), and `--annotate`'s `poly` selectors still choose *whether*
  poly numbers draw at all (e.g. `none`, `poly:hi`). (Under `--layout breakdown` each brush is alone in
  its pane, so cross-brush overlap disappears and the outline only marks the occasional same-brush
  overlap.)
- **On-face numbers are graded translucent by depth.** A visible face is drawn at 56% opacity, and each
  face in front of it keeps 60% of that (near faces clear, buried faces faint), so the nearer faces'
  numbers stand out. A face counts as "in front" under the **self-or-solid** rule: a nearer front face
  that covers it dims it **iff** that occluder is a **solid** CSG op (added/semi-solid/mover) **or**
  belongs to the **same brush**. So a subtract/hollow room's near walls dim its own far walls (depth
  grading), while a solid brush sitting **inside** a room is **not** dimmed by the room's walls; solid
  brushes still dim across brushes. A number that would be **unreadable on screen** is omitted — a
  **view-dependent** verdict: a face too small, too edge-on, or too zoomed-out to read gets no number,
  and the same face is numbered once it's big enough on screen (zoomed in, or in its `--layout
  breakdown` pane). There is no fallback for an omitted face.
- **`--annotate`** takes a **comma-set of selectors** (the drawn labels are their **union**). A bare
  **kind** means ALL of that kind; each colon **filter** narrows; multiple filters on one selector
  intersect; commas union. Tokens are case/whitespace-insensitive.
  - Kinds: **`poly`** (on-geometry face indices), **`name`** (actor names — i.e. their **legend rows**).
  - `poly` filters: **`vis`** (retained as an inert alias of bare `poly` — see the note below),
    **`hi`** (highlighted faces only).
  - `name` filters: **`brush`** (brush names), **`point`** (point-actor names), **`hi`**
    (highlighted actors). (`highlighted` is accepted as a synonym for `hi`.) A `name:*` selector now
    controls whether an actor is **listed in the legend**; `poly:*` controls on-geometry indices.
  - Examples: `name:brush` = brush names only, no indices; `poly:vis` = every face (same as bare
    `poly`); `name:brush:hi,name:point` = highlighted brush names ∪ all point names.
  - Whole-value keywords (stand alone): **`none`** = nothing; **`all`** = `poly,name` (every face
    incl. back-facing + every name); **`highlighted`** = `poly:hi,name:hi`.
  - **Default:** `poly:vis,poly:hi,name` — face indices (painted on-face) + all names. (On-face
    numbering is facing-blind, so `poly:vis` — now an inert alias of bare `poly` — numbers every face;
    opacity, not presence, is the front/back cue. `vis` is kept only so pre-facing-blind specs still
    parse.)
  - An invalid token is a clean named error (e.g. `--annotate: unknown filter 'foo' for kind 'poly'`).
- **Point actors** render as their **DT_Sprite** billboard (footprint `DrawScale·USize × DrawScale·
  VSize`) or, for DT_Mesh/DT_None (or a missing/undecodable sprite), a small **marker** (a filled
  diamond in the actor's tint, with a white halo so it stands out) at Location. Its **name is in the
  legend**, not beside the marker.
- **`--frame TARGET`** frames a target to fill the view (frames only — never highlights), in one of two
  forms. A **selector** — a bare **`BRUSH`** name frames that actor's whole AABB, or **`BRUSH:IDX`**
  frames ONE poly (a multi-index / `:all` value is an error). OR an **explicit world AABB** — six
  comma-separated numbers **`X0,Y0,Z0,X1,Y1,Z1`**, framed **exactly** (+ a small margin). **`--frame-
  tightness N`** (default `0.8`, must be in `[0, 1]`) sets framing tightness toward a **selector**
  target only: `0` = whole-set frame, `1` = tightest (target + margin); no `--frame` ⇒ no-op. An
  explicit-AABB `--frame` is always framed exactly — `--frame-tightness` does NOT modulate it.
- **`--highlight POLY|NAME`** emphasises a poly or an actor; repeatable, no effect on framing. A
  token **with a colon** is a poly selector `BRUSH:IDX` (set form `BRUSH:1,2` / `BRUSH:all` too) — those
  polys draw in their brush's vivid CSG hue + a bolder line. A token **without a colon** is an
  **actor name**: a brush actor highlights **all** its polys; a point actor gets **corner brackets**
  (a selection reticle) framing its sprite/marker. An unknown name / a selector on a non-brush → clean
  exit 2.
- **`--focus BRUSH`** spotlights ONE brush: only it shows face indices (in its tint), and
  every OTHER brush recedes to a **faint (dimmed)** wireframe — for reading a single brush's faces in a
  busy scene. All actor names still appear in the legend. **`--highlight` overrides `--focus`**: a
  highlighted poly/actor still draws vivid+bold on top and keeps its index even when its brush is not
  the focus (focus dims; highlight re-lights specific elements). An unknown name / a point actor →
  clean exit 2.
- **`--show SET`** is a **comma-set (union)** of range overlays to draw for **POINT** actors (default:
  none). Members: **`collision`** — a faint light-red collision cylinder for every colliding point actor
  (`bCollideActors`): a circle in TOP, a `2·CollisionRadius × 2·CollisionHeight` rect in FRONT/SIDE, an
  8-sided wire cylinder in ISO (`CollisionHeight` is a HALF-height); **`light-range`** — a faint orange
  sphere of a light's reach (`25·(LightRadius+1)` UU); **`sound-range`** — a faint blue sphere of an
  AmbientSound's reach (`25·(SoundRadius+1)` UU). Brush actors (including movers) are excluded, so a
  brush preview needs no class schema. An unknown member is a clean named error.
- `--out PATH` is the host image path. **A preview is always a PNG** (written via **Pillow**, the
  LLM-viewable form — there is no flag and no other way to get raw PPM out of the CLI). Whatever
  extension you pass is **replaced** by `.png`, so `--out shot.jpg` writes `shot.png`, and an
  extensionless `--out shot` writes `shot.png`. `--out` is **optional**: with no `--out`, a unique
  temp file is minted (`uedcli-preview-*.png`). Either way the **absolute path actually written is
  always printed to stdout**.

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
stash capture [--id ID] [--force] [--from-t3d <FILE…|->] [<names…>]
stash show    <id> [<names…>] [--summary]        # T3D dump (default), or a bbox/class/poly summary
stash list                                        # register ids
stash preview <id> [<names…>] <preview opts>      # composite wireframe (like actor preview)
stash drop    <id>
stash apply   <id> [--at X,Y,Z] [--group NAME | --no-group] [--folder PATH]
stash promote <id> --as <name> [--force] [--prefab-dir DIR]
```

- **`stash capture`** takes actors from the current level (empty names + `--from-t3d` = all), or from
  one-or-more T3D files (or a `-` stdin snippet) via **`--from-t3d <FILE…|->`** (multiple concatenate;
  `-` is the sole value; `names` still selects a subset of the source). `--id` defaults to an
  auto-slug from the first actor name; `--force` overwrites an existing id. Capture normalizes the set
  to its bbox-min corner and records the original world anchor. It reads the game's `.u` packages
  (an ingested Mover is folded to its base pose, which needs the class hierarchy — see
  [Projects](#projects-uedclitoml)).
- **`stash apply`** is a **model-side merge into the current level** (no editor): it translates to
  the placement anchor, auto-allocates fresh names, sets Group, appends order, and unions the set's
  packages. **Without `--at`, it applies at the captured world anchor.** `--group` defaults to the id;
  `--no-group` strips it; `--folder PATH` also stamps a uedcli-side folder (independent of `--group`).
- **`stash promote`** copies a register entry into the durable prefab library (the sharing step).
- **CSG-combining a stash** is not a stash verb: pipe it into the generator instead —
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

# `level materialize` — build the map file

**`level materialize`** is the pure build step: it drives **UnrealEd** to compile the selected
level's T3D trunk into the `.dx`/`.unr` **build artifact** — map-file output only (the T3D tree is the
source, reached via git, not a build target).

```
level materialize [--out OUT] [--overwrite] [--no-verify] [--keep-build]
```

- **`--out OUT`** names the destination map file (`.dx` or `.unr`). It **refuses to overwrite an
  existing file** (exit 2) unless **`--overwrite`** is given.
- A **post-build verify** (H3) confirms the rebuilt map matches the intended trunk; **`--no-verify`**
  skips it (debugging / known-buggy verify), and **`--keep-build`** copies the built map to the
  project's `.uedcli/tmp/` on a verify FAILURE instead of discarding it.
- The verify compares the built map against the trunk in UnrealEd's own terms, which means it needs
  each actor class's **defaults** out of the game's `.u` packages. They are resolved *before* the
  editor starts, so an actor whose `Class=` is not fully qualified (`Package.Class`) — or whose
  package is missing from the configured paths — **exits 2 in about a second**, naming the actor and
  the class, instead of failing after a full build. `--no-verify` does not need them.
- Committing is your own `git`. Lightmaps and rebuilt BSP are **regenerable build output**, never
  part of the level's identity.

*(A native, in-process Rust build is under development, targeting byte-identity with UnrealEd's build
of the same trunk; the editor path above remains the current one.)*

---

# `level preview` — freely-posed still shots

**`level preview`** renders **still first-person shots** of the current level from arbitrary camera
poses. It is a **two-tier** command behind one verb, sharing one batched **pose grammar**. It is
read-only — it never writes the trunk or a committed map.

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
  later batches skip the boot. It is the default because it shows lighting/meshes/sky and because the
  offline draft mis-renders overlapping-subtract geometry silently.
  - **`--map PATH`** previews a **prebuilt** map file instead of the selected trunk (skips the
    materialize cache); actor-relative shots resolve against the running game.
  - **`--rebuild`** forces a fresh materialize under a new unique name (guarantees the game reloads
    it).
  - **`--keep-alive`** PINs the warm container (disables idle death) and prints its **noVNC URL** for
    live inspection (dev-debug; release the pin with `docker rm -f`).
  - Without `--map`, this tier **materializes the trunk internally** — post-verify included, and
    with no `--no-verify` escape here — so it inherits `level materialize`'s requirement that every
    actor class be fully qualified and its package present on the search paths. An unresolvable
    class exits 2 naming the actor, before anything is built.
- **`--native`** — the opt-in offline draft. **No container at all**: the native CSG core carves the
  trunk in-process and a software rasterizer renders **textured, flat-shaded** perspective stills in
  seconds. Movers render at base pose; point actors, meshes, sky, lighting, and translucency do NOT
  render (translucent/masked faces render opaque). `--fov DEG` (default 75) applies here; `--map` /
  `--rebuild` / `--keep-alive` are rejected with `--native`.

**Shared:** `--out-dir DIR` (required unless `--list-actors`; created if absent), `--size WxH`
(default 1280×960).

## Discovery mode

**`--list-actors Package.Class`** (with `--game --map`) prints the running map's actors of that class
as `Name x y z` instead of shooting (e.g. `Engine.PathNode` blankets every walkable spot) — so you
can discover `@Actor` refs to compose into shots. `--sample N` prints N evenly-spread; no screenshots,
`--out-dir` not needed.

---

# Texture catalog (offline, no level needed)

The `texture` verbs maintain a tracked, hash-versioned catalog of every texture package on the
substrate path. Classification (`tags[]`, `description`, named colors) accretes onto each entry and is
never clobbered by a re-sync. Every verb takes `--catalog-dir DIR` (default: the resolved project's
catalog dir — the `uedcli.toml` `catalog` key, or `<root>/texture-catalog/`).

```bash
# discover + export packages; build/refresh the per-package manifests
uedcli texture sync [--package CoreTexMetal] [--force]

# list catalog entries (offline, manifest-only), optionally filtered by state
uedcli texture list [--package P] [--unclassified | --classified | --stale | --removed]

# search refs by text/tag/color (ranked)
uedcli texture search wall --tag metal --color grey

# the tag vocabulary + occurrence counts (curbs drift)
uedcli texture tags [--package P]

# classification progress + worklist
uedcli texture classify status [--full] [--package P]

# record LLM/human classification (replaces the provided fields)
uedcli texture classify set CoreTexMetal.Area51Wall_A \
    --tags metal,wall --description "riveted metal wall panel" --colors grey
```

Each entry carries: `ref` (the address for `brush poly set --texture`, e.g.
`CoreTexMetal.Area51Wall_A`), `image_hash` (sha256 of the decoded pixels — tracks identity across
renames), auto-derived dominant `colors` (overridable), open `tags[]` / `description`, and the
`stale`/`removed` flags. Manifests live in the tracked `catalog` dir; viewable PNGs land under the
per-user cache `~/.uedcli/cache/textures/<package>/` (never the in-repo `.uedcli/`).

---

# Class discovery (offline, reads the game `.u`)

```bash
# browse actor classes as an indented inheritance TREE (rooted at Engine.Actor)
uedcli class list [--depth N|all] [--subclass-of Package.Class] [--package P]
                  [--flat] [--include-non-actor] [--include-abstract]

# a class's OWN editable props grouped by editor category + super chain + placeable/abstract flags
uedcli class show <Package.Class> [--depth N|all] [--category NAME]
```

- **`class list`** auto-fits ~60 lines; abstract classes are marked `*`, a collapsed node shows its
  hidden direct-subclass count as `(N)`. `--flat` gives a pipeable one-`Package.Class`-per-line list;
  `--subclass-of` reroots (e.g. `--subclass-of Engine.Mover`); `--depth all` for the whole tree.
- **`class show`** is the UnrealEd property-browser view (Movement/Display/Lighting/…): own editable
  props by category, non-editable internals hidden, inherited props collapsed to per-category counts.
  `--depth N|all` expands inherited props (tagged with their source class); `--category NAME`
  (repeatable) shows only that category, expanded over the whole chain.
- Reading a class means reading its whole **super chain**, so if an ANCESTOR's package is missing
  from the search path (or unreadable), `class show` **fails with exit 2 naming that package** —
  `cannot read schema for DeusEx.Flare: package 'Engine' (needed for Engine.Actor) not found on the
  schema search path …` — instead of printing the class's own properties as if that were the full
  list. (A missing package for the class you NAMED is caught earlier, as `unknown class: …`.)

---

# Substrate & cache utilities

- **`substrate stub [package] [--force] [--list]`** — convert a Deus Ex v68 code package (`.u`) into
  a UED22-loadable v69 "stub" (mesh-preserving; the editor is v69-authoritative). `--list` prints the
  stub cache manifest without building.
- **`cache clear`** — delete the persistent package-schema cache (`~/.uedcli/cache/schema`); it is
  pure derivable throwaway and rebuilds on the next command (escape-hatch / reclaim old
  decoder-version dirs).
- **`cache gc [--max-bytes N] [--max-entries N]`** — *shrink* that cache instead of emptying it:
  delete the orphaned old decoder-version (`v<N>/`) dirs, then evict entries least-recently-used
  until the cache fits its cap (default 256 MiB, no count cap; `N=0` evicts everything). Cached
  entries are derivable, so an evicted one just re-decodes the next time it is needed. A GC already
  runs automatically after a cache write — reach for this verb only to reclaim disk on demand. Prints
  a one-line summary; a negative cap exits 2.
