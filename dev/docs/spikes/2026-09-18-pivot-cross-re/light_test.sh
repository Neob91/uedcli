#!/bin/bash
# Leave exactly ONE Light in the level, select it through a verb that DOES notify
# (ACTOR SELECT OFCLASS -> edactSelectOfClass -> NoteSelectionChange), then capture a
# fresh CAMERA OPEN view. If GPivotShown were true for a lone point actor, the pivot
# cross would appear at the light's own projected position.
set -e
d() { docker exec pivot-probe python3 /opt/uned/wine_ctl.py exec "$1" >/dev/null; sleep 1.2; }
d "SELECTNAME NAME=ProbeLight1"
d "ACTOR DELETE"
d "ACTOR SELECT NONE"
d "ACTOR SELECT OFCLASS CLASS=ENGINE.LIGHT"
docker exec pivot-probe python3 /opt/uned/wine_ctl.py edit-copy 2>&1 | grep "Begin Actor" || true
