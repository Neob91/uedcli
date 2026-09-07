# _venv.sh — HOST-NATIVE Python for uedcli dev, with the Rust extension built in a container.
#
# uedcli (the CLI) and pytest run on the HOST in a Python 3.12 venv — Python 3 is on most hosts, and
# host-native means native access to asset dirs, no dev-container path juggling, and the CLI reaches
# the docker daemon directly to drive the editor/game runtime containers. What ISN'T on most hosts is
# Rust, so the ONE thing that needs a container is building `uedcli_native`: `ensure_native_ext`
# builds the abi3 wheel in a Docker image (Rust + libpython) and pip-installs it into the venv, and
# `run_cargo_test` runs the goldens there. Requires `python3.12` on PATH and Docker. Owner ruling
# 2026-08-06; `dev/docs/dev-runtime.md`. Sourced by bin/uedcli + bin/test.
#   UEDCLI_VENV=<dir>       venv location (default .venv)
#   UEDCLI_VENV_REBUILD=1   force a dep reinstall
#   UEDCLI_SKIP_NATIVE=1    skip the Rust ext build + cargo test
set -euo pipefail

UEDCLI_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
VENV="${UEDCLI_VENV:-$UEDCLI_DIR/.venv}"
PY="$VENV/bin/python"
_DEPS_MARKER="$VENV/.uedcli-deps"
_DEPS_SPEC="Pillow>=11 pytest>=8,<9"

ensure_venv() {
  if [ -x "$PY" ] && [ "$(cat "$_DEPS_MARKER" 2>/dev/null || true)" = "$_DEPS_SPEC" ] \
     && [ -z "${UEDCLI_VENV_REBUILD:-}" ]; then
    return 0
  fi
  command -v python3.12 >/dev/null 2>&1 \
    || { echo "uedcli: python3.12 is required on PATH (e.g. via pyenv) but was not found." >&2; exit 1; }
  [ -x "$PY" ] || python3.12 -m venv "$VENV" >&2
  # shellcheck disable=SC2086
  "$PY" -m pip install --quiet --disable-pip-version-check --upgrade pip $_DEPS_SPEC >&2 \
    || { echo "uedcli: venv dependency install failed" >&2; exit 1; }
  printf '%s' "$_DEPS_SPEC" > "$_DEPS_MARKER"
}

# --- native extension (uedcli_native) — built in a container (no host Rust needed) ---------------
_NATIVE_DIR="$UEDCLI_DIR/uedcli-native"
_NATIVE_MARKER="$VENV/.uedcli-native"
_BUILD_IMAGE="uedcli-rust-build"
_DOCKERFILE="$UEDCLI_DIR/dev-container/Dockerfile"

_ensure_build_image() {
  command -v docker >/dev/null 2>&1 || return 1
  local want have
  want="$(sha256sum "$_DOCKERFILE" | cut -d' ' -f1)"
  have="$(docker image inspect "$_BUILD_IMAGE" --format '{{ index .Config.Labels "uedcli.dockerfile" }}' 2>/dev/null || true)"
  [ "$want" = "$have" ] && return 0
  echo "uedcli: building the Rust-build image $_BUILD_IMAGE (one-time)" >&2
  docker build --label "uedcli.dockerfile=$want" -t "$_BUILD_IMAGE" "$UEDCLI_DIR/dev-container" >&2
}

# Run cargo/maturin in the build image as the invoking uid (outputs land uid-owned; CARGO_HOME + the
# target dir live under the bind-mounted crate so caches persist and nothing is left root-owned).
_rust_build_run() {
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e CARGO_HOME=/io/target/.cargo \
    -v "$_NATIVE_DIR":/io -w /io "$_BUILD_IMAGE" "$@"
}

ensure_native_ext() {
  [ -n "${UEDCLI_SKIP_NATIVE:-}" ] && return 0
  [ -d "$_NATIVE_DIR" ] || return 0
  local hash
  hash="$(cat "$_NATIVE_DIR/Cargo.toml" "$_NATIVE_DIR"/src/*.rs 2>/dev/null | sha256sum | cut -d' ' -f1)"
  if [ "$(cat "$_NATIVE_MARKER" 2>/dev/null || true)" = "$hash" ] \
     && "$PY" -c "import uedcli_native" >/dev/null 2>&1; then
    return 0
  fi
  if ! _ensure_build_image; then
    echo "uedcli: docker not available — skipping uedcli_native build (native materialize + gate-5" \
         "tests will be skipped)." >&2
    return 0
  fi
  rm -rf "$_NATIVE_DIR/target/wheels"
  # Cargo decides freshness by MTIME, so a crate whose sources were restored with older timestamps
  # (`git archive` stamps the commit time; `tar -x`, `cp -p`, `rsync -t` preserve the stored ones)
  # is taken as up to date and the wheel silently keeps the PREVIOUS build's code. That produced a
  # false UNATCO N=116 ladder bail on 2026-09-07 (board `native-ext-binary-not-stable-across-builds`:
  # six "different revision" builds all emitted one byte-identical package). The content hash above
  # is the real freshness test; make the mtimes agree with it before cargo looks at them.
  find "$_NATIVE_DIR" -path "$_NATIVE_DIR/target" -prune -o -type f -exec touch {} + \
    || { echo "uedcli: cannot refresh uedcli-native source mtimes — refusing to build a wheel that" \
              "may be stale" >&2; return 0; }
  _rust_build_run maturin build --release -o /io/target/wheels >&2 \
    || { echo "uedcli: uedcli_native build failed — native materialize unavailable" >&2; return 0; }
  local whl; whl="$(ls -t "$_NATIVE_DIR"/target/wheels/uedcli_native-*.whl 2>/dev/null | head -1 || true)"
  [ -n "$whl" ] || { echo "uedcli: no wheel produced" >&2; return 0; }
  "$VENV/bin/pip" install --quiet --force-reinstall --no-deps "$whl" >&2 \
    || { echo "uedcli: pip install of uedcli_native failed" >&2; return 0; }
  printf '%s' "$hash" > "$_NATIVE_MARKER"
}

# Rust goldens — the pure-core `cargo test`, run in the build image (needs Rust + libpython).
run_cargo_test() {
  [ -n "${UEDCLI_SKIP_NATIVE:-}" ] && return 0
  [ -d "$_NATIVE_DIR" ] || return 0
  _ensure_build_image || { echo "bin/test: docker not available — skipped cargo test" >&2; return 0; }
  _rust_build_run cargo test --quiet
}
