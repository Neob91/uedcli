+++
priority = "p3"
kind = "finding"
summary = "Ortho pane silently switches to textured shading via focus+key"
+++

# Ortho pane silently switches to textured shading via focus+key

Live-tested finding (originally filed as "the 2D view started rendering textured for some reason!").
Root-caused, not a code defect in `OrthoViewport.tsx`'s mode-handling (`activeMaterials`, the
`mode !== 'wireframe'` mesh gate) -- that logic is correct and unchanged since `37378ecf`. Confirmed
with a headless-browser repro (screenshots): a plain click/tap anywhere inside an ortho pane sets it
as `focusedPane` (`QuadLayout.tsx`'s `onPointerDown`), which is by design (Task 20: `1`-`4` targets
"whichever pane was focused most recently"). If a `1`-`4` key is then pressed -- for any reason,
including muscle-memory aimed at the Perspective pane -- it silently sets that ortho pane's mode to
`unlit`/`flat`/`lit`, rendering the solid textured mesh instead of wireframe.

This is likely exactly what a live tester experienced: click around in the 2D view (to select/
inspect something), then press a number key, and the ortho pane goes textured with no visible
explanation. The mechanism works as designed; what makes it look like a bug is the combination of
(a) any click stealing pane focus with no visible indicator besides a small dot next to the pane
label, and (b) `GUI.md`'s own already-tracked "Known open gap": **no visible render-mode selector
UI** -- so once a pane's mode flips, there's no way to see (or reason about) why.

Not fixed here -- a real UI fix (a visible per-pane mode indicator/selector) is already in progress
in another concurrent workstream (worktree `gui-render-mode-selector`); avoid duplicating it. Once
that lands, re-check whether this confusion is resolved by visibility alone, or whether the
focus-steals-on-any-click behavior itself also needs a narrower trigger (e.g. only a drag/tap that
resolves to a selection, not a bare pointerdown).
