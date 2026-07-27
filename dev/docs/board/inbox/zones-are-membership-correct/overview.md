+++
priority = "p?"
kind = "unknown"
summary = "Zones are membership-correct"
+++

# Zones are membership-correct

Native's interior/water/sky partition matches the editor
(renumbered): interior zone conn `0x6` ↔ water conn `0x6`, sky **isolated** conn `0x8` — identical
to `Test_Castle`. Native sky zone sits cleanly ABOVE the castle (z≥420, skybox at z2488–3512); **no
interior surface is wrongly assigned to the isolated sky/solid zone**, so nothing is zone-culled.
Part of one convex room renders lit while part is black in-game ⇒ not a per-zone cull.
