+++
priority = "p2"
kind = "implement"
summary = "Editor-driving verbs under the dev wrapper leave root-owned files"
+++

# Editor-driving verbs under the dev wrapper leave root-owned files

p2. The dev
container runs `--user host-uid`, but the sibling editor containers it spawns (`editor.py`'s
`docker compose run`) run as **root** with no `--user`, so files they write into mounted host paths
(`~/.uedcli/cache/stubs`, editor scratch) become root-owned and can then block the host user / the
`--user` dev container from rewriting them. (This already bit us: a pre-existing root-owned
`~/.uedcli/cache/stubs` from an earlier editor/stub run — `sudo chown -R "$USER":"$USER" ~/.uedcli`
clears it.) Fix: run editor containers as the host user, or make the caches tolerate mixed
ownership. Also: only the repo + `~/.uedcli` are identity-mounted — per-game base-asset `paths`
outside the repo (`[games.*]`) will need identity mounts once materialize wires them. Full editor-
verb validation under the wrapper (path translation, socket perms) is still unrun.
(Flagged 2026-07-11 during dev-wrapper build; from cold-review findings.)
