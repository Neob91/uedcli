# Native-preview anchor — the one-time LIVE reference (spec §9 build gate)

**Purpose.** The native rasterizer's texture mapping (`U = (P − base)·TextureU + PanU`,
`V = (P − base)·TextureV + PanV`, texels, V = image row top-down) is self-consistent by
construction — a systematically flipped render would pass every offline test. This spike
banks REAL-ENGINE reference renders of a known fixture level and records the three
verdicts no self-referential test can pin: **U direction**, **V row order**, and **Pan
sign/frame**. The golden image (`tests/fixtures/native_preview_golden.png`) was blessed
only AFTER these verdicts (2026-07-16).

## The fixture (`trunk/` — the committed T3D tree)

One room + one pillar, authored with uedcli verbs (live 2026-07-16):

| Actor | What | Why |
|---|---|---|
| `AnchorRoom_9cjbuh` | 512×512×256 `CSG_Subtract` at origin, ALL faces `Texture=UNATCO.UNAT_PersOnly` (a 128×128 text sign — unambiguous orientation) | U/V verdicts read straight off the rendered text |
| — its poly **3** (the −Y wall, centroid `(0,−256,0)`) | authored **`Pan U=64 V=32`** (half tile / quarter tile) | the Pan verdict face |
| `AnchorPillar_2wy2fd` | 96×96×192 `CSG_Add`, **`Rotation=(Yaw=8192)`** (45°), `Texture=UNATCO.MedSignLite_A` | rotated-brush transform reference |
| `Start_ie3yb8`, `RoomLight_rfudhj` | PlayerStart + a bright light | game-render spawn + visibility |
| `TargetPan_ole8ov` / `TargetPlain_xqukn4` | `Tag=TargetPan`/`TargetPlain` markers at the −Y / +Y wall centres | `FaceActor <tag>` aiming for the posed game shots |

Texture package closure: `UNATCO.utx` → `CoreTexDetail.utx` (+ substrate Core/Engine).
NB the first editor render silently rendered `Engine.DefaultTexture` bubbles because the
minimal package dir was missing `CoreTexDetail` — the known content→content dependency
(quirks.md "Containers / package resolution"); `OBJ LOAD` fails silently on the editor
console, so an unbound-texture render is the only symptom.

## The references

- **`editor-ref/`** — the (now retired) editor-screenshot `level preview`, shaded mode
  (`overview.png` = CAMERA ALIGN on the room, `pillar.png` = on the pillar). Captured
  BEFORE the S6 deletion, live 2026-07-16.
- **`game-ref/`** — the actual game (uplayctl session on the materialized `AnchorPan.dx`),
  player ghost-posed at pawn `(−25,−25,−80)` (eye = pawn Z + `BaseEyeHeight` 40 —
  `Human.uc:415`), `FaceActor TargetPan` → `pan-wall.png` (yaw −15215 UU), `FaceActor
  TargetPlain` → `plain-wall.png` (yaw 15429 UU). HUD/crosshair visible — ignore.
- **`native/`** — the native backend rendering the SAME trunk at the SAME eye/pose/896×800
  /75° FOV (the game's `DesiredFOV` default), for side-by-side comparison.

## Verdicts (all CONFIRMED, live 2026-07-16)

1. **U direction ✅** — `u = (P − base)·TextureU + PanU` in texels, texel column
   left-to-right in the image. Evidence: on every wall the sign text's LEFT-TO-RIGHT
   glyph order in the native render matches editor AND game (e.g. the +Y wall renders
   horizontally mirrored in both; the −Y wall does not).
2. **V row order ✅** — `v` indexes image rows TOP-DOWN (row 0 = the image's top).
   Evidence: with the builder's authored `TextureV` axes the sign text renders
   per-glyph VERTICALLY FLIPPED on the ±X/−Y walls in editor, game, and native alike
   (`overview.png` / `pan-wall.png` vs `native/pan-wall.png`).
3. **Pan sign/frame ✅** — Pan ADDS to the texel coordinate in the same frame
   (`+PanU` columns, `+PanV` rows). Evidence: `pan-verdict-bands.png` — the game's
   panned −Y wall band (top) vs native WITH the authored pan (middle: plate centres
   match within ~10 px) vs native with pan ZEROED (bottom: pattern displaced by half a
   tile horizontally and a quarter tile vertically — exactly U=64/V=32 on the 128² sign).
4. **Camera basis/FOV ✅ (bonus)** — at the identical eye/rotation the native and game
   frames compose identically (`native/plain-wall.png` vs `game-ref/plain-wall.png`:
   pillar edge and wall sign grid land at the same screen positions; small vertical
   drift ≈ eye-height smoothing, not a mapping error).

## Reproduce

```
# trunk lives here (committed); scratch copies under _scratch/anchor/
UEDCLI_PROJECT=<...>/_scratch/anchor/uedcli bin/uedcli level materialize --out <Maps>/AnchorPan.dx
cd Tools/uplayctl && bin/uplayctl session start --map AnchorPan
UPLAYCTL_SESSION=<id> bin/uplayctl send "RunConsoleCommand ghost" "SetPlayerLocation 0 0 0" \
    "FaceActor TargetPan" "GetPlayerPosition" "GetPlayerRotation"
UPLAYCTL_SESSION=<id> bin/uplayctl shot pan-wall.png
# native side: preview_native.render_shots at the read-back pose (see native/)
```

Perf note (S7 acceptance numbers live here too): see `perf.md`.
