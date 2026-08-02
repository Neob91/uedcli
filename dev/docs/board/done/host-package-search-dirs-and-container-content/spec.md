# Spec — host search-dirs vs container mounts: detect drift

DRAFT. The item is mostly obsolete; the residual is small. Surfaces one owner decision.

## Goal

The item warns that two lists — `packages.substrate_search_dirs` (repo-root `Sounds`/`Music`/`LUM`/…)
and `_remap_to_container`'s `/content/<sub>` targets — can drift, and that a missing `/content/LUM`
mount would revive the silent unresolved-load failure D4 exists to prevent. It asks: decide where
compiled `LUM` content lives, whether `Sounds`/`Music` are vestigial, then derive both lists from one
source (or add a compose-parsing test).

## Current state — most of the item is already resolved

The **2026-07-14 asset-wiring cutover** removed the machinery the item describes:

- `packages.substrate_search_dirs` **no longer exists** (grep: zero refs). There is no hardcoded
  repo-root `Sounds`/`Music`/`LUM` search list. All package dirs now come from config `paths` —
  the game's base dirs plus the project's overlay (`config.composed_search_dirs`, `config.py:442`) —
  per `direction/projects-and-config.md` "Layered packages".
- The static `/content/{Textures,Maps,System}` + stub `/content/{Sounds,Music}` mounts are **gone**
  from `uned/docker-compose.yml` (grep: no `/content` mount). Each composed dir is now bind-mounted
  read-only at `/resources/r<NNN>` by `container_assets.resource_mounts` (`container_assets.py:41`).
- Host→container remapping (`container_assets.remap`, `container_assets.py:104`) uses the **same**
  `mounts` list the caller bind-mounted — never a recomputed second list. So the `/resources` mounts
  and their remap targets **cannot drift**: they are one source by construction.

So the item's core questions are answered by direction/design, not code:

- **Where does compiled `LUM` content live?** In a config `paths` dir like any other package content;
  it becomes a `/resources/<n>` mount automatically. There is no `LUM`-specific path or mount to
  maintain, so no `/content/LUM` gap can arise.
- **Are `Sounds`/`Music` vestigial?** The hardcoded search dirs are gone; sound/music packages
  resolve from config `paths` (per `direction/asset-catalog.md` — the catalog's `sound`/`music`
  arms). Nothing repo-root-hardcoded remains.

## The residual drift — fixed container roots, spelled in three places

Drift is eliminated for the config-driven mounts, but the **fixed** container roots `/stubs` and
`/opt/UED22` are independent string literals in more than one place, with no single source and no
test:

- `container_assets.STUBS_CONTAINER_DIR = "/stubs"`, `UED22_CONTAINER_DIR = "/opt/UED22"`
  (`container_assets.py:30-31`) — used to build the `Paths` lines and `container_search_dirs`.
- `packages._STUBS_MOUNT = "/stubs"`, `packages._BAKED_UED22 = "/opt/UED22"` (`packages.py:195-196`)
  — a **second, independent copy** used by `_remap_to_container` (`packages.py:214-236`) to map a
  stub-cache / UED22 host file to its container path.
- `uned/docker-compose.yml:22` mounts the host stub cache at `/stubs`; the Dockerfile bakes UED22 at
  `/opt/UED22` (`uned/Dockerfile:40`).

If the compose mount point or the baked UED22 path changed, the two Python constant sets and the
compose/image would silently disagree: `remap` would hand the editor a container path it can't see —
exactly the D4 silent-unresolved-load failure, just narrowed from the config dirs to the fixed roots.
No test asserts the three agree (grep: none).

## Design

Minimal, single-source:

1. **Collapse the duplicate constants.** `packages.py` imports `container_assets.STUBS_CONTAINER_DIR`
   / `UED22_CONTAINER_DIR` instead of redefining `_STUBS_MOUNT` / `_BAKED_UED22`. One source for each
   fixed root on the Python side. (`container_assets` is the lower module — it already owns the
   canonical spelling for the `Paths` generator.)
2. **Pin the compose ↔ code agreement with a test.** Parse `uned/docker-compose.yml`, assert the
   stub-cache volume's container target equals `container_assets.STUBS_CONTAINER_DIR`. UED22 is baked
   by the Dockerfile (`COPY UED22/ /opt/UED22/`), so assert `UED22_CONTAINER_DIR` matches that
   `COPY` target too. This is the "add a test parsing docker-compose.yml" the item proposed, retargeted
   from the (now-gone) `/content/*` remaps to the fixed roots that remain.
3. **Close the obsolete parts.** Record in the item that `substrate_search_dirs`, the `/content`
   mounts, and the `LUM`/`Sounds`/`Music` questions are moot post-cutover; no `LUM` content path is
   hardcoded.

No new behaviour; no CLI surface change; no flags.

## Edge cases & errors

- The compose-parse test tolerates the `${UEDCLI_STUB_CACHE:-…}:/stubs:ro` form — it asserts the
  container side (`:/stubs`), not the host side.
- `_remap_to_container` still raises `ValueError` on a path under no container-visible root
  (`packages.py:235`) — kept; the constant-collapse doesn't touch that fail-loud.

## Tests

- `test_container_assets` / `test_packages`: after the collapse, `packages` and `container_assets`
  report the identical `/stubs` and `/opt/UED22` spellings (a value-equality assertion, so a future
  edit to one is caught).
- New compose/Dockerfile-parse test: the `/stubs` mount target and the UED22 `COPY` dest equal the
  `container_assets` constants.

## Open questions

See `questions/`. One decision: implement the small single-source + test, or close the item as
mostly-obsolete and accept the latent fixed-root duplication.
