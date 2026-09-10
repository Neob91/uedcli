#!/usr/bin/env bash
# Recreate the ephemeral UED22 probe container (the editor dies on a Critical Error dialog) and
# block until its window resolves. Repo-tree stub-cache path: the docker daemon here cannot see
# $HOME (parallel-editors.md "A bind-mount source must be visible to the docker daemon").
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
name="${1:-uned-skinprobe}"
stubs="${UEDCLI_STUB_CACHE:-/workspace/uedcli/.uedcli/probe-stubs}"
mkdir -p "$stubs"
docker rm -f "$name" >/dev/null 2>&1 || true
# Deus Ex CONTENT: the baked ini's `Paths=../Textures/*.utx` / `../Sounds/*.uax` resolve beside
# /opt/UED22, so mounting the game dirs there is all it takes to make DeusEx*.u loadable — without
# them a mesh package load dies on "Can't find file for package 'Effects'".
game="${UEDCLI_GAME_DIR:-/workspace/uedcli/dev/games/deusex}"
( cd "$here/../../../../../uned" && UEDCLI_STUB_CACHE="$stubs" \
    docker compose run -d --name "$name" -v "uned-wp-${name}:/wineprefix" \
      -v "$game/Textures:/opt/Textures:ro" -v "$game/Sounds:/opt/Sounds:ro" \
      -v "$game/Music:/opt/Music:ro" uned >/dev/null )
exec bash "$here/wait_ready.sh" "$name"
