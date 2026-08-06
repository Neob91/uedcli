# _dev-container.sh — ensure the long-running uedcli DEV container is up, and exec into it.
#
# uedcli dev (the CLI + its test suite) runs INSIDE a Rust+Python+deps container, docker-exec'd into
# (owner ruling 2026-08-06; dev/docs/direction/process.md). The container is LONG-RUNNING so exec is
# cheap; the repo is IDENTITY-mounted (same path host<->container) so uedcli never branches on paths.
# This is dev tooling — NOT the FEX editor/game RUNTIME container that ships in releases.
#
# Sourced by bin/uedcli and bin/test. Knobs:
#   UEDCLI_DEV_MOUNTS="/a /b"  extra IDENTITY mounts (e.g. game asset dirs the CLI reads)
#   UEDCLI_DEV_REBUILD=1       force an image rebuild
set -euo pipefail

UEDCLI_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
DEV_IMAGE="uedcli-dev"
# One long-running container per checkout (worktrees have distinct roots), keyed by the root path.
DEV_CONTAINER="uedcli-dev-$(printf '%s' "$UEDCLI_DIR" | cksum | cut -d' ' -f1)"
_DOCKERFILE="$UEDCLI_DIR/dev-container/Dockerfile"

ensure_dev_container() {
  command -v docker >/dev/null 2>&1 || { echo "uedcli: docker not found on PATH" >&2; exit 1; }
  # (Re)build when the image is missing or the Dockerfile changed (its hash rides on an image label).
  local want have
  want="$(sha256sum "$_DOCKERFILE" | cut -d' ' -f1)"
  have="$(docker image inspect "$DEV_IMAGE" --format '{{ index .Config.Labels "uedcli.dockerfile" }}' 2>/dev/null || true)"
  if [ "$want" != "$have" ] || [ -n "${UEDCLI_DEV_REBUILD:-}" ]; then
    echo "uedcli: building dev container $DEV_IMAGE (Rust + Python + deps)" >&2
    docker build --label "uedcli.dockerfile=$want" -t "$DEV_IMAGE" "$UEDCLI_DIR/dev-container" >&2
  fi
  # Start the long-running container if it is not already up.
  if [ -z "$(docker ps -q -f "name=^${DEV_CONTAINER}$" 2>/dev/null)" ]; then
    docker rm -f "$DEV_CONTAINER" >/dev/null 2>&1 || true
    local mounts=( -v "$UEDCLI_DIR:$UEDCLI_DIR" )
    # From a worktree, .git is a pointer to the shared git dir OUTSIDE UEDCLI_DIR; mount that common
    # dir (identity) so git works in-container. On the main checkout it is already inside the mount.
    local gcd; gcd="$(git -C "$UEDCLI_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -n "$gcd" ] && [ -d "$gcd" ] && [ "${gcd#$UEDCLI_DIR/}" = "$gcd" ]; then
      mounts+=( -v "$gcd:$gcd" )
    fi
    # host docker socket: the containerized CLI drives the editor/game RUNTIME containers on the host.
    [ -S /var/run/docker.sock ] && mounts+=( -v /var/run/docker.sock:/var/run/docker.sock )
    local m; for m in ${UEDCLI_DEV_MOUNTS:-}; do mounts+=( -v "$m:$m" ); done
    docker run -d --name "$DEV_CONTAINER" -w "$UEDCLI_DIR" "${mounts[@]}" "$DEV_IMAGE" sleep infinity >/dev/null
  fi
  _ensure_native_ext
}

# Build uedcli_native into the container's interpreter (as root: pip installs to /usr/local), gated on
# a crate-source hash so an unchanged tree is a no-op. Shared by bin/test (native pytest tests) and
# bin/uedcli (`level materialize` native). UEDCLI_SKIP_NATIVE skips it.
_ensure_native_ext() {
  [ -n "${UEDCLI_SKIP_NATIVE:-}" ] && return 0
  [ -d "$UEDCLI_DIR/uedcli-native" ] || return 0
  docker exec -w "$UEDCLI_DIR" "$DEV_CONTAINER" bash -c '
    set -euo pipefail
    h="$(cat uedcli-native/Cargo.toml uedcli-native/src/*.rs 2>/dev/null | sha256sum | cut -d" " -f1)"
    [ "$(cat /tmp/.uedcli-native-hash 2>/dev/null || true)" = "$h" ] && exit 0
    echo "uedcli: building uedcli_native in the dev container" >&2
    rm -rf /tmp/wheels
    ( cd uedcli-native && maturin build --release -o /tmp/wheels ) >&2
    pip install --quiet --force-reinstall --no-deps /tmp/wheels/uedcli_native-*.whl >&2
    printf "%s" "$h" > /tmp/.uedcli-native-hash
  ' >&2
}

# Exec a command inside the dev container at the repo root; TTY-aware, exit code propagated. Extra
# `docker exec` flags (e.g. -e VAR) may be passed before `--`: `dev_exec -e X=1 -- cmd args`.
dev_exec() {
  local flags=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do flags+=( "$1" ); shift; done
  [ "${1:-}" = "--" ] && shift
  [ -t 0 ] && flags+=( -it )
  docker exec "${flags[@]}" -w "$UEDCLI_DIR" "$DEV_CONTAINER" "$@"
}
