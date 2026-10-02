#!/usr/bin/env bash
# The editor's log file is write-buffered, so `read_log_since` right after an exec often shows
# nothing. Give it a moment, then tail.
set -eu
sleep "${2:-8}"
docker exec "$1" sh -c 'tail -n 25 /opt/UED22/Editor.log'
