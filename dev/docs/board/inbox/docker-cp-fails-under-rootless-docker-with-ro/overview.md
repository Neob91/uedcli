+++
priority = "p2"
kind = "owner-question"
summary = "docker cp fails under rootless docker with :ro bind mounts — blocks level materialize install (all arches)"
+++

# docker cp fails under rootless docker with :ro bind mounts — blocks level materialize install (all arches)

On this sandbox host the docker daemon is rootless (`/home/rootless/.local/share/docker`). `level
materialize`'s final step `docker cp <editor-container>:/work/<uuid>.dx <staging>`
(`apply._save_and_swap_verified` → `xfer.cp_out`) fails:

```
Error response from daemon: remount-ro …/overlayfs/…/stubs, flags: 0x1021: operation not permitted
```

`docker cp` from a RUNNING container pauses it and remounts its mounts read-only; rootless docker
can't do that remount for a `:ro` bind mount. The trigger is the `:ro` mount, reproduced with NO
editor and NO FEX (`docker run -e LAUNCH_UED=0 -v dir:/stubs:ro …; docker cp …:/work/x → host` →
same error). So it is:

- **arch-independent** — hits the amd64 path too, not FEX-specific;
- **pre-existing** — the `/stubs` (+ `/resources`) `:ro` mounts and `docker cp` are not new;
- confined to the artifact-extraction step. The FEX editor build + `MAP SAVE` + H3 verify all pass
  before it (see the FEX editor-runtime work) — the built, H3-verified `.dx` is complete in the
  container; only copying it out fails.

The error is now surfaced clearly (`xfer._cp` prints docker's stderr instead of a bare
`CalledProcessError`).

## Owner decision

Per `conventions.md` ("if something can't run on a host, that's a broken host to FIX … not a second
code path") this reads as a host fix. Options:

1. **Fix the host** — rootful docker, or a rootless setup whose overlay permits the cp remount
   (fuse-overlayfs). Preferred by the convention; no code change.
2. **Change `xfer.cp_out` to stream via `docker exec cat`** — avoids the remount, uniform on every
   host (not an env branch). Broader blast radius (shared by screenshot/texture/csg_golden); only
   `cp_out` of single files is affected, but it needs its own review + tests.

Recommend (1). Filing (2) as the fallback if this env must run materialize as-is.
