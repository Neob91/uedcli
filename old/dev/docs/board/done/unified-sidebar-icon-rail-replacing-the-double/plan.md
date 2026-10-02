# Unified Sidebar (Icon Rail) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two independently-collapsible sidebars (`OrgPanel` nested in `QuadLayout`, `Inspector` a top-level sibling in `App`) with one `Sidebar` component: a permanent icon rail plus one active registry-driven panel, extensible to future panels by adding registry entries only.

**Architecture:** A new `sidebarRegistry.ts` builds an ordered list of ALREADY-RENDERED `SidebarPanelDef`s (`content: ReactNode` plus a plain `hasIndicator: boolean`, not closures a prop-less `render()`/`hasIndicator()` callback would have to invoke) from the live `App.tsx` props each launch panel (`Inspector`, `OrgPanel`) actually needs. A new `useSidebar.ts` hook -- called by `App.tsx` itself, not `Sidebar.tsx` -- owns collapse + active-tab state as `{ collapsed, activeTabId, setActiveTab }` (no separate `toggleCollapsed`: `setActiveTab` alone decides collapse-vs-switch), persisted to two `localStorage` keys. A new `useSelectionSeen.ts` hook, also called by `App.tsx`, tracks the Selection tab's own "last seen" identity and produces the `hasUnseenSelection` boolean fed into `buildSidebarPanels`. `Sidebar.tsx` itself is purely presentational: it receives `panels`/`collapsed`/`activeTabId`/`setActiveTab`/the raw selection as props and renders the persistent selection strip (mounted even while collapsed, shrunk to icon tokens), the rail (reading `panel.hasIndicator` uniformly, never hardcoded to any one panel id), and the active panel's `content`. `App.tsx` mounts `<Sidebar>` in place of its old `.inspector-pane-wrapper`; `QuadLayout.tsx` drops `OrgPanel` and its own collapsible-panel wiring entirely, and the `F`-key camera-framing mechanism it used to own locally is lifted into `App.tsx` as a controlled prop pair (`frameRequest`/`frameActors`) so the org panel -- now hosted by `Sidebar`, a sibling of `QuadLayout` rather than its child -- can still trigger it.

**Tech Stack:** React 19, TypeScript (strict, `verbatimModuleSyntax`, `noUnusedLocals`/`noUnusedParameters`), Vitest + `@testing-library/react`, plain CSS custom properties (no CSS framework).

**Spec:** `dev/docs/board/to-plan/unified-sidebar-icon-rail-replacing-the-double/spec.md` (settled; read alongside this plan — this plan argues from it and does not restate every rationale).

## Global Constraints

- One panel visible at a time, switched only via the permanent icon rail — never tabs-on-open, never a context-driven single slot.
- No auto-switching, ever: selecting something in the viewport or via the Org tab never opens or switches the sidebar.
- The Selection rail icon shows a small dot when there is unseen selection content and Selection isn't the active tab; the dot clears only by switching to the Selection tab yourself.
- A persistent "current selection" strip is always visible above the active panel, independent of which tab is showing, and stays visible even when the sidebar is collapsed (shrunk to icon token(s) only, no text) — the one piece of "Selection" content not gated behind the Selection tab.
- Actor and surface selection are not mutually exclusive in the strip: one line per non-empty kind, never joined with "+"/inline. Single actor: `<name> · <class>`; multiple: `<N> actors`. Single surface: `<actor>:<polyIndex> · <texture ref>` (`#<poly.tex_index>`, or `(untextured)` when negative); multiple: `<N> surfaces`. Each line is prefixed with a small icon token, not a word (▣ actor, ▦ surface — placeholders, exact glyphs deferred).
- Clicking the strip switches to the Selection tab — a deliberate click, not a violation of the no-auto-switch rule.
- No simultaneous multi-panel/split view.
- Fixed width ~280px; no drag-to-resize.
- Right side of the viewport.
- Expanded by default, Selection tab active. Below the existing 768px responsive breakpoint, still collapses by default unless the user has manually overridden it (persisted).
- Collapse control: clicking the ALREADY-active rail icon collapses the sidebar; clicking a different icon switches to it (and expands if collapsed) — no separate `◀`/`▶` toggle button.
- `OrgPanel.tsx` / `Inspector.tsx` internals are unchanged — same props, same rendered DOM.
- Old `localStorage` keys (`uedcli-org-panel-collapsed`, `uedcli-inspector-pane-collapsed`) are simply abandoned; no migration.
- Rail icon glyphs are a placeholder/later polish pass: `▣` Selection, `☰` Org, matching the mockup.

## File Structure

- **Create** `web/src/panels/sidebarRegistry.ts` — `SidebarPanelDef` type + `buildSidebarPanels()`, the ordered launch registry (`selection` wrapping `Inspector`, `org` wrapping `OrgPanel`).
- **Create** `web/src/panels/sidebarRegistry.test.ts` — registry order/wiring/`hasIndicator` regression tests.
- **Create** `web/src/layout/useSidebar.ts` — the `{ collapsed, activeTabId, setActiveTab }` hook, composing `useCollapsiblePanel` for the collapse half and its own `localStorage` key for the active tab; `setActiveTab` alone decides collapse-vs-switch (no separate `toggleCollapsed`).
- **Create** `web/src/layout/useSidebar.test.ts` — collapse/active-tab persistence + breakpoint default tests.
- **Create** `web/src/layout/useSelectionSeen.ts` — `useHasUnseenSelection`, the Selection-tab discoverability-dot tracker; called by `App.tsx`, not `Sidebar.tsx` (spec's "Selection strip data").
- **Create** `web/src/layout/useSelectionSeen.test.ts` — its own focused tests.
- **Create** `web/src/panels/Sidebar.tsx` — the shell: selection strip (always mounted, even collapsed), rail, active panel body. Purely presentational — takes collapse/active-tab/indicator state as props.
- **Create** `web/src/panels/Sidebar.test.tsx` — active-panel switching, rail-click wiring, indicator dot (generic, via `hasIndicator`), strip content/click/collapsed-icon-only tests.
- **Modify** `web/src/index.css` — remove the dead `.org-panel-wrapper`/`.inspector-pane-wrapper`/`.sidebar-toggle`/`.inspector-pane` rules, shrink `.org-panel` to its own content-only styling, add `.sidebar`/`.sidebar-body`/`.sidebar-rail`/`.sidebar-rail-button`/`.sidebar-rail-dot`/`.sidebar-panel`/`.sidebar-panel-body`/`.selection-strip*`, and fix the stale `.org-panel-wrapper`/`.inspector-pane-wrapper` reference in the `html, body, #root, #app-root` comment.
- **Modify** `web/src/sidebarOverflow.test.ts` — repoint its `.org-panel`/`.inspector-pane` assertions at the new `.sidebar`/`.sidebar-panel`/`.sidebar-panel-body` selectors.
- **Modify** `web/src/scene/QuadLayout.tsx` — drop `OrgPanel`/`useCollapsiblePanel`/`onSelectMany`/local frame state; accept `frameRequest`/`frameActors` as controlled props instead.
- **Modify** `web/src/scene/QuadLayout.test.tsx` — update the test `Harness` to the new prop shape.
- **Modify** `web/src/App.tsx` — lift `frameRequest`/`frameActors`/`handleOrgSelect` up from where `QuadLayout` used to own them; call `useSidebar()`/`useHasUnseenSelection()`; build the sidebar registry; mount `<Sidebar>` in place of the old inspector wrapper.
- **Modify** `web/src/App.test.tsx` — repoint the batch-actor-select coexistence test at the real Sidebar's Org panel now that `QuadLayout` no longer receives `onSelectMany`.

## Task 1: `sidebarRegistry.ts` — the panel registry

**Files:**
- Create: `web/src/panels/sidebarRegistry.ts`
- Create: `web/src/panels/sidebarRegistry.test.ts`

**Interfaces:**
- Consumes: `SceneActor` (`web/src/api.ts`), `Inspector`/`SurfaceSelection` (`web/src/panels/Inspector.tsx`), `OrgPanel` (`web/src/panels/OrgPanel.tsx`).
- Produces: `SidebarPanelDef` (`{ id: string; icon: string; title: string; hasIndicator: boolean; content: ReactNode }`) and `buildSidebarPanels(args: BuildSidebarPanelsArgs): SidebarPanelDef[]`, both imported by `Sidebar.tsx`/`Sidebar.test.tsx` (Task 3) and `App.tsx` (Task 5).

- [ ] **Step 1: Write `sidebarRegistry.ts`**

```ts
// The unified sidebar's panel registry (unified-sidebar spec's Architecture -> Components): an
// ordered list of ALREADY-RENDERED panel definitions Sidebar.tsx iterates without knowing what any
// of them render. `content` is a rendered ReactNode, not a render() closure -- OrgPanel/Inspector
// each need live App.tsx state as props (selection, actors, callbacks), which only a real render
// call (not a prop-less function reference) can supply; `hasIndicator` is likewise a plain boolean
// the CALLER computes for this render, not a callback Sidebar would have to invoke itself. Adding a
// future panel (texture search, etc.) is a new case in buildSidebarPanels only -- Sidebar.tsx itself
// never changes.
import { createElement } from 'react'
import type { ReactNode } from 'react'

import type { SceneActor } from '../api'
import { Inspector } from './Inspector'
import type { SurfaceSelection } from './Inspector'
import { OrgPanel } from './OrgPanel'

export interface SidebarPanelDef {
  id: string
  icon: string
  title: string
  hasIndicator: boolean // already computed by the caller for THIS render, not a callback
  content: ReactNode // already-rendered -- e.g. createElement(Inspector, { selected: ... })
}

export interface BuildSidebarPanelsArgs {
  selectedActors: SceneActor[]
  selectedSurfaces: SurfaceSelection[]
  // The Selection rail icon's discoverability dot (spec's Decisions section): computed by the
  // caller (App.tsx, via useSelectionSeen.ts -- Task 2) from state buildSidebarPanels itself has no
  // access to (which tab was last active when). Used as-is for the `selection` entry's
  // `hasIndicator`; `org` has no discoverability signal in this design (spec's Components section).
  hasUnseenSelection: boolean
  orgActors: SceneActor[]
  selectedNames: ReadonlySet<string>
  onSelectOrgBatch: (names: string[], additive: boolean) => void
}

/** The launch registry (spec's Scope: Selection + Org/Search only, everything else is a later
 * addition). Icon glyphs are the mockup's own placeholders -- the spec explicitly defers picking
 * the final ones. */
export function buildSidebarPanels(args: BuildSidebarPanelsArgs): SidebarPanelDef[] {
  return [
    {
      id: 'selection',
      icon: '▣',
      title: 'Selection',
      hasIndicator: args.hasUnseenSelection,
      content: createElement(Inspector, { selected: args.selectedActors, selectedSurfaces: args.selectedSurfaces }),
    },
    {
      id: 'org',
      icon: '☰',
      title: 'Org / Search',
      hasIndicator: false,
      content: createElement(OrgPanel, {
        actors: args.orgActors,
        selectedNames: args.selectedNames,
        onSelectActor: args.onSelectOrgBatch,
      }),
    },
  ]
}
```

- [ ] **Step 2: Write `sidebarRegistry.test.ts`**

```ts
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SceneActor } from '../api'
import { buildSidebarPanels } from './sidebarRegistry'

afterEach(cleanup)

function actor(name: string, folder: string | null = null): SceneActor {
  return {
    name,
    cls: 'Engine.Light',
    bbox_lo: [0, 0, 0],
    bbox_hi: [1, 1, 1],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    categories: [],
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
  }
}

describe('buildSidebarPanels', () => {
  it('builds "selection" then "org", with the mockup\'s placeholder icons/titles', () => {
    const panels = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: false,
      orgActors: [],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    expect(panels.map((p) => p.id)).toEqual(['selection', 'org'])
    expect(panels[0].icon).toBe('▣')
    expect(panels[0].title).toBe('Selection')
    expect(panels[1].icon).toBe('☰')
    expect(panels[1].title).toBe('Org / Search')
  })

  it('the "selection" entry\'s content renders the Inspector with the given actor selection', () => {
    const [selectionPanel] = buildSidebarPanels({
      selectedActors: [actor('Room')],
      selectedSurfaces: [],
      hasUnseenSelection: false,
      orgActors: [],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    render(selectionPanel.content)
    expect(screen.getByRole('heading', { name: 'Room' })).toBeTruthy()
  })

  it('the "org" entry\'s content renders the OrgPanel with the given actors', () => {
    const [, orgPanel] = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: false,
      orgActors: [actor('Torch1')],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    render(orgPanel.content)
    expect(screen.getByTestId('org-panel')).toBeTruthy()
  })

  it('forwards onSelectOrgBatch to OrgPanel exactly as OrgPanel calls it', () => {
    const onSelectOrgBatch = vi.fn()
    const [, orgPanel] = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: false,
      orgActors: [actor('Loose1')],
      selectedNames: new Set(),
      onSelectOrgBatch,
    })
    render(orgPanel.content)
    screen.getByTestId('org-folder-no-folder').click()
    expect(onSelectOrgBatch).toHaveBeenCalledWith(['Loose1'], false)
  })

  it('the "selection" entry\'s hasIndicator mirrors hasUnseenSelection', () => {
    const withDot = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: true,
      orgActors: [],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    expect(withDot[0].hasIndicator).toBe(true)

    const withoutDot = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: false,
      orgActors: [],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    expect(withoutDot[0].hasIndicator).toBe(false)
  })

  it('the "org" entry\'s hasIndicator is always false -- Org has no discoverability signal', () => {
    const panels = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: true,
      orgActors: [],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    expect(panels[1].hasIndicator).toBe(false)
  })
})
```

- [ ] **Step 3: Run the new test**

Run: `cd web && npx vitest run src/panels/sidebarRegistry.test.ts`
Expected: 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src/panels/sidebarRegistry.ts web/src/panels/sidebarRegistry.test.ts
git commit -m "Add sidebarRegistry: the unified sidebar's panel registry"
```

## Task 2: `useSidebar.ts` and `useSelectionSeen.ts` — sidebar state and the selection-seen dot tracker

**Files:**
- Create: `web/src/layout/useSidebar.ts`
- Create: `web/src/layout/useSidebar.test.ts`
- Create: `web/src/layout/useSelectionSeen.ts`
- Create: `web/src/layout/useSelectionSeen.test.ts`

**Interfaces:**
- Consumes: `useCollapsiblePanel`, `SIDEBAR_COLLAPSE_BREAKPOINT_PX` (`web/src/layout/useCollapsiblePanel.ts`, both unmodified).
- Produces: `UseSidebarResult` (`{ collapsed: boolean; activeTabId: string; setActiveTab: (id: string) => void }`) and `useSidebar()` — both called by `App.tsx` (Task 5) and threaded down into `Sidebar.tsx` (Task 3) as plain props, never called by `Sidebar.tsx` itself. Also produces `useHasUnseenSelection(identity: string, activeTabId: string): boolean`, called by `App.tsx` (Task 5) to compute the `hasUnseenSelection` fed into `buildSidebarPanels` (Task 1) — `Sidebar.tsx` never sees this hook at all.

- [ ] **Step 1: Write `useSidebar.ts`**

```ts
// The unified sidebar's collapse + active-tab state (unified-sidebar spec's Architecture ->
// Components): one hook replacing the org-panel's and inspector-pane's separate
// `useCollapsiblePanel` calls. Collapse reuses that hook outright (same 768px-breakpoint default,
// same persisted-choice override); which registry panel is active is a second, independently
// persisted choice. `setActiveTab` is the ONLY thing that ever changes `collapsed` -- there is no
// separate `toggleCollapsed` in the public shape (spec's Decisions -> "Collapse control"): clicking
// the already-active tab collapses; clicking a different tab switches to it and expands.
import { useState } from 'react'

import { useCollapsiblePanel } from './useCollapsiblePanel'

const ACTIVE_TAB_STORAGE_KEY = 'uedcli-sidebar-active-tab'
const DEFAULT_ACTIVE_TAB_ID = 'selection'

function readStoredActiveTab(): string | null {
  try {
    return localStorage.getItem(ACTIVE_TAB_STORAGE_KEY)
  } catch {
    // localStorage unavailable (private mode, blocked) -- fall back to the default tab.
    return null
  }
}

export interface UseSidebarResult {
  collapsed: boolean
  activeTabId: string
  setActiveTab: (id: string) => void
}

export function useSidebar(): UseSidebarResult {
  const { collapsed, toggle: toggleCollapsed } = useCollapsiblePanel('uedcli-sidebar-collapsed')
  const [activeTabId, setActiveTabState] = useState<string>(() => readStoredActiveTab() ?? DEFAULT_ACTIVE_TAB_ID)

  const setActiveTab = (id: string) => {
    if (!collapsed && id === activeTabId) {
      // Clicking the already-active tab while expanded IS the collapse control (spec's Decisions
      // section) -- toggle collapse, leave the active tab untouched.
      toggleCollapsed()
      return
    }
    setActiveTabState(id)
    try {
      localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, id)
    } catch {
      // Persistence is a nicety -- a blocked localStorage just means the choice doesn't survive a reload.
    }
    if (collapsed) toggleCollapsed() // switching tabs while collapsed also expands
  }

  return { collapsed, activeTabId, setActiveTab }
}
```

- [ ] **Step 2: Write `useSidebar.test.ts`**

```ts
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { SIDEBAR_COLLAPSE_BREAKPOINT_PX } from './useCollapsiblePanel'
import { useSidebar } from './useSidebar'

function setViewportWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
}

beforeEach(() => {
  localStorage.clear()
  setViewportWidth(1920)
})

afterEach(() => {
  localStorage.clear()
})

describe('useSidebar', () => {
  it('defaults to the "selection" tab and expanded above the breakpoint, with no stored choice', () => {
    const { result } = renderHook(() => useSidebar())
    expect(result.current.activeTabId).toBe('selection')
    expect(result.current.collapsed).toBe(false)
  })

  it('defaults to collapsed below the breakpoint, with no stored choice', () => {
    setViewportWidth(SIDEBAR_COLLAPSE_BREAKPOINT_PX - 1)
    const { result } = renderHook(() => useSidebar())
    expect(result.current.collapsed).toBe(true)
  })

  it('setActiveTab on the already-active tab collapses the sidebar, and persists that across a fresh hook instance', () => {
    const { result, unmount } = renderHook(() => useSidebar())
    expect(result.current.collapsed).toBe(false)
    expect(result.current.activeTabId).toBe('selection')

    act(() => result.current.setActiveTab('selection')) // same as the current tab -> collapse
    expect(result.current.collapsed).toBe(true)
    expect(result.current.activeTabId).toBe('selection') // unchanged

    unmount()
    const { result: fresh } = renderHook(() => useSidebar())
    expect(fresh.current.collapsed).toBe(true)
  })

  it('an explicit collapse choice wins over the breakpoint, same as useCollapsiblePanel', () => {
    const { result } = renderHook(() => useSidebar())
    act(() => result.current.setActiveTab('selection')) // collapses (already active)
    setViewportWidth(1920)
    const { result: fresh } = renderHook(() => useSidebar())
    expect(fresh.current.collapsed).toBe(true)
  })

  it('setActiveTab changes the active tab and persists it across a fresh hook instance', () => {
    const { result, unmount } = renderHook(() => useSidebar())
    act(() => result.current.setActiveTab('org'))
    expect(result.current.activeTabId).toBe('org')
    expect(result.current.collapsed).toBe(false) // switching tabs never collapses

    unmount()
    const { result: fresh } = renderHook(() => useSidebar())
    expect(fresh.current.activeTabId).toBe('org')
  })

  it('setActiveTab on the active tab while COLLAPSED expands instead of collapsing further', () => {
    const { result } = renderHook(() => useSidebar())
    act(() => result.current.setActiveTab('selection')) // collapse
    expect(result.current.collapsed).toBe(true)

    act(() => result.current.setActiveTab('selection')) // same tab again, but now collapsed
    expect(result.current.collapsed).toBe(false)
    expect(result.current.activeTabId).toBe('selection')
  })
})
```

- [ ] **Step 3: Run the new test**

Run: `cd web && npx vitest run src/layout/useSidebar.test.ts`
Expected: 6 tests PASS.

- [ ] **Step 4: Write `useSelectionSeen.ts`**

```ts
// The unified sidebar's Selection-tab discoverability dot (spec's Decisions section: a dot on the
// Selection rail icon when there's unseen selection content and Selection isn't the active tab).
// Lives in App.tsx's own layer (spec's "Selection strip data": App.tsx computes hasUnseenSelection
// and feeds it into buildSidebarPanels as a plain boolean) -- NOT in Sidebar.tsx, which only ever
// reads whatever boolean each SidebarPanelDef already carries, the same way any future panel's own
// indicator condition would.
import { useEffect, useRef } from 'react'

const SELECTION_TAB_ID = 'selection'

/** `identity` must be a STABLE string that changes iff the actual selection changes -- a fresh
 * array/Set identity every render must not itself count as a change (see App.tsx's own
 * `selectionIdentity` computation, built from the already-available `selectedNames`/
 * `selectedSurfaces` sets). Tracks the last identity seen while `activeTabId === 'selection'`;
 * returns `true` once the identity changes while a DIFFERENT tab is active, and clears the instant
 * `activeTabId` becomes `'selection'` again. */
export function useHasUnseenSelection(identity: string, activeTabId: string): boolean {
  const lastSeen = useRef(identity)
  useEffect(() => {
    if (activeTabId === SELECTION_TAB_ID) lastSeen.current = identity
  }, [activeTabId, identity])
  return activeTabId !== SELECTION_TAB_ID && identity !== lastSeen.current
}
```

- [ ] **Step 5: Write `useSelectionSeen.test.ts`**

```ts
import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useHasUnseenSelection } from './useSelectionSeen'

describe('useHasUnseenSelection', () => {
  it('is false while the Selection tab is active, even as the identity changes', () => {
    const { result, rerender } = renderHook(
      ({ identity, activeTabId }: { identity: string; activeTabId: string }) => useHasUnseenSelection(identity, activeTabId),
      { initialProps: { identity: '', activeTabId: 'selection' } },
    )
    expect(result.current).toBe(false)

    rerender({ identity: 'A', activeTabId: 'selection' })
    expect(result.current).toBe(false)
  })

  it('becomes true once the identity changes while a DIFFERENT tab is active', () => {
    const { result, rerender } = renderHook(
      ({ identity, activeTabId }: { identity: string; activeTabId: string }) => useHasUnseenSelection(identity, activeTabId),
      { initialProps: { identity: 'A', activeTabId: 'org' } },
    )
    expect(result.current).toBe(false) // no change yet

    rerender({ identity: 'A,B', activeTabId: 'org' })
    expect(result.current).toBe(true)
  })

  it('clears once the Selection tab becomes active again', () => {
    const { result, rerender } = renderHook(
      ({ identity, activeTabId }: { identity: string; activeTabId: string }) => useHasUnseenSelection(identity, activeTabId),
      { initialProps: { identity: 'A', activeTabId: 'org' } },
    )
    rerender({ identity: 'A,B', activeTabId: 'org' })
    expect(result.current).toBe(true)

    rerender({ identity: 'A,B', activeTabId: 'selection' })
    expect(result.current).toBe(false)
  })
})
```

- [ ] **Step 6: Run the new test**

Run: `cd web && npx vitest run src/layout/useSelectionSeen.test.ts`
Expected: 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/layout/useSidebar.ts web/src/layout/useSidebar.test.ts web/src/layout/useSelectionSeen.ts web/src/layout/useSelectionSeen.test.ts
git commit -m "Add useSidebar + useSelectionSeen: state for the unified sidebar"
```

## Task 3: `Sidebar.tsx` — the shell component

**Files:**
- Create: `web/src/panels/Sidebar.tsx`
- Create: `web/src/panels/Sidebar.test.tsx`

**Interfaces:**
- Consumes: `SidebarPanelDef` (Task 1), `SurfaceSelection` (`web/src/panels/Inspector.tsx`), `SceneActor` (`web/src/api.ts`).
- Produces: `SidebarProps` (`{ panels: SidebarPanelDef[]; collapsed: boolean; activeTabId: string; setActiveTab: (id: string) => void; selectedActors: SceneActor[]; selectedSurfaces: SurfaceSelection[] }`) and `Sidebar(props: SidebarProps)`, mounted by `App.tsx` (Task 5) — which also owns the `useSidebar()`/`useHasUnseenSelection()` calls (Task 2) that produce `collapsed`/`activeTabId`/`setActiveTab`/each panel's `hasIndicator`. `Sidebar.tsx` itself calls neither hook and hardcodes no panel id when reading indicators.

- [ ] **Step 1: Write `Sidebar.tsx`**

```tsx
// The unified sidebar (icon rail + one active panel), replacing the old org-panel/inspector-pane
// double sidebar (unified-sidebar spec). Purely presentational: collapse/active-tab state and each
// panel's `hasIndicator` are all owned by the caller (App.tsx, via useSidebar/useSelectionSeen) and
// passed in as props -- Sidebar knows nothing about what a panel contains, or why any panel's
// indicator is on, so a future panel's own indicator condition needs no change here.
import type { SceneActor } from '../api'
import type { SurfaceSelection } from './Inspector'
import type { SidebarPanelDef } from './sidebarRegistry'

export interface SidebarProps {
  panels: SidebarPanelDef[]
  collapsed: boolean
  activeTabId: string
  setActiveTab: (id: string) => void
  selectedActors: SceneActor[]
  selectedSurfaces: SurfaceSelection[]
}

function actorLineText(actors: SceneActor[]): string {
  return actors.length === 1 ? `${actors[0].name} · ${actors[0].cls}` : `${actors.length} actors`
}

function surfaceLineText(surfaces: SurfaceSelection[]): string {
  if (surfaces.length === 1) {
    const { actorName, polyIndex, poly } = surfaces[0]
    const texture = poly.tex_index >= 0 ? `#${poly.tex_index}` : '(untextured)'
    return `${actorName}:${polyIndex} · ${texture}`
  }
  return `${surfaces.length} surfaces`
}

/** The persistent "current selection" strip (spec's Decisions section): always mounted above
 * `.sidebar-body`, independent of which tab is showing AND independent of collapse state (spec:
 * "the strip stays visible even when the sidebar is collapsed, shrunk to its icon token(s) only").
 * When `collapsed`, each non-empty kind's line drops its text entirely -- just the icon token,
 * since there's no room for it in the ~36px rail width once `.sidebar-panel` is gone. */
function SelectionStrip({
  actors,
  surfaces,
  collapsed,
  onClick,
}: {
  actors: SceneActor[]
  surfaces: SurfaceSelection[]
  collapsed: boolean
  onClick: () => void
}) {
  const empty = actors.length === 0 && surfaces.length === 0
  return (
    <div
      className={collapsed ? 'selection-strip selection-strip-collapsed' : 'selection-strip'}
      data-testid="selection-strip"
      onClick={onClick}
    >
      {empty ? (
        !collapsed && (
          <div className="selection-strip-line selection-strip-empty" data-testid="selection-strip-empty">
            No selection
          </div>
        )
      ) : (
        <>
          {actors.length > 0 && (
            <div className="selection-strip-line" data-testid="selection-strip-actor">
              <span className="selection-strip-icon" aria-hidden="true">
                ▣
              </span>
              {!collapsed && actorLineText(actors)}
            </div>
          )}
          {surfaces.length > 0 && (
            <div className="selection-strip-line" data-testid="selection-strip-surface">
              <span className="selection-strip-icon" aria-hidden="true">
                ▦
              </span>
              {!collapsed && surfaceLineText(surfaces)}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export function Sidebar({ panels, collapsed, activeTabId, setActiveTab, selectedActors, selectedSurfaces }: SidebarProps) {
  const activePanel = panels.find((p) => p.id === activeTabId)

  // The strip's own click never collapses -- it always means "go to Selection", never "toggle
  // collapse". Reusing setActiveTab RAW here would collapse the sidebar if the user clicks the
  // strip while already on the (expanded) Selection tab, which is not what a control whose whole
  // point is staying visible at all times should do on a click.
  const onStripClick = () => {
    if (collapsed || activeTabId !== 'selection') setActiveTab('selection')
  }

  return (
    <div className="sidebar" data-testid="sidebar">
      <SelectionStrip actors={selectedActors} surfaces={selectedSurfaces} collapsed={collapsed} onClick={onStripClick} />
      <div className="sidebar-body">
        <div className="sidebar-rail">
          {panels.map((panel) => (
            <button
              key={panel.id}
              type="button"
              className="sidebar-rail-button"
              data-testid={`sidebar-rail-${panel.id}`}
              aria-pressed={!collapsed && panel.id === activeTabId}
              title={panel.title}
              onClick={() => setActiveTab(panel.id)}
            >
              {panel.icon}
              {panel.hasIndicator && (
                <span className="sidebar-rail-dot" data-testid={`sidebar-dot-${panel.id}`} aria-hidden="true" />
              )}
            </button>
          ))}
        </div>
        {!collapsed && activePanel && (
          <div className="sidebar-panel">
            <div className="sidebar-panel-body">{activePanel.content}</div>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Write `Sidebar.test.tsx`**

```tsx
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ScenePoly, SceneActor } from '../api'
import type { SurfaceSelection } from './Inspector'
import { Sidebar } from './Sidebar'
import type { SidebarProps } from './Sidebar'
import type { SidebarPanelDef } from './sidebarRegistry'

afterEach(cleanup)

const PANELS: SidebarPanelDef[] = [
  {
    id: 'selection',
    icon: '▣',
    title: 'Selection',
    hasIndicator: false,
    content: <div data-testid="panel-selection-content">selection content</div>,
  },
  {
    id: 'org',
    icon: '☰',
    title: 'Org / Search',
    hasIndicator: false,
    content: <div data-testid="panel-org-content">org content</div>,
  },
]

function actor(name: string): SceneActor {
  return {
    name,
    cls: 'Engine.Light',
    bbox_lo: [0, 0, 0],
    bbox_hi: [1, 1, 1],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    categories: [],
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
  }
}

function poly(overrides: Partial<ScenePoly> = {}): ScenePoly {
  return {
    verts: [0, 0, 0, 1, 0, 0, 1, 1, 0],
    base: [0, 0, 0],
    tu: [1, 0, 0],
    tv: [0, 1, 0],
    pan: [0, 0],
    tex_index: 12,
    masked: false,
    two_sided: false,
    blend: 'opaque',
    flags: 0,
    lightmap: null,
    owner: 'Room',
    i_brush_poly: 4,
    ...overrides,
  }
}

function renderSidebar(overrides: Partial<SidebarProps> = {}) {
  const setActiveTab = vi.fn()
  const props: SidebarProps = {
    panels: PANELS,
    collapsed: false,
    activeTabId: 'selection',
    setActiveTab,
    selectedActors: [],
    selectedSurfaces: [],
    ...overrides,
  }
  render(<Sidebar {...props} />)
  return { setActiveTab }
}

describe('Sidebar active panel', () => {
  it("renders only the active panel's content", () => {
    renderSidebar({ activeTabId: 'selection' })
    expect(screen.getByTestId('panel-selection-content')).toBeTruthy()
    expect(screen.queryByTestId('panel-org-content')).toBeNull()
  })

  it('switches which content renders when activeTabId changes', () => {
    renderSidebar({ activeTabId: 'org' })
    expect(screen.getByTestId('panel-org-content')).toBeTruthy()
    expect(screen.queryByTestId('panel-selection-content')).toBeNull()
  })
})

describe('Sidebar collapse', () => {
  it('collapsing hides the panel content but keeps the rail AND the selection strip', () => {
    renderSidebar({ collapsed: true })
    expect(screen.getByTestId('sidebar-rail-selection')).toBeTruthy()
    expect(screen.getByTestId('sidebar-rail-org')).toBeTruthy()
    expect(screen.queryByTestId('panel-selection-content')).toBeNull()
    expect(screen.getByTestId('selection-strip')).toBeTruthy()
  })

  it('clicking a rail icon always calls setActiveTab with that panel id -- the hook (Task 2) decides collapse-vs-switch', () => {
    const { setActiveTab } = renderSidebar({ activeTabId: 'selection', collapsed: false })
    fireEvent.click(screen.getByTestId('sidebar-rail-selection'))
    expect(setActiveTab).toHaveBeenCalledWith('selection')
  })

  it('clicking a different rail icon calls setActiveTab with the new id', () => {
    const { setActiveTab } = renderSidebar({ activeTabId: 'selection', collapsed: false })
    fireEvent.click(screen.getByTestId('sidebar-rail-org'))
    expect(setActiveTab).toHaveBeenCalledWith('org')
  })
})

describe('Sidebar selection strip', () => {
  it('renders "No selection" when both kinds are empty and expanded', () => {
    renderSidebar()
    expect(screen.getByTestId('selection-strip-empty').textContent).toBe('No selection')
  })

  it('renders no text at all when both kinds are empty and COLLAPSED', () => {
    renderSidebar({ collapsed: true })
    expect(screen.queryByTestId('selection-strip-empty')).toBeNull()
    expect(screen.queryByTestId('selection-strip-actor')).toBeNull()
    expect(screen.queryByTestId('selection-strip-surface')).toBeNull()
  })

  it('renders a single actor as "<name> · <class>" when expanded', () => {
    renderSidebar({ selectedActors: [actor('Torch1')] })
    expect(screen.getByTestId('selection-strip-actor').textContent).toBe('▣Torch1 · Engine.Light')
  })

  it('renders only the actor ICON TOKEN, no text, when collapsed', () => {
    renderSidebar({ collapsed: true, selectedActors: [actor('Torch1')] })
    expect(screen.getByTestId('selection-strip-actor').textContent).toBe('▣')
  })

  it('renders 2+ actors as "<N> actors" when expanded', () => {
    renderSidebar({ selectedActors: [actor('A'), actor('B')] })
    expect(screen.getByTestId('selection-strip-actor').textContent).toBe('▣2 actors')
  })

  it('renders a single surface as "<actor>:<index> · <texture ref>" when expanded', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 4, poly: poly() }
    renderSidebar({ selectedSurfaces: [surface] })
    expect(screen.getByTestId('selection-strip-surface').textContent).toBe('▦Room:4 · #12')
  })

  it('renders only the surface ICON TOKEN, no text, when collapsed', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 4, poly: poly() }
    renderSidebar({ collapsed: true, selectedSurfaces: [surface] })
    expect(screen.getByTestId('selection-strip-surface').textContent).toBe('▦')
  })

  it('renders 2+ surfaces as "<N> surfaces" when expanded', () => {
    const surfaces: SurfaceSelection[] = [
      { actorName: 'Room', polyIndex: 1, poly: poly() },
      { actorName: 'Room', polyIndex: 2, poly: poly() },
    ]
    renderSidebar({ selectedSurfaces: surfaces })
    expect(screen.getByTestId('selection-strip-surface').textContent).toBe('▦2 surfaces')
  })

  it('renders both an actor line and a surface line when both kinds are selected', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 4, poly: poly() }
    renderSidebar({ selectedActors: [actor('Room')], selectedSurfaces: [surface] })
    expect(screen.getByTestId('selection-strip-actor')).toBeTruthy()
    expect(screen.getByTestId('selection-strip-surface')).toBeTruthy()
  })

  it('shows both icon tokens (no text) when both kinds are selected and collapsed', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 4, poly: poly() }
    renderSidebar({ collapsed: true, selectedActors: [actor('Room')], selectedSurfaces: [surface] })
    expect(screen.getByTestId('selection-strip-actor').textContent).toBe('▣')
    expect(screen.getByTestId('selection-strip-surface').textContent).toBe('▦')
  })

  it('clicking the strip while a different tab is active switches to the Selection tab', () => {
    const { setActiveTab } = renderSidebar({ activeTabId: 'org', selectedActors: [actor('Torch1')] })
    fireEvent.click(screen.getByTestId('selection-strip'))
    expect(setActiveTab).toHaveBeenCalledWith('selection')
  })

  it('clicking the strip while COLLAPSED switches to the Selection tab, never collapsing further', () => {
    const { setActiveTab } = renderSidebar({ collapsed: true, activeTabId: 'org' })
    fireEvent.click(screen.getByTestId('selection-strip'))
    expect(setActiveTab).toHaveBeenCalledWith('selection')
  })

  it('clicking the strip while ALREADY on the Selection tab and expanded does nothing (never collapses)', () => {
    const { setActiveTab } = renderSidebar({ activeTabId: 'selection', collapsed: false })
    fireEvent.click(screen.getByTestId('selection-strip'))
    expect(setActiveTab).not.toHaveBeenCalled()
  })
})

describe('Sidebar rail indicator dot', () => {
  it('shows a dot on a panel whose hasIndicator is true', () => {
    const panelsWithDot: SidebarPanelDef[] = [{ ...PANELS[0], hasIndicator: true }, PANELS[1]]
    renderSidebar({ panels: panelsWithDot })
    expect(screen.getByTestId('sidebar-dot-selection')).toBeTruthy()
    expect(screen.queryByTestId('sidebar-dot-org')).toBeNull()
  })

  it('shows no dot when every panel\'s hasIndicator is false', () => {
    renderSidebar({ panels: PANELS })
    expect(screen.queryByTestId('sidebar-dot-selection')).toBeNull()
    expect(screen.queryByTestId('sidebar-dot-org')).toBeNull()
  })
})
```

- [ ] **Step 3: Run the new test**

Run: `cd web && npx vitest run src/panels/Sidebar.test.tsx`
Expected: 20 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src/panels/Sidebar.tsx web/src/panels/Sidebar.test.tsx
git commit -m "Add Sidebar: the unified icon-rail sidebar shell"
```

## Task 4: CSS — rail, panel, selection strip

**Files:**
- Modify: `web/src/index.css`
- Modify: `web/src/sidebarOverflow.test.ts`

**Interfaces:**
- Consumes: existing tokens `--border`, `--surface-1`, `--surface-2`, `--surface-2-hover`, `--fg`, `--fg-muted`, `--accent`, `--sem-selection`, `--overlay-fg-hover` (all declared in `index.css`'s `:root`/`:root[data-theme='light']`/`prefers-color-scheme` blocks — no new tokens).
- Produces: CSS classes `.sidebar`, `.sidebar-body`, `.sidebar-rail`, `.sidebar-rail-button`, `.sidebar-rail-dot`, `.sidebar-panel`, `.sidebar-panel-body`, `.selection-strip`, `.selection-strip-collapsed`, `.selection-strip-line`, `.selection-strip-icon`, `.selection-strip-empty`, all consumed by `Sidebar.tsx` (Task 3).

This task also resolves a real conflict between the spec's literal "kept as-is" instruction for `.org-panel`/`.inspector-pane` and correctness: those two rules used to each own their FULL box model (fixed width, height, border, background, own scrolling) because each was a direct flex child of the old wrapper. Nested one level deeper now (inside `.sidebar-panel-body`), keeping their old box-model declarations verbatim would double borders/backgrounds and — worse — misinterpret `flex: 0 0 220px` as a COLUMN-axis height once `.sidebar-panel` is a flex column, visibly breaking the layout. This task instead consolidates box sizing (width, border, background, the one scroll region) onto the new shared `.sidebar-panel`/`.sidebar-panel-body`, and reduces `.org-panel`/`.inspector-pane`'s own rules to genuinely internal content styling. `.inspector` itself (`Inspector.tsx`'s own root class, distinct from the App-level `.inspector-pane` wrapper rule) already has no box-model rule of its own, confirming this split is how the wrapper/content boundary already worked. It also introduces `.sidebar-body` (the rail+panel flex row) so the persistent selection strip (Task 3) can sit above it and stay mounted even while `.sidebar-panel` is gone (spec's collapsed-strip requirement) — `.sidebar` itself becomes a flex COLUMN rather than a row for exactly this reason.

- [ ] **Step 1: Replace the old sidebar-wrapper/toggle CSS with the new rail+panel+strip CSS**

In `web/src/index.css`, replace:

```css
/* Collapsible sidebar wrapper (mobile/laptop layout spec, owner-approved 2026-09-18): shared shape
   for the org-panel wrapper here and `.inspector-pane`'s own wrapper in App.tsx -- a toggle button
   docked at the sidebar's edge, always rendered, plus the panel's own content when expanded. Only
   `flex: 0 0 auto` sizing and `height: 100%` are shared; each wrapper's toggle sits at whichever edge
   faces the viewport (see `.org-panel-wrapper .sidebar-toggle` / `.inspector-pane-wrapper
   .sidebar-toggle` below). */
.org-panel-wrapper,
.inspector-pane-wrapper {
  display: flex;
  flex: 0 0 auto;
  height: 100%;
}

.sidebar-toggle {
  flex: 0 0 auto;
  width: 20px;
  font: inherit;
  font-size: 11px;
  border: none;
  border-left: 1px solid var(--border);
  background: var(--surface-1);
  color: var(--fg-muted);
  cursor: pointer;
}

.sidebar-toggle:hover {
  color: var(--fg);
  background: var(--surface-2-hover);
}

/* The inspector pane sits on the far right, so its toggle -- the sidebar's own left edge -- comes
   BEFORE its content in the wrapper's flex row; the org panel's toggle does too (see the JSX order
   in QuadLayout.tsx), since it also sits to the right of the quad. Both share the same visual result:
   a thin always-visible strip at the boundary between the sidebar and the rest of the layout. */
```

with:

```css
/* The unified sidebar (icon rail + one active panel), replacing the old org-panel/inspector-pane
   double sidebar (unified-sidebar spec). `.sidebar` is a non-shrinking flex COLUMN child of
   `#app-root` (same role `.org-panel-wrapper`/`.inspector-pane-wrapper` used to have): the
   persistent selection strip spans its full width on top, with `.sidebar-body` (a flex row: the
   rail, then the active panel) filling the rest. `.sidebar-rail` is always rendered (the "small
   margin" the viewport gives up even fully collapsed); `.sidebar-panel` (the active registry entry's
   content) only mounts while expanded -- the strip does NOT depend on it (spec's Decisions: "the
   strip stays visible even when the sidebar is collapsed"). */
.sidebar {
  display: flex;
  flex-direction: column;
  flex: 0 0 auto;
  height: 100%;
}

.sidebar-body {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
}

.sidebar-rail {
  display: flex;
  flex: 0 0 36px;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 6px 0;
  border-left: 1px solid var(--border);
  background: var(--surface-1);
}

.sidebar-rail-button {
  position: relative;
  width: 28px;
  height: 28px;
  font-size: 15px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--fg-muted);
  cursor: pointer;
}

.sidebar-rail-button:hover {
  background: var(--surface-2-hover);
  color: var(--fg);
}

.sidebar-rail-button[aria-pressed='true'] {
  background: var(--surface-2);
  color: var(--fg);
}

/* The Selection tab's discoverability dot (spec's Decisions section): unseen selection content
   while a different tab is active. Generic -- any panel's `hasIndicator` draws this same dot, not
   just Selection's. */
.sidebar-rail-dot {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--sem-selection);
}

.sidebar-panel {
  display: flex;
  flex-direction: column;
  flex: 0 0 280px;
  min-width: 0;
  height: 100%;
  border-left: 1px solid var(--border);
  background: var(--surface-1);
  color: var(--fg);
  box-sizing: border-box;
}

/* The persistent "current selection" strip (spec's Decisions section): always visible above
   `.sidebar-body`, independent of which tab is showing AND independent of collapse state. Clicking
   it switches to the Selection tab. */
.selection-strip {
  flex: 0 0 auto;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  border-left: 1px solid var(--border);
  cursor: pointer;
}

.selection-strip:hover {
  background: var(--overlay-fg-hover);
}

/* Collapsed sidebar (spec's Decisions section): no room for name/class/texture-ref text in the
   ~36px rail width once `.sidebar-panel` is gone -- Sidebar.tsx renders icon tokens only (no text
   children) in this state; this class just centers/tightens the container to match. */
.selection-strip-collapsed {
  padding: 6px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.selection-strip-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.selection-strip-collapsed .selection-strip-line {
  justify-content: center;
}

.selection-strip-line + .selection-strip-line {
  margin-top: 4px;
}

.selection-strip-icon {
  flex: 0 0 auto;
  color: var(--accent);
}

.selection-strip-empty {
  color: var(--fg-muted);
}

/* The active registry panel's own content -- the ONE scroll region for whichever panel is showing
   (org tree or inspector), replacing the two separate per-panel scroll areas `.org-panel`/
   `.inspector-pane` used to each own. */
.sidebar-panel-body {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: auto;
  padding: 8px 12px;
  box-sizing: border-box;
}
```

- [ ] **Step 2: Fix the stale `.org-panel-wrapper`/`.inspector-pane-wrapper` reference in the `html, body, #root, #app-root` comment**

In `web/src/index.css`, replace:

```css
html,
body,
#root,
#app-root {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  /* Bug fix: a non-shrinking sidebar (.org-panel-wrapper/.inspector-pane-wrapper, flex: 0 0 auto)
     could force #app-root's flex row wider than the viewport, and with no overflow-x set anywhere
     in this chain the browser scrolled the WHOLE PAGE horizontally instead of clipping/scrolling
     just the sidebar. The page itself must never need horizontal scroll -- each sidebar handles its
     own overflow (see .org-panel/.inspector-pane's own overflow-x below). */
  overflow-x: hidden;
}
```

with:

```css
html,
body,
#root,
#app-root {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  /* Bug fix: a non-shrinking sidebar (.sidebar, flex: 0 0 auto) could force #app-root's flex row
     wider than the viewport, and with no overflow-x set anywhere in this chain the browser scrolled
     the WHOLE PAGE horizontally instead of clipping/scrolling just the sidebar. The page itself must
     never need horizontal scroll -- the sidebar handles its own overflow internally (see
     .sidebar-panel-body's own overflow-x below). */
  overflow-x: hidden;
}
```

- [ ] **Step 3: Shrink `.org-panel` to its own content-only styling**

In `web/src/index.css`, replace:

```css
/* Org panel sidebar (Part 6, Task 23): folder tree + label facets + find. */
.org-panel {
  flex: 0 0 220px;
  min-width: 0;
  height: 100%;
  overflow-y: auto;
  /* Bug fix: a long unwrapped folder/actor name could overflow the sidebar's own fixed width --
     scroll it internally rather than letting it escape into the page (see #app-root's overflow-x
     above for why that used to scroll the whole page). */
  overflow-x: auto;
  padding: 8px;
  border-left: 1px solid var(--border);
  background: var(--surface-1);
  color: var(--fg);
  font-size: 12px;
}
```

with:

```css
/* Org panel content (Part 6, Task 23): folder tree + label facets + find. Box sizing (width,
   scrolling, border, background) now lives on the shared `.sidebar-panel`/`.sidebar-panel-body`
   (unified-sidebar spec) -- only this panel's own smaller font size stays here. */
.org-panel {
  font-size: 12px;
}
```

- [ ] **Step 4: Delete the now-dead `.inspector-pane` rule**

In `web/src/index.css`, delete exactly this block (nothing replaces it — `.sidebar-panel`/`.sidebar-panel-body` from Step 1 already cover the same box model). The blank line before it (after `.build-toolbar .changes-badge`'s closing `}`) and the blank line after it (before `.inspector-sections > * + *`) both stay — old_string below is only the rule itself, no surrounding blank lines, so replacing it with nothing leaves those two blank lines adjacent rather than collapsing to one:

```css
.inspector-pane {
  flex: 0 0 280px;
  /* Bug fix: matches .org-panel's min-width: 0 -- without it, a flex item's automatic minimum
     width defaults to its content's min-content size, which can force the pane wider than its
     280px flex-basis (e.g. a long unbroken inspector value). */
  min-width: 0;
  overflow-y: auto;
  /* Bug fix: a wide inspector table/value could overflow the sidebar's own fixed width -- scroll
     it internally rather than letting it escape into the page (see #app-root's overflow-x above). */
  overflow-x: auto;
  border-left: 1px solid var(--border);
  padding: 8px 12px;
  box-sizing: border-box;
}
```

- [ ] **Step 5: Update `sidebarOverflow.test.ts`'s selectors for the new structure**

Replace the full contents of `web/src/sidebarOverflow.test.ts` with:

```ts
/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

// jsdom (this suite's DOM environment) never lays out CSS, so no test here can measure real pixel
// overflow -- same limitation toolbarLayout.test.ts already documents, and confirmed again for this
// bug fix: no runnable headless browser is available in this sandbox (chrome-headless-shell is
// missing shared libraries with no root to install them, the same gap GUI-PARITY.md records). These
// assertions instead pin the specific rules the sidebar-overflow bug hinges on -- a regression to
// either shape would let the page need horizontal scroll again even though nothing else in the
// suite would notice.
const CSS = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'index.css'), 'utf8')

/** The declaration block for one CSS selector, or null if the selector isn't found. */
function ruleBody(selector: string): string | null {
  const escaped = selector.replace(/[.[\]]/g, '\\$&')
  const match = new RegExp(`(?<![\\w-])${escaped}\\s*\\{([^}]*)\\}`).exec(CSS)
  return match ? match[1] : null
}

describe('sidebar overflow CSS (board item sidebar-can-overflow-viewport-needs-scroll)', () => {
  it('the page root chain clips horizontal overflow instead of letting the whole page scroll', () => {
    // `.sidebar` is a non-shrinking flex child (flex: 0 0 auto) of #app-root, same role
    // `.org-panel-wrapper`/`.inspector-pane-wrapper` used to have (unified-sidebar spec) -- without
    // overflow-x: hidden somewhere in this chain, a narrow viewport (or a manually-reopened sidebar
    // below the responsive breakpoint) forces the whole page wider than the viewport and the PAGE
    // scrolls, instead of the sidebar handling its own overflow internally.
    const body = ruleBody('html,\nbody,\n#root,\n#app-root')
    expect(body).not.toBeNull()
    expect(body).toMatch(/overflow-x:\s*hidden/)
  })

  it('.sidebar stays a non-shrinking flex child, same as the old per-panel wrappers', () => {
    const body = ruleBody('.sidebar')
    expect(body).not.toBeNull()
    expect(body).toMatch(/flex:\s*0 0 auto/)
  })

  it('.sidebar-panel-body scrolls its own horizontal overflow (long folder/actor names, wide inspector values) instead of escaping the sidebar', () => {
    const panel = ruleBody('.sidebar-panel')
    expect(panel).not.toBeNull()
    expect(panel).toMatch(/min-width:\s*0/)
    const panelBody = ruleBody('.sidebar-panel-body')
    expect(panelBody).not.toBeNull()
    expect(panelBody).toMatch(/overflow-x:\s*auto/)
  })

  it('the flex chain down to the sidebar allows shrinking below content size (min-width: 0), so overflow is handled by the sidebar itself, not by growing an ancestor', () => {
    for (const selector of ['.viewport-pane', '.viewport-content', '.quad-layout-root', '.quad-layout']) {
      const body = ruleBody(selector)
      expect(body, `${selector} rule should exist`).not.toBeNull()
      expect(body, `${selector} should have min-width: 0`).toMatch(/min-width:\s*0/)
    }
  })
})
```

- [ ] **Step 6: Run the updated test**

Run: `cd web && npx vitest run src/sidebarOverflow.test.ts`
Expected: 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/index.css web/src/sidebarOverflow.test.ts
git commit -m "Replace the double-sidebar CSS with the unified sidebar's rail/panel/strip"
```

## Task 5: Migrate the mount points — `QuadLayout.tsx` and `App.tsx`

**Files:**
- Modify: `web/src/scene/QuadLayout.tsx`
- Modify: `web/src/scene/QuadLayout.test.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`

**Interfaces:**
- Consumes: `Sidebar`/`SidebarProps` (Task 3), `buildSidebarPanels`/`BuildSidebarPanelsArgs` (Task 1), `useSidebar`/`UseSidebarResult` (Task 2), `useHasUnseenSelection` (Task 2), `unionBBox`/`FrameRequest` (`web/src/scene/frame.ts`, unmodified).
- Produces: `QuadLayoutProps` gains `frameRequest: FrameRequest | null` and `frameActors: (names: ReadonlySet<string>) => void`, loses `onSelectMany`. `App.tsx` owns `frameRequest`/`frameActors`/`handleOrgSelect` and the sidebar's `collapsed`/`activeTabId`/`setActiveTab`/`hasUnseenSelection` where `QuadLayout.tsx`/`Sidebar.tsx` used to own pieces of this themselves.

This task's files are interdependent and must land together: `QuadLayout.tsx` can only drop `onSelectMany` from its own prop type once `App.tsx` stops passing it, and `App.tsx` can only stop passing it once it has somewhere else to route the org panel's batch-select-and-frame behavior (`Sidebar`, via the registry). `App.test.tsx` also changes in this same commit (Step 15 below): it drives `QuadLayout`'s stubbed props directly, and one of its existing tests calls `.onSelectMany(...)` on that stub — once `QuadLayout` genuinely stops receiving that prop, the stub no longer has it, and the OLD call would throw `TypeError: quad.onSelectMany is not a function` at runtime. Splitting any of this into separate commits would leave a broken intermediate state (a TypeScript excess-property error at the `<QuadLayout>` call site, an unused destructured parameter, or a failing test), so all four files change in this one task/commit.

- [ ] **Step 1: `QuadLayout.tsx` — drop the `OrgPanel`/`unionBBox` imports it no longer needs, keep `FrameRequest`**

In `web/src/scene/QuadLayout.tsx`, replace:

```ts
import type { AtlasPayload, LightmapPayload, ScenePayload } from '../api'
import { useCollapsiblePanel } from '../layout/useCollapsiblePanel'
import { OrgPanel } from '../panels/OrgPanel'
import type { FrameRequest } from './frame'
import { unionBBox } from './frame'
import { DEFAULT_GRID_SIZE, GRID_SIZE_OPTIONS } from './grid'
```

with:

```ts
import type { AtlasPayload, LightmapPayload, ScenePayload } from '../api'
import type { FrameRequest } from './frame'
import { DEFAULT_GRID_SIZE, GRID_SIZE_OPTIONS } from './grid'
```

- [ ] **Step 2: `QuadLayout.tsx` — update `QuadLayoutProps`**

Replace:

```ts
export interface QuadLayoutProps {
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload | null
  selectedNames: ReadonlySet<string>
  onSelectActor: (name: string, additive: boolean) => void
  // Surface (single-polygon texture) selection -- see Viewport3D.tsx's identical prop doc for the
  // full model. A distinct set from `selectedNames`, threaded to every pane the same way.
  selectedSurfaces: ReadonlySet<string>
  onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
  // OrgPanel's own batch-select shape (Task 23): a folder-node click replaces/adds a whole actor
  // set at once -- distinct from the single-name onSelectActor above, which selectionSet.ts's
  // toggleSelection doesn't need to grow a bulk form to cover.
  onSelectMany: (names: ReadonlySet<string>, additive: boolean) => void
  onDeselect: () => void
  // The real shading-mode gating signal (Task 19, buildStatus.ts's resolveBuildSolved).
  buildSolved: boolean
}
```

with:

```ts
export interface QuadLayoutProps {
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload | null
  selectedNames: ReadonlySet<string>
  onSelectActor: (name: string, additive: boolean) => void
  // Surface (single-polygon texture) selection -- see Viewport3D.tsx's identical prop doc for the
  // full model. A distinct set from `selectedNames`, threaded to every pane the same way.
  selectedSurfaces: ReadonlySet<string>
  onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
  onDeselect: () => void
  // The real shading-mode gating signal (Task 19, buildStatus.ts's resolveBuildSolved).
  buildSolved: boolean
  // Lifted to App.tsx (unified-sidebar migration): the org panel that used to live inside this
  // component now renders from Sidebar.tsx, a sibling of QuadLayout in App.tsx -- so the `F`-key
  // framing mechanism SelectionKeys already used here (frameActors/frameRequest) is a controlled
  // prop instead of local state, the one shared instance App's org-panel entry drives too.
  frameRequest: FrameRequest | null
  frameActors: (names: ReadonlySet<string>) => void
}
```

- [ ] **Step 3: `QuadLayout.tsx` — accept the new props, remove the local frame state**

Replace:

```ts
export function QuadLayout({
  scene,
  atlas,
  lightmap,
  selectedNames,
  onSelectActor,
  selectedSurfaces,
  onSelectSurface,
  onSelectMany,
  onDeselect,
  buildSolved,
}: QuadLayoutProps) {
  const [maximized, setMaximized] = useState<PaneId | null>(null)
  const [frameRequest, setFrameRequest] = useState<FrameRequest | null>(null)
  // A plain counter, not React state, so pressing `F` on the SAME selection twice still produces a
  // distinct `seq` each time (FrameRequest's own doc comment) without needing frameRequest itself
  // in this callback's dependency array (which would race a rapid double-press against the state
  // update it triggers).
  const frameSeq = useRef(0)

  // Reused, not re-specified, by Part 6's org panel (Task 23): folder-node selection frames its
  // actor set through this SAME callback, not a second framing mechanism.
  const frameActors = useCallback(
    (names: ReadonlySet<string>) => {
      const bbox = unionBBox(scene.actors.filter((a) => names.has(a.name)))
      if (!bbox) return // nothing to frame -- unionBBox's own no-op signal (frame.ts)
      frameSeq.current += 1
      setFrameRequest({ bbox, seq: frameSeq.current })
    },
    [scene.actors],
  )

  // Focused pane (Task 20): set on a pointerdown anywhere inside a pane, via bubbling -- no per-pane
```

with:

```ts
export function QuadLayout({
  scene,
  atlas,
  lightmap,
  selectedNames,
  onSelectActor,
  selectedSurfaces,
  onSelectSurface,
  onDeselect,
  buildSolved,
  frameRequest,
  frameActors,
}: QuadLayoutProps) {
  const [maximized, setMaximized] = useState<PaneId | null>(null)

  // Focused pane (Task 20): set on a pointerdown anywhere inside a pane, via bubbling -- no per-pane
```

- [ ] **Step 4: `QuadLayout.tsx` — remove the org-panel collapse hook**

Replace:

```ts
  // Collapsible org-panel sidebar (mobile/laptop layout spec, owner-approved 2026-09-18): defaults
  // open above the responsive breakpoint / collapsed below it, overridden permanently once the user
  // manually toggles it (persisted in localStorage) -- see useCollapsiblePanel's own doc comment.
  const { collapsed: orgPanelCollapsed, toggle: toggleOrgPanel } = useCollapsiblePanel('uedcli-org-panel-collapsed')

  // Resizable panes (bug report item 3): the column/row split as a fraction (0..1) of the quad's
```

with:

```ts
  // Resizable panes (bug report item 3): the column/row split as a fraction (0..1) of the quad's
```

- [ ] **Step 5: `QuadLayout.tsx` — remove `handleOrgSelect`**

Replace:

```ts
  // OrgPanel's folder-node/find-result selection reuses BOTH mechanisms this plan already built --
  // selectedNames (via onSelectMany, not a second selection model) and frameActors (Task 15,
  // verbatim, not a second framing mechanism) -- spec §5's own requirement.
  const handleOrgSelect = useCallback(
    (names: string[], additive: boolean) => {
      const nameSet = new Set(names)
      onSelectMany(nameSet, additive)
      frameActors(nameSet)
    },
    [onSelectMany, frameActors],
  )

  return (
```

with:

```ts
  return (
```

- [ ] **Step 6: `QuadLayout.tsx` — remove the org-panel-wrapper JSX**

Replace:

```tsx
      </SceneResourcesProvider>
      {/* Collapsible sidebar (mobile/laptop layout spec): the toggle itself always renders, so a
          collapsed panel can always be reopened; the panel's own (potentially heavy) content only
          mounts while expanded. */}
      <div className="org-panel-wrapper">
        <button
          type="button"
          className="sidebar-toggle"
          onClick={toggleOrgPanel}
          aria-pressed={orgPanelCollapsed}
          aria-label={orgPanelCollapsed ? 'Show folders panel' : 'Hide folders panel'}
          title={orgPanelCollapsed ? 'Show folders panel' : 'Hide folders panel'}
        >
          {orgPanelCollapsed ? '◀' : '▶'}
        </button>
        {!orgPanelCollapsed && (
          <OrgPanel actors={scene.actors} selectedNames={selectedNames} onSelectActor={handleOrgSelect} />
        )}
      </div>
    </div>
  )
}
```

with:

```tsx
      </SceneResourcesProvider>
    </div>
  )
}
```

- [ ] **Step 7: `QuadLayout.test.tsx` — update the `Harness` to the new prop shape**

In `web/src/scene/QuadLayout.test.tsx`, replace:

```tsx
  return (
    <QuadLayout
      scene={SCENE}
      atlas={ATLAS}
      lightmap={null}
      selectedNames={selectedNames}
      onSelectActor={onSelectActor}
      selectedSurfaces={selectedSurfaces}
      onSelectSurface={onSelectSurface}
      onSelectMany={(names, additive) => setSelectedNames((s) => (additive ? new Set([...s, ...names]) : new Set(names)))}
      onDeselect={() => {
        setSelectedNames(new Set())
        setSelectedSurfaces(new Set())
      }}
      buildSolved={buildSolved}
    />
  )
}
```

with:

```tsx
  return (
    <QuadLayout
      scene={SCENE}
      atlas={ATLAS}
      lightmap={null}
      selectedNames={selectedNames}
      onSelectActor={onSelectActor}
      selectedSurfaces={selectedSurfaces}
      onSelectSurface={onSelectSurface}
      onDeselect={() => {
        setSelectedNames(new Set())
        setSelectedSurfaces(new Set())
      }}
      buildSolved={buildSolved}
      frameRequest={null}
      frameActors={() => {}}
    />
  )
}
```

- [ ] **Step 8: Run `QuadLayout.test.tsx`**

Run: `cd web && npx vitest run src/scene/QuadLayout.test.tsx`
Expected: all existing tests still PASS (no test in this file exercises `onSelectMany`/framing directly, so this is a pure prop-shape update).

- [ ] **Step 9: `App.tsx` — update imports**

Replace:

```ts
import { useCallback, useEffect, useMemo, useState } from 'react'

import type { AtlasPayload, LightmapPayload, ScenePayload, ScenePoly, StatusPayload } from './api'
import { fetchLevelState, fetchStatus, postLoad, postRebuild, switchLevel } from './api'
import { useCollapsiblePanel } from './layout/useCollapsiblePanel'
import { Inspector } from './panels/Inspector'
import type { SurfaceSelection } from './panels/Inspector'
import { LevelPicker } from './panels/LevelPicker'
import { subscribeChangesAvailable } from './reload'
import { resolveBuildSolved } from './scene/buildStatus'
import { QuadLayout } from './scene/QuadLayout'
import { clearSelection, parseSurfaceKey, surfaceKey, toggleSelection } from './scene/selectionSet'
import { useTheme } from './theme/useTheme'
import type { ThemePreference } from './theme/useTheme'
```

with:

```ts
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { AtlasPayload, LightmapPayload, ScenePayload, ScenePoly, StatusPayload } from './api'
import { fetchLevelState, fetchStatus, postLoad, postRebuild, switchLevel } from './api'
import { useHasUnseenSelection } from './layout/useSelectionSeen'
import { useSidebar } from './layout/useSidebar'
import type { SurfaceSelection } from './panels/Inspector'
import { LevelPicker } from './panels/LevelPicker'
import { Sidebar } from './panels/Sidebar'
import { buildSidebarPanels } from './panels/sidebarRegistry'
import { subscribeChangesAvailable } from './reload'
import { resolveBuildSolved } from './scene/buildStatus'
import type { FrameRequest } from './scene/frame'
import { unionBBox } from './scene/frame'
import { QuadLayout } from './scene/QuadLayout'
import { clearSelection, parseSurfaceKey, surfaceKey, toggleSelection } from './scene/selectionSet'
import { useTheme } from './theme/useTheme'
import type { ThemePreference } from './theme/useTheme'
```

- [ ] **Step 10: `App.tsx` — replace the old inspector collapse hook with the unified sidebar's own state hooks**

Replace:

```ts
  // Collapsible inspector sidebar (mobile/laptop layout spec, owner-approved 2026-09-18) -- see
  // QuadLayout.tsx's identical org-panel wiring and useCollapsiblePanel's own doc comment. A
  // separate storage key: the two sidebars toggle independently, per the owner's spec.
  const { collapsed: inspectorCollapsed, toggle: toggleInspector } = useCollapsiblePanel('uedcli-inspector-pane-collapsed')

  useEffect(() => {
    fetch('/api/health')
```

with:

```ts
  // The unified sidebar's own collapse/active-tab state (spec's Architecture -> Components) --
  // owned HERE, not inside Sidebar.tsx, because the Selection tab's discoverability dot (below)
  // needs `activeTabId` too (spec's "Selection strip data"). Sidebar.tsx receives all three as
  // plain props, same as any other panel-agnostic piece of its own state.
  const { collapsed: sidebarCollapsed, activeTabId: sidebarActiveTabId, setActiveTab: setSidebarActiveTab } = useSidebar()
  // A stable string that changes iff the actor+surface selection ITSELF changes -- a fresh Set
  // every render must not itself register as a change (useSelectionSeen.ts's own doc comment).
  const selectionIdentity = useMemo(
    () => `${[...selectedNames].sort().join(',')}|${[...selectedSurfaces].sort().join(',')}`,
    [selectedNames, selectedSurfaces],
  )
  // The Selection rail icon's discoverability dot (spec's Decisions section) -- the ONLY thing that
  // computes `hasIndicator` for the `selection` registry entry; Sidebar.tsx never computes it.
  const hasUnseenSelection = useHasUnseenSelection(selectionIdentity, sidebarActiveTabId)

  useEffect(() => {
    fetch('/api/health')
```

- [ ] **Step 11: `App.tsx` — add the lifted frame state and `handleOrgSelect`**

Replace:

```ts
  const onDeselect = useCallback(() => {
    setSelectedNames(clearSelection())
    setSelectedSurfaces(clearSelection())
  }, [])
  const [reloading, setReloading] = useState(false)
```

with:

```ts
  const onDeselect = useCallback(() => {
    setSelectedNames(clearSelection())
    setSelectedSurfaces(clearSelection())
  }, [])
  // Frame-on-select (quad-layout Task 15/23): lifted here from QuadLayout so the org panel -- now
  // hosted by Sidebar, a sibling of QuadLayout rather than its child -- can still trigger the same
  // camera-framing QuadLayout's own `F` key uses (SelectionKeys' onFrame). One shared frameRequest,
  // threaded down into QuadLayout as a controlled prop.
  const frameSeq = useRef(0)
  const [frameRequest, setFrameRequest] = useState<FrameRequest | null>(null)
  const frameActors = useCallback(
    (names: ReadonlySet<string>) => {
      if (!scene) return
      const bbox = unionBBox(scene.actors.filter((a) => names.has(a.name)))
      if (!bbox) return // nothing to frame -- unionBBox's own no-op signal (frame.ts)
      frameSeq.current += 1
      setFrameRequest({ bbox, seq: frameSeq.current })
    },
    [scene],
  )
  // OrgPanel's own batch-select shape: a folder-node click replaces/adds a whole actor set at once
  // AND frames the camera onto it -- mirrors QuadLayout's own former handleOrgSelect exactly.
  const handleOrgSelect = useCallback(
    (names: string[], additive: boolean) => {
      const nameSet = new Set(names)
      onSelectMany(nameSet, additive)
      frameActors(nameSet)
    },
    [onSelectMany, frameActors],
  )
  const [reloading, setReloading] = useState(false)
```

- [ ] **Step 12: `App.tsx` — build the sidebar registry**

Replace:

```ts
  const selectedSurfaceInfos = useMemo(() => {
    const infos: SurfaceSelection[] = []
    for (const key of selectedSurfaces) {
      const parsed = parseSurfaceKey(key)
      const poly = parsed ? polyByKey.get(key) : undefined
      if (parsed && poly) infos.push({ actorName: parsed.actor, polyIndex: parsed.polyIndex, poly })
    }
    return infos
  }, [polyByKey, selectedSurfaces])

  // The real shading-mode gating signal (Task 19) -- derived from the /status polling this toolbar
  // already does, not a second fetch.
  const buildSolved = resolveBuildSolved(status)
```

with:

```ts
  const selectedSurfaceInfos = useMemo(() => {
    const infos: SurfaceSelection[] = []
    for (const key of selectedSurfaces) {
      const parsed = parseSurfaceKey(key)
      const poly = parsed ? polyByKey.get(key) : undefined
      if (parsed && poly) infos.push({ actorName: parsed.actor, polyIndex: parsed.polyIndex, poly })
    }
    return infos
  }, [polyByKey, selectedSurfaces])

  // The unified sidebar's registry (Selection + Org/Search launch panels) -- rebuilt each render
  // from the current selection/actor props, same cost class as selectedActors/polyByKey above.
  // `hasUnseenSelection` (Step 10) is the ONLY thing that sets the `selection` entry's indicator --
  // buildSidebarPanels itself has no notion of "which tab was active when".
  const sidebarPanels = useMemo(
    () =>
      buildSidebarPanels({
        selectedActors,
        selectedSurfaces: selectedSurfaceInfos,
        hasUnseenSelection,
        orgActors: scene?.actors ?? [],
        selectedNames,
        onSelectOrgBatch: handleOrgSelect,
      }),
    [selectedActors, selectedSurfaceInfos, hasUnseenSelection, scene, selectedNames, handleOrgSelect],
  )

  // The real shading-mode gating signal (Task 19) -- derived from the /status polling this toolbar
  // already does, not a second fetch.
  const buildSolved = resolveBuildSolved(status)
```

- [ ] **Step 13: `App.tsx` — pass the lifted frame props into `QuadLayout`**

Replace:

```tsx
          <QuadLayout
            scene={scene}
            atlas={atlas}
            lightmap={lightmap}
            selectedNames={selectedNames}
            onSelectActor={onSelectActor}
            selectedSurfaces={selectedSurfaces}
            onSelectSurface={onSelectSurface}
            onSelectMany={onSelectMany}
            onDeselect={onDeselect}
            buildSolved={buildSolved}
          />
```

with:

```tsx
          <QuadLayout
            scene={scene}
            atlas={atlas}
            lightmap={lightmap}
            selectedNames={selectedNames}
            onSelectActor={onSelectActor}
            selectedSurfaces={selectedSurfaces}
            onSelectSurface={onSelectSurface}
            onDeselect={onDeselect}
            buildSolved={buildSolved}
            frameRequest={frameRequest}
            frameActors={frameActors}
          />
```

- [ ] **Step 14: `App.tsx` — mount `Sidebar` in place of the old inspector wrapper**

Replace:

```tsx
      {/* Collapsible sidebar (mobile/laptop layout spec) -- see QuadLayout.tsx's identical org-panel
          wrapper for the shared shape/rationale. */}
      <div className="inspector-pane-wrapper">
        <button
          type="button"
          className="sidebar-toggle"
          onClick={toggleInspector}
          aria-pressed={inspectorCollapsed}
          aria-label={inspectorCollapsed ? 'Show inspector panel' : 'Hide inspector panel'}
          title={inspectorCollapsed ? 'Show inspector panel' : 'Hide inspector panel'}
        >
          {inspectorCollapsed ? '◀' : '▶'}
        </button>
        {!inspectorCollapsed && (
          <div className="inspector-pane">
            <Inspector selected={selectedActors} selectedSurfaces={selectedSurfaceInfos} />
          </div>
        )}
      </div>
```

with:

```tsx
      {/* The unified sidebar (icon rail + one active panel) -- replaces the old org-panel/
          inspector-pane double sidebar (unified-sidebar spec). Sidebar itself is purely
          presentational; collapse/active-tab state and each panel's `hasIndicator` are all owned
          here (Step 10/12 above) and passed down as plain props. */}
      <Sidebar
        panels={sidebarPanels}
        collapsed={sidebarCollapsed}
        activeTabId={sidebarActiveTabId}
        setActiveTab={setSidebarActiveTab}
        selectedActors={selectedActors}
        selectedSurfaces={selectedSurfaceInfos}
      />
```

- [ ] **Step 15: `App.test.tsx` — repoint the batch-actor-select test at the real Sidebar's Org panel**

`App.tsx` no longer passes `onSelectMany` to `<QuadLayout>` (Step 13 above dropped it) — `OrgPanel`, the only consumer of that App-level state setter, moved out of `QuadLayout` and into `Sidebar` (Task 3/Step 14). The existing `a batch actor select keeps surfaces, additive or replacing` test drives `onSelectMany` directly on the stubbed `QuadLayout`'s captured props; once that prop no longer exists, the old call throws `TypeError: quad.onSelectMany is not a function`. Drive the SAME real behavior (App's own `handleOrgSelect`/`onSelectMany` state setters) through the real `Sidebar` + `OrgPanel` instead — both render for real in this file already (only the WebGL quad is stubbed), the same way `sidebarRegistry.test.ts` (Task 1) drives `OrgPanel`'s own `org-folder-no-folder` control.

In `web/src/App.test.tsx`, replace:

```tsx
import { afterEach, describe, expect, it, vi } from 'vitest'
```

with:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
```

Replace:

```tsx
interface QuadSelectionProps {
  onSelectActor: (name: string, additive: boolean) => void
  onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
  onSelectMany: (names: ReadonlySet<string>, additive: boolean) => void
  onDeselect: () => void
}
```

with:

```tsx
interface QuadSelectionProps {
  onSelectActor: (name: string, additive: boolean) => void
  onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
  onDeselect: () => void
}
```

Replace:

```tsx
describe('App: actor + surface selection coexistence', () => {
  const ACTOR = {
```

with:

```tsx
describe('App: actor + surface selection coexistence', () => {
  // The unified sidebar persists its active-tab/collapse choice to localStorage (useSidebar.ts) --
  // clear it so the batch-select test's tab switching below can't leak into another test's default
  // "Selection tab active" assumption, regardless of file execution order.
  beforeEach(() => {
    localStorage.clear()
  })

  const ACTOR = {
```

Replace:

```tsx
  // A batch actor select never clears surfaces, additive or replacing: UED22's actor batch verbs
  // don't -- `edactBoxSelect` clears `bSelected` in its own inline loop and never touches a surf,
  // and `edactSelectAll`/`edactSelectOfClass`/`mapSelect*` never mention `PF_Selected` at all.
  it('a batch actor select keeps surfaces, additive or replacing', async () => {
    const quad = await renderSelectable()
    act(() => quad.onSelectSurface('Room', 4, false))
    act(() => quad.onSelectMany(new Set(['Room']), true))
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()

    act(() => quad.onSelectMany(new Set(['Room']), false))
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()
    expect(screen.getByTestId('inspector-surface')).toBeTruthy()
  })
```

with:

```tsx
  // A batch actor select never clears surfaces, additive or replacing: UED22's actor batch verbs
  // don't -- `edactBoxSelect` clears `bSelected` in its own inline loop and never touches a surf,
  // and `edactSelectAll`/`edactSelectOfClass`/`mapSelect*` never mention `PF_Selected` at all.
  //
  // `QuadLayout` no longer hosts the org panel (unified-sidebar migration: `OrgPanel` moved into
  // `Sidebar`, a sibling of `QuadLayout` in `App.tsx`), so it no longer receives `onSelectMany` as a
  // prop at all -- the batch-select control this test needs to drive now lives in the real
  // `Sidebar`'s Org panel (rendered for real here, same as `Inspector` already is; only the WebGL
  // quad is stubbed). Switch to the Org tab, click the "no folder" bucket (Room has `folder: null`)
  // the same way `sidebarRegistry.test.ts` already does, then switch back to the Selection tab to
  // read the result off the Inspector.
  it('a batch actor select keeps surfaces, additive or replacing', async () => {
    const quad = await renderSelectable()
    act(() => quad.onSelectSurface('Room', 4, false))

    fireEvent.click(screen.getByTestId('sidebar-rail-org'))
    fireEvent.click(screen.getByTestId('org-folder-no-folder'), { ctrlKey: true }) // additive
    fireEvent.click(screen.getByTestId('sidebar-rail-selection'))
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()

    fireEvent.click(screen.getByTestId('sidebar-rail-org'))
    fireEvent.click(screen.getByTestId('org-folder-no-folder')) // replacing
    fireEvent.click(screen.getByTestId('sidebar-rail-selection'))
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()
    expect(screen.getByTestId('inspector-surface')).toBeTruthy()
  })
```

- [ ] **Step 16: Run `App.test.tsx`**

Run: `cd web && npx vitest run src/App.test.tsx`
Expected: all tests PASS — including the just-rewritten `a batch actor select keeps surfaces, additive or replacing` test (Step 15 above). This file DOES need a change in this task, not zero changes: `QuadLayout` no longer receives `onSelectMany` as a prop (Steps 1-3), so the stubbed mock in `App.test.tsx` no longer has that method either, and the OLD direct `quad.onSelectMany(...)` call would throw `TypeError: quad.onSelectMany is not a function` if left as-is. Every other test in this file is unaffected — jsdom's default `window.innerWidth` (1024) is above the 768px breakpoint, so `Sidebar` renders expanded with the "selection" tab active by default, the same `inspector-empty`/`inspector`/`inspector-surface`/`inspector-sections` testids these tests already assert on.

- [ ] **Step 17: Run the whole frontend suite and the TypeScript build**

Run: `cd web && npm test`
Expected: all tests PASS (no regressions in any file this task didn't touch).

Run: `cd web && npx tsc -b`
Expected: no NEW errors introduced by this task's changes (compare against the pre-existing error list from a clean `git stash` build if any doubt remains about a specific error's origin).

- [ ] **Step 18: Commit**

```bash
git add web/src/scene/QuadLayout.tsx web/src/scene/QuadLayout.test.tsx web/src/App.tsx web/src/App.test.tsx
git commit -m "Mount the unified Sidebar in App.tsx; drop QuadLayout's own org panel"
```

## Task 6: Manual verification

No headless browser is available in this sandbox (`dev/docs/rules/tests.md`'s testing guidance and `GUI-PARITY.md`'s repeated notes both confirm this for the wider project — `chrome-headless-shell`/`chromium-1243` are missing shared libraries with no root to install them). This task is therefore a written checklist for a session with a real browser (or for the human owner) rather than an automated screenshot step, following the same pattern this project's other GUI work uses when live rendering isn't available.

**Files:** none (verification only).

- [ ] **Step 1: Start the dev server**

Run: `cd web && npm run dev`

This starts Vite's dev server (see `web/vite.config.ts`'s proxy config — it expects `uedcli serve` running on port 8765 for the `/api`/`/ws` proxy to resolve; start that separately, e.g. `bin/uedcli serve`, if a live level needs to load).

- [ ] **Step 2: Open the app in a real browser and verify the checklist below**

- The sidebar is on the right, expanded by default, ~280px wide, with a Selection tab active and the Selection panel showing "No selection" (or the current selection, if one already exists from a prior session's `localStorage`).
- The rail shows two icons (▣ Selection, ☰ Org / Search) in a narrow (~36px) permanent strip to the right of the panel.
- Selecting an actor in any viewport pane does NOT switch the active tab away from wherever it currently is (no auto-switch) — but the selection strip above the active panel updates immediately to show the new selection.
- With the Org tab active, selecting an actor shows a small dot on the Selection rail icon; switching to the Selection tab clears the dot.
- Clicking the selection strip switches to the Selection tab.
- Clicking the Org rail icon switches to the Org panel and shows the same folder tree/find box `OrgPanel.tsx` always has; clicking a folder node still selects its actors AND frames the camera onto them (the `F`-key framing behavior, now driven through the lifted `frameActors`).
- Clicking the currently-active tab's rail icon again collapses the sidebar to just the rail; clicking either rail icon while collapsed re-expands it to that tab.
- Collapse the sidebar (click the active rail icon again) with something selected: the persistent selection strip is STILL visible, shrunk to icon token(s) only for whichever kind(s) are selected (no name/class/texture-ref text) — clicking it while collapsed re-expands the sidebar to the Selection tab.
- Selecting one actor, then one surface via Ctrl-click (or Shift-click per `dev/docs/GUI.md`'s "Selection & the Inspector"), shows BOTH an actor line and a surface line in the strip, and both the actor and surface sections in the Selection panel.
- Resizing the browser window below 768px width (with no manual sidebar toggle yet this session) collapses the sidebar to just the rail automatically; above 768px it stays expanded.
- No horizontal scrollbar appears on the page itself at any window width — the sidebar handles its own internal scrolling if content overflows (long actor/folder names, wide inspector tables).

- [ ] **Step 3: Report the result**

If every item above holds, verification is complete — no code change needed. If any item fails, file a board item (`bin/board new inbox`) describing the exact divergence rather than silently patching it outside this plan's scope, per this repo's `CLAUDE.md` "a decision is implemented as given, never altered without an explicit yes" — a failure here means either this plan's own implementation has a bug (fix it, re-run the relevant task's tests) or the spec itself needs revisiting (ask the owner, don't guess).

## Open items

- `dev/docs/GUI.md` describes the org panel as living inside `QuadLayout`. This plan moves it into
  `Sidebar` instead (a sibling of `QuadLayout` in `App.tsx`) — the org panel's own behavior survives
  the refactor unchanged, only its mount point's shape changes. Updating `dev/docs/GUI.md` to match
  needs the owner's explicit yes before anyone edits it (`CLAUDE.md`'s `dev/docs/` approval gate) —
  filed here as a follow-up this plan does not itself carry out.
