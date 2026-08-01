# Expose all five missing poly-flags as settable, or hold back a subset?

## Context

The five are `bigwavy`/`smallwavy` (render distortion), `lowshadowdetail`/`highshadowdetail`
(per-surface lightmap resolution → lightmap memory), and `brightcorners` (lightmap edge-brightening).
All five are plain `PolyFlags` bits: round-trip-clean through the paste path, CSG/solidity-neutral
(the native core reads only semisolid/notsolid/portal), and distinct from every editor-transient bit.
So none is a *correctness* risk — the only argument for holding one back is that its effect (a wobble,
extra lightmap memory) is a heavy-handed thing to hand an author.

- Option A (recommended): expose all five. The guiding goal is to expose every UnrealEd surface
  attribute as text; the side effects are deliberate author choices, documented in the kb.
- Option B: expose only the benign ones (e.g. `brightcorners`) and leave wavy / shadow-detail
  documented-but-unsettable, as today.

Recommendation: A — add all five to `PF_NAMES`.

## Answer

<!-- Empty = open. -->
