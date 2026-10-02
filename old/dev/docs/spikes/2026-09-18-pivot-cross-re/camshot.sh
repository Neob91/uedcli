#!/bin/bash
# Open a fresh CAMERA OPEN viewport (renders on first paint, so it shows the CURRENT
# selection/pivot state without needing a click-repaint) and capture just that window.
# $1 = output name, $2 = camera name (must be unique per shot), $3 = REN (default 13 top-ortho)
set -e
n="$1"; cam="$2"; ren="${3:-13}"
docker exec pivot-probe python3 /opt/uned/wine_ctl.py exec \
  "CAMERA OPEN NAME=$cam XR=760 YR=560 REN=$ren FLAGS=127" >/dev/null
sleep 3
docker exec -i -e DISPLAY=:99 pivot-probe bash -s "$cam" "$n" <<'SH'
cam="$1"; n="$2"
xid=$(wmctrl -l | grep -iE 'map|viewport' | tail -1 | awk '{print $1}')
echo "capturing $xid"
import -window "$xid" "/work/$n.png"
SH
docker cp "pivot-probe:/work/$n.png" "_scratch/pivotre/$n.png" >/dev/null
echo "_scratch/pivotre/$n.png"
