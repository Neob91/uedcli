+++
priority = "p1"
kind = "debug"
summary = "Residual native render-black (s76/s69/s07 left) is ZONE/SKY PORTALIZATION, not lighting/solidity — corrects the occlusion-fix handoff premise"
+++

# Residual native render-black (s76/s69/s07 left) is ZONE/SKY PORTALIZATION, not lighting/solidity — corrects the occlusion-fix handoff premise

p1 **Residual native render-black (s76/s69/s07 left) is ZONE/SKY PORTALIZATION, not
lighting/solidity — corrects the occlusion-fix handoff premise.** After shipping the bspcsg-core
switch (decisions 2026-07-17 21:10), the coordinator framed the leftover black as "bspcsg's ~0.03%
wrongly-solid cells over-occluding light LOS." Four measurements on shipped `NativeCastle.dx` vs
editor `Test_Castle.dx` DISPROVE that: (1) point-in-solid sweep through the dark nooks is
char-for-char IDENTICAL to the editor — no wrongly-solid cell exists; (2) the +4 bias origin is not
in solid for the dark surfs; (3) with the CORRECT dark test (walk the light run for set bits — an
empty run is `iLightActors→0`-terminator, NOT `==-1`; testing `==-1` manufactures false regressions)
native has 59 dark vs editor 55, and only ONE clean native-dark-but-editor-lit surface (surf#278, a
wall — a hard bake edge case); (4) the biggest dark surfaces (skybox #461–466, towers #369–421) are
dark in BOTH maps, and s76 black pixels raycast onto surfaces that HAVE lightmaps. Conclusion: the
black is a render/zone difference (NativeCastle's incomplete zone/sky portalization — the handoff
commit says so), fixed by the zones/portalization work item, NOT by any bspcsg solidity change. Do
NOT chase a bspcsg over-occlusion fix for this — there is nothing wrongly-solid to fix (evidence in
spike §20 §18 "CORRECTED diagnosis"). Open sub-item: surf#278's single-surface dark-vs-editor-lit is
a real but tiny bake edge case (origin clear, all LOS blocked) — low priority, needs the two-sided /
lumel-position angle, not solidity.
