+++
priority = "p2"
kind = "chore"
summary = "Host package search-dirs and container `/content` mounts can drift silently"
+++

# Host package search-dirs and container `/content` mounts can drift silently

`packages.substrate_search_dirs` lists repo-root `Sounds`, `Music`, `LUM` (plus
`System`/`Textures`/`Maps`), and `_remap_to_container` maps any of them to `/content/<sub>`. But
`uned/docker-compose.yml` mounts only `/content/{Textures,Maps,System}` plus stub
`/content/{Sounds,Music}`; there is **no `/content/LUM` mount**. Latent today, but if a `LUM`
content package lands, `ensure_load` hands the editor `/content/LUM/...` which the container can't
see — reviving the silent unresolved-load failure D4 exists to prevent. Decide where compiled
`LUM` content lives, whether the repo-root `Sounds`/`Music` search dirs are vestigial, then make
the two lists derive from one source (or add a test parsing `docker-compose.yml` that asserts
every `/content/*` remap target is mounted). Surfaced by the 2026-06-21 container-fs-isolation
review.
