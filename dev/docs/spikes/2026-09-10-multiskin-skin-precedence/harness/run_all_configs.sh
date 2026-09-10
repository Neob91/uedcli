#!/usr/bin/env bash
# One FRESH ephemeral editor per config. A `CAMERA OPEN` window is capture-once and the editor
# wedges after a few map cycles, so reusing one container across configs produces stale/identical
# frames — restart instead.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:?usage: run_all_configs.sh <out-dir> <config> [<config> ...]}"
mkdir -p "$out"
for cfg in "${@:2}"; do
  echo "===== $cfg"
  bash "$here/respawn.sh" uned-skinprobe
  python3 "$here/live_probe.py" uned-skinprobe "$out" "$cfg"
done
docker rm -f uned-skinprobe >/dev/null 2>&1 || true
docker volume rm uned-wp-uned-skinprobe >/dev/null 2>&1 || true
