# Spec: unified sidebar (icon rail + one active panel)

Design process: brainstorming skill, architectural path. Clarifying questions answered via
`AskUserQuestion`; visual review via an artifact mockup (link in `overview.md`), iterated through
several rounds of owner feedback. This document is the settled result.

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
    the strip shows both when they are.
  - One line per non-empty kind (actor line, surface line), never joined with "+"/inline — each
    gets its own row so neither reads as a continuation of the other.
  - A single actor selected: `<name> · <class>`. Multiple: `<N> actors`.
  - A single surface selected: `<name> · <texture>`. Multiple: `<N> surfaces`.
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
  while any other tab (e.g. a future Texture Search) is active, so there's no remaining case that
  needs two panels visible at once. **Not a total rejection of the idea** — if a future workflow
  genuinely needs it, that's new scope for its own spec, not something this design commits to now.
- **Fixed width, ~280px.** No drag-to-resize (unlike the quad's own pane splitters) — one width,
  matching today's wider Inspector, no new persisted-resize state.
- **Right side.** Matches both of today's sidebars and this class of editor's convention.
- **Expanded by default, Selection tab active**, matching today's always-visible Inspector. Below
  the existing 768px responsive breakpoint, still collapses by default (unchanged from today's
  `useCollapsiblePanel` behavior) unless the user has manually overridden it.

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

- **`web/src/panels/Sidebar.tsx`** (new) — the shell. Renders the selection strip, the rail
  (iterating the registry), and the active panel's `render()`. Knows nothing about what a panel
  contains.
- **`web/src/panels/sidebarRegistry.ts`** (new) — an ordered list of panel definitions:
  ```ts
  type SidebarPanelDef = {
    id: string;
    icon: string;          // rail glyph, plain text/unicode — matches this app's existing
                            // no-icon-library convention (`.sidebar-toggle`'s ◀/▶)
    title: string;
    hasIndicator?: () => boolean;
    render: () => ReactNode;
  };
  ```
  Launch entries: `selection` (wraps `Inspector.tsx` unchanged), `org` (wraps `OrgPanel.tsx`
  unchanged). Adding a future panel (texture search, etc.) is a new entry here only — `Sidebar.tsx`
  itself does not change.
- **`web/src/layout/useSidebar.ts`** (new, replaces both `useCollapsiblePanel` call sites) — one
  hook: `{ collapsed, activeTabId, toggleCollapsed, setActiveTab }`. Persists to `localStorage`
  (two keys: collapse choice, active tab), same 768px-breakpoint default-when-unset behavior as
  today's `useCollapsiblePanel`/`resolveCollapsed`.
- **`OrgPanel.tsx` / `Inspector.tsx`** — internals unchanged. Each is used as-is inside its
  registry entry's `render()`.

### Selection strip data

The strip needs the current actor + surface selection identities regardless of which tab is
active — this is already available at the `App.tsx` level (the same state `Inspector`/`OrgPanel`
already receive as props today), so `Sidebar` takes it as props; no new global state.

The Selection rail icon's indicator dot is local to `Sidebar`/`useSidebar`: track the last
selection identity the Selection tab was active for (a ref), compare against current selection on
every change, show the dot when they differ and `activeTabId !== 'selection'`, clear on switching
to `selection`.

### Migration

- `App.tsx`: drop `.inspector-pane-wrapper` and its `useCollapsiblePanel('uedcli-inspector-pane-collapsed')`
  call; mount `<Sidebar>` in its place.
- `QuadLayout.tsx`: drop `.org-panel-wrapper`, its `useCollapsiblePanel('uedcli-org-panel-collapsed')`
  call, and the `OrgPanel` import. `.quad-layout-root` no longer needs to reserve sidebar width —
  simplifies (doesn't need to touch) the existing `.quad-toolbar`-anchored-to-`.quad-layout` fix.
- CSS: `.org-panel`/`.inspector` class names and their internal styling are kept as-is (re-parented,
  not rewritten); new CSS is the rail (`~36px`, plain flex column of buttons) and a shared
  `.sidebar-panel` container (`280px` fixed) plus the `.selection-strip` block.
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

- `useSidebar.test.ts` — collapse/active-tab persistence, 768px breakpoint default, same shape as
  today's `useCollapsiblePanel.test.ts`.
- `Sidebar.test.tsx` — only the active panel's content renders; indicator dot appears/clears per
  the rules above; collapsing hides the panel but keeps the rail; selection strip renders actor-only,
  surface-only, both (two lines), multi-select-collapsed-to-count, and empty states; clicking the
  strip switches to the Selection tab.
- `OrgPanel.test.tsx` / `Inspector.test.tsx` — unchanged (same props, same internal DOM).

## Open items for `plan.md`

- Exact rail icon glyphs for Selection/Org (placeholder `▣`/`☰` used in the mockup — cosmetic,
  doesn't block planning the mechanism).
- Whether `useSidebar`'s two `localStorage` keys should be namespaced together (e.g. one JSON blob)
  or stay as two plain keys mirroring today's convention — an implementation detail, not a design
  fork.
