# Fix the residual fixed-root duplication, or close the item as obsolete?

## Context

The item's original drift (two hardcoded search-dir lists, a missing `/content/LUM` mount) is gone:
the 2026-07-14 cutover deleted `substrate_search_dirs` and the static `/content` mounts, and the
`/resources/<n>` mounts + their remap targets now derive from ONE `mounts` list (cannot drift). `LUM`
content is just a config `paths` dir → a `/resources` mount; nothing `LUM`-specific is hardcoded.

The only residual is the **fixed** container roots `/stubs` and `/opt/UED22`, spelled independently in
`container_assets.py` (`STUBS_CONTAINER_DIR`/`UED22_CONTAINER_DIR`), `packages.py`
(`_STUBS_MOUNT`/`_BAKED_UED22`), and the compose file / Dockerfile — with no test asserting they
agree. A latent D4 risk if a mount point ever changes.

Options:

- **Recommended — small single-source fix.** `packages.py` imports the two `container_assets`
  constants (drop its own copies); add a test parsing `docker-compose.yml` + the Dockerfile that
  asserts the `/stubs` mount target and the UED22 `COPY` dest equal those constants. Low cost, closes
  the latent gap for good.
- **Close as obsolete.** Accept the fixed-root duplication (the roots rarely change); mark the item
  done, noting the cutover already removed the real drift.

## Answer

<!-- Empty = open. -->
