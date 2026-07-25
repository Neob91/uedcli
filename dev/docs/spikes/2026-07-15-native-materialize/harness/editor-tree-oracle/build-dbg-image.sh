#!/usr/bin/env bash
# Build the debug editor image (dx-lum-uned + gdb) used by the editor-tree oracle.
# Idempotent: skips if the image already exists (pass --force to rebuild).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="dx-lum-uned-dbg:latest"
if [[ "${1:-}" != "--force" ]] && docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "$IMAGE already present (--force to rebuild)"; exit 0
fi
docker build -t "$IMAGE" -f "$HERE/Dockerfile.dbg" "$HERE"
echo "built $IMAGE"
