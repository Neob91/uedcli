+++
priority = "p2"
kind = "chore"
summary = "FLAG for the texture workstream: two corpus claims in its spec/plan are measured over UNTRACKED files, so its \"exact count\" criteria cannot pass on a clean clone"
+++

# FLAG for the texture workstream: two corpus claims in its spec/plan are measured over UNTRACKED files, so its "exact count" criteria cannot pass on a clean clone

Not my change —
surfaced by a round-4 reviewer over the same commit range. (a) `<repo>/Textures` is labelled
"git-tracked, 6 packages / 418 Texture exports"; `git ls-files Textures/` returns **4** packages
(`France.utx`, `LUM_CharacterTex.utx`, `LUM_CoreTex.utx`, `LUM_InfoPortraits.utx`) totalling **384**
exports — `CoreTexSky.utx` and `CoreTexWater.utx` are untracked working-tree files. (b) The UED22
figure ("34 packages / 1,998 exports") only reproduces with a RECURSIVE scan; non-recursive gives
32 / 1,934, and the extra two are `DoNotPlaceInventorySpots/Engine.u` + `PlaceInventorySpots/`
`Engine.u`, whose 32 textures each duplicate the top-level `Engine.u`'s. Re-measure over
`git ls-files`, or commit the two `.utx` and say so, before S1 starts. (2026-07-25.)
