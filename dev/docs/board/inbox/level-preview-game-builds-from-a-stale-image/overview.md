+++
priority = "p2"
kind = "debug"
summary = "level preview --game builds from a stale image tag (dx-lum-uned vs ued-x86-runtime)"
+++

# level preview --game builds from a stale image tag (dx-lum-uned vs ued-x86-runtime)

`uedcli/game/Dockerfile:9` (`FROM --platform=linux/amd64 dx-lum-uned`) and
`uedcli/game/build-image.sh:30` (`docker run -d --name "$B" … dx-lum-uned …`) name the image
`dx-lum-uned`. `uned/docker-compose.yml` builds and runs the tag `ued-x86-runtime:latest`; only its
`container_name` is still `dx-lum-uned`.

So on a host provisioned by compose alone, the first `level preview --game` dies at image build:

```
uedcli-game image build failed:
  == step 1: compile UedPreview (engine-only, regular UED22 UCC) in a builder ==
  Unable to find image 'dx-lum-uned:latest' locally
  docker: Error response from daemon: pull access denied for dx-lum-uned, …
```

Worked around by hand with `docker tag ued-x86-runtime:latest dx-lum-uned:latest`, after which the
render produced correct lit frames — so the substrate is right and only the tag is wrong.

Fix is presumably to name the compose tag (or one shared constant) in both files. Check first
whether `dev/scripts/setup-game-preview.sh` hides this by tagging `dx-lum-uned` itself: if it does,
the two provisioning paths disagree and that is the real defect.

Found running `level preview --game` on `06_HongKong_WanChai_Market.dx`, 2026-08-23.
