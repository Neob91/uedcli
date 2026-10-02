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
