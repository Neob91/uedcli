+++
priority = "p3"
kind = "chore"
summary = "Slice 6: package_path_or_exit moved to resources; targets aliased in dispatch"
+++

# Slice 6: two implementation choices worth recording

Both are behavior-preserving; noted so a later reviewer/slice isn't surprised.

## `_package_path_or_exit` → `resources.package_path_or_exit`

The plan lists only `read_t3d_input`, `read_t3d_files`, `validate_ingest_actors` for `cli.ingest`.
`validate_ingest_actors` needs project + composed-package-path resolution, which lived in
`dispatch._package_path_or_exit`. `cli.ingest` cannot import `cli.dispatch` (later owner), so that
helper had to move to an earlier owner. It resolves project + games-config + composed files and raises
the canonical `resources.NO_GAMES_CONFIG`/`NO_PACKAGE_PATH` — squarely `cli.resources`' domain — so it
became `resources.package_path_or_exit`. Its other caller, `dispatch._validate_texture_ref` (brush,
stays in dispatch), now calls `resources.package_path_or_exit` too. Test seam moved:
`test_class_discovery.test_package_path_seam_without_games_config_raises_clean`.

## `cli.targets` imported into dispatch as `target_names`

`_dispatch` (the ~1200-line route) uses a pervasive local variable `targets` (poly/rotate/scale/bake
branches). A bare `from . import targets` would make `targets` function-local across all of `_dispatch`
and break every `targets.resolve_target_names(...)` reference with `UnboundLocalError`. So dispatch
imports it as `from . import targets as target_names`; `target_names.resolve_target_names(...)` is a
runtime module-attribute lookup, so patching the owner (`targets.resolve_target_names`) still reaches
it. When these handlers move into `cli.commands` families (slices 7-10) the collision disappears and
the alias can be dropped.
