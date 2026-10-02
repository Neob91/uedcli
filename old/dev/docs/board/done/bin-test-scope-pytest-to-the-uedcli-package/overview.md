+++
priority = "p?"
kind = "unknown"
summary = "`bin/test` — scope pytest to the `uedcli` package (fixes tree-walk hang) + rename from `bin/uedcli-test`"
+++

# `bin/test` — scope pytest to the `uedcli` package (fixes tree-walk hang) + rename from `bin/uedcli-test`

— 2026-07-12 (branch `uedcli-impl`, commit `6cd30ce58`). Root cause of a
reproducible multi-minute hang: `pytest.ini` had **no `testpaths`**, so the wrapper's args branch
(`pytest -k … -q`, no path) made pytest recursively collect the ENTIRE `Tools/uedcli` tree — the
baked editor, asset dirs, and a stray `dev/docs/spikes/bspspike/test_umodel_serialize.py` that
hardcodes another machine's `/home/human/...` paths. (No-arg runs passed an explicit `uedcli`
target, so they were fine — which is why it looked intermittent.) Fix: `testpaths = uedcli` in
`pytest.ini` scopes every bare pytest (incl. `-k`) to the package; an explicit path arg still
overrides. Verified: the previously-hanging `bin/test -k "preview or stash"` now finishes in ~24s.
Renamed the wrapper `bin/uedcli-test` → `bin/test` and updated all references (`CLAUDE.md`,
`README.md`, `docs/README.md`, `dev/docs/dev-runtime.md`, `bin/_dev-run.sh` header), noting in each
that it must be run **path-qualified** (`bin/test`) since `test` is a shell builtin.
**Wrapper-hang debugging note for the next session:** the dev wrapper's own hang symptom can also be
caused by concurrent `bin/test` runs leaving stray `docker exec … pytest` processes inside the warm
`uedcli-run-*` container — if the wrapper stalls, `docker exec <c> python -m pytest uedcli -k … -q`
directly (repo is mounted at the same host path inside the container) bypasses it and is the fast
way to confirm the container itself is healthy.
