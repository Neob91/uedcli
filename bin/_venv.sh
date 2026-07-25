# _venv.sh — ensure a HOST-NATIVE Python 3.12 venv for uedctl dev.
#
# uedctl runs on the HOST (like the eventual Nuitka release binary), NOT inside a
# container — so it has native filesystem access to the game's asset dirs wherever
# they live, with no bind-mounting of arbitrary host roots into a dev container
# (which could shadow/clobber the container's own dirs — see decisions.md
# 2026-07-14 "venv for dev"). The editor/build containers uedctl DRIVES still run
# via docker (host daemon); only uedctl itself is native.
#
# Requires python3.12 on PATH (pyenv provides it here). Sourced by bin/uedctl and
# bin/test; both call `ensure_venv` then exec `$PY`. `UEDCTL_VENV=<dir>` overrides
# the location; `UEDCTL_VENV_REBUILD=1` forces a dep reinstall.
set -euo pipefail

UEDCTL_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"   # <repo>/Tools/uedctl
VENV="${UEDCTL_VENV:-$UEDCTL_DIR/.venv}"
PY="$VENV/bin/python"
_DEPS_MARKER="$VENV/.uedctl-deps"
# Pillow: uedctl's only third-party RUNTIME dep (texture-catalog PCX decode). pytest: dev/test only.
_DEPS_SPEC="Pillow>=11 pytest>=8,<9"

ensure_venv() {
  if [ -x "$PY" ] && [ "$(cat "$_DEPS_MARKER" 2>/dev/null || true)" = "$_DEPS_SPEC" ] \
     && [ -z "${UEDCTL_VENV_REBUILD:-}" ]; then
    return 0
  fi
  if ! command -v python3.12 >/dev/null 2>&1; then
    echo "uedctl: python3.12 is required on PATH (e.g. via pyenv) but was not found." >&2
    exit 1
  fi
  [ -x "$PY" ] || python3.12 -m venv "$VENV" >&2
  # shellcheck disable=SC2086
  "$PY" -m pip install --quiet --disable-pip-version-check --upgrade pip $_DEPS_SPEC >&2 \
    || { echo "uedctl: venv dependency install failed" >&2; exit 1; }
  printf '%s' "$_DEPS_SPEC" > "$_DEPS_MARKER"
}

# --- native extension (uedctl_native) — OPTIONAL, source-hash-gated ----------
# Builds the Rust PyO3 extension into the venv so `level materialize` (native) and the
# gate-5 cross-check can run.  OPTIONAL by design: if `cargo` is absent (or
# UEDCTL_SKIP_NATIVE is set) it warns and returns success — a docs-only or pure-Python
# change still runs pytest (native tests `importorskip("uedctl_native")`).  Gated on a
# hash of the crate sources so a `.rs` edit triggers a rebuild but an unchanged tree does
# not (the pip deps-marker can't cover Rust — spec §8.3).
_NATIVE_DIR="$UEDCTL_DIR/uedctl-native"
_NATIVE_MARKER="$VENV/.uedctl-native"

ensure_native_ext() {
  [ -n "${UEDCTL_SKIP_NATIVE:-}" ] && return 0
  [ -d "$_NATIVE_DIR" ] || return 0
  [ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
  if ! command -v cargo >/dev/null 2>&1; then
    echo "uedctl: cargo not found — skipping uedctl_native build (native materialize + " \
         "gate-5 tests will be skipped). Install Rust to enable." >&2
    return 0
  fi
  local hash
  hash="$(cat "$_NATIVE_DIR/Cargo.toml" "$_NATIVE_DIR"/src/*.rs 2>/dev/null \
          | sha256sum | cut -d' ' -f1)"
  if [ "$(cat "$_NATIVE_MARKER" 2>/dev/null || true)" = "$hash" ] \
     && "$PY" -c "import uedctl_native" >/dev/null 2>&1; then
    return 0
  fi
  "$PY" -m maturin --version >/dev/null 2>&1 || "$VENV/bin/maturin" --version >/dev/null 2>&1 \
    || "$PY" -m pip install --quiet maturin >&2 \
    || { echo "uedctl: maturin install failed — skipping native ext" >&2; return 0; }
  ( cd "$_NATIVE_DIR" && VIRTUAL_ENV="$VENV" PATH="$VENV/bin:$PATH" \
      "$VENV/bin/maturin" develop --release >&2 ) \
    || { echo "uedctl: uedctl_native build failed — native materialize unavailable" >&2; \
         return 0; }
  printf '%s' "$hash" > "$_NATIVE_MARKER"
}
