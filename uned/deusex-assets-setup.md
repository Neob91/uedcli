# Populating `DeusExAssets/` — see the canonical guide

The Deus Ex asset-provisioning guide — installing content + v68 `.u` code from an installed game
**or** the raw multi-volume ACE installer, how the gitignored `DeusExAssets/` tree is mounted and
wired into the editor per-command, and the toolchain finding that the committed **UED22 v469 UCC** (not
any Deus Ex UCC/SDK) is what decompiles v68 `.u` — now lives in the uedctl doc tree:

**→ [`../dev/docs/deusex-assets-setup.md`](../dev/docs/deusex-assets-setup.md)**

The machinery it describes lives here in `uned/`; `dev/scripts/install-deusex-assets.sh` sets up a
full working game copy under `dev/games/<game>/` and populates this `uned/DeusExAssets/` tree from it
(both gitignored; the `DeusExAssets/` destination is fixed at `uned/`, independent of the script's
location).
Since the asset-wiring cutover (2026-07-14), `docker-compose.yml` and `entrypoint.sh` NO LONGER
mount `DeusExAssets`/wire the package `Paths` — uedctl composes each container's asset mounts +
`[Core.System] Paths` per-command instead (the whole composed dir set, incl. the v68 `System/` code
decompile source, mounts at `/resources/<n>`; see `editor.ensure_editor` / `stub.ephemeral_build_container`).
