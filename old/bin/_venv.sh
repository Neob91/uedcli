# _venv.sh — HOST-NATIVE Python for uedcli dev. Shared paths/constants plus two kinds of function:
# `ensure_*` (provision — builds/downloads things, needs Docker) used ONLY by old/bin/build (and
# the legacy bin/build-standalone); `check_*` (read-only — fails fast with "run old/bin/build
# first" instead of provisioning) used by bin/uedcli + bin/test, so just running the CLI never
# needs Docker or network, only what build already put on disk.
#
# The venv's Python comes from `uv`'s managed Python (`python-build-standalone`) — statically
# linked, no `libpython.so` dependency (confirmed via `ldd`: only base-system libs every Linux host
# already has) — fetched inside a container (`ghcr.io/astral-sh/uv`), never needing host
# python3.12. Rejected first: creating the venv inside a plain `python:3.12-slim` container — its
# `python` either symlinks to a container-only path or (with `--copies`) copies a binary
# dynamically linked against `libpython3.12.so.1.0` (also container-only) — neither runs on the
# host afterward. `uv`'s managed builds avoid this; the ONE remaining wrinkle is that creating the
# venv INSIDE a container still bakes in the CONTAINER's view of the bind-mounted path (`/io/...`)
# into its symlinks, so `ensure_venv` rewrites them to the real host path afterward.
#
# uedcli (the CLI) and pytest run on the HOST in this venv — host-native means native access to
# asset dirs wherever they are on the host (not just inside a project dir), and the CLI reaches the
# docker daemon directly to drive the editor/game runtime containers. `uedcli_native` (Rust) is
# built in a container too (unchanged, already Docker-only). Sourced by bin/uedcli + bin/test +
# bin/build-standalone + old/bin/build.
#   UEDCLI_VENV=<dir>       venv location (default .venv)
#   UEDCLI_VENV_REBUILD=1   force a dep reinstall
#   UEDCLI_SKIP_NATIVE=1    skip the Rust ext build + cargo test
set -euo pipefail

UEDCLI_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
VENV="${UEDCLI_VENV:-$UEDCLI_DIR/.venv}"
PY="$VENV/bin/python"
_DEPS_MARKER="$VENV/.uedcli-deps"
_DEPS_SPEC="Pillow>=11 pytest>=8,<9 pytest-xdist>=3,<4 fastapi>=0.115 uvicorn>=0.32 watchfiles>=0.24 httpx>=0.27 websockets>=13"
_UV_IMAGE="ghcr.io/astral-sh/uv:bookworm-slim"
_UV_PYTHON_DIR="$UEDCLI_DIR/.cache/uv-python"
_UV_CACHE_DIR="$UEDCLI_DIR/.cache/uv"

# --- venv: check (fail-fast, no provisioning) vs. ensure (provision, needs Docker) ---------------

check_venv() {
  [ -x "$PY" ] && [ "$(cat "$_DEPS_MARKER" 2>/dev/null || true)" = "$_DEPS_SPEC" ] \
    || { echo "uedcli: venv missing or stale — run old/bin/build first" >&2; exit 2; }
}

ensure_venv() {
  if [ -x "$PY" ] && [ "$(cat "$_DEPS_MARKER" 2>/dev/null || true)" = "$_DEPS_SPEC" ] \
     && [ -z "${UEDCLI_VENV_REBUILD:-}" ]; then
    return 0
  fi
  command -v docker >/dev/null 2>&1 \
    || { echo "uedcli: docker is required to provision the venv." >&2; exit 1; }
  mkdir -p "$_UV_PYTHON_DIR" "$_UV_CACHE_DIR"
  rm -rf "$VENV"
  local rel_venv="${VENV#"$UEDCLI_DIR"/}"
  # Values go in via -e, never interpolated into the script text: $_DEPS_SPEC holds version specs
  # like `Pillow>=11`, and interpolating it into a string that's then re-parsed as a NEW script
  # would have `>=`/`<` read as real shell redirection operators. Expanding $UEDCLI_DEPS_SPEC as a
  # variable INSIDE the container's own shell is safe — variable expansion is never re-tokenized
  # for shell operators, only the self-contained SC2086 word-split pip needs.
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -e UEDCLI_REL_VENV="$rel_venv" -e UEDCLI_DEPS_SPEC="$_DEPS_SPEC" \
    -e UV_PYTHON_INSTALL_DIR=/io/.cache/uv-python -e UV_CACHE_DIR=/io/.cache/uv \
    -v "$UEDCLI_DIR":/io -w /io \
    "$_UV_IMAGE" sh -c '
      set -eu
      uv venv --managed-python --python 3.12 "$UEDCLI_REL_VENV"
      # shellcheck disable=SC2086
      uv pip install --python "$UEDCLI_REL_VENV"/bin/python --quiet --upgrade pip \
        $UEDCLI_DEPS_SPEC
    ' >&2 \
    || { echo "uedcli: venv provisioning failed" >&2; exit 1; }
  # The venv was created with the project dir mounted at /io, so uv baked /io/... into both the
  # python/python3/python3.12 SYMLINKS and every console-script's SHEBANG line (pip, pytest, every
  # future entry point an install adds) -- rewrite both to the real host path, or every one of
  # them is unusable outside a container with that exact mount.
  local f target
  for f in "$VENV"/bin/*; do
    [ -L "$f" ] && target="$(readlink "$f")" && case "$target" in
      /io/*) ln -sf "$UEDCLI_DIR/${target#/io/}" "$f" ;;
    esac
    if [ -f "$f" ] && [ ! -L "$f" ] && head -c2 "$f" 2>/dev/null | grep -q '^#!'; then
      # -i.bak (concatenated, no space), never bare -i: BSD/macOS sed requires the backup suffix
      # as part of the -i flag itself and otherwise eats the next argument (the file to edit) as
      # the sed SCRIPT, failing with "extra characters at the end of n command" -- GNU sed accepts
      # the same -i.bak form identically, so this is one code path for both, not an OS branch.
      # sed and rm are separate statements, not `&&`-chained: under `set -e`, a failing command is
      # exempt from aborting the script UNLESS it's the last in an AND-OR list -- chaining
      # `&& rm -f "$f.bak"` after sed would make sed no longer last, silently swallowing a sed
      # failure and leaving a broken shebang in place undetected (the exact "no silent half-
      # answers" failure this project explicitly forbids).
      sed -i.bak "1s|^#!/io/|#!$UEDCLI_DIR/|" "$f"
      rm -f "$f.bak"
    fi
  done
  [ -x "$PY" ] || { echo "uedcli: venv python still not runnable after path fixup" >&2; exit 1; }
  printf '%s' "$_DEPS_SPEC" > "$_DEPS_MARKER"
}

# --- native extension (uedcli_native) — built in a container (no host Rust needed) ---------------
_NATIVE_DIR="$UEDCLI_DIR/uedcli-native"
_NATIVE_MARKER="$VENV/.uedcli-native"
_BUILD_IMAGE="uedcli-rust-build"
_DOCKERFILE="$UEDCLI_DIR/dev-container/Dockerfile"
_BUILD_DOCKERFILE="$UEDCLI_DIR/dev-container/build.Dockerfile"

_native_ext_hash() {
  find "$_NATIVE_DIR" -path "$_NATIVE_DIR/target" -prune -o \( -name '*.rs' -o -name 'Cargo.toml' \) -print \
    | sort | xargs sha256sum | sha256sum | cut -d' ' -f1
}

# Read-only: sets UEDCLI_NATIVE_EXT_FRESH, never builds. Mirrors ensure_native_ext's own
# "default to stale" semantics but with no Docker fallback — bin/uedcli must never trigger a
# build itself. A stale/missing ext is NOT fatal here: every uedcli_native call site already
# refuses to run on UEDCLI_NATIVE_EXT_FRESH=0 rather than use a stale build (owner ruling
# 2026-09-11), so the CLI as a whole still starts; only the verbs that need it are blocked.
check_native_ext() {
  export UEDCLI_NATIVE_EXT_FRESH=0
  [ -n "${UEDCLI_SKIP_NATIVE:-}" ] && return 0
  [ -d "$_NATIVE_DIR" ] || return 0
  [ "$(cat "$_NATIVE_MARKER" 2>/dev/null || true)" = "$(_native_ext_hash)" ] \
    && "$PY" -c "import uedcli_native" >/dev/null 2>&1 \
    && export UEDCLI_NATIVE_EXT_FRESH=1
  return 0
}

_ensure_build_image() {
  command -v docker >/dev/null 2>&1 || return 1
  local want have
  want="$(sha256sum "$_DOCKERFILE" | cut -d' ' -f1)"
  have="$(docker image inspect "$_BUILD_IMAGE" --format '{{ index .Config.Labels "uedcli.dockerfile" }}' 2>/dev/null || true)"
  [ "$want" = "$have" ] && return 0
  echo "uedcli: building the Rust-build image $_BUILD_IMAGE (one-time)" >&2
  docker build --label "uedcli.dockerfile=$want" -t "$_BUILD_IMAGE" "$UEDCLI_DIR/dev-container" >&2
}

ensure_native_ext() {
  [ -n "${UEDCLI_SKIP_NATIVE:-}" ] && return 0
  [ -d "$_NATIVE_DIR" ] || return 0
  local hash; hash="$(_native_ext_hash)"
  if [ "$(cat "$_NATIVE_MARKER" 2>/dev/null || true)" = "$hash" ] \
     && "$PY" -c "import uedcli_native" >/dev/null 2>&1; then
    export UEDCLI_NATIVE_EXT_FRESH=1
    return 0
  fi
  # Past this point a rebuild is needed. Default to "confirmed stale" and only flip to fresh on
  # the actual successful install below — every remaining early return (no Docker, build failure,
  # ...) leaves the pessimistic default in place.
  export UEDCLI_NATIVE_EXT_FRESH=0
  if ! _ensure_build_image; then
    echo "uedcli: docker not available — skipping uedcli_native build (native materialize + gate-5" \
         "tests will be skipped; any command that needs uedcli_native will refuse to run rather" \
         "than silently use a stale build)." >&2
    return 0
  fi
  rm -rf "$_NATIVE_DIR/target/wheels"
  # Cargo decides freshness by MTIME, so a crate whose sources were restored with older timestamps
  # (`git archive` stamps the commit time; `tar -x`, `cp -p`, `rsync -t` preserve the stored ones)
  # is taken as up to date and the wheel silently keeps the PREVIOUS build's code. That produced a
  # false UNATCO N=116 ladder bail on 2026-09-07 (board `native-ext-binary-not-stable-across-builds`:
  # six "different revision" builds all emitted one byte-identical package). The content hash above
  # is the real freshness test; make the mtimes agree with it before cargo looks at them. Still
  # needed with the buildx cache mount below (`build.Dockerfile`'s comment): that mount persists
  # Cargo's own incremental-build state across builds exactly like the old bind-mounted target dir
  # did, so it inherits the same mtime hazard.
  find "$_NATIVE_DIR" -path "$_NATIVE_DIR/target" -prune -o -type f -exec touch {} + \
    || { echo "uedcli: cannot refresh uedcli-native source mtimes — refusing to build a wheel that" \
              "may be stale" >&2; return 0; }
  docker buildx build --target wheel-export \
    --output "type=local,dest=$_NATIVE_DIR/target/wheels" \
    -f "$_BUILD_DOCKERFILE" "$_NATIVE_DIR" >&2 \
    || { echo "uedcli: uedcli_native build failed — native materialize unavailable" >&2; return 0; }
  local whl; whl="$(ls -t "$_NATIVE_DIR"/target/wheels/uedcli_native-*.whl 2>/dev/null | head -1 || true)"
  [ -n "$whl" ] || { echo "uedcli: no wheel produced" >&2; return 0; }
  "$VENV/bin/pip" install --quiet --force-reinstall --no-deps "$whl" >&2 \
    || { echo "uedcli: pip install of uedcli_native failed" >&2; return 0; }
  printf '%s' "$hash" > "$_NATIVE_MARKER"
  export UEDCLI_NATIVE_EXT_FRESH=1
}

# --- resolve-wasm artifact (web/src/wasm) — built in a container (no host Rust/wasm-bindgen) -----
_WASM_MARKER="$VENV/.uedcli-native-wasm"
_WASM_OUT="$UEDCLI_DIR/web/src/wasm"

ensure_wasm_artifact() {
  [ -n "${UEDCLI_SKIP_NATIVE:-}" ] && return 0
  [ -d "$_NATIVE_DIR/resolve-wasm" ] || return 0
  local hash
  hash="$(find "$_NATIVE_DIR/resolve-core" "$_NATIVE_DIR/resolve-wasm" -path '*/target' -prune -o \
    \( -name '*.rs' -o -name 'Cargo.toml' \) -print | sort | xargs sha256sum | sha256sum | cut -d' ' -f1)"
  if [ "$(cat "$_WASM_MARKER" 2>/dev/null || true)" = "$hash" ] && [ -f "$_WASM_OUT/resolve_wasm_bg.wasm" ]; then
    return 0
  fi
  # Past this point the existing artifact (if any) is confirmed STALE or MISSING. Remove the
  # marker FIRST, before attempting a rebuild -- this is the refuse-at-use signal spec §5 requires
  # (mirroring ensure_native_ext's own "default to stale, only flip to fresh on real success"
  # pattern): if the rebuild below fails for ANY reason, no later check can mistake the old bytes
  # for current ones, because the marker they'd be compared against is gone.
  rm -f "$_WASM_MARKER"
  if ! _ensure_build_image; then
    echo "uedcli: docker not available -- WASM artifact missing/stale; npm test/build will fail" >&2
    return 1   # NOT return 0 -- unlike ensure_native_ext (whose Python callers tolerate a missing
  fi             # extension via UEDCLI_NATIVE_EXT_FRESH), nothing downstream can gracefully run
                  # without a WASM artifact at all, so silently returning success here is exactly
                  # the "stale build with no signal" failure mode spec §5 names.
  find "$_NATIVE_DIR" -path "$_NATIVE_DIR/target" -prune -o -type f -exec touch {} + \
    || { echo "uedcli: cannot refresh resolve-wasm source mtimes" >&2; return 1; }
  mkdir -p "$_WASM_OUT"
  docker buildx build --target wasm-export \
    --output "type=local,dest=$_WASM_OUT" \
    -f "$_BUILD_DOCKERFILE" "$_NATIVE_DIR" >&2 \
    || { echo "uedcli: resolve-wasm build failed" >&2; return 1; }
  # A zero-exit `docker buildx build` doesn't guarantee the expected file landed (a renamed
  # wasm-bindgen output, an empty export stage) -- mirror ensure_native_ext's own guard rather
  # than trusting the exit code alone; write the marker ONLY once the real file is confirmed
  # present.
  [ -f "$_WASM_OUT/resolve_wasm_bg.wasm" ] \
    || { echo "uedcli: resolve-wasm build produced no artifact at $_WASM_OUT/resolve_wasm_bg.wasm" >&2; return 1; }
  printf '%s' "$hash" > "$_WASM_MARKER"
}

# Rust goldens — the pure-core `cargo test`, run in the build image (needs Rust + libpython).
run_cargo_test() {
  [ -n "${UEDCLI_SKIP_NATIVE:-}" ] && return 0
  [ -d "$_NATIVE_DIR" ] || return 0
  _ensure_build_image || { echo "bin/test: docker not available — skipped cargo test" >&2; return 0; }
  docker buildx build --target test -f "$_BUILD_DOCKERFILE" "$_NATIVE_DIR"
}
