# Spec: unified sidebar (icon rail + one active panel)

Design process: brainstorming skill, architectural path. Clarifying questions answered via
`AskUserQuestion`; visual review via an artifact mockup (link in `overview.md`), iterated through
several rounds of owner feedback. Revised once more after a `requesting-code-review`-style spec
review (registry render-signature fix, the texture-ref field's real data source, the collapse
affordance, the `sidebarOverflow.test.ts` dependency, and other gaps below — resolved by matching
existing code/decisions already on record, not new owner input). This document is the settled
result.

## Problem

Two independently-collapsible sidebars exist today, both on the right, at two different DOM
levels:

- `OrgPanel.tsx` (`.org-panel`, 220px, `web/src/panels/OrgPanel.tsx`) — actor name search + label
  chip filters + folder tree, nested inside `QuadLayout.tsx`'s `.quad-layout-root`.
- `Inspector.tsx` (`.inspector-pane`, 280px, `web/src/panels/Inspector.tsx`) — read-only
  actor/surface property viewer, a top-level sibling in `App.tsx`, outside `QuadLayout` entirely.

Each has its own `useCollapsiblePanel` instance and its own `localStorage` key. The owner wants one
sidebar, near-100%-of-viewport by default (only a small permanent margin), that can grow to
surface more tools later (texture alignment, actor/texture/sound/music search, editable properties)
without becoming cluttered.

## Decisions (from `AskUserQuestion` rounds)

- **Scope**: design the general panel system now; launch with two panels (Selection, Org/Search).
  Every other listed idea (texture align, texture/sound/music search, editable properties) is a
  later addition to the same system, out of scope for the first implementation.
- **One panel visible at a time**, switched via a **permanent icon rail** (not tabs-on-open, not a
  context-driven single slot). The rail is the "small margin" the viewport gives up even when
  everything else is collapsed.
- **No auto-switching, ever.** Selecting something in the viewport, or via the Org tab, never
  forces the sidebar open or forces a tab switch. Reason (owner): future panels (brush builders,
  etc.) must not have a stray click or exploratory browsing yank the user's tab away.
- **Selection has a non-intrusive discoverability signal instead**: a small dot indicator on the
  Selection rail icon when there's unseen selection content and Selection isn't the active tab.
  Clearing happens by switching to the Selection tab yourself.
- **A persistent "current selection" strip, always visible above the active panel** (whichever tab
  is showing) — added after the owner felt the no-auto-switch + dot-only design didn't surface
  enough at-a-glance info. This is the one piece of "Selection" content that isn't gated behind the
  Selection tab.
  - Actor and surface selection are **not mutually exclusive** — both can be non-empty at once, and
    the strip shows both when they are. Confirmed against UED22 by disassembly (GUI-PARITY.md
    "Actor + surface selection coexist; only a plain click clears both") and already implemented in
    `App.tsx`: a PLAIN pick clears both kinds; a Ctrl+pick, a Shift+pick of a surface's owning brush,
    and the org panel's batch select (`onSelectMany`, which never clears surfaces at all, additive or
    not) all leave the other kind standing. The strip just renders whatever `selectedNames`/
    `selectedSurfaces` currently hold — it needs no gating logic of its own; `App.tsx`'s existing
    handlers are the only place this rule is enforced.
  - One line per non-empty kind (actor line, surface line), never joined with "+"/inline — each
    gets its own row so neither reads as a continuation of the other.
  - A single actor selected: `<name> · <class>`. Multiple: `<N> actors`.
  - A single surface selected: `<name> · <texture ref>`, where `<texture ref>` is
    `#<poly.tex_index>` (or `(untextured)` when `tex_index < 0`) — the exact string
    `Inspector.tsx`'s own `SurfaceDetail` already shows (`poly.tex_index >= 0 ? '#${poly.tex_index}'
    : '(untextured)'`). Not a texture NAME: the client has no texture-catalog lookup today
    (`Inspector.tsx`'s own doc comment says so), so the strip matches the one texture-identifying
    string that already exists rather than inventing a new one. Multiple surfaces: `<N> surfaces`.
  - Each line is prefixed with a small colored **icon token** (not a word) marking actor vs.
    surface — e.g. `▣` for actor, `▦` for surface (exact glyphs are a later polish pass, owner
    deferred this). This is deliberate: a text label like "Surface" sitting next to a name is
    ambiguous if an actor is ever literally named or classed that — an icon is a separate,
    non-user-editable channel, so it can't collide with arbitrary content.
  - Clicking the strip **does** switch to the Selection tab. This is a deliberate user action on a
    dedicated control, not an automatic side effect of selecting in the viewport — it does not
    violate the no-auto-switch rule above.
  - This strip is also what resolved a separate concern (below) about wanting two panels open at
    once.
- **No simultaneous multi-panel / split view.** Raised as a concern (wanting Selection + Texture
  Search open together while assigning a texture to a surface) and explicitly dropped once the
  persistent strip covered the actual need — the strip already shows the selected surface's texture
  reference while any other tab (e.g. a future Texture Search) is active, so there's no remaining
  case that needs two panels visible at once. **Not a total rejection of the idea** — if a future
  workflow genuinely needs it, that's new scope for its own spec, not something this design commits
  to now.
- **Fixed width, ~280px.** No drag-to-resize (unlike the quad's own pane splitters) — one width,
  matching today's wider Inspector, no new persisted-resize state.
- **Right side.** Matches both of today's sidebars and this class of editor's convention.
- **Expanded by default, Selection tab active**, matching today's always-visible Inspector. Below
  the existing 768px responsive breakpoint, still collapses by default (unchanged from today's
  `useCollapsiblePanel` behavior) unless the user has manually overridden it.
- **Collapse control: click the active rail icon again.** Already decided in the original
  `AskUserQuestion` round ("a slim icon rail... click an icon to open that panel, click its active
  icon again to collapse") but never carried into this document — restating explicitly since a
  plan-writer needs a concrete affordance: there is no separate `◀`/`▶` toggle button (that was
  today's per-sidebar `.sidebar-toggle`, which is removed). Clicking a non-active rail icon switches
  to it (and expands if collapsed); clicking the ALREADY-active icon collapses.
- **The selection strip stays visible even when the sidebar is collapsed**, shrunk to its icon
  token(s) only (no name/class text — there's no room in the ~36px rail width). This follows directly
  from the strip's own reason for existing (know what's selected without opening a panel) — collapsing
  the panel shouldn't defeat that. Expanding restores the full `<name> · <class>` text.

## Architecture

One `Sidebar` component, mounted once, replacing both of today's mount points. This is also what
fixes the actual structural bug behind the "double sidebar" complaint (two different DOM levels) —
`QuadLayout.tsx` stops knowing about the org panel at all, so `.quad-layout-root` becomes just the
2×2 grid.

```
App.tsx
 └─ #app-root (flex row)
     ├─ .viewport-pane (toolbar row + QuadLayout, unchanged except OrgPanel removed)
     └─ Sidebar               <-- new, replaces .inspector-pane-wrapper
         ├─ selection strip   <-- always rendered, independent of active tab
         ├─ sidebar rail      <-- permanent, ~36px
         └─ active panel      <-- one of the registry entries below, ~280px when expanded
```

### Components

- **`web/src/panels/sidebarRegistry.ts`** (new) — the panel definition shape, and a factory that
  BUILDS the ordered list each render (not a static module-level list — `OrgPanel`/`Inspector` each
  need live `App.tsx` state as props, which a prop-less `render()` couldn't supply):
  ```ts
  export interface SidebarPanelDef {
    id: string;
    icon: string;          // rail glyph, plain text/unicode — matches this app's existing
                            // no-icon-library convention (`.sidebar-toggle`'s ◀/▶)
    title: string;
    hasIndicator: boolean; // already computed by the caller for THIS render, not a callback
    content: ReactNode;    // already-rendered — e.g. <Inspector selected={...} .../>
  }

  export function buildSidebarPanels(props: {
    selected: SceneActor[];
    selectedSurfaces: SurfaceSelection[];
    hasUnseenSelection: boolean;
    actors: SceneActor[];
    selectedNames: ReadonlySet<string>;
    onSelectActor: (name: string, additive: boolean) => void;
    onSelectMany: (names: ReadonlySet<string>, additive: boolean) => void;
  }): SidebarPanelDef[]
  ```
  Launch entries: `selection` (`<Inspector selected={props.selected}
  selectedSurfaces={props.selectedSurfaces} />`, `hasIndicator: props.hasUnseenSelection`), `org`
  (`<OrgPanel actors={props.actors} selectedNames={props.selectedNames}
  onSelectActor={props.onSelectActor} onSelectMany={props.onSelectMany} />`, `hasIndicator: false` —
  Org has no discoverability signal in this design). Adding a future panel (texture search, etc.) is
  a new case inside `buildSidebarPanels` plus whatever new props it needs threaded in from
  `App.tsx` — `Sidebar.tsx` itself still does not change, since it only ever reads the generic
  `SidebarPanelDef` shape (`icon`/`title`/`hasIndicator`/`content`), never panel-specific props.
- **`web/src/panels/Sidebar.tsx`** (new) — the shell. Takes `panels: SidebarPanelDef[]` (from
  `buildSidebarPanels`) plus the `useSidebar()` state below. Renders the selection strip, the rail
  (one button per panel, dot shown when `panel.hasIndicator`), and the active panel's `content`.
  Knows nothing about what a panel contains — the indicator mechanism is generic (reads a boolean off
  each def), not hardcoded to the `selection` panel.
- **`web/src/layout/useSidebar.ts`** (new, replaces both `useCollapsiblePanel` call sites) — one
  hook: `{ collapsed, activeTabId, setActiveTab }` — no separate `toggleCollapsed` in the public
  shape, since `setActiveTab` is the only thing that ever changes `collapsed` (clicking a
  non-active icon: switch tab, expand; clicking the active icon: collapse). Persists to
  `localStorage` (two keys: collapse choice, active tab), same 768px-breakpoint
  default-when-unset behavior as today's `useCollapsiblePanel`/`resolveCollapsed`.
  `Sidebar.tsx`'s rail button `onClick` always calls `setActiveTab(panel.id)`, never a separate
  collapse handler.
- **`OrgPanel.tsx` / `Inspector.tsx`** — internals unchanged. Each is invoked as-is inside
  `buildSidebarPanels`, same props they already take today.

### Selection strip data

The strip needs the current actor + surface selection identities regardless of which tab is
active — this is already available at the `App.tsx` level (the same state `Inspector`/`OrgPanel`
already receive as props today), so `App.tsx` computes `hasUnseenSelection` and passes both it and
the raw selection down through `buildSidebarPanels`'s props; no new global state.

`hasUnseenSelection` (a new small hook, `useSelectionSeen` or inlined in `App.tsx` — implementation
detail for `plan.md`): track the last selection identity seen while `activeTabId === 'selection'`
(a ref), compare against the current selection on every change, `true` when they differ AND
`activeTabId !== 'selection'`, reset to `false` the instant `activeTabId` becomes `'selection'`.
This is the ONLY thing computing `hasIndicator` for the `selection` entry — `Sidebar.tsx` itself
just reads whatever boolean each `SidebarPanelDef` carries.

### Migration

- `App.tsx`: drop `.inspector-pane-wrapper` and its `useCollapsiblePanel('uedcli-inspector-pane-collapsed')`
  call; mount `<Sidebar>` in its place.
- `QuadLayout.tsx`: drop `.org-panel-wrapper`, its `useCollapsiblePanel('uedcli-org-panel-collapsed')`
  call, and the `OrgPanel` import. `.quad-layout-root` no longer needs to reserve sidebar width —
  simplifies (doesn't need to touch) the existing `.quad-toolbar`-anchored-to-`.quad-layout` fix.
- CSS, precisely (two DIFFERENT classes were conflated in an earlier draft of this document —
  `.inspector-pane` is the 280px WRAPPER box in `index.css` today, `.inspector` is `Inspector.tsx`'s
  own internal `dt`/`dd`/`table` styling and is untouched either way):
  - `.org-panel` (today: `flex: 0 0 220px`, its own padding/background/border) and `.inspector-pane`
    (today: `flex: 0 0 280px`, `min-width: 0`, `overflow-x: auto`, padding/border) both LOSE their own
    box-sizing rules (`flex`/`min-width`/`overflow-x`/border) — those move to the new shared
    `.sidebar-panel` (`width: 280px` fixed, `min-width: 0`, `overflow-x: auto`, one border). What's
    left of `.org-panel`/`.inspector` (padding/background for `.org-panel`'s own content; `Inspector`'s
    internal table/dt/dd rules) stays, nested inside `.sidebar-panel`.
  - New: `.sidebar-rail` (`~36px`, plain flex column of buttons) and `.selection-strip` (its own
    block, collapsing to icon-only width per the Decisions section above).
  - **`web/src/sidebarOverflow.test.ts` MUST be updated in the same change**, not left behind: it
    currently asserts `.org-panel`/`.inspector-pane` each carry `min-width: 0` + `overflow-x: auto`,
    and that `.viewport-pane`/`.viewport-content`/`.quad-layout-root`/`.quad-layout` carry
    `min-width: 0` (pinning the fix for a real prior bug — a non-shrinking sidebar forcing the whole
    page to scroll horizontally). Once those two rules move to `.sidebar-panel`, this test's
    `.org-panel`/`.inspector-pane` assertions must be repointed at `.sidebar-panel` (same properties,
    new selector) — the four ancestor-chain assertions (`viewport-pane` etc.) are unaffected and stay
    as-is, since that chain doesn't change.
- `localStorage`: old keys (`uedcli-org-panel-collapsed`, `uedcli-inspector-pane-collapsed`) are
  simply abandoned (no migration) — per this project's no-back-compat-cruft convention, a stale
  browser localStorage key left over from a prior session is not a compatibility concern worth
  coding around.

## Non-goals (explicitly cut, YAGNI)

- Drag-to-resize the sidebar.
- Multiple panels visible/docked at once (split view). Superseded by the persistent strip for the
  one concrete case raised; revisit only if a real new case shows up.
- Auto-switching the active tab on any selection event.
- Picking the exact rail icon glyphs — placeholder glyphs only, owner deferred final icon choice to
  a later pass.

## Out of scope for this spec, but designed for

These are why the registry exists rather than two hardcoded panels — each becomes a new
`sidebarRegistry.ts` entry in its own future spec, no changes to `Sidebar.tsx`/`useSidebar.ts`:

- Texture search / alignment (server-side catalog already exists: `uedcli/texture_catalog.py`,
  `uedcli/cli/commands/texture.py` — no GUI exposure yet).
- Sound/music search (`uedcli/audio_catalog.py`, `uedcli/cli/commands/audio.py` — same gap).
- Editable actor properties (`Inspector.tsx` is read-only today; `dev/docs/GUI.md`'s "Future
  direction" section already notes the owner wants effective-vs-own-property display and editing —
  unrelated to this spec beyond both living in the `selection` registry entry eventually).

## Testing

- `useSidebar.test.ts` — collapse/active-tab persistence, 768px breakpoint default (same shape as
  today's `useCollapsiblePanel.test.ts`), plus `setActiveTab(currentlyActiveId)` collapses instead of
  no-op'ing.
- `sidebarRegistry.test.ts` — `buildSidebarPanels` returns the `selection`/`org` defs with the right
  `content`/`hasIndicator` for a given props shape (no rendering assertions needed beyond what
  `Sidebar.test.tsx` already covers end to end).
- `Sidebar.test.tsx` — only the active panel's content renders; a panel's dot appears/clears per
  `hasIndicator`; clicking the active rail icon again collapses; collapsing hides the panel content
  but keeps the rail AND the strip (shrunk to icon-only); selection strip renders actor-only,
  surface-only, both (two lines), multi-select-collapsed-to-count, and empty states; clicking the
  strip switches to the Selection tab.
- `sidebarOverflow.test.ts` — updated in place (see Migration) to assert `.sidebar-panel` instead of
  `.org-panel`/`.inspector-pane`; the four ancestor-chain assertions are untouched.
- `OrgPanel.test.tsx` / `Inspector.test.tsx` — unchanged (same props, same internal DOM).

## Open items for `plan.md`

- Exact rail icon glyphs for Selection/Org (placeholder `▣`/`☰` used in the mockup — cosmetic,
  doesn't block planning the mechanism).
- Whether `useSidebar`'s two `localStorage` keys should be namespaced together (e.g. one JSON blob)
  or stay as two plain keys mirroring today's convention — an implementation detail, not a design
  fork.
- The icon-only shrink treatment for the collapsed strip (stacked dots vs. a single combined badge
  when both actor and surface are selected) — a small visual detail, not a mechanism question.
