+++
priority = "p1"
kind = "implement"
summary = "radii overlay was a dark red at 0.55 alpha from a banned third-party source; real Editor.dll uses C_BrushWire in perspective, C_ActorArrow in ortho, and no alpha -- fixed"
+++

# Radii overlay hardly visible — done (real RE, 2026-09-18)

Owner report: "Radii are hardly visible in radii view. The color must be off." It was.

## What was wrong

`RadiiOverlays.tsx` painted all four overlays (perspective cylinder + sphere, ortho collision +
light) in one `RADII_COLOR = (163,0,0)` at `OVERLAY_OPACITY = 0.55`. Both came from a third-party UE1
source tree, now banned as evidence. The value `(163,0,0)` is right for two of the four; the
perspective ones are a different constant entirely, and the 0.55 alpha was invented.

## What the real binary does

Disassembled `uned/UED22/Editor.dll`'s `UEditorEngine::Draw` radii block (VA `0x1003d45b`–
`0x1003da5a`) and `uned/UED22/render.dll`'s `URender` vtable. Full trace — every RVA/VA, offset and
cross-check — is in `GUI-PARITY.md`'s "Radii overlay colors" section. The short version:

| Overlay | Pane | Draw call | Color |
|---|---|---|---|
| Collision | perspective | `URender::DrawCylinder` | `C_BrushWire` `(255,63,63)` |
| Collision | ortho | `DrawCircle` (top) / `DrawBox` (front, side) | `C_ActorArrow` `(163,0,0)` |
| Light radius | every pane | `DrawCircle` | `C_ActorArrow` `(163,0,0)` |

No blend stage exists on any of them. Values from our own `uned/UED22/unrealtournament.ini`
`[Editor.EditorEngine]`; the member offsets from our own `uned/UED22/Editor.u`'s declaration order,
anchored on `C_BrushWire = UEditorEngine+0x1ac` (already pinned live by the pivot-cross work).

## Fixed

`web/src/scene/RadiiOverlays.tsx`: two constants instead of one, no `transparent`/`opacity`.
Regression `web/src/scene/RadiiOverlays.test.tsx`. The harness (`harness-*.py` here) is a generic
PE-disassembly kit — export/import listing, VA pointer search, vtable dump, disp32 brute-force scan,
`.rdata` reads, `.u` `ScriptText` extraction.

## Left open, deliberately

- **No live browser screenshot.** This host cannot run Chromium (`chromium-1243` is missing 17
  shared libraries including `libglib-2.0.so.0`; no root, `apt-get update` denied) and rootless
  docker cannot bind-mount the worktree. Verified instead by rendering a real
  `/api/level/showcase_bar/scene` payload through `@react-three/test-renderer` and reading each
  material back. A live A/B is still owed.
- Two shape divergences the disassembly surfaced, filed separately rather than changed here:
  `gui-light-radius-is-a-camera-facing-circle-not`,
  `gui-drawcircle-segment-count-is-adaptive`.
