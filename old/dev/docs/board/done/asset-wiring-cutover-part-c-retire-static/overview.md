+++
priority = "p?"
kind = "unknown"
summary = "Asset-wiring cutover — Part C (retire static compose mounts + entrypoint sed)"
+++

# Asset-wiring cutover — Part C (retire static compose mounts + entrypoint sed)

— BUILT
2026-07-14. Removed `docker-compose.yml`'s static `/deusex`+`/content`+Sounds/Music stub mounts,
deleted `entrypoint.sh`'s `$DEUSEX_ASSETS_DIR` `Paths` `sed` block, and dropped the
`UED_DEUSEX_ASSETS_DIR=/nonexistent` stopgap. The no-GUI build container
(`stub.ephemeral_build_container`) self-wires its assets like the GUI editor (crafted
`[Core.System] Paths` ini bind-mounted pre-launch, shared `editor.engine_ini_mount`). Decision:
`direction/containers.md` (2026-07-14 13:30). Its **deferred remnant is now RESOLVED** by the config-drive
finalization below.
