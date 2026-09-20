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
