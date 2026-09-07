+++
priority = "p2"
kind = "debug"
summary = "Leaf 9's permeating-light decision is a floating-point knife-edge: two builds of the SAME native source disagree about it, one gating PASS and one FAIL. The canonical build passes, so the level is unblocked; the knife-edge itself is `native-ext-binary-not-stable-across-builds`."
+++

# UNATCO N=116 — leaf 9's permeating light is a codegen-sensitive near-tie

## DONE 2026-09-07 — the level is unblocked, the underlying near-tie is not fixed

`ladder_run.py --dx 03_NYC_UNATCOHQ.dx --from 116 --to 116 --force-ref` PASSES on the canonical
build, and the level then walks to **N=162** (bails at N=163, a different item). No code change
closed it and none was needed: the divergence is real native output, but from a DIFFERENT COMPILED
BINARY of the same source.

## What was actually measured

Building the crate two ways — the canonical layout (what `bin/_venv.sh` builds) and a copy of the
same `src/` missing `uedcli-native/.cargo/config.toml` — yields two `.so`s 5,472 bytes apart, each
deterministic on its own (three runs each, byte-identical output; two independently rebuilt N=116
references also agree with each other). Their UNATCO N=116 packages differ, and ONLY in the lighting:

    bbox sphere vectors points nodes surfs verts zones bounds leafhulls lightbits   SAME
    leaves lightmap lights                                                          DIFF

`Model.Lights` is **941 vs 940** — the canonical build's 940 matches UED22. The one extra entry is at
index 40: light index 74 prepended to **leaf 9**'s permeating run, which shifts every later leaf's
`iPermeating` by +1 and every later `LightMap` record's `iLightActors` with it. Those shifted offsets
are what the original report read as "13 of 214 lightmaps differ in both directions" — one insertion,
not thirteen decisions.

So this is one more `ActorVisibility` beam-flood near-tie, the same family as
`island-n-123-world-model2-leaf-permeating-light` (leaf 26, unresolved) and the fixed
`nyc-bar-n-151-world-model2-leaf-permeating-light` (the unnormalized beam plane). Here the margin is
narrower than the difference between two compilations of the same arithmetic, which is why it moved
without a source change.

Ruled out along the way, each by rebuilding that revision's `src/` in an otherwise identical crate
and gating: the `ClipBspSurf` raster port (`b028ccf7`), the lightmap zero-vertex allocate gate
(`23fa4fc9`), Pass D's split-original kill (`11bfe3bb`), the `MakePortals` portal builder
(`567291a2`), the permeating beam-plane normalize (`59ada80e`) and the f32 `PointRegion` descent
(`5cd24228`). The tree as of the original report (`20bc0f79^`) also PASSES when built canonically.
`parity_gate.py` has not changed since 2026-09-05, so the pass is not a widened mask.

## What is still owed

- The binary-stability hazard: `native-ext-binary-not-stable-across-builds`.
- The faithful fix for the flood's decision boundary, which this shares with
  `island-n-123-world-model2-leaf-permeating-light`. Nothing here narrows that; leaf 9 is a second
  worked example of it, and a cheaper one (UNATCO N=116 rebuilds in ~1 min).

## The original report

`lightrun_diff.py` on the cached pair: `Model.Lights` 941 vs 940, 214 lightmaps both sides, 13
differing.

| lightmap | native | UED22 |
|---|---|---|
| 15, 84, 94 | one light each (`light322` / `light178` / `light198`) | empty |
| 70, 72, 78, 80 | `light199` prepended to a run of 3 both sides agree on | the 3 |
| 85 | empty | 7 lights (`light339 338 332 331 177 172 207`) |
| 100 | `light312` prepended to a run of 2 | the 2 |
