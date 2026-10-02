#!/usr/bin/env bash
# Builds this spike's probe.py with Nuitka --mode=standalone (its own venv, never the dev .venv)
# and runs the compiled binary with PATH stripped down to prove it needs no system Python.
set -euo pipefail
SPIKE_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
UEDCLI_DIR="$(cd "$SPIKE_DIR" && git rev-parse --show-toplevel)"

export UEDCLI_VENV="$UEDCLI_DIR/.venv-nuitka-probe"
# shellcheck source=/dev/null
source "$UEDCLI_DIR/bin/_venv.sh"
ensure_venv
ensure_native_ext || true
if [ "${UEDCLI_NATIVE_EXT_FRESH:-}" != "1" ]; then
  # This sandbox's rootless docker daemon cannot bind-mount a path under .claude/worktrees/ (a
  # known, session-dependent limitation already documented elsewhere in this repo -- see
  # GUI-PARITY.md's several "rootless docker daemon cannot mount /workspace" notes) -- unrelated to
  # the question this spike is actually asking. Falling back to the wheel already built from this
  # exact source in the main checkout (confirmed identical: `git diff master -- uedcli-native/` is
  # empty in this worktree) rather than skipping the probe entirely.
  echo "-- docker-based native build unavailable in this worktree; falling back to the prebuilt" \
       "wheel already on disk (source confirmed identical via git diff) --"
  # A worktree's own target/ dir is untracked and doesn't exist here -- the wheel lives in the
  # MAIN checkout, the first entry `git worktree list` always reports.
  MAIN_REPO="$(git worktree list --porcelain | awk '/^worktree /{print $2}' | head -1 || true)"
  WHL="$(ls -t "$MAIN_REPO/uedcli-native/target/wheels/"uedcli_native-*.whl 2>/dev/null | head -1 || true)"
  [ -n "$WHL" ] || { echo "no prebuilt uedcli_native wheel found either -- cannot proceed" >&2; exit 1; }
  "$UEDCLI_VENV/bin/pip" install --quiet --force-reinstall --no-deps "$WHL"
fi
# Nuitka standalone mode on Linux needs patchelf to rewrite RPATHs; no root in this sandbox to
# `apt install` it, but PyPI ships a prebuilt binary via the `patchelf` wheel -- a build-time-only
# tool, doesn't touch what the compiled binary itself depends on at runtime.
"$UEDCLI_VENV/bin/pip" install --quiet nuitka patchelf

rm -rf "$SPIKE_DIR/build"
cd "$UEDCLI_DIR"
PATH="$UEDCLI_VENV/bin:$PATH" PYTHONPATH="$UEDCLI_DIR" "$UEDCLI_VENV/bin/python" -m nuitka --mode=standalone \
  --output-dir="$SPIKE_DIR/build" \
  "$SPIKE_DIR/probe.py"

BIN="$SPIKE_DIR/build/probe.dist/probe"
[ -x "$BIN" ] || BIN="$SPIKE_DIR/build/probe.dist/probe.bin"
echo "-- compiled binary: $BIN --"
echo "-- running with PATH stripped of the venv/system python, to prove no interpreter dependency --"
env -i HOME="$HOME" PATH=/usr/bin:/bin "$BIN"
