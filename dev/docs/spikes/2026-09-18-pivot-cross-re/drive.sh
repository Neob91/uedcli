#!/bin/bash
# Send one console line to the ephemeral editor.
set -e
docker exec pivot-probe python3 /opt/uned/wine_ctl.py exec "$1"
