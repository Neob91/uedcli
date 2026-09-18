#!/bin/bash
# Screenshot the editor window to a host path under _scratch/pivotre/.
set -e
n="$1"
docker exec pivot-probe python3 /opt/uned/wine_ctl.py shot "/work/$n.png" >/dev/null
docker cp "pivot-probe:/work/$n.png" "_scratch/pivotre/$n.png" >/dev/null
echo "_scratch/pivotre/$n.png"
