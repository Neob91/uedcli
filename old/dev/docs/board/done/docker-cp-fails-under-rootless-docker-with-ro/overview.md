+++
priority = "p2"
kind = "debug"
summary = "docker cp-out fails under rootless docker (remount-ro :ro mount); fixed by docker exec cat streaming"
+++

# docker cp-out fails under rootless docker

`docker cp <container>:file → host` remounts the container's mounts read-only for the copy; rootless
docker can't do that for the `:ro` `/stubs` bind mount (`remount-ro … operation not permitted`),
which broke `level materialize`'s final `.dx` install (arch-independent — the amd64 path too). Owner
chose the uniform code fix over a host change: `xfer.cp_out` now streams via `docker exec … cat`
(no remount, works rootless + rootful, on every host). Done.
