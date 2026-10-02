+++
priority = "p2"
kind = "unknown"
summary = "Nuitka standalone-release build for uedcli"
+++

# Nuitka standalone-release build for uedcli

p2. The dev loop now runs uedcli in a
Python-3.12 Docker image (`bin/uedcli` + `docker/Dockerfile` + `bin/_dev-run.sh`; see
`dev/docs/dev-runtime.md`). The intended *release* is a Nuitka-compiled single binary (interpreter
+ Pillow baked in, no host deps). Open: how the editor-driving verbs' Docker dependency is handled
in a standalone binary (the binary still needs a docker CLI + daemon to spin editor containers).
(Deferred per Andrzej, 2026-07-11.)
