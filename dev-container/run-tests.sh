#!/usr/bin/env bash
# run-tests.sh — INSIDE the dev container: run pytest + the Rust cargo goldens. Invoked by bin/test
# via `docker exec` (the native extension is already built by _dev-container.sh's _ensure_native_ext).
# Args pass straight to pytest. `UEDCLI_SKIP_NATIVE` skips the cargo goldens (pytest-only).
set -euo pipefail
cd "$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"   # repo root (identity path)
ROOT="$PWD"

rc=0
if [ "$#" -eq 0 ]; then
  PYTHONPATH="$ROOT" python -m pytest uedcli -q -o cache_dir=/tmp/pytest_cache || rc=$?
else
  PYTHONPATH="$ROOT" python -m pytest "$@" -q -o cache_dir=/tmp/pytest_cache || rc=$?
fi

# Rust goldens — the pure-core `cargo test` (links libpython, present in this image).
if [ -z "${UEDCLI_SKIP_NATIVE:-}" ] && [ -d uedcli-native ]; then
  ( cd uedcli-native && PYO3_PYTHON="$(command -v python)" cargo test -q ) || rc=$?
fi
exit "$rc"
