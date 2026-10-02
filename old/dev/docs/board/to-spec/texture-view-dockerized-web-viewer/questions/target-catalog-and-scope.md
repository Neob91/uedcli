# `texture view`: is a web viewer in scope, and against which catalog?

## Context

The item wants a `texture view` verb serving a dockerized web UI (thumbnails + search) over the
texture catalog. Three coupled decisions gate whether and how to build it:

1. **In uedcli's scope at all?** No direction doc authorizes a web server. `direction/containers.md`
   says the only containers uedcli drives are wine ones and "uedcli itself never runs in one".
   `direction/asset-catalog.md` frames the audience as an LLM agent, whose answer to "see an asset" is
   `preview` (produce the image) + `search` (rank refs) — files and lines, not an HTTP UI. A human
   browse tool is reasonable to want, but it is a different modality and audience.

2. **Dockerized or in-process?** Native offline decode + a stdlib HTTP server need no container, which
   fits the "wine-only containers" ruling better. A container would be a new non-wine container type.
   Recommend in-process if built.

3. **Which store?** The 2026-06-22 note has it reading the legacy `texture-catalog/` + `.uedcli/
   textures/`. But `direction/asset-catalog.md` deletes that store for hash-keyed classify shards + a
   content-addressed preview cache. A viewer on the legacy layout is throwaway.

Recommendation: if approved, build it **in-process (no Docker)**, against the **asset-catalog redesign
store**, reusing the existing `search` ranking and native `preview` decode — and sequence it *after*
the redesign lands. If a human browse tool is not wanted (agents use `preview`/`search`), close the
item.

## Answer

<!-- Empty = open. -->
