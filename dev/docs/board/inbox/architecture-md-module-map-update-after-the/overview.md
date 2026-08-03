+++
priority = "p2"
kind = "owner-question"
summary = "architecture.md module-map + dispatch._*/cli.py references are stale after the command-layer reorg; proposed exact edits below need a yes."
+++

# architecture.md module-map update after the command-layer reorg

## Why this needs a yes

The command-layer reorg (commit `d4145f0`) split `uedcli/cli.py` and `uedcli/dispatch.py` into the
`uedcli/cli/` package. It deliberately did NOT touch `dev/docs/architecture.md`, so the file's
"Command API" module-map bullet and ~40 `dispatch._*` / `cli.py` references now point at files and
symbols that no longer exist. Editing `architecture.md` needs the owner's approval (the `dev/docs`
gate), so this item proposes the exact text and waits.

This is the ONLY reorg doc deliberately deferred. The reorg's own commit already updated the
rationale docs (`rationale/cli.md`, `mapimport.md`, `reported-coordinates.md`, `surface.md`,
`userdocs.md`) and the code comments; no spike or unrealed doc referenced the old
layout. `architecture.md` is the last stale doc.

Every mapping below was verified against the code, not the reorg plan, and no old `uedcli/cli.py` /
`uedcli/dispatch.py` remains. `tool_assets.py` and `userdocs.py` stay at `uedcli/` — untouched by the
reorg — so the bullet's text about them is correct and kept.

## New layout (one line per owner)

- `cli/main.py` — parser assembly (`build_parser`, `main`).
- `cli/dispatch.py` — `_dispatch` (family routing, function-local imports) + `dispatch()` (the
  ordered process-error guard). `dispatch()` keeps its name and home, so bare references to the
  guard stay correct.
- `cli/parsers/` — one registrar per family + `_arguments.py` (shared arg types/converters/flags:
  `parse_coord`, `parse_decimal`, `parse_bbox`, `parse_pan`, `_tree_flag`).
- `cli/commands/` — one owner per family. `actor/` and `brush/` are packages (`routes.py` + feature
  modules); the rest are flat modules plus `mover.py`.
- Cross-family owners directly in `cli/`: `errors.py`, `resources.py`, `level_sources.py`,
  `ingest.py`, `targets.py`, `rendering.py`, `placement.py`, `generators.py`.

## Edit A — the "Command API" module-map bullet (lines 62-74)

**Before** (the opening clause):

> - **Command API** — `cli.py` (argparse verb surface), `dispatch.py` (routes verbs, records
>   one command per mutation).

**After:**

> - **Command API** — the `cli/` package. `main.py` assembles the argparse surface
>   (`build_parser`/`main`); `parsers/` holds one registrar per family plus `_arguments.py` — the
>   shared arg types/converters/flags (`parse_coord`/`parse_decimal`/`parse_bbox`/`parse_pan`,
>   `_tree_flag`). `dispatch.py` routes each verb to its family with a function-local import (so one
>   family loads no other) and wraps `_dispatch` in the ordered process-error guard `dispatch()`.
>   `commands/` holds one owner per family — `actor/` and `brush/` are packages (`routes.py` + feature
>   modules), the rest flat modules plus `mover.py`. Cross-family owners sit directly in `cli/`:
>   `errors.py`, `resources.py` (project / class-index / schema+defaults / mover-index /
>   texture-resolver seams), `level_sources.py` (the `LevelSource` classes + `resolve_level_source` /
>   `resolve_level_only`), `ingest.py`, `targets.py`, `rendering.py`, `placement.py`, `generators.py`.

(Drops "records one command per mutation" — there is no command log in the git-native model; the file
says so elsewhere: "no per-command blob log". Flagging the drop because it is more than a re-home.)

The rest of the bullet (the `Relative CLI file paths … resolve against the cwd`, `tool_assets.py`,
`userdocs.py`, and the guard-taxonomy sentences at lines 64-86) stays as written except edit B's
`dispatch._dispatch_docs` row.

## Edit B — named-reference substitutions

Each row is an exact find→replace: the old symbol and its verified new owner. Grouped by target.

### To `resources.py` (public seams — no leading underscore)

| Line | Old | New |
|------|-----|-----|
| 973  | `dispatch._mover_index` | `resources.mover_index` |
| 1014 | `dispatch._mover_index` | `resources.mover_index` |
| 1493 | `dispatch._mover_index` | `resources.mover_index` |
| 1494 | `_class_index` | `resources.class_index` |
| 1063 | `dispatch._default_location_for` → `_class_defaults` | `resources.default_location_for` → `resources.class_defaults` |
| 2494 | the `_class_defaults` seam; a `_texture_resolver` | the `resources.class_defaults` seam; `resources.texture_resolver` |
| 1193-1195 | `dispatch.py` wires the handlers plus FOUR mockable seams … `_class_schema` … `_class_defaults` … `_struct_members` … `_enum_names` | `commands/actor/prop.py` wires the handlers plus FOUR mockable seams … `resources.class_schema` … `resources.class_defaults` … `resources.struct_members` … `resources.enum_names` |

### To `level_sources.py`

| Line(s) | Old | New |
|------|-----|-----|
| 331  | seam (all in `dispatch.py`): | seam (all in `level_sources.py`): |
| 327, 328, 359, 363, 1578, 1778 | `_resolve_level_source` | `level_sources.resolve_level_source` |
| 373, 841 | `_resolve_level_only` | `level_sources.resolve_level_only` |

### To `parsers/_arguments.py`

| Line | Old | New |
|------|-----|-----|
| 132  | `parse_bbox` (`cli.py`) | `parse_bbox` (`parsers/_arguments.py`) |
| 392  | `cli.parse_coord` | `parse_coord` (`parsers/_arguments.py`) |
| 394  | `cli.parse_decimal` | `parse_decimal` (`parsers/_arguments.py`) |
| 363  | `cli._tree_flag(parser)` | `_tree_flag` (`parsers/_arguments.py`) |

### To `commands/`

| Line | Old | New |
|------|-----|-----|
| 74   | `dispatch._dispatch_docs` | `commands/docs.py`'s `run` |
| 732  | `dispatch._dispatch_docs` | `commands/docs.py`'s `run` |
| 134  | `dispatch._find_class_filter` | `commands/actor/query.py`'s `_find_class_filter` |
| 274  | `substrate stub` handler in `dispatch.py` | `substrate stub` handler in `commands/substrate.py` |
| 442  | `dispatch._stash_register_for` | `commands/stash.py`'s `_resolve_stash_register` (renamed) |
| 865  | `dispatch._level_preview` | `commands/level.py`'s `_level_preview` |
| 981  | `dispatch._level_list` | `commands/level.py`'s `_level_list` |
| 989  | `dispatch._level_status` | `commands/level.py`'s `_level_status` |
| 1000 | `dispatch._project_show` | `commands/project.py`'s `run` (renamed) |
| 1010 | `dispatch._event_graph` | `commands/event.py`'s `_event_graph` |
| 1039 | `dispatch._ingest_actor_t3d`; `_validate_ingest_actors` | `commands/actor/edit.py`'s `_ingest_actor_t3d`; `ingest.validate_ingest_actors` |
| 1438 | `dispatch._capture_from_t3d` | `commands/stash.py`'s `_capture_from_t3d` |
| 1576 | `dispatch._level_import` + `_resolve_import_dest` | `commands/level.py`'s `_level_import` + `_resolve_import_dest` |
| 1823 | `dispatch._print_poly_selectors` | `commands/brush/poly.py`'s `_print_poly_selectors` |
| 1957 | `dispatch._check_positive_build_dims` | `commands/brush/build.py`'s `_check_positive_build_dims` |
| 1962 | `dispatch._POSITIVE_BUILD_DIMS` | `commands/brush/build.py`'s `_POSITIVE_BUILD_DIMS` |
| 2096 | `dispatch._advise_swept_brush` | `commands/brush/build.py`'s `_advise_swept_brush` |

### To `placement.py` / `targets.py` / `ingest.py` / `rendering.py`

| Line | Old | New |
|------|-----|-----|
| 464  | `dispatch._apply_set` | `placement.apply_set` |
| 1047 | `dispatch._resolve_target_names` | `targets.resolve_target_names` |
| 1357 | `dispatch._validate_ingest_actors` | `ingest.validate_ingest_actors` |
| 2209 | `dispatch._preview_movers` | `rendering.preview_movers` |
| 2298 | `dispatch._render_breakdown_grid` | `rendering._render_breakdown_grid` |
| 2441 | `dispatch._render_breakdown_grid` | `rendering._render_breakdown_grid` |
| 2309 | `_resolve_focus` in dispatch | `rendering._resolve_focus` |

### Generator verbs (line 787)

**Before:** **Generator verbs (stdout T3D producers)** — `dispatch.py` handles these without
resolving a selected trunk *level*
**After:** **Generator verbs (stdout T3D producers)** — the actor/brush family routes
(`commands/actor/routes.py` / `commands/brush/routes.py`) handle these source-free (shared
post-processing in `generators.py`), without resolving a selected trunk *level*

### "Adding a verb" steps (lines 1776, 1778)

- L1776 `1.` `cli.py`: add the parser under … → `1.` `parsers/<family>.py`: add the parser under …
- L1778 `2.` `dispatch.py`: content verbs resolve the selected trunk level via
  `_resolve_level_source(args)` → `2.` `commands/<family>`: content verbs resolve the selected trunk
  level via `level_sources.resolve_level_source(args)`

### The three preview-data seams (lines 2492-2494)

`_preview_render_data`, `_preview_point_data`, `_resolve_point_render` all moved to `rendering.py`.
The surrounding prose "**`preview.py` stays resolver-free** — dispatch computes the `PointRender`s in
…" reads as stale (rendering.py, not dispatch, computes them). Proposed reword: "… — `rendering.py`
computes the `PointRender`s in `_preview_render_data`/`_preview_point_data`/`_resolve_point_render`,
resolving each field instance-else-class-default via the `resources.class_defaults` seam and decoding
sprites through `resources.texture_resolver`".

## Not proposing exact text (owner's call)

Beyond the named symbols above, the file uses the bare word "dispatch" as prose for "the command
front door" in ~10 spots (lines 121, 141, 968, 1473, 1956, 1971, 2047, 2052, 2276, 2444, 2486, 2651
— e.g. "the dispatch find handler", "at the dispatch seam", "Parsed in dispatch", "the stitch lives
in dispatch"). `dispatch()` still exists in `cli/dispatch.py`, but the work these describe now lives
in the family / cross-family modules, so several read as loosely wrong. Rewording is style, not
structure — flagged for the owner rather than guessed at.

Likewise the guard-taxonomy sentence (lines 75-86) names pre-reorg error classes
(`_SelectionExit`/`_ProjectError`); the reorg moved these to `cli/errors.py` as
`CommandError`/`ProjectError` (the guard now also catches `CoordinateError`/`ClassRefError`/
`SchemaError`/`CacheWriteError`/`OSError`). That is an accuracy drift wider than a re-home, so it is
flagged, not rewritten here.
