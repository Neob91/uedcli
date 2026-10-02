+++
priority = "p3"
kind = "chore"
summary = "Slice 6: package_path_or_exit moved to resources; targets aliased in dispatch"
+++

# Slice 6: two implementation choices worth recording

Both behavior-preserving. `dispatch._package_path_or_exit` moved to `resources.package_path_or_exit`
(needed by `cli.ingest`, which cannot import `cli.dispatch`; test seam moved to
`test_class_discovery.test_package_path_seam_without_games_config_raises_clean`). `cli.targets` is
imported into dispatch as `from . import targets as target_names` to avoid an `UnboundLocalError`
against the pervasive local `targets` variable in `_dispatch`; drop the alias once slices 7-10 move
those handlers into `cli.commands` and the collision disappears.
