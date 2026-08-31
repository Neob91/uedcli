# Level

Create, inspect, lint, import/reimport, build, and photograph a level. Most verbs operate on the
**current level**, named by `$UEDCLI_LEVEL` — see [`docs/README.md`](../../README.md#choosing-a-level).

| Command | What it does |
|---|---|
| [`level create <name>`](create.md) | scaffold a NEW level directory `maps/<name>/` with a `LevelInfo` actor (required by `materialize`); prints `to edit it: export UEDCLI_LEVEL=<name>` |
| [`level import MAPFILE --tree KIND/NAME [--overwrite]`](import.md) | decode an existing COMPILED map file (`.dx`/`.unr`) into a NEW level or stash — the inverse of `materialize`, and no editor is involved |
| [`level reimport MAPFILE --tree level/NAME [--force]`](reimport.md) | fold a hand-edited COMPILED map back into the level trunk that produced it, matching actors by NAME |
| [`level list [--json]`](list.md) | list the project's levels (trunk dirs under `<maps>`), one name per line to stdout (pipe-friendly); a count + the active `$UEDCLI_LEVEL` go to stderr |
| [`level status [--tree KIND/NAME] [--json]`](status.md) | thin read-only dashboard for the current level (or a `--tree` box): actor counts, duplicate `order_value`s, git state |
| [`level doctor [--json] [--severity …] [--category …]`](doctor.md) | statically check the level for BSP/geometry problems, fully offline |
| [`level materialize [--out OUT] [--overwrite] …`](materialize.md) | drive UnrealEd to compile the trunk into the `.dx`/`.unr` build artifact |
| [`level photo SHOT… --out-dir DIR …`](photo.md) | render still first-person shots of the current level from arbitrary camera poses |

See also: [`event graph`](../event.md) (level lint & trigger wiring), [Level lifecycle](../../usage/README.md) for the create → populate → materialize → photo → hand-edit → reimport round trip.
