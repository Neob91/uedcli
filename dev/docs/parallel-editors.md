# Running uedcli operations in parallel (ephemeral editors)

Some tasks want to drive **many independent editor sessions at once** — validating
every builder, exercising a clip across 20 brushes, sweeping a parameter space —
without touching the persistent `dx-lum-uned` editor or serializing through it.
The pattern: spin up one **ephemeral editor per work item** via `docker compose
run`, drive it, tear it down. This doc is the recipe and its load-bearing gotchas.

> All `docker compose` commands below run from `Tools/uedcli/uned/` (where
> `docker-compose.yml` lives). There is **no `/repo` bind mount** (container-fs
> isolation, D4): the substrate is baked into the image and game assets are exposed via
> per-command config-driven read-only mounts — the WHOLE composed config dir set at `/resources/<n>`
> via the ONE `resource_mounts` scheme (decisions.md 2026-07-14 19:21, was the static
> `/deusex`+`/content` + a separate `/install-system` code mount); the only mutable space is the
> container-local `/work` dir, which dies with the container.

## Why `docker compose run`, not `up`

`docker compose run` starts a one-off container from the same `uned` service
(same image, same read-only content mounts) but, unlike `up`:
- it **ignores `container_name`** and lets you assign a unique `--name`, so many
  can coexist; and
- it **does NOT publish the service's ports** unless you pass `--service-ports`.
  The compose service maps `127.0.0.1:6080`; under `up` a second instance would
  collide on that port. Under `run` the ports simply aren't published, so N
  instances coexist with zero port conflict. (We don't need noVNC for headless
  drives — `docker exec … wine_ctl.py` reaches the editor regardless.)

## The isolation requirements

Two things are still shared and must be isolated per run; the old in-container
scratch concerns are now handled structurally by container-fs isolation:

1. **WINEPREFIX (`/wineprefix`) — give each run its own volume.** The service
   mounts a *named* volume `wine-prefix:/wineprefix`; every `run` would mount the
   **same** named volume, and concurrent `wineserver`s on one prefix corrupt the
   registry/locks. Override per run with a unique volume:
   ```
   docker compose run -d --name uned-job-7 -v uned-wp-job-7:/wineprefix uned
   ```
   A fresh empty volume is **seeded from the image's baked `/wineprefix`** (the
   Dockerfile runs `wineboot --init` at build), so each run gets an isolated,
   already-initialized prefix — no slow runtime `wineboot`.

2. **Box-size cache — one per worker.** `writes` caches the working SELECT-INSIDE
   box size at `UEDCLI_BOX_CACHE` (default `/tmp/uedcli_box_cache.json`) — a HOST
   file. Parallel host processes racing on one file can corrupt it (writes are
   best-effort, so it degrades rather than crashes, but set
   `UEDCLI_BOX_CACHE=/tmp/box_<id>.json` per worker to be clean).

⚠️ **A bind-mount SOURCE must be visible to the docker DAEMON, not just your shell.**
`level preview` boots the editor with a per-boot `UnrealEd.ini` override mounted
`-v <host-ini>:/opt/UED22/UnrealEd.ini`. The source path was first written to the system
tempdir (`/tmp`); under a sandboxed shell (e.g. `devdawg-shell`) `/tmp` is **private to the
sandbox**, so the daemon resolves `/tmp/<c>.preview.ini` against its OWN tmp, finds nothing,
**auto-creates a directory** there, and the file-onto-file mount fails with
`not a directory` — the editor never boots. Write any host→daemon bind source **under the
repo tree** (uedcli uses the project state dir `<root>/.uedcli/tmp/`), which the daemon sees at an identical real path,
exactly as the repo-relative compose asset mount (`./DeusExAssets`) already relies on. (The
stub-cache mount is NO longer such an example — it is the absolute per-user stub cache,
`${UEDCLI_STUB_CACHE:-${HOME}/.uedcli/cache/stubs}`, fed the resolved `config.stub_cache_root()`
via the compose env, not a repo-tree path.) Live-confirmed 2026-07-06. The `UnrealEd.ini` mount is **read-write** (wine rewrites
the ini on exit; a `:ro` mount → EACCES → GPF).

**No longer a concern — in-container editor scratch.** Every editor temp (paste/
import T3D, MAP EXPORT readbacks, screenshots) now lives in the container-local
`/work` dir, uuid-suffixed (`writes.CONTAINER_TMP = "/work"`, `xfer` mints the
paths). `/work` is private to each container and dies with it, so two workers
**cannot** clobber each other's scratch the way the old shared `/repo/Temp` mount
allowed — and there is no host-side `/repo/Temp` to coordinate on or clean up.
Reads are model-side now (no fixed-path MAP EXPORT context file to make
per-worker). Any host↔container file you need crosses via `xfer.cp_in`/`cp_out`,
which already uuid-suffix the `/work` path.

## Readiness

The entrypoint writes `/run/uned.pid` once the editor window exists. Poll it:
```
docker exec <container> python3 /opt/uned/wine_ctl.py status
# ready when stdout has "alive=True" AND a RESOLVED "window=<digits>"
```
⚠️ **Require a numeric `window=<id>`, not the bare substring `window=`.** For the first
seconds after launch `status` prints `window=<unresolved: could not find an UnrealEd
window>` (process up, window not yet mapped) — a substring check treats that as ready and
the very next `exec` fails "could not find an UnrealEd window". `_wait_ready` matches
`window=\d` (live-confirmed 2026-07-06, surfaced by `level preview` whose boot immediately
drives the editor). The image is warm, so the real handle usually resolves within a few seconds.

## Concurrency is MEMORY-bound — cap it

Each ephemeral editor is a full stack (Xvfb + fluxbox + x11vnc + websockify + wine
+ the editor) and costs on the order of **~0.5 GB RSS**, more during `MAP REBUILD`.
Do **not** launch an unbounded fan-out: on a shared box with little free RAM, 20
simultaneous editors OOM. Use a **bounded worker pool** sized to *available* memory
(`free -g`), and **tear each container + its volume down before starting the next**
so memory is reclaimed between items:
```bash
MAXJ=4                      # size to free RAM, not core count
for i in $(seq 0 19); do
  worker "$i" &             # spin up → wait ready → drive → docker rm -f + volume rm
  while [ "$(jobs -r | wc -l)" -ge "$MAXJ" ]; do wait -n; done
done
wait
```
This is still "in parallel" — `MAXJ` items run concurrently — just bounded. State
the cap and the reason when you report results; a silent cap reads as "ran all 20
at once" when it didn't.

## Bypass the trunk for headless exercises

uedcli runs host-side and reaches the editor via `docker exec`; its durable state is the
git-tracked T3D trunk, and machine-local scratch lives in the project's `<root>/.uedcli/`
state dir (the session store is long deleted). For *validation/exercise* runs (where you're
proving geometry round-trips, not recording authored history), call `builders` / `writes` /
`clip` **directly** against a `Driver(container)` — no trunk, no project resolution. That
keeps each worker self-contained.

Example — export the current level from a named container:

```python
import tempfile, pathlib
from uedcli.driver import Driver
from uedcli import xfer

driver = Driver("uned-job-7")
work = xfer.work_path("t3d")                   # uuid-suffixed /work path
driver.exec(f"MAP EXPORT FILE={driver.to_z_path(work)}")
with tempfile.NamedTemporaryFile(suffix=".t3d", delete=False) as f:
    host_path = f.name
xfer.cp_out(driver.container, work, host_path)
t3d = pathlib.Path(host_path).read_text()
```

`driver.exec` sends a console command; `xfer.cp_out` copies the result file from
the container's `/work` dir to a host temp path. `xfer` (not `Driver`) owns the
`/work` path generation and `docker cp` boundary — use `xfer.work_path` to mint a
unique path, then `xfer.cp_out(container, container_path, host_path)` to retrieve it.

## Cleanup

Always reclaim everything on completion (and on failure — tear down in the worker,
not just at the end):
```
docker rm -f <each container>
docker volume rm <each uned-wp-* volume>
```
Removing the container reclaims its `/work` scratch automatically (it's
container-local, not a host mount — nothing to `rm` on the host). Any host-side
files you `xfer.cp_out`'d under `.uedcli/` you clean up yourself. Leave the
persistent `dx-lum-uned` editor and its `wine-prefix` volume untouched — the
ephemeral runs never share them.
