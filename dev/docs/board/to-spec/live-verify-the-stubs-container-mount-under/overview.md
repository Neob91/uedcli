+++
priority = "p2"
kind = "debug"
summary = "Live-verify the `/stubs` container mount under the env-fed source"
+++

# Live-verify the `/stubs` container mount under the env-fed source

(git-native
slice 7; premise updated 2026-07-18). The stub-mount source is now
`${UEDCLI_STUB_CACHE:-${HOME}/.uedcli/cache/stubs}` — BOTH `editor.ensure_editor` and
`stub.ephemeral_build_container` pass `UEDCLI_STUB_CACHE` (the resolved `config.stub_cache_root()`,
an absolute path) in the compose env, so `${HOME}` interpolation and the stripped-env cron/systemd
concern no longer apply to uedcli-driven spin-ups (only to a hand-run `docker compose`). Remaining
leg: confirm on a live editor container that a real `level materialize`/`level photo` still
`OBJ LOAD`s the v69 stubs from `/stubs`. Substrate-gated — cannot be checked offline. From the
slice-7 flag (2026-07-08).
