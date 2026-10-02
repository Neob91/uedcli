#!/bin/bash
# Move every non-main window off-screen so the floating Log/Textures windows stop
# painting black over the viewports (dev/docs/unrealed/rendering.md).
set -e
MID=$(docker exec pivot-probe python3 /opt/uned/wine_ctl.py status | grep -oE 'window=[0-9]+' | cut -d= -f2)
MHEX=$(printf '0x%08x' "$MID")
docker exec -e DISPLAY=:99 pivot-probe bash -c "wmctrl -l | awk -v m=$MHEX 'tolower(\$1)!=tolower(m){print \$1}' | xargs -r -I{} wmctrl -i -r {} -e 0,3200,3200,200,150"
echo "swept (main=$MHEX)"
