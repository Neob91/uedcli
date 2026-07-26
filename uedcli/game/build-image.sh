#!/usr/bin/env bash
# build-image.sh — build the uedcli-game image (level preview --game).
# args: <game-system-dir> <boot-map-src> [content-dir ...]
# Two steps because a Docker RUN cannot see asset mounts (spec §5 gate fold):
#   1) compile UedPreview{,DX}.u in a MOUNTED builder container (skipped when the uscript
#      tree is byte-unchanged since the last successful compile — source-hash stamp);
#   2) stage .u + the substrate boot map + entrypoint, thin `docker build`.
# The whole run is under a flock (two concurrent previews must not race the tag/staging).
# The v469 UCC toolchain is user-supplied at game/inputs/edit (see inputs/README.md);
# preview_game.py checks it and names the error BEFORE calling here.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"             # Tools/uedcli/uedcli/game
GSYS="$1"; BOOTMAP="$2"; shift 2
CONTENT_DIRS=("$@")
IN="$HERE/inputs"; STG="$HERE/staging"
[ -e "$IN/edit/hUCC.exe" ] || { echo "missing UCC toolchain at $IN/edit (see inputs/README.md)" >&2; exit 3; }

exec 9>"/tmp/uedcli-game-imgbuild.lock"
flock 9

uscript_hash() { ( cd "$HERE" && find uscript -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1 ); }
mkdir -p "$STG"
STAMP="$STG/uscript.sha256"
WANT="$(uscript_hash)"

if [ -e "$STG/UedPreview.u" ] && [ -e "$STG/UedPreviewDX.u" ] && [ -e "$STAMP" ] && [ "$(cat "$STAMP")" = "$WANT" ]; then
  echo "== step 1: SKIP (uscript unchanged) =="
else
  echo "== step 1: compile UedPreview packages in a mounted builder =="
  B=uedcli-game-imgbuild
  docker rm -f "$B" >/dev/null 2>&1 || true
  MOUNTS=(-v "$GSYS":/gsys:ro)
  i=0
  for d in "${CONTENT_DIRS[@]}"; do MOUNTS+=(-v "$d":/gc$i:ro); i=$((i+1)); done
  docker run -d --name "$B" -e LAUNCH_UED=0 "${MOUNTS[@]}" dx-lum-uned >/dev/null
  for _ in $(seq 1 30); do docker exec "$B" wine --version >/dev/null 2>&1 && break; sleep 2; done
  docker cp "$IN/edit" "$B:/work/edit" >/dev/null
  docker exec "$B" bash -lc 'rm -rf /work/uscript' >/dev/null
  docker cp "$HERE/uscript" "$B:/work/uscript" >/dev/null
  docker exec "$B" bash /work/uscript/build.sh /work/uscript \
    || { echo "compile FAILED" >&2; docker rm -f "$B" >/dev/null; exit 4; }
  docker cp "$B:/work/build/System/UedPreview.u" "$STG/UedPreview.u"
  docker cp "$B:/work/build/System/UedPreviewDX.u" "$STG/UedPreviewDX.u"
  docker rm -f "$B" >/dev/null
  echo "$WANT" > "$STAMP"
fi

echo "== stage boot map + shared shot model =="
cp "$BOOTMAP" "$STG/BootMap.dx"
cp "$HERE/../preview_shots.py" "$STG/preview_shots.py"   # baked so preview_batch can resolve @actor poses

echo "== step 2: docker build uedcli-game =="
docker build -t uedcli-game -f "$HERE/Dockerfile" "$HERE"
echo "== done: uedcli-game =="
