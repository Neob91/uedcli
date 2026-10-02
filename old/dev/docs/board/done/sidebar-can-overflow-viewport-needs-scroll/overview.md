+++
priority = "p1"
kind = "debug"
summary = "DONE -- fixed page-level horizontal overflow from the fixed-width sidebars; no separate vertical bug found"
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

## Outcome (2026-09-19)

**Root cause confirmed, horizontal half.** `.org-panel-wrapper`/`.inspector-pane-wrapper` are
non-shrinking flex children (`flex: 0 0 auto`, ~240px/~300px including their toggle strips) of
`#app-root`/`.quad-layout-root`. Neither `html`/`body`/`#root`/`#app-root` nor `.quad-layout-root`
set `overflow-x`, so once the two sidebars plus the shrunk quad content don't fit a viewport (a
custom width between the 768px collapse breakpoint and roughly 768+540px, or a sidebar manually
reopened below the breakpoint via `useCollapsiblePanel`'s localStorage override), the flex row grows
past the viewport and the whole PAGE gets a horizontal scrollbar -- exactly the report. Also found:
`.inspector-pane` was missing the `min-width: 0` `.org-panel` already had, and neither sidebar had
its own `overflow-x`, so a long unwrapped name/value inside a correctly-sized sidebar could still
visually escape it (browsers' `overflow-y: auto` -> `overflow-x: auto` coercion likely papered over
this already, but nothing made that explicit or testable).

**Vertical half: no separate bug found.** The height chain (`html`/`body`/`#root`/`#app-root` ->
`.viewport-pane` -> `.viewport-content` -> `.quad-layout-root`) is a complete `height: 100%`
chain resolving against the viewport, and both sidebars already had `overflow-y: auto` with a
definite height to scroll within. Static CSS/flexbox analysis found no path for a tall sidebar to
force page-level vertical scroll independent of the horizontal bug (a horizontal scrollbar eating
viewport height could compound it, but that's the same root cause, not a second one). Not
independently live-verified (see Verification below) -- if the owner still sees vertical page
scroll after this fix, it needs a fresh report.

**Fix** (`web/src/index.css`):
- `overflow-x: hidden` on the shared `html, body, #root, #app-root` rule -- the page itself can
  never need horizontal scroll now, regardless of what any descendant does.
- `.inspector-pane`: added `min-width: 0` (parity with `.org-panel`) and `overflow-x: auto`.
- `.org-panel`: added `overflow-x: auto` explicitly (previously relied on the browser's implicit
  `overflow-y: auto` -> `overflow-x: auto` coercion).

**Verification.** No headless browser is runnable in this sandbox (`chrome-headless-shell` is
missing shared libraries, no root to install them -- the same gap `GUI-PARITY.md` already
documents; confirmed again this session with a direct Playwright launch attempt). Verified instead:
- A new regression test, `web/src/sidebarOverflow.test.ts`, following this codebase's own established
  pattern for exactly this class of bug (`web/src/toolbarLayout.test.ts`'s doc comment: jsdom never
  lays out CSS, so these tests pin the specific rules the bug hinges on via string assertions on
  `index.css`'s own text) -- asserts the `overflow-x: hidden` rule, `.org-panel`/`.inspector-pane`'s
  `min-width: 0` + `overflow-x: auto`, and `min-width: 0` down the whole ancestor chain
  (`.viewport-pane`/`.viewport-content`/`.quad-layout-root`/`.quad-layout`).
- Full frontend suite (`web/`, vitest): 48 files / 418 tests green (`--no-file-parallelism` --
  the default parallel run hit worker-pool startup timeouts on 27 files under this sandbox's
  resource contention, an environment issue unrelated to this change; the sequential rerun is clean).
- `npx tsc -b` shows 10 pre-existing errors (missing `@types/node` for the `node:*` imports these
  CSS-assertion tests use) -- already present on master via `toolbarLayout.test.ts` before this
  change, not a regression; out of scope to fix here.

Genuinely NOT live-verified: real rendered pixels/scrollbars at narrow/tablet/desktop widths. If a
future session gets a working headless browser in this repo, re-verify with real screenshots per the
board item's original ask.
