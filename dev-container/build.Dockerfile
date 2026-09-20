# syntax=docker/dockerfile:1
# Builds/tests the `uedcli_native` crate against `uedcli-rust-build` (see ./Dockerfile) with NO
# bind mount — the crate is uploaded as the build context (`COPY . /io`) and results leave via
# buildx's local exporter, both of which go over the same client<->daemon API connection a plain
# `docker build` already uses. A bind mount (`docker run -v host:/io`) instead needs the SOURCE
# path to exist on the DAEMON's own filesystem, which fails outright against a remote/sibling
# daemon (this repo's own dev sandbox: `DOCKER_HOST=tcp://dind:...`, a separate container with no
# view of this host's files at all — `mkdir /workspace: permission denied`). `RUN --mount=type=
# cache` keeps Cargo's incremental target dir persisted on the DAEMON side across builds (locked,
# since several worktrees/sessions may build against the same daemon at once), so build speed
# matches the old bind-mounted-target-dir behavior.
#
# Targets:
#   test          -- `cargo test --quiet`; a failing test fails the build (non-zero exit), same as
#                     the old `docker run ... cargo test` did.
#   wheel-export  -- a `scratch` stage holding just the built wheel, for `--output type=local`.
FROM uedcli-rust-build:latest AS src
COPY . /io
WORKDIR /io
ENV CARGO_HOME=/io/target/.cargo

FROM src AS test
RUN --mount=type=cache,id=uedcli-native-cargo-target,target=/io/target,sharing=locked \
    cargo test --quiet

FROM src AS wheel
RUN --mount=type=cache,id=uedcli-native-cargo-target,target=/io/target,sharing=locked \
    maturin build --release -o /tmp/wheels

FROM scratch AS wheel-export
COPY --from=wheel /tmp/wheels /
