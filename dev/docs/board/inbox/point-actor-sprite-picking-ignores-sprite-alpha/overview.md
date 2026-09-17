+++
priority = "p1"
kind = "investigate"
summary = "point actors (rendered as sprites) select on any click inside their bounding quad, including transparent/alpha pixels"
+++

# point-actor sprite picking ignores sprite alpha

Point actors render as billboard sprites (icon textures with transparent padding around the visible
icon shape). Clicking should only select the actor when the click lands on the sprite's actually-
visible (non-transparent) pixels — not anywhere in its bounding quad, including the invisible/alpha
margin around the icon.

## Why this needs UED22 confirmation

Part of `GUI-PARITY.md`'s open "Click/hit-detection algorithm" question
(`dev/docs/board/inbox/gui-click-detection-algorithm-not-re-d-against/`). UED22 sprite icons are the
same kind of alpha-masked billboard; whether its own hit-test does per-pixel alpha testing or some
other shape (e.g. a fixed-radius circle) is unconfirmed and needs the disassembly + live-capture
method that item already scoped.

## Repro

1. Select a render mode where point actors show as sprites.
2. Click a point in the sprite's bounding quad that is clearly outside the icon's drawn shape (a
   transparent corner of the billboard).
3. Expected: the click passes through to whatever's actually visible there. Actual: the actor gets
   selected.

## Where to look

`web/src/scene/` sprite rendering + `tapSelect.ts`/`selection.ts`'s raycast-vs-AABB fallback
(`GUI-PARITY.md` already describes a "ray-vs-AABB" fallback path for sprites — likely the exact
mechanism to fix, e.g. by sampling the sprite texture's alpha channel at the hit point, or hit-testing
against a tighter shape than the full billboard quad).
