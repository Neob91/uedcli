#!/usr/bin/env bash
# build-image.sh — build the uedcli-game image (level preview --game).
# args: <boot-map-src>
# Two steps because a Docker RUN cannot see asset mounts (spec §5 gate fold):
#   1) compile the engine-only UedPreview.u in a builder container with the base image's
#      own regular UED22 UCC — no game System, no content mounts (UedPreview names
#      only stock Core/Engine/IpDrv; see uscript/build.sh). Skipped when the uscript tree is
#      byte-unchanged since the last successful compile (source-hash stamp);
#   2) stage .u + the substrate boot map + entrypoint, thin `docker build`.
# The whole run is under a flock (two concurrent previews must not race the tag/staging).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"             # Tools/uedcli/uedcli/game
BOOTMAP="$1"
STG="$HERE/staging"

exec 9>"/tmp/uedcli-game-imgbuild.lock"
flock 9

uscript_hash() { ( cd "$HERE" && find uscript -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1 ); }
mkdir -p "$STG"
STAMP="$STG/uscript.sha256"
WANT="$(uscript_hash)"

if [ -e "$STG/UedPreview.u" ] && [ -e "$STAMP" ] && [ "$(cat "$STAMP")" = "$WANT" ]; then
  echo "== step 1: SKIP (uscript unchanged) =="
else
  echo "== step 1: compile UedPreview (engine-only, regular UED22 UCC) in a builder =="
  B=uedcli-game-imgbuild
  docker rm -f "$B" >/dev/null 2>&1 || true
  docker run -d --name "$B" -e LAUNCH_UED=0 --entrypoint bash dx-lum-uned -lc 'sleep 3600' >/dev/null
  for _ in $(seq 1 30); do docker exec "$B" wine --version >/dev/null 2>&1 && break; sleep 2; done
  # /work is created by the base entrypoint, which the bash --entrypoint override bypasses — so make
  # it here, else `docker cp … :/work/uscript` fails "Could not find the file /work in container".
  docker exec "$B" bash -lc 'mkdir -p /work && rm -rf /work/uscript' >/dev/null
  docker cp "$HERE/uscript" "$B:/work/uscript" >/dev/null
  docker exec "$B" bash /work/uscript/build.sh /work/uscript \
    || { echo "compile FAILED" >&2; docker rm -f "$B" >/dev/null; exit 4; }
  docker cp "$B:/work/build/System/UedPreview.u" "$STG/UedPreview.u"
  docker rm -f "$B" >/dev/null
  echo "$WANT" > "$STAMP"
fi

echo "== stage boot map + shared shot model =="
cp "$BOOTMAP" "$STG/BootMap.dx"
cp "$HERE/../preview_shots.py" "$STG/preview_shots.py"   # baked so preview_batch can resolve @actor poses

echo "== step 2: docker build uedcli-game =="
docker build -t uedcli-game -f "$HERE/Dockerfile" "$HERE"
echo "== done: uedcli-game =="
