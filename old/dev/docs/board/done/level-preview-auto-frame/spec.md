# Spec — `level preview` auto-frame (replace broken POS@ROT posing)

**Status:** revised 2026-07-12 after two cold reviews (findings resolved inline below).
Ephemeral; fold decisions into `decisions.md` + `rendering.md` on land.
**Evidence:** `dev/docs/spikes/2026-07-12-preview-pose-calibration/spike.md` (+ `spike3_castle.py` shots).

## Problem
`level preview`'s pose is non-functional: `CAMERA ALIGN` on the helper **point** actor sets camera
**position only** — the `Rotation` never reaches the headless render (calibration: all 9 pitch/yaw
poses → identical view). So `POS@ROT` can vary only *where the camera stands*, never *where it looks*.
The `PRESETS` table is moot.

## Working mechanism (verified) + its honest limits
`CAMERA ALIGN NAME=<BRUSH>` repositions **and aims** the camera to FRAME that brush, and the render
reflects it (verified live on the castle: `frame_keep`, `frame_tower`, `over_world` are distinct,
correctly-aimed shots). **Limits, stated honestly (both reviewers, A#1/A#5/B-M2):**
- **Framing is size-locked and tight.** Distance ∝ the target brush's own size. A room-sized *subtract*
  → a wide interior establishing shot (the good case). A big solid (keep/tower) → a usable but tight
  shot with little margin. A *small* solid (a door) → a near-useless close-up of its own face. There
  is **no in-context padding / zoom-out** in v1.
- **One canonical angle per brush.** No multi-angle survey; two identical brushes in identical
  surroundings render identically (the spike's byte-identical pillars). This is a real capability
  reduction vs the *promise* of old POS@ROT (which never actually delivered multiple angles either —
  it only varied position — but the intent is now explicitly deferred).
- **Interior only.** Every camera is inside the level's enclosing subtract; no exterior bird's-eye.
  That's level geometry, not a preview limit.

⇒ The **reliably-useful** shot is the **overview** (frame the enclosing subtract). Framing a specific
brush is a secondary, size-dependent convenience. The interface centers the overview accordingly.

## Design — auto-frame a target
Per-shot grammar `TARGET[:MODE][=NAME]`; `TARGET` omittable (defaults to the overview).

- **No TARGET** (`level preview --out-dir D`) or **`all`/`level`** → the **overview**: frame the level's
  enclosing volume. `:MODE`/`=NAME` still allowed on the bare `all` token.
- **A brush actor name** → auto-frame that brush (tight, size-locked; documented). Resolved
  case-insensitively via `query.resolve_actor_name`.
- **`:MODE`** and **`=NAME`** unchanged (`:` and `=` are safe delimiters — UnrealEd FNames contain
  neither; state this invariant in code).

### Reserved-token precedence (A#3/B-M3)
`all` and `level` are **reserved**, checked **before** `resolve_actor_name`, case-insensitively — so a
brush literally named `all`/`level`/`ALL` is shadowed and unreachable via preview. Documented in
`--help`. (Chosen over introducing an `actor bbox` query verb now — that's logged as a follow-up so
the overview stays composable later; for v1 a reserved word is the smaller change.)

### Overview resolution (C1/C2/A#2 — resolve in dispatch, to a concrete brush)
In `dispatch._level_preview` (where the `Level` is already loaded, BEFORE any editor boot), resolve
`all`/`level`/no-target → the name of the brush with the **largest world-space AABB volume among
`CSG_Subtract` brushes** (the enclosing room is a subtract; a big solid ADD frames uselessly per the
limits above, so solids are NOT overview candidates). World AABB uses `rotation.world_vertices(actor)`
(honors Location/rotation), **not** the brush-local `doctor._aabb` (A#7). Tie-break: first in
`level.order` (deterministic). If **no subtract brush exists**, exit 2 with a clear message naming the
level: `level '<name>' has no enclosing (subtract) brush to frame for an overview; name a specific
brush actor instead`. `preview_render` then only ever receives a **real brush name** — `_frame_target`
stays single-path (no `all` branch in the renderer).

### Target validation (A#4/m1 — up front, pre-boot, all-or-nothing)
For each resolved TARGET, in `dispatch._level_preview` before booting any editor:
- must resolve to an existing actor (else exit 2 `actor not found: <target>` — print our own string;
  `resolve_actor_name` raises `KeyError` whose text is in `e.args[0]`, not `str(e)` (m3/A#8));
- must be a **brush** actor: `actor.brush is not None`. A Mover carries a brush and is allowed. A
  point actor (Light/PlayerStart/…) → exit 2 `cannot frame point actor '<name>' (class <cls>):
  auto-frame needs a brush; use 'all' for the level overview`.
- a stray `@` in a target (old syntax) → the resolve fails; add a hint: `('<t>' looks like the old
  POS@ROT syntax, which was removed — pass a brush name or 'all')` (m4).

## Code changes
- `preview_shots.py`: `Shot(pos,rot,rot_label,mode,name)` → `Frame(target: str, mode, name)`. Delete
  `PRESETS`, `_parse_pos`, `_parse_rot`, `SHOT_TOKEN`, the `@` grammar. `parse_shot`→`parse_frame`
  (`TARGET[:MODE][=NAME]`; empty target only allowed as the literal bare form → normalized to `all`;
  empty `=NAME`/unknown `:MODE` → ValueError as today). `shot_filename`→`frame_filename`: stem =
  `=NAME` else the target; **keep a slug-safety fallback** — if the target isn't slug-safe, fall back
  to `shot-<i>` (A#6); `all` is slug-safe. Keep `MODE_INI`.
- `preview_render.py`: `_pose_camera` → `_frame_target(drv, name)`: `selectname(name);
  camera_align(name=name)` (the `selectname` is kept intentionally — matches the verified spike recipe;
  the gizmo it draws is cleared by the existing `ACTOR SELECT NONE` in `_render_one`). Drop
  `_resolve_pos`. `_render_one` calls `_frame_target(drv, frame.target)`.
- `dispatch._level_preview`: parse frames; resolve `all`/`level`/no-target → concrete brush name
  (overview resolution above); validate every TARGET (validation above); pass real brush names on.
- `cli.py`: `_CoordArgumentParser._parse_optional` — **drop the `SHOT_TOKEN` branch, KEEP the
  `_COORD_TOKEN` branch** (still needed for `--at`; A#7). Remove the `from .preview_shots import
  SHOT_TOKEN` import. Preview positional: `nargs="*"` metavar `TARGET[:MODE][=NAME]`, rewritten
  `help=` (targets are actor names or `all`; explain size-locked framing + reserved words).
- Promote `world`-AABB helper: add a small `bbox`/AABB util (reuse `rotation.world_vertices` + min/max)
  usable by the overview resolver now and a future `actor bbox` verb (don't reach into `doctor._aabb`).

## Interface examples
```
level preview --out-dir shots                     # overview (frames the enclosing subtract)
level preview --out-dir shots all:wire=overview   # overview, wireframe
level preview --out-dir shots Keep_8ghqei         # tight shot of the keep (size-locked)
level preview --out-dir shots all TowerNE_1f5drh  # overview + a tower
```

## Migration — everything that references the removed API (M1/A#4)
- **Tests (rewrite/replace):** `tests/test_preview_shots.py` (all `parse_shot`/`PRESETS`/
  `shot_filename`), `tests/test_preview_render.py` (`Shot(...)`, `_resolve_pos`, `_pose_camera`),
  and any preview cases in `tests/test_preview.py` / `tests/test_dispatch.py` / the integration test.
  New tests: `parse_frame` (`TARGET`, `:mode`, `=name`, `:mode=name`, bare `all`, bad mode, empty
  name); reserved-token shadows an actor named `all`; overview resolver picks the largest subtract,
  tie-break by order, and errors on a no-subtract level; point-actor target → exit 2 naming actor+class;
  `frame_filename` (`=NAME`, `<target>`, `<target>-<mode>`, non-slug-safe fallback, `-2` collision);
  `_frame_target` mock-Driver test (issues `selectname`+`camera_align(name=)`, no helper add/delete).
- **Docs:** `dev/docs/unrealed/rendering.md` (correct "Posed shots" → auto-frame only; cite spike),
  `docs/usage.md` (`level preview` section still shows POS@ROT + stale VNC/session model),
  `dev/docs/architecture.md` (preview description), module docstrings in `preview_shots.py`/
  `preview_render.py`/`dispatch._level_preview` that cite the 2026-07-06 spec.
- `decisions.md`: new UTC-stamped entry (POS@ROT→auto-frame; rejected alt: keep chasing rotation-
  render now / union-AABB marker). Inbox: (a) "steerable framing angle" follow-up carrying the
  spike's specific untested lead — *point-align to set position, then brush-align to fit* (m5/A#5);
  (b) "`actor bbox` query verb" so overview/selection composes (B-M3); (c) note v1's capability
  reduction so Andrzej can weigh it (A#5).
```
