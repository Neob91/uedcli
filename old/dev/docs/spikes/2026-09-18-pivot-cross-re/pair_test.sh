#!/bin/bash
# Two Lights selected (Count==2, SnapCount==0): does the cross appear on its own?
# Then force a SetPivot with those 2 still selected (EDIT PIVOT HERE) and look again.
set -e
d() { docker exec pivot-probe python3 /opt/uned/wine_ctl.py exec "$1" >/dev/null; sleep 1.2; }
d "MAP IMPORTADD FILE=Z:\\work\\light.t3d"
d "ACTOR SELECT NONE"
d "ACTOR SELECT OFCLASS CLASS=ENGINE.LIGHT"
docker exec pivot-probe python3 /opt/uned/wine_ctl.py edit-copy 2>&1 | grep -c "Begin Actor" || true
