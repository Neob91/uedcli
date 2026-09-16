#!/usr/bin/env bash
# Restarts round_robin_ladder.py on any exit (bail, infra crash, host reboot) -- state is fully
# persisted, so each restart resumes exactly where it left off. Run from the repo root; adjust
# UEDCLI_HOME/TMPDIR for a different host/checkout (2026-09-16 sandbox values below).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." # repo root, from this harness dir
export UEDCLI_HOME="${UEDCLI_HOME:-/workspace/uedcli/.uedcli-home}"
export TMPDIR="${TMPDIR:-$PWD/_scratch/pttmp}"
mkdir -p "$TMPDIR"
while true; do
  echo "[supervisor] $(date '+%H:%M:%S') starting round_robin_ladder.py"
  .venv/bin/python3 dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/round_robin_ladder.py
  rc=$?
  echo "[supervisor] $(date '+%H:%M:%S') driver exited rc=$rc -- restarting in 10s"
  sleep 10
done
