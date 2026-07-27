+++
priority = "p1"
kind = "debug"
summary = "Native map built by `bspcsg` does not become PLAYABLE in-game (pawn never possesses / `--game` travel never completes) even though the shipped map travels fine in the same warm container"
+++

# Native map built by `bspcsg` does not become PLAYABLE in-game (pawn never possesses / `--game` travel never completes) even though the shipped map travels fine in the same warm container

Confirmed 2026-07-17: `--game --map <our.dx>` never possesses a pawn on the UNATCO
map (travel deadline expires → REBOOT_BUDGET retries burn the whole timeout), while
`03_NYC_UNATCOHQ.dx` travels + shoots 5 frames in the SAME warm container — so it's OUR build, not
the harness. A direct link probe (drive the warm container: `TravelToLevel <our-stem>` then poll
`GetCurrentLevelName`/`Ping`) shows the link goes **completely dead** after the travel — no reply
for 120s — so the engine **crashes or hangs at LOAD time** on our `.dx`, which is DISTINCT from
(and earlier than) the runtime "pawn falls through the floor" collision-fall (that would still
LOAD + possess, then sink). So it is NOT confirmed to be only the collision-hull leak
(MEMORY: native-castle-blocker-is-collision; architecture.md "leaf-bounding repair"/
`bound_leaked_solid_leaves`); it needs a **game-log capture on load** to pin the cause — a bad
export/ref/BSP the always-on OFFLINE self-check doesn't catch, a missing package, or the hull leak
surfacing as a load-time AV. Next step: `--keep-alive` a container, travel to our map, read
`DeusEx.log`. **BUT the GEOMETRY is correct and renders**: the OFFLINE native rasterizer (`level preview
--native`, routed through `build_geometry_bspcsg`) renders the UNATCO trunk recognizably — the
spawn corridor (tiled walls + red herringbone floor + "U.N.A.T.C.O. Personnel ONLY" sign), Manderley's
wood-paneled office (both framed diplomas + desk), the security room — matching the editor golden's
BSP geometry (shots in `_scratch/shots/unatco-native-offline` vs `unatco-editor`). Missing in the
draft tier: mesh/decoration actors (terminals, chairs), lighting, sky projection. So: **the rotation
fix + bspcsg build produce correct renderable geometry; the in-game LOAD failure is the single
biggest blocker to a WALKABLE native UNATCO** (diagnose via DeusEx.log; likely `bound_leaked_solid_leaves`
/ hull emission at DX scale, or an export/ref the offline self-check misses). (`--native` had to
no-op its scale-reject gate, like materialize, to accept the ~90 PostScale'd brushes — same
scale-drop gap.)
