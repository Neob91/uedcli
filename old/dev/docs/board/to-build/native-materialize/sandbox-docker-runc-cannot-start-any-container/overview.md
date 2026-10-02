+++
priority = "p1"
kind = "debug"
summary = "Sandbox docker/runc cannot start any container — blocks all live-editor work (golden builds, gdb capture)"
+++

# Sandbox docker/runc cannot start any container — blocks all live-editor work

Found 2026-08-31, first hit by a `node_flags` live-verification subagent (`node-flags-0x40-0x80-
divergence-from-movers-no`), confirmed independently in the coordinating session.

## Symptom

`docker run --rm hello-world` (the official zero-dependency sanity image, no project Dockerfile
involved) fails:

```
docker: Error response from daemon: failed to create task for container: failed to start shim:
start failed: io.containerd.runc.v2: fork/exec /usr/local/bin/containerd-shim-runc-v2: resource
temporarily unavailable: exit status 1
```

The subagent saw a related but not identical error on the same underlying fault (`runc did not
terminate successfully: exit status 2`, `failed to create shim task: ttrpc: closed`), reproduced 4
independent ways (plain debian image, `hello-world`, a fresh `ued-x86-runtime` build, retries with
pauses). `docker info`/`docker ps` work fine — the daemon itself (`DOCKER_HOST=tcp://dind:2375`,
rootless) is reachable over the API — but nothing can start a container process. `/sys/fs/cgroup` is
mounted read-only, no systemd ("Running in rootless-mode without cgroups...").

Reproduced again in the coordinating session, twice, same `resource temporarily unavailable`.

## Diagnosis so far

Not a project Dockerfile problem, not a project config problem — the official `hello-world` image
fails the same way. Ruled out obvious local resource exhaustion: `ulimit -u` unlimited, only 28
processes for this user, no leftover/zombie containers (`docker ps -a`: 1 entry). Points at the
`dind` (docker-in-docker) sidecar itself being unable to fork/exec `containerd-shim-runc-v2` —
plausibly a host-level or sidecar-level resource ceiling (fork limit, PID cgroup cap on the sidecar
container) not visible from inside this session, possibly shared load from other concurrent
sandbox sessions on the same host. Not fixable from within an agent session — no access to the dind
sidecar's own limits.

## Impact

Blocks ANY task needing a live UED22 editor container: new self-built goldens for un-cached levels,
gdb/live-capture verification (this is what stopped the `node_flags` 0x40/0x80 live-verification
task this round — it fell back to static disassembly instead). Does NOT block work against
already-cached goldens (`/tmp/uedcli-parity-cache/`, `parity_report.py`'s cache) or pure static
analysis/disassembly.

## Not done

No fix attempted — outside this session's visibility/control. If this persists across future
sessions, worth flagging to whoever manages the sandbox infrastructure. Retry periodically; may be
transient (shared host load).
