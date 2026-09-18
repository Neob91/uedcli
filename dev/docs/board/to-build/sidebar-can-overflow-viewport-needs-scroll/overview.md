+++
priority = "p1"
kind = "debug"
summary = "sidebars can overflow the viewport, forcing page scroll -- fix both axes"
+++

# Sidebar can overflow the viewport, both axes

Owner report (2026-09-18): "Sidebar can fall outside the screen, and you need to scroll. Fix this,
vertically and horizontally."

## Likely root cause (code read, not yet live-confirmed)

`web/src/index.css`'s `.org-panel` is `flex: 0 0 220px` (fixed width, `flex-shrink: 0` implied by the
`0 0` shorthand) with `overflow-y: auto` but no `overflow-x` handling. `#app-root` (`display: flex;
flex-direction: row`) and `body`/`html`/`#root` (`width:100%; height:100%`) have no `overflow:
hidden`/`min-width: 0` anywhere in the chain to stop a non-shrinking fixed-width child from pushing
the whole page wider than the viewport -- the classic flexbox overflow trap (a flex child needs
`min-width: 0`/`min-height: 0` to be allowed to shrink below its content's intrinsic size; without
it, the PAGE grows instead of the content scrolling internally). Likely affects both `.org-panel` and
`.inspector-pane` (`web/src/App.tsx`), and both axes: horizontally on a narrow viewport (220px+280px
sidebars don't fit), vertically if a sidebar's own content (a long folder tree, a big inspector
payload) exceeds the viewport height without the wrapper chain constraining it first.

## What to do

1. Reproduce first -- narrow the viewport (or use a small/mobile emulated width) and a level with a
   large org-panel tree / inspector payload, confirm the page itself scrolls instead of the sidebar's
   own `overflow-y: auto` handling it internally.
2. Fix by ensuring every ancestor in the flex chain (`#app-root`, `.viewport-pane`, `.quad-layout-
   root`, `.org-panel-wrapper`/`.inspector-pane-wrapper`) has `min-width: 0`/`min-height: 0` where
   needed, and that `body`/`#root`/`#app-root` don't allow horizontal page overflow (`overflow-x:
   hidden` at the right level, or ensuring nothing can force width past 100%). Add `overflow-x`
   handling to `.org-panel`/`.inspector-pane` themselves if their own content (long unwrapped folder
   names, wide inspector tables) can overflow horizontally within a correctly-sized sidebar.
3. This is layout/CSS work adjacent to (but distinct from) today's `useCollapsiblePanel.ts`/sidebar-
   collapse landing -- check whether the collapse mechanism's own width transitions introduced or
   exposed this, or whether it predates that work.
4. Live-verify at multiple viewport widths (narrow mobile, in-between tablet, normal desktop) with
   real screenshots -- confirm the PAGE itself never needs horizontal scroll, and each sidebar's own
   content scrolls internally when it's taller than available height.

## Where to look

`web/src/index.css` (`.org-panel`, `.inspector-pane`, `#app-root`, `.viewport-pane`, `.quad-layout-
root`, `.org-panel-wrapper`/`.inspector-pane-wrapper`), `web/src/App.tsx`, `web/src/scene/
QuadLayout.tsx`.
