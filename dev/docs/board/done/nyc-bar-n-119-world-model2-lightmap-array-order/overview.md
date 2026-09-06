+++
priority = "p2"
kind = "debug"
summary = "DONE — the world `LightMap` array reordered from index 144 because native's allocate walk claimed a surf at a node with NO vertices. UnrealEd's walk (`Editor.dll 0x100a4a90`) tests `node->NumVertices != 0` first, so such a node neither allocates nor claims, and the surf gets its record at the later non-empty node. Byte-exact, no mask."
spikes = ["dev/docs/spikes/2026-09-06-lightmap-alloc-zero-vert-gate/"]
+++

# NYC_Bar N=119 — world `Model2` `LightMap` array order

Fixed 2026-09-06. Surfs 174 and 178 each sit on one 0-vertex node and one 3-vertex node; native
allocated their records at the 0-vertex node (records 144 and 152) where UED22 allocates at the
3-vertex one (228 and 229), shifting every record in between. Fix: `light.rs::lightmap_emit_order`
gates the claim on `num_vertices != 0` and claims a surf only when a record is actually appended.

Corpus: the gated walk predicts the stored record→surf order of 161/161 shipped Deus Ex world
Models; the ungated one 158.

Detail: `dev/docs/spikes/2026-09-06-lightmap-alloc-zero-vert-gate/spike.md`.
