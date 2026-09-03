+++
priority = "p2"
kind = "debug"
summary = "level photo --game builds from a stale image tag (dx-lum-uned vs ued-x86-runtime)"
+++

# level photo --game builds from a stale image tag (dx-lum-uned vs ued-x86-runtime)

Fixed: `uedcli/game/Dockerfile`, `uedcli/game/build-image.sh`, and `dev/scripts/setup-game-preview.sh`
now all reference `ued-x86-runtime:latest` — the tag `uned/docker-compose.yml` actually builds.
`dx-lum-uned` stays the standing container's name only, never an image reference.
