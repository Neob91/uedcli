# Spike 2026-07-12 — `level preview` camera pose is broken: rotation never reaches the render

## Why
A live `level preview` of the castle (2026-07-12) framed the target in only ~1 of 3 shots; the rest
buried the camera in a wall or aimed off into empty room. `@top` gave a horizon, not a top-down. The
2026-07-06 spike that built the posing recipe had **explicitly left the pitch sign + yaw compass
unverified by image** (that spike.md, lines 49–50, 204), and `preview_shots.py PRESETS` says the same
("signs PROVISIONAL until a live shot confirms"). This spike is that missing confirmation.

## Harness
`calib.py` + `spike2_lookat.py` (this dir). Both boot ONE ephemeral editor via the REAL preview code
path — `ensure_editor(ini_overrides=_ini_for_mode("shaded"))`, `_pose_camera`, `_WMCTRL_SWEEP`,
`CROP`, main-pane `screenshot` — and materialize an ASYMMETRIC landmark scene so a view's direction
is readable from its silhouette:

| direction | landmark | silhouette |
|---|---|---|
| +X East | 1 pillar | one vertical |
| +Y North | 2 pillars | two verticals |
| −X West | 3 pillars | three verticals |
| −Y South | one wide 400-u wall | a wide slab |

Plus a floor pad + ceiling bar to read pitch. Camera at room centre `(0,0,−80)`.
Run: `bash -c 'source bin/_dev-run.sh && dev_docker_run python3 <harness>.py'`.

## Finding 1 — camera ROTATION is never applied to the headless render ❌ (live 2026-07-12)
`calib.py` swept yaw `{0,90,180,270}` (pitch −3) and pitch `{−89,−45,0,45,89}` (yaw 0) via the helper-
Light + `CAMERA ALIGN` mechanism that `preview_render._pose_camera` uses. **All nine shots render the
identical level view from the identical spot, looking the same default direction** (`yaw000/090/180`
all show the SAME single centred pillar; `pitch_dn89` and `pitch_up89` both show the SAME level
horizon, not floor/ceiling). Artifacts: `_scratch/preview-calib/*.png`.

⇒ `CAMERA ALIGN` on a **point** actor (the Light helper) sets only camera **position**; the actor's
`Rotation` FRotator does **not** reach the rendered perspective view. The 2026-06-20 "ALIGN adopts the
full FRotator" result verified the *stored* camera rotation via a `MAP SAVE` readback — **never a
rendered view** — so it was true of the saved value but not of the pixels. Every past "distinct posed
image" differed by the helper's **position**, which mis-read as rotation working. **The `PRESETS`
pitch/yaw table is therefore irrelevant** — no angle is ever honoured.

This fully explains the castle preview: shots differed only by camera position, so framing was a
lottery and `@top`/yaw did nothing.

## Finding 2 — `CAMERA ALIGN` on a BRUSH re-aims AND repositions; the render DOES reflect it ✅
`spike2_lookat.py` aligned to each landmark **brush** in turn. The docs said aligning to a
`Class=Brush` does a "look-at/frame" (not a rotation-adopt). Confirmed, with a catch:
- The camera **repositions + aims to FRAME the brush**, and the **render reflects it** (unlike the
  point-actor path) — `south_wall.png` (the big 400-u wall) is a clean interior look at the wall.
- **Framing distance scales with the brush's SIZE.** The three 48-u pillars (`East/West/North`) each
  put the camera almost *inside* the pillar → a blurry texture close-up, and being identical-sized
  they produced **byte-identical** images (`md5` match) regardless of their different locations.
- The framing **angle is canonical** (fixed relative to the brush), not caller-chosen.
Artifacts: `_scratch/preview-lookat/*.png`.

⇒ A working aim primitive exists: **align to a brush that spans the target's bounding box** → a
reliable framed shot of that target, from a canonical angle, pulled back ∝ the box size.

## Consequence / fix direction
The `POS@ROT` interface can't work as built — rotation is unrenderable via the point-align path.
Rebuild `level preview` posing around **look-at / auto-frame**: "frame this target" (an actor, an
explicit bbox, or the whole level) by aligning to a transient brush covering it. Open sub-question for
implementation: whether the framing **angle** can be steered (e.g. pre-position the camera via a point-
align, then brush-align to fit — untested) or is canonical-only. Even canonical-only is a large net
win over today's framing lottery.

Superseded: `preview_shots.PRESETS` semantics; `rendering.md` "Posed shots" claim that the main-pane
ALIGN path yields arbitrary posed shots (it yields arbitrary **positions**, fixed orientation).

## Finding 3 — RMB-DRAG rotates the rendered view: arbitrary orientation IS achievable ✅ (live 2026-07-12)
The console rotation paths are all dead (Finding 1: point-align stores-but-doesn't-render; Finding 2:
brush-align snaps to a canonical frame ignoring prior position — `spike4` gave 4 byte-identical shots).
But **`wine_ctl drag` (RMB drag = camera mouselook) rotates the camera AND the render reflects it**
(a real drag forces the llvmpipe repaint a console command can't). `spike5_drag.py`: from the room
centre, six RMB-drags gave **six DISTINCT images** (md5). Calibrated in the preview full-window pane:
- **Default facing after point-align = +X (East), pitch ~0** (`default.png` = the 1-pillar East view).
- **+dx → yaw** (`yaw_p1500` = dx+1500 ≈ 90° swung the North 2-pillars into frame; a room corner
  appears). **+dy → pitch DOWN** (`pitch_p500` = dy+500 looks straight at the floor). Rate ≈ **0.06°/px
  yaw, 0.10°/px pitch** (per `wine_ctl cmd_drag`; relative-motion, paced, RMB). Artifacts:
  `_scratch/preview-drag/*.png`.

⇒ **The fix**: position via point-align (Finding 1's working half), orientation via a computed
RMB-drag delta from the known default (East/level). Free-pose = drag to (pitch,yaw); look-at = drag to
the (pitch,yaw) of the POS→TARGET vector; presets = compute POS + look-at. Exact deg/px + the default
facing must be pinned precisely (open-loop, optionally closed-loop-refined) during implementation.

## Finding 4 — brush-align view direction follows the target's YAW (azimuth), never its pitch/roll ✅❌ (live 2026-07-12)
Follow-up to "no mouse drag / no world-rotation": can the *canonical* brush-align angle be steered by
the TARGET BRUSH's orientation? Tested with a flat "signboard" slab (320×24×200, big-face normal ±Y)
at the room centre, aligned at several rotations (`spike6_oriented.py`, `spike7_elevation.py`):
- **YAW steers AZIMUTH ✅.** `yaw0` vs `yaw90` — the world-axis gizmo rotates 90° (+X points right at
  yaw0; +Y points right at yaw90), i.e. the camera orbited 90° horizontally with the slab. Distinct
  images per yaw. (Distance ∝ presented face size — a rotated slab frames closer; controllable via
  slab size.)
- **PITCH and ROLL do NOT tilt the camera ❌.** `pitch45`, `pitch90`, `roll45`, `roll±90` all render a
  LEVEL view (gizmo Z-up unchanged, horizon centred); `roll90`==`roll_n90` byte-identical. The camera
  stays upright/level regardless of the target's pitch/roll — brush-align uses only the horizontal
  (yaw) component of the target's facing. Artifacts: `_scratch/preview-oriented/*`, `_scratch/preview-
  elevation/*`.

⇒ **Ceiling of the console-only (no-drag) mechanism:** view a target from any AZIMUTH (compass
bearing) + any HEIGHT (target Z) + any DISTANCE (target size), but **always LEVEL** — no top-down /
elevated bird's-eye. Elevation would require the mouse-drag (rejected, Finding 3) or world-rotation
(rejected). Build target = **horizontal look-at / orbit**: spawn a throwaway target brush at the
look-at point, yaw it so align frames from the desired bearing, align, render.
