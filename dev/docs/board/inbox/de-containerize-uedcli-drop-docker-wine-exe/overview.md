+++
priority = "p2"
kind = "unknown"
summary = "De-containerize uedcli (drop Docker/wine/`.exe`) — roadmap specced, awaiting Andrzej's scope decision"
+++

# De-containerize uedcli (drop Docker/wine/`.exe`) — roadmap specced, awaiting Andrzej's scope decision

`p2` Spike series `dev/docs/spikes/2026-06-27-decontainerize-uedcli/` (texture/mesh/package-
write/qualify/lighting/stub-elimination) + roadmap `dev/docs/specs/2026-06-27-uedcli-decontainerization-roadmap-design.md`.
PROVEN native: texture decode (pixel-exact vs UCC), package-container write (byte-exact), qualification.
CONFIRMED: stubs exist for mesh-format + Engine/Core divergence (not v68/v69); native write deletes the
whole stub pipeline. The dominant work is the offline BSP engine (D2) + completing/​inverting the `Model`
serial format. **Geometry premise CONFIRMED game-side (🔬 2026-06-28, `decisions.md` 2026-06-28):** the
game never re-runs CSG and uses the pre-built BSP for render AND collision (0-node world → spawn crash;
68-node → spawns + walks); v69 `.dx` loads in v68 game. So Q0 is now a pure effort/strategy fork, not a
feasibility unknown. **Next gate (cheap, high-value, runnable now): hand-build a minimal native `Model`
→ native `.dx` → load in `dx-game` → does the player spawn?** — every game-pass so far used the editor's
`EDIT PASTE`; a natively-synthesized `Model` has never been game-loaded. **Still blocked on Andrzej's Q0
scope decision** (promote D2 to required vs editor-`MAP REBUILD`-only-geometry intermediate) — a scope
call only he can make. Once decided: Phase A (native texture sync / qualify / `.dx`-read,
container-free, low-risk) and Phase B (native package writer + `FPropertyTag`/`ULevel` body) triage to `to-plan`.
