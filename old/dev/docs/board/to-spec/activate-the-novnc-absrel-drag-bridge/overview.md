+++
priority = "p3"
kind = "chore"
summary = "Activate the noVNC abs→rel drag bridge on the standing editors"
+++

# Activate the noVNC abs→rel drag bridge on the standing editors

Bridge is
DONE and live-verified (`uned/vnc_input_bridge.py` + `entrypoint.sh` `-pipeinput`; image rebuilt
2026-06-22), but a container only picks it up on a fresh start — recreate `dx-lum-uned`
(`docker compose up -d --force-recreate`) when no session is mid-drive. Re-confirm in a real
browser once one runs here.
