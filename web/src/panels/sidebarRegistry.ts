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
