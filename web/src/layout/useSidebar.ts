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
