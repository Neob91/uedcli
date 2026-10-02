#!/usr/bin/env bash
# Spike: does UnrealEd (the materialize path uedcli uses — MAP IMPORTADD + MAP EXPORT,
# and after MAP REBUILD) preserve a Mover's authored NumKeys when trailing keyframes are
# zero, or does it auto-decrement NumKeys past trailing all-zero keys?
#
# The answer decides uedcli's shrink model: if the editor KEEPS NumKeys, then move/rotate
# only ever GROW it and shrinking must be an explicit verb (remove/clear); if the editor
# DECREMENTS it, uedcli should mirror that automatically.
#
# Method mirrors 2026-07-18-exec-file-console-batch/harness/exec_file_probe.sh: boot an
# ephemeral uned editor, drive it over `docker exec … wine_ctl.py`, batch the per-fixture
# console sequence into ONE `EXEC <file>` script (rides through the GC "Cleaning up…"
# dialog), read the whole-level T3D back with MAP EXPORT, grep the mover's NumKeys/KeyPos.
#
# Usage: numkeys_probe.sh            (boots+tears down uned-spike-numkeys)
#        numkeys_probe.sh <container> (drive an already-running container; no teardown)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
FIX="$HERE/fixtures"
UNED_DIR="$(cd "$HERE/../../../../../uned" && pwd)"   # Tools/uedcli/uned
OUT="$HERE/out"; mkdir -p "$OUT"

C="${1:-}"; OWN=0
if [ -z "$C" ]; then
  C=uned-spike-numkeys; OWN=1
  docker rm -f "$C" >/dev/null 2>&1
  (cd "$UNED_DIR" && docker compose run -d --name "$C" -v "uned-wp-$C:/wineprefix" uned) >/dev/null
fi

echo "== waiting for the editor window (<=90s)"
up=0
for i in $(seq 1 30); do
  out=$(docker exec "$C" python3 /opt/uned/wine_ctl.py status 2>&1 || true)
  if echo "$out" | grep -qE 'alive=True' && echo "$out" | grep -qE 'window=[0-9]'; then up=1; echo "  up: $out"; break; fi
  sleep 3
done
if [ "$up" != 1 ]; then echo "FAIL: editor never came up"; [ "$OWN" = 1 ] && docker rm -f "$C" >/dev/null 2>&1; exit 1; fi

dismiss() { # dismiss the GC "Cleaning up…" xmessage dialog if present
  docker exec "$C" sh -c 'wid=$(DISPLAY=:99 xdotool search --onlyvisible --name xmessage 2>/dev/null | head -1); [ -n "$wid" ] && DISPLAY=:99 xdotool windowactivate --sync "$wid" && DISPLAY=:99 xdotool key Return' >/dev/null 2>&1 || true
}
ued() { docker exec "$C" python3 /opt/uned/wine_ctl.py exec "$1"; }

run_fixture() { # run_fixture <label> <fixture-file>
  local label="$1" fx="$2" base; base="$(basename "$fx" .t3d)"
  echo; echo "===== fixture: $label ($base) ====="
  grep -nE 'NumKeys|KeyPos' "$fx" | sed 's/^/  authored: /'
  # MAP IMPORTADD needs a Begin Map…End Map envelope; the generator emits a bare actor block.
  { echo "Begin Map"; cat "$fx"; echo "End Map"; } > "$OUT/$base.t3d"
  docker cp "$OUT/$base.t3d" "$C:/work/$base.t3d" >/dev/null
  # One EXEC script: fresh level, exact grid, import, export pre-rebuild, rebuild, export post.
  cat > "$OUT/$base.exec" <<EXEC
MAP NEW
MAP GRID X=1 Y=1 Z=1
MAP IMPORTADD FILE=Z:\work\\$base.t3d
MAP EXPORT FILE=Z:\work\\${base}_pre.t3d
MAP REBUILD
MAP EXPORT FILE=Z:\work\\${base}_post.t3d
EXEC
  docker cp "$OUT/$base.exec" "$C:/work/$base.exec" >/dev/null
  dismiss
  ued "EXEC Z:\\work\\$base.exec"
  # Poll for the last marker (post-rebuild export) up to ~40s.
  for i in $(seq 1 20); do
    if docker exec "$C" test -s "/work/${base}_post.t3d" 2>/dev/null; then break; fi
    sleep 2
  done
  docker cp "$C:/work/${base}_pre.t3d"  "$OUT/${base}_pre.t3d"  >/dev/null 2>&1 || echo "  (no pre export)"
  docker cp "$C:/work/${base}_post.t3d" "$OUT/${base}_post.t3d" >/dev/null 2>&1 || echo "  (no post export)"
  for phase in pre post; do
    local f="$OUT/${base}_${phase}.t3d"
    if [ -s "$f" ]; then
      local nk; nk=$(grep -E '^\s*NumKeys=' "$f" | head -1 | tr -d ' ')
      echo "  readback $phase: ${nk:-NumKeys=<absent → 2>}; KeyPos lines: $(grep -cE 'KeyPos\(' "$f")"
      grep -nE 'NumKeys=|KeyPos\(' "$f" | sed 's/^/    /'
    else
      echo "  readback $phase: <no export file>"
    fi
  done
}

run_fixture "6-key, KeyPos(5) POPULATED (baseline round-trip)" "$FIX/mover_k5_populated.t3d"
run_fixture "6-key, ALL movement keys ZERO (user: set key 5 back to 0,0,0)" "$FIX/mover_k5_zeroed.t3d"
run_fixture "6-key, only KeyPos(1) set (trailing 2..5 zero)" "$FIX/mover_k1_only.t3d"

echo; echo "== editor liveness after probes:"; docker exec "$C" python3 /opt/uned/wine_ctl.py status 2>&1 || true
if [ "$OWN" = 1 ]; then
  docker rm -f "$C" >/dev/null 2>&1
  docker volume rm "uned-wp-$C" >/dev/null 2>&1
fi
echo "== done"