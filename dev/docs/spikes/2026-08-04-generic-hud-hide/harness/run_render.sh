#!/usr/bin/env bash
# run_render.sh — host orchestrator. Boots a dx-lum-uned container (Xvfb up, LAUNCH_UED=0),
# stages the spike pkg + room + scripts, boots DeusEx.exe, drives the 3-frame capture, and
# copies the PNGs out. Emulated amd64 wine on arm64 is SLOW; boot has a relaunch loop.
#   arg1: output dir for the PNGs (default: harness/out)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
OUT="${1:-$HERE/out}"; mkdir -p "$OUT"
DXSYS="$REPO/.claude/worktrees/installer-url/dev/games/dxreal/system"
TEX="$REPO/_scratch/roomtex"
ROOM="$REPO/_scratch/roomexec/room.dx"
C=uedpreview-spike-render

[ -e "$HERE/UedPreview.u" ] || { echo "missing UedPreview.u — run build_pkg.sh first" >&2; exit 2; }
[ -d "$DXSYS" ] || { echo "missing dxreal system at $DXSYS" >&2; exit 2; }

docker rm -f "$C" >/dev/null 2>&1 || true
echo "[run] starting container"
docker run -d --name "$C" -e LAUNCH_UED=0 -e UED_GEOMETRY=1400x1050x24 \
  -v "$DXSYS":/gsys -v "$TEX":/gtex dx-lum-uned >/dev/null
# wait for Xvfb (:99) up
for _ in $(seq 1 60); do
  docker exec "$C" bash -lc 'xdpyinfo -display :99 >/dev/null 2>&1' && break; sleep 1; done

echo "[run] staging files"
docker exec "$C" bash -lc 'mkdir -p /work'
docker cp "$HERE/UedPreview.u" "$C:/work/UedPreview.u" >/dev/null
docker cp "$ROOM" "$C:/work/room.dx" >/dev/null
docker cp "$HERE/boot_game.sh" "$C:/work/boot_game.sh" >/dev/null
docker cp "$HERE/drive.py"     "$C:/work/drive.py" >/dev/null

echo "[run] booting DeusEx.exe (this can take minutes under emulation) ..."
docker exec -e UED_SIZE_X=1280 -e UED_SIZE_Y=960 "$C" bash /work/boot_game.sh

echo "[run] link up — driving capture"
docker exec "$C" python3 /work/drive.py

echo "[run] copying PNGs to $OUT"
for f in hud_baseline hud_generic_clean hud_dxdriver_clean; do
  docker cp "$C:/work/$f.png" "$OUT/$f.png" >/dev/null 2>&1 && echo "  $OUT/$f.png" || echo "  MISSING $f.png"
done
echo "[run] DeusEx.log tail:"; docker exec "$C" bash -lc 'tail -8 /work/dx/System/DeusEx.log 2>/dev/null | tr -d "\000"' || true
docker rm -f "$C" >/dev/null
echo "[run] done"
