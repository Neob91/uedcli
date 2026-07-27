+++
priority = "p?"
kind = "unknown"
summary = "Stub-build + texture-sync discovery config-driven, then unified onto ONE mount set"
+++

# Stub-build + texture-sync discovery config-driven, then unified onto ONE mount set

— BUILT
2026-07-14. `texture sync` is project-scoped: discovers EVERY package (all extensions — a `.u` can
hold textures) from `config.composed_search_files(project, user_config)` (project shadows base) and
writes the catalog to `<project>/texture-catalog/` (`config.project_catalog_dir`). Stub-build sources
its v68 `.u` from the whole composed search path (one `search_dirs`, first-`.u`-wins), threaded
through `stub_missing_packages`/`ensure_stub`/`compute_cache_key` and `stub_closure.resolve`;
`substrate stub` + the lazy trigger in `qualify.export_and_qualify` too. **ONE uniform mount set for
ALL containers** (editor/preview/texture/stub): `container_assets.split_dirs`/`classify_dir` DELETED;
everything mounts the whole composed set via `resource_mounts` → `/resources/<n>`. Safety = Paths
order: `/stubs` (v69) first, so a stub shadows any v68 `.u` on the editor's Paths. Retired
`packages.substrate_code_dirs`/`enumerate_substrate_packages`; `repo_paths.install_system_root`/
`install_content_dirs` kept only as test install pointers. Live-verified: `foobar` materialize
(editor unaffected with 45 v68 `.u` now on Paths — inert via demand-load + stubs-first), stub source
→ `/resources/r002/DXOgg.u`, `texture sync --package Airfield` → 108 textures → project catalog.
Decisions: decisions.md 2026-07-14 17:40 then 19:21 (the uniform-mount supersession); docs reconciled
(`architecture.md` texture-catalog + schema + stubbing + container sections). Two cold reviewers
flagged the one real risk (one HIGH): an unstubbed v68 code package referenced by materialize/preview
would demand-load the v68 `.u` and wedge the editor. GUARDED — `ensure_load`'s
`packages.unloadable_v68_packages` gate refuses it with a clean named error before any `OBJ LOAD`.
**Deferred remnant (capability):** AUTO-stub referenced packages in `level materialize` so such a
level actually builds (not just fails cleanly) — `board/inbox/`.
